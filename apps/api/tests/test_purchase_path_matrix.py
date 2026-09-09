from dataclasses import replace
from decimal import Decimal
from uuid import UUID

import pytest
from app.auth.errors import ApiProblem
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.procurement.models import PurchaseOrder, PurchaseOrderItem
from app.procurement.repositories import PurchaseOrderRepository
from app.procurement.schemas import PurchaseOrderConfirm, PurchaseOrderDecision
from app.procurement.services import PurchaseOrderCommandService
from app.sales.models import SalesOrder, SalesOrderItem
from app.work.models import Activity
from sqlalchemy import event, select
from test_document_review import reviewer
from test_purchase_changes import change_request, replacement
from test_purchase_receiving import confirmed_purchase, receipt

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)
STATES = [
    "DRAFT",
    "APPROVED",
    "SENT",
    "CONFIRMED",
    "PARTIALLY_RECEIVED",
    "RECEIVED",
    "CLOSED",
    "CANCELLED",
]
ALLOWED = {
    "approve": {"DRAFT", "APPROVED"},
    "send": {"APPROVED", "SENT"},
    "confirm": {"SENT", "CONFIRMED"},
    "receive": {"CONFIRMED", "PARTIALLY_RECEIVED"},
    "close": {"RECEIVED"},
    "cancel": {"DRAFT", "APPROVED", "SENT", "CONFIRMED", "PARTIALLY_RECEIVED"},
    "amend": {"DRAFT", "APPROVED", "SENT", "CONFIRMED", "PARTIALLY_RECEIVED"},
}


def snapshot(f):
    with f.session_factory() as session:
        return {
            model.__tablename__: list(session.execute(select(model.__table__).order_by(model.id)))
            for model in (
                SalesOrder,
                SalesOrderItem,
                PurchaseOrder,
                PurchaseOrderItem,
                Activity,
                AuditLog,
                OutboxEvent,
                IdempotencyKey,
            )
        }


def prepare(f, action, state):
    purchase = confirmed_purchase(f)
    record_id = UUID(purchase["id"])
    with f.session_factory.begin() as session:
        # Stored-state guard isolation, not replacement for the natural receiving lifecycle.
        row = session.get(PurchaseOrder, record_id)
        row.status = state
        for item in session.scalars(
            select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == record_id)
        ):
            if state in {"RECEIVED", "CLOSED"}:
                item.received_quantity = item.quantity
            elif state == "PARTIALLY_RECEIVED":
                item.received_quantity = Decimal("0.5")
        session.flush()
        purchase["version"] = row.version
    body = {"expected_version": purchase["version"]}
    if action == "confirm":
        body |= {
            "supplier_reference": purchase["supplier_reference"],
            "expected_delivery_date": purchase["expected_delivery_date"],
        }
    elif action == "receive":
        body = receipt(purchase, "0.25")
    elif action == "close":
        body["reason"] = "All receipts checked"
    elif action in {"cancel", "amend"}:
        body = change_request(purchase)
        if action == "amend":
            body["replacement"] = replacement(purchase)
    return record_id, body


def call(f, context, action, record_id, body):
    request = body
    if action == "confirm":
        request = PurchaseOrderConfirm.model_validate(body)
    elif action in {"approve", "send"}:
        request = PurchaseOrderDecision.model_validate(body)
    return getattr(PurchaseOrderCommandService(f.session_factory), action)(
        context, record_id, request, idempotency_key="matrix"
    )


def execute_and_check(f, action, state, role):
    record_id, body = prepare(f, action, state)
    subject, context = reviewer(f, role)
    headers = f.headers(subject, f.organization_a) | {"Idempotency-Key": "matrix"}
    path = f"/api/v1/purchase-orders/{record_id}/{action}"
    before = snapshot(f)
    response = f.client.post(path, headers=headers, json=body)
    roles = {MembershipRole.ADMIN, MembershipRole.MANAGER}
    if action in {"send", "confirm", "receive", "close"}:
        roles.add(MembershipRole.OPERATIONS)
    error = None
    if role not in roles:
        error = "PERMISSION_DENIED"
    elif state not in ALLOWED[action]:
        error = "PURCHASE_NOT_FULLY_RECEIVED" if action == "close" else "INVALID_STATE_TRANSITION"
    if error:
        assert response.status_code == (403 if role not in roles else 409), response.text
        assert response.json()["code"] == error
        with pytest.raises(ApiProblem) as denied:
            call(f, context, action, record_id, body)
        assert denied.value.code == error
        assert snapshot(f) == before
        return
    assert response.status_code == 200, response.text
    expected = {
        "approve": "APPROVED",
        "send": "SENT",
        "confirm": "CONFIRMED",
        "receive": "PARTIALLY_RECEIVED",
        "close": "CLOSED",
        "cancel": "CANCELLED",
        "amend": "DRAFT",
    }[action]
    assert response.json()["status"] == expected
    after = snapshot(f)
    no_op = action in {"approve", "send", "confirm"} and state == expected
    evidence_count = 0 if no_op else 1
    if action == "amend":
        evidence_count = 3
    for table in ("activities", "audit_logs", "outbox_events"):
        assert len(after[table]) == len(before[table]) + evidence_count
    assert after["sales_orders"] == before["sales_orders"]
    assert after["sales_order_items"] == before["sales_order_items"]
    assert f.client.post(path, headers=headers, json=body).json() == response.json()
    assert call(f, context, action, record_id, body).id == UUID(response.json()["id"])
    assert snapshot(f) == after


