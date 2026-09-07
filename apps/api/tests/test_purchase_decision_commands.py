from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from threading import Barrier, Event
from uuid import UUID

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.identity.enums import MembershipRole
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.procurement.models import PurchaseOrder
from app.procurement.schemas import PurchaseOrderConfirm, PurchaseOrderDecision
from app.procurement.services import PurchaseOrderCommandService
from app.procurement.text_review import PurchaseTextReviewRequest, PurchaseTextReviewService
from app.sales.models import SalesOrder
from app.work.models import Activity
from sqlalchemy import event, func, select
from test_document_review import reviewer
from test_purchase_creation_idempotency import request as create_purchase
from test_purchase_creation_idempotency import setup as creation_inputs
from test_quotation_vertical_slice import post_ok, purchase_decision

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration
ACTIONS = ("approve", "send", "confirm")
TARGET = {"approve": "APPROVED", "send": "SENT", "confirm": "CONFIRMED"}


def setup(f, action):
    _, data = creation_inputs(f)
    response = create_purchase(f, data, "purchase")
    assert response.status_code == 201
    purchase = response.json()
    for preceding in ACTIONS[: ACTIONS.index(action)]:
        purchase = post_ok(
            f, f"/api/v1/purchase-orders/{purchase['id']}/{preceding}", "quotation-manager"
        )
    body = purchase_decision(f, purchase["id"])
    if action == "confirm":
        body = {
            **body,
            "supplier_reference": "SUPPLIER-ACK",
            "expected_delivery_date": "2026-11-05",
        }
    return UUID(purchase["id"]), body, purchase


def counts(f):
    with f.session_factory() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (Activity, AuditLog, OutboxEvent, IdempotencyKey)
        )


def invoke(f, action, record_id, body, key="decision", subject="quotation-manager"):
    headers = f.headers(subject, f.organization_a)
    if key is not None:
        headers["Idempotency-Key"] = key
    return f.client.post(
        f"/api/v1/purchase-orders/{record_id}/{action}", json=body, headers=headers
    )


def call(f, context, action, record_id, body, key="decision"):
    service = PurchaseOrderCommandService(f.session_factory)
    if action == "confirm":
        return service.confirm(
            context, record_id, PurchaseOrderConfirm.model_validate(body), idempotency_key=key
        )
    return getattr(service, action)(
        context, record_id, PurchaseOrderDecision.model_validate(body), idempotency_key=key
    )


@pytest.mark.parametrize("action", ACTIONS)
def test_required_guards_exact_retry_and_guarded_noop(quotation_fixture, action):
    f = quotation_fixture
    record_id, body, _ = setup(f, action)
    before = counts(f)
    for invalid in (None, {}, {**body, "expected_version": 0}, {**body, "status": TARGET[action]}):
        assert invoke(f, action, record_id, invalid).status_code == 422
    for key in (None, "", "  ", "x" * 256):
        assert invoke(f, action, record_id, body, key).status_code == 422
    assert counts(f) == before
    first = invoke(f, action, record_id, body)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == TARGET[action]
    after = counts(f)
    assert after == tuple(value + 1 for value in before)
    assert invoke(f, action, record_id, body).json() == first.json()
    conflict = invoke(
        f, action, record_id, {**body, "expected_version": body["expected_version"] + 1}
    )
    assert conflict.status_code == 409 and conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    stale = invoke(f, action, record_id, body, "new-stale")
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    assert counts(f) == after
    current = {**body, **purchase_decision(f, record_id)}
    assert invoke(f, action, record_id, current, "current-noop").json() == first.json()
    assert counts(f) == (*after[:-1], after[-1] + 1)
    if action == "confirm":
        before = counts(f)
        for change in ({"supplier_reference": "CHANGED"}, {"expected_delivery_date": "2026-11-06"}):
            conflict = invoke(f, action, record_id, {**current, **change}, "new-conflict")
            assert (
                conflict.status_code == 409
                and conflict.json()["code"] == "SUPPLIER_CONFIRMATION_CONFLICT"
            )
        assert counts(f) == before


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("role", list(MembershipRole))
def test_each_role_is_rechecked_for_http_and_service_replay(quotation_fixture, action, role):
    f = quotation_fixture
    record_id, body, _ = setup(f, action)
    assert invoke(f, action, record_id, body).status_code == 200
    subject, context = reviewer(f, role)
    before = counts(f)
    response = invoke(f, action, record_id, body, subject=subject)
    required = (
        {Permission.PROCUREMENT_APPROVE, Permission.PROFIT_READ}
        if action == "approve"
        else {Permission.PROCUREMENT_WRITE}
    )
    if required <= context.permissions:
        assert response.status_code == 200
        replay = call(f, context, action, record_id, body)
        assert replay.id == record_id
        assert (replay.total is not None) == (Permission.PROFIT_READ in context.permissions)
    else:
        assert response.status_code == 403
        with pytest.raises(ApiProblem) as denied:
            call(f, context, action, record_id, body)
        assert denied.value.status == 403
    assert counts(f) == before


