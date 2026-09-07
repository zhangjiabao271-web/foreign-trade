from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership
from app.platform.models import AuditLog, DocumentSequence, IdempotencyKey, OutboxEvent
from app.procurement.models import PurchaseOrder, PurchaseOrderItem
from app.procurement.services import PurchaseOrderCommandService
from app.work.models import Activity
from sqlalchemy import event, func, select
from test_order_procurement_vertical_slice import create_confirmed_order
from test_quotation_vertical_slice import post_ok

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration


def setup(f):
    order, _, company = create_confirmed_order(f)
    post_ok(f, f"/api/v1/companies/{company}/roles", "quotation-sales", {"role": "SUPPLIER"}, 201)
    return order, {
        "sales_order_id": order["id"],
        "supplier_company_id": company,
        "currency_code": "CNY",
        "exchange_rate": "0.12800000",
        "items": [
            {"sales_order_item_id": item["id"], "quantity": "0.2500", "unit_cost": "4.1234"}
            for item in order["items"]
        ],
    }


def counts(f):
    with f.session_factory() as session:
        return (
            *[
                session.scalar(select(func.count()).select_from(model))
                for model in (
                    PurchaseOrder,
                    PurchaseOrderItem,
                    Activity,
                    AuditLog,
                    OutboxEvent,
                    IdempotencyKey,
                )
            ],
            session.scalar(select(func.sum(DocumentSequence.next_value))),
        )


def context(f, permissions=frozenset({Permission.PROCUREMENT_WRITE, Permission.PROFIT_READ})):
    return RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=permissions,
        request_id=uuid4(),
    )


def request(f, body, key, *, subject="quotation-manager", organization=None):
    headers = f.headers(subject, organization or f.organization_a)
    if key is not None:
        headers["Idempotency-Key"] = key
    return f.client.post("/api/v1/purchase-orders", headers=headers, json=body)


def test_creation_replay_conflict_and_later_state_keep_one_purchase(quotation_fixture):
    f = quotation_fixture
    _, body = setup(f)
    first = request(f, body, "create-once")
    assert first.status_code == 201, first.text
    before = counts(f)
    assert request(f, body, "create-once").json() == first.json()
    assert counts(f) == before
    changed = {**body, "exchange_rate": "0.13000000"}
    conflict = request(f, changed, "create-once")
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert counts(f) == before
    purchase_id = first.json()["id"]
    approved = post_ok(f, f"/api/v1/purchase-orders/{purchase_id}/approve", "quotation-manager")
    before = counts(f)
    replay = request(f, body, "create-once")
    assert replay.status_code == 201
    assert replay.json() == approved
    assert counts(f) == before
    with f.session_factory() as session:
        key = session.scalar(
            select(IdempotencyKey).where(IdempotencyKey.scope == "purchase_order.create")
        )
        assert key.status == "COMPLETED"
        assert key.resource_id == UUID(purchase_id)
        assert key.resource_type == "purchase_order"


def test_key_validation_permission_tenant_and_legacy_new_command_semantics(quotation_fixture):
    f = quotation_fixture
    _, body = setup(f)
    first = request(f, body, "scoped-key")
    assert first.status_code == 201
    with f.session_factory.begin() as session:
        member = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_b
            )
        )
        member.role = MembershipRole.MANAGER
    before = counts(f)
    assert request(f, body, "scoped-key", subject="quotation-sales").status_code == 403
    assert (
        request(
            f, body, "scoped-key", subject="quotation-other", organization=f.organization_b
        ).status_code
        == 404
    )
    for key in ("", " " * 4, "x" * 256):
        assert request(f, body, key).status_code == 422
    assert counts(f) == before
    with pytest.raises(ApiProblem) as denied:
        PurchaseOrderCommandService(f.session_factory).create(
            context(f, frozenset()), body, idempotency_key="scoped-key"
        )
    assert denied.value.status == 403
    assert counts(f) == before
    # V1 callers omitting a key still request new purchases, not retry deduplication.
    one = request(f, body, None)
    two = request(f, body, None)
    assert one.status_code == two.status_code == 201
    assert len({first.json()["id"], one.json()["id"], two.json()["id"]}) == 3


@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
def test_creation_evidence_failure_rolls_back_key_lines_and_number(quotation_fixture, table):
    f = quotation_fixture
    _, body = setup(f)
    before = counts(f)

    def fail(_connection, _cursor, statement, *_args):
        if statement.lower().startswith(f"insert into {table} "):
            raise RuntimeError("injected creation evidence failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected creation evidence failure"):
            PurchaseOrderCommandService(f.session_factory).create(
                context(f), body, idempotency_key="recoverable-create"
            )
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert counts(f) == before
    first = request(f, body, "recoverable-create")
    assert first.status_code == 201
    assert request(f, body, "recoverable-create").json() == first.json()


@pytest.mark.parametrize("mode", ["same", "conflict", "capacity"])
def test_concurrent_creation_serializes_replay_and_preserves_capacity(quotation_fixture, mode):
    f = quotation_fixture
    order, body = setup(f)
    if mode == "capacity":
        body = {
            **body,
            "items": [
                {**line, "quantity": item["quantity"]}
                for line, item in zip(body["items"], order["items"], strict=True)
            ],
        }
    before = counts(f)

    def create(index):
        data = {**body, "exchange_rate": "0.13000000"} if mode == "conflict" and index else body
        key = f"parallel-{index}" if mode == "capacity" else "parallel"
        try:
            purchase = PurchaseOrderCommandService(f.session_factory).create(
                context(f), data, idempotency_key=key
            )
            return str(purchase.id)
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, (0, 1)))
    after = counts(f)
    assert after[0] == before[0] + 1
    assert after[1] == before[1] + len(body["items"])
    assert after[2:6] == tuple(value + 1 for value in before[2:6])
    if mode == "same":
        assert results[0] == results[1]
    elif mode == "conflict":
        assert results.count("IDEMPOTENCY_CONFLICT") == 1
    else:
        assert sum(result == "PURCHASE_QUANTITY_EXCEEDED" for result in results) == 1