@pytest.mark.parametrize("state", STATES)
@pytest.mark.parametrize("action", list(ALLOWED))
def test_all_purchase_command_states(quotation_fixture, action, state):
    execute_and_check(quotation_fixture, action, state, MembershipRole.MANAGER)


@pytest.mark.parametrize("role", list(MembershipRole))
@pytest.mark.parametrize("action", ["receive", "close", "cancel", "amend"])
def test_remaining_purchase_command_roles(quotation_fixture, action, role):
    state = "RECEIVED" if action == "close" else "CONFIRMED"
    execute_and_check(quotation_fixture, action, state, role)


@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
def test_close_rolls_back_after_each_evidence_insert(quotation_fixture, table):
    f = quotation_fixture
    record_id, body = prepare(f, "close", "RECEIVED")
    _, context = reviewer(f)
    before = snapshot(f)
    inserted = []

    def fail_after_insert(_connection, _cursor, statement, *_args):
        if statement.lstrip().lower().startswith(f"insert into {table} "):
            inserted.append(table)
            raise RuntimeError("injected close evidence failure")

    event.listen(f.engine, "after_cursor_execute", fail_after_insert)
    try:
        with pytest.raises(RuntimeError, match="injected close evidence failure"):
            call(f, context, "close", record_id, body)
    finally:
        event.remove(f.engine, "after_cursor_execute", fail_after_insert)
    assert inserted == [table]
    assert snapshot(f) == before
    assert call(f, context, "close", record_id, body).status == "CLOSED"
    after = snapshot(f)
    call(f, context, "close", record_id, body)
    assert snapshot(f) == after


def test_purchase_repository_paths_scope_foreign_rows(quotation_fixture):
    f = quotation_fixture
    purchase = confirmed_purchase(f)
    record_id = UUID(purchase["id"])
    before = snapshot(f)
    with f.session_factory() as session:
        repo = PurchaseOrderRepository(session)
        assert repo.get(organization_id=f.organization_b, record_id=record_id) is None
        assert (
            repo.get_for_update(organization_id=f.organization_b, purchase_order_id=record_id)
            is None
        )
        assert not repo.list(organization_id=f.organization_b)
        assert repo.count(organization_id=f.organization_b) == 0
        assert not repo.list_recent(
            organization_id=f.organization_b,
            limit=20,
            sales_order_id=UUID(purchase["sales_order_id"]),
        )
        assert not repo.items(organization_id=f.organization_b, purchase_order_id=record_id)
        assert repo.items_for_orders(
            organization_id=f.organization_b, purchase_order_ids=[record_id]
        ) == {record_id: []}
        assert not repo.activities(
            organization_id=f.organization_b, purchase_order_id=record_id, offset=0, limit=20
        )
        with pytest.raises(ApiProblem) as missing:
            repo.list_recent(organization_id=f.organization_b, limit=20, cursor=record_id)
        assert missing.value.status == 404
    subject, context = reviewer(f)
    with f.session_factory.begin() as session:
        session.add(
            OrganizationMembership(
                organization_id=f.organization_b,
                user_id=context.user_id,
                role="MANAGER",
                status="ACTIVE",
            )
        )
    foreign = replace(context, organization_id=f.organization_b)
    headers = f.headers(subject, f.organization_b) | {"Idempotency-Key": "foreign-close"}
    assert f.client.get("/api/v1/me/context", headers=headers).status_code == 200
    path = f"/api/v1/purchase-orders/{record_id}"
    assert (
        f.client.post(
            path + "/close",
            headers=headers,
            json={
                "expected_version": purchase["version"],
                "reason": "Foreign close",
            },
        ).status_code
        == 404
    )
    review_path = path + "/text-review"
    original = f.client.get(review_path, headers=f.headers(subject, f.organization_a))
    assert original.status_code == 200
    review_body = {
        "expected_version": original.json()["version"],
        "content_digest": original.json()["content_digest"],
        "release": True,
        "confirmed": True,
        "reason": "Foreign review",
    }
    assert f.client.get(review_path, headers=headers).status_code == 404
    assert f.client.post(review_path, headers=headers, json=review_body).status_code == 404
    with pytest.raises(ApiProblem) as missing:
        call(
            f,
            foreign,
            "close",
            record_id,
            {"expected_version": purchase["version"], "reason": "Foreign close"},
        )
    assert missing.value.status == 404
    assert snapshot(f) == before