@pytest.mark.parametrize("action", ACTIONS)
def test_later_progress_live_privacy_foreign_and_deleted_replay(quotation_fixture, action):
    f = quotation_fixture
    record_id, body, purchase = setup(f, action)
    first = invoke(f, action, record_id, body).json()
    _, context = reviewer(f)
    with f.session_factory.begin() as session:
        session.get(PurchaseOrder, record_id).status = "CLOSED"
        session.get(SalesOrder, UUID(purchase["sales_order_id"])).status = "COMPLETED"
    before = counts(f)
    replay = call(f, context, action, record_id, body)
    assert replay.status == "CLOSED"
    field = {"approve": "approved_at", "send": "sent_at", "confirm": "confirmed_at"}[action]
    assert replay.model_dump(mode="json")[field] == first[field]
    if action != "approve":
        reduced = replace(context, permissions=context.permissions - {Permission.PROFIT_READ})
        replay = call(f, reduced, action, record_id, body)
        assert (
            replay.total
            is replay.items[0].unit_cost
            is replay.items[0].description_snapshot
            is None
        )
    with pytest.raises(ApiProblem) as foreign:
        call(f, replace(context, organization_id=f.organization_b), action, record_id, body)
    assert foreign.value.status == 404
    with f.session_factory.begin() as session:
        session.get(PurchaseOrder, record_id).deleted_at = datetime.now(UTC)
    assert invoke(f, action, record_id, body).status_code == 404
    assert counts(f) == before


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("status", ("COMPLETED", "CANCELLED"))
def test_finalized_parent_blocks_new_decision_without_receipt(quotation_fixture, action, status):
    f = quotation_fixture
    record_id, body, purchase = setup(f, action)
    with f.session_factory.begin() as session:
        session.get(SalesOrder, UUID(purchase["sales_order_id"])).status = status
    before = counts(f)
    response = invoke(f, action, record_id, body)
    assert response.status_code == 409 and response.json()["code"] == "ORDER_FINALIZED"
    assert counts(f) == before


@pytest.mark.parametrize("action", ACTIONS)
def test_decision_waits_for_parent_finalization_transaction(quotation_fixture, action):
    f = quotation_fixture
    record_id, body, purchase = setup(f, action)
    _, context = reviewer(f)
    before = counts(f)
    waiting = Event()

    def observe(_connection, _cursor, statement, *_args):
        if "from sales_orders" in statement.lower() and "for update" in statement.lower():
            waiting.set()

    def run():
        try:
            call(f, context, action, record_id, body)
        except ApiProblem as error:
            return error.code
        return "unexpected success"

    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            with f.session_factory.begin() as session:
                parent = session.scalar(
                    select(SalesOrder)
                    .where(
                        SalesOrder.organization_id == f.organization_a,
                        SalesOrder.id == UUID(purchase["sales_order_id"]),
                    )
                    .with_for_update()
                )
                event.listen(f.engine, "before_cursor_execute", observe)
                future = pool.submit(run)
                assert waiting.wait(timeout=10)
                assert not future.done()
                parent.status = "COMPLETED"
            assert future.result(timeout=10) == "ORDER_FINALIZED"
        finally:
            event.remove(f.engine, "before_cursor_execute", observe)
    assert counts(f) == before


@pytest.mark.parametrize("action", ("send", "confirm"))
def test_replay_reflects_current_text_review_without_releasing_prices(quotation_fixture, action):
    f = quotation_fixture
    record_id, body, _ = setup(f, action)
    assert invoke(f, action, record_id, body).status_code == 200
    _, context = reviewer(f)
    reduced = replace(context, permissions=context.permissions - {Permission.PROFIT_READ})
    service = PurchaseTextReviewService(f.session_factory)
    for release in (True, False):
        snapshot = service.inspect(context, record_id)
        service.decide(
            context,
            record_id,
            PurchaseTextReviewRequest(
                expected_version=snapshot.version,
                content_digest=snapshot.content_digest,
                release=release,
                confirmed=True,
                reason="Independently review original purchase text",
            ),
            key=f"review-{release}",
        )
        before = counts(f)
        replay = call(f, reduced, action, record_id, body)
        assert replay.content_visible is release
        assert (replay.items[0].description_snapshot is not None) is release
        assert replay.total is replay.items[0].unit_cost is None
        assert counts(f) == before


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("table", ("activities", "audit_logs", "outbox_events"))
def test_decision_evidence_failure_rolls_back_all_facts(quotation_fixture, action, table):
    f = quotation_fixture
    record_id, body, purchase = setup(f, action)
    _, context = reviewer(f)
    before = counts(f)

    def fail(_connection, _cursor, statement, *_args):
        if statement.lower().startswith(f"insert into {table} "):
            raise RuntimeError("injected purchase decision failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected purchase decision failure"):
            call(f, context, action, record_id, body)
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert counts(f) == before
    stored = f.client.get(
        f"/api/v1/purchase-orders/{record_id}",
        headers=f.headers("quotation-manager", f.organization_a),
    ).json()
    assert stored == purchase
    assert invoke(f, action, record_id, body).status_code == 200


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("mode", ("same", "different", "changed"))
def test_concurrent_decisions_preserve_one_effect(quotation_fixture, action, mode):
    f = quotation_fixture
    record_id, body, _ = setup(f, action)
    _, context = reviewer(f)
    before = counts(f)
    barrier = Barrier(2)

    def run(index):
        request = (
            {**body, "expected_version": body["expected_version"] + 1}
            if mode == "changed" and index
            else body
        )
        barrier.wait(timeout=10)
        try:
            return str(
                call(
                    f,
                    context,
                    action,
                    record_id,
                    request,
                    f"race-{index}" if mode == "different" else "race",
                ).id
            )
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, (0, 1)))
    assert counts(f) == tuple(value + 1 for value in before)
    if mode == "same":
        assert results == [str(record_id), str(record_id)]
    else:
        assert results.count(str(record_id)) == 1
        assert any(value in {"VERSION_CONFLICT", "IDEMPOTENCY_CONFLICT"} for value in results)
