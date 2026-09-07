from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.identity.enums import MembershipRole
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.sales.models import SalesOrder
from app.sales.order_schemas import SalesOrderConfirm
from app.sales.order_services import SalesOrderCommandService
from app.work.models import Activity, Task
from sqlalchemy import event, func, select
from test_document_review import reviewer
from test_order_procurement_vertical_slice import create_accepted_quotation
from test_quotation_vertical_slice import order_confirmation, post_ok

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration


def setup(f, deposit="0.3"):
    quote, _, _ = create_accepted_quotation(f)
    order = post_ok(
        f,
        "/api/v1/sales-orders",
        "quotation-manager",
        {
            "quotation_id": quote["id"],
            "deposit_rate": deposit,
        },
        201,
    )
    return UUID(order["id"]), SalesOrderConfirm(expected_version=order["version"])


def counts(f):
    with f.session_factory() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (Task, Activity, AuditLog, OutboxEvent, IdempotencyKey)
        )


def invoke(f, order_id, body, key="confirm", subject="quotation-manager"):
    headers = f.headers(subject, f.organization_a)
    if key is not None:
        headers["Idempotency-Key"] = key
    return f.client.post(f"/api/v1/sales-orders/{order_id}/confirm", json=body, headers=headers)


@pytest.mark.parametrize("deposit", ("0", "0.3"))
def test_required_guards_and_atomic_single_confirmation(quotation_fixture, deposit):
    f = quotation_fixture
    order_id, request = setup(f, deposit)
    body = request.model_dump()
    before = counts(f)
    for invalid in (None, {}, {"expected_version": 0}, {**body, "status": "EXECUTING"}):
        assert invoke(f, order_id, invalid).status_code == 422
    for key in (None, "", "  ", "x" * 256):
        assert invoke(f, order_id, body, key).status_code == 422
    assert counts(f) == before
    first = invoke(f, order_id, body)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == ("EXECUTING" if deposit == "0" else "DEPOSIT_PENDING")
    assert first.json()["confirmed_at"] is not None
    after = counts(f)
    assert after == tuple(value + 1 for value in before)
    assert invoke(f, order_id, body).json() == first.json()
    assert counts(f) == after
    changed = invoke(f, order_id, {"expected_version": request.expected_version + 1})
    assert changed.status_code == 409 and changed.json()["code"] == "IDEMPOTENCY_CONFLICT"
    stale = invoke(f, order_id, body, "new-stale")
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    assert counts(f) == after
    # The old already-confirmed no-op still requires fresh opening preconditions.
    assert (
        invoke(f, order_id, order_confirmation(f, order_id).model_dump(), "fresh").json()
        == first.json()
    )
    assert counts(f) == (*after[:-1], after[-1] + 1)


@pytest.mark.parametrize("role", list(MembershipRole))
def test_confirmation_replay_rechecks_http_and_service_authority(quotation_fixture, role):
    f = quotation_fixture
    order_id, request = setup(f)
    assert invoke(f, order_id, request.model_dump()).status_code == 200
    subject, context = reviewer(f, role)
    before = counts(f)
    result = invoke(f, order_id, request.model_dump(), subject=subject)
    service = SalesOrderCommandService(f.session_factory)
    if Permission.ORDER_CONFIRM in context.permissions:
        assert result.status_code == 200
        assert service.confirm(context, order_id, request, key="confirm").id == order_id
    else:
        assert result.status_code == 403
        with pytest.raises(ApiProblem) as denied:
            service.confirm(context, order_id, request, key="confirm")
        assert denied.value.status == 403
    assert counts(f) == before


def test_stale_draft_rejected_and_retry_projection_tracks_current_privacy(quotation_fixture):
    f = quotation_fixture
    order_id, request = setup(f)
    _, context = reviewer(f)
    with f.session_factory.begin() as session:
        session.get(SalesOrder, order_id).version += 1
    before = counts(f)
    stale = invoke(f, order_id, request.model_dump())
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    assert counts(f) == before
    request = order_confirmation(f, order_id)
    service = SalesOrderCommandService(f.session_factory)
    first = service.confirm(context, order_id, request, key="confirm")
    with f.session_factory.begin() as session:
        session.get(SalesOrder, order_id).status = "READY_TO_SHIP"
    after = counts(f)
    reduced = replace(context, permissions=context.permissions - {Permission.PROFIT_READ})
    replay = service.confirm(reduced, order_id, request, key="confirm")
    assert replay.id == order_id and replay.status == "READY_TO_SHIP"
    assert replay.confirmed_at == first.confirmed_at
    assert replay.total == first.total and replay.deposit_amount == first.deposit_amount
    assert replay.total_cost is replay.payment_terms is None
    assert replay.items[0].unit_cost is replay.items[0].description_snapshot is None
    with pytest.raises(ApiProblem) as foreign:
        service.confirm(
            replace(context, organization_id=f.organization_b), order_id, request, key="confirm"
        )
    assert foreign.value.status == 404
    with f.session_factory.begin() as session:
        session.get(SalesOrder, order_id).deleted_at = datetime.now(UTC)
    assert invoke(f, order_id, request.model_dump()).status_code == 404
    assert counts(f) == after


@pytest.mark.parametrize("table", ("tasks", "activities", "audit_logs", "outbox_events"))
def test_confirmation_rolls_back_task_state_evidence_and_key(quotation_fixture, table):
    f = quotation_fixture
    order_id, request = setup(f)
    _, context = reviewer(f)
    before = counts(f)

    def fail(_connection, _cursor, statement, *_args):
        if statement.lower().startswith(f"insert into {table} "):
            raise RuntimeError("injected confirmation failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected confirmation failure"):
            SalesOrderCommandService(f.session_factory).confirm(
                context, order_id, request, key="recover"
            )
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert counts(f) == before
    with f.session_factory() as session:
        row = session.get(SalesOrder, order_id)
        assert (row.status, row.version, row.confirmed_at) == (
            "DRAFT",
            request.expected_version,
            None,
        )
    assert invoke(f, order_id, request.model_dump(), "recover").status_code == 200


@pytest.mark.parametrize("mode", ("same_key", "different_key", "changed_payload"))
def test_concurrent_confirmation_creates_one_task_and_one_receipt(quotation_fixture, mode):
    f = quotation_fixture
    order_id, request = setup(f)
    _, context = reviewer(f)
    before = counts(f)
    barrier = Barrier(2)

    def run(index):
        body = request
        if mode == "changed_payload" and index:
            body = SalesOrderConfirm(expected_version=request.expected_version + 1)
        barrier.wait(timeout=10)
        try:
            result = SalesOrderCommandService(f.session_factory).confirm(
                context, order_id, body, key=f"race-{index}" if mode == "different_key" else "race"
            )
            return str(result.id)
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(run, (0, 1)))
    assert counts(f) == tuple(value + 1 for value in before)
    if mode == "same_key":
        assert result == [str(order_id), str(order_id)]
    else:
        assert result.count(str(order_id)) == 1
        assert (
            "VERSION_CONFLICT" in result
            if mode == "different_key"
            else any(value in {"VERSION_CONFLICT", "IDEMPOTENCY_CONFLICT"} for value in result)
        )
