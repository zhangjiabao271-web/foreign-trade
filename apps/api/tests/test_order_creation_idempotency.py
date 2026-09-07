from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.identity.enums import MembershipRole
from app.platform.models import AuditLog, DocumentSequence, IdempotencyKey, OutboxEvent
from app.sales.models import SalesOrder, SalesOrderItem
from app.sales.order_schemas import SalesOrderConfirm
from app.sales.order_services import SalesOrderCommandService
from app.sales.text_review import CommercialTextReviewRequest, CommercialTextReviewService
from app.work.models import Activity
from sqlalchemy import event, func, select
from test_document_review import reviewer
from test_order_procurement_vertical_slice import create_accepted_quotation

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration


def setup(f):
    quote, _, _ = create_accepted_quotation(f)
    return {"quotation_id": quote["id"], "deposit_rate": "0.3", "deposit_due_date": "2026-10-01"}


def invoke(f, body, key="create", subject="quotation-sales", organization=None):
    headers = f.headers(subject, organization or f.organization_a)
    if key is not None:
        headers["Idempotency-Key"] = key
    return f.client.post("/api/v1/sales-orders", json=body, headers=headers)


def counts(f):
    with f.session_factory() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (
                SalesOrder,
                SalesOrderItem,
                Activity,
                AuditLog,
                OutboxEvent,
                IdempotencyKey,
            )
        )


def test_creation_replay_keeps_original_facts_and_rejects_different_deposit(quotation_fixture):
    f = quotation_fixture
    body = setup(f)
    original = deepcopy(body)
    _, context = reviewer(f, MembershipRole.MANAGER)
    service = SalesOrderCommandService(f.session_factory)
    first = service.create(context, body, key="create")
    assert body == original
    service.confirm(context, first.id, SalesOrderConfirm(expected_version=first.version), key="c")
    before = counts(f)
    replay = invoke(f, {**body, "deposit_rate": "0.3000"})
    assert replay.status_code == 201
    result = replay.json()
    assert result["id"] == str(first.id) and result["status"] == "DEPOSIT_PENDING"
    assert result["total"] == str(first.total) and result["deposit_amount"] == str(
        first.deposit_amount
    )
    assert result["total_cost"] is result["payment_terms"] is None
    assert result["items"][0]["unit_cost"] is result["items"][0]["description_snapshot"] is None
    assert counts(f) == before
    for change in ({"deposit_rate": "0.4"}, {"deposit_due_date": "2026-10-02"}):
        for key in ("create", "fresh", None):
            conflict = invoke(f, {**body, **change}, key)
            assert conflict.status_code == 409
            assert conflict.json()["code"] == (
                "IDEMPOTENCY_CONFLICT" if key == "create" else "ORDER_CREATION_CONFLICT"
            )
    assert counts(f) == before
    for key in ("fresh-matching", None):
        assert invoke(f, body, key).json()["id"] == str(first.id)
    assert counts(f) == (*before[:-1], before[-1] + 2)
    with f.session_factory() as session:
        stored = session.get(SalesOrder, first.id)
        assert stored.deposit_rate == first.deposit_rate
        assert stored.deposit_due_date == first.deposit_due_date
        assert stored.total_cost == first.total_cost and stored.payment_terms == first.payment_terms


@pytest.mark.parametrize("role", list(MembershipRole))
def test_creation_replay_rechecks_http_and_service_authority(quotation_fixture, role):
    f = quotation_fixture
    body = setup(f)
    first = invoke(f, body)
    assert first.status_code == 201
    subject, context = reviewer(f, role)
    before = counts(f)
    response = invoke(f, body, subject=subject)
    service = SalesOrderCommandService(f.session_factory)
    if Permission.ORDER_WRITE in context.permissions:
        assert response.status_code == 201
        replay = service.create(context, body, key="create")
        assert str(replay.id) == first.json()["id"]
        assert (replay.total_cost is not None) == (Permission.PROFIT_READ in context.permissions)
    else:
        assert response.status_code == 403
        with pytest.raises(ApiProblem) as denied:
            service.create(context, body, key="create")
        assert denied.value.status == 403
    assert counts(f) == before


def test_invalid_keys_foreign_and_deleted_replay_leave_no_receipt(quotation_fixture):
    f = quotation_fixture
    body = setup(f)
    first = invoke(f, body).json()
    before = counts(f)
    for key in ("", "  ", "x" * 256):
        assert invoke(f, body, key).status_code == 422
    assert (
        invoke(f, body, organization=f.organization_b, subject="quotation-other").status_code == 404
    )
    _, context = reviewer(f)
    with pytest.raises(ApiProblem) as foreign:
        SalesOrderCommandService(f.session_factory).create(
            replace(context, organization_id=f.organization_b), body, key="create"
        )
    assert foreign.value.status == 404
    with f.session_factory.begin() as session:
        session.get(SalesOrder, UUID(first["id"])).deleted_at = datetime.now(UTC)
    assert invoke(f, body).status_code == 404
    assert counts(f) == before


def test_replay_uses_current_independent_order_text_review(quotation_fixture):
    f = quotation_fixture
    body = setup(f)
    created = invoke(f, body).json()
    record_id = UUID(created["id"])
    _, context = reviewer(f)
    service = CommercialTextReviewService(f.session_factory)
    for release in (True, False):
        snapshot = service.inspect(context, "sales_order", record_id)
        service.decide(
            context,
            "sales_order",
            record_id,
            CommercialTextReviewRequest(
                expected_version=snapshot.version,
                content_digest=snapshot.content_digest,
                release=release,
                confirmed=True,
                reason="Review order source independently",
            ),
            key=f"review-{release}",
        )
        before = counts(f)
        replay = invoke(f, body)
        assert replay.status_code == 201
        result = replay.json()
        assert result["content_visible"] is release
        assert (result["items"][0]["description_snapshot"] is not None) is release
        assert result["total_cost"] is result["items"][0]["unit_cost"] is None
        assert counts(f) == before


@pytest.mark.parametrize(
    "table", ("sales_order_items", "activities", "audit_logs", "outbox_events")
)
def test_creation_failure_rolls_back_snapshot_number_and_receipt(quotation_fixture, table):
    f = quotation_fixture
    body = setup(f)
    _, context = reviewer(f)
    before = counts(f)
    with f.session_factory() as session:
        sequences_before = session.scalar(select(func.count()).select_from(DocumentSequence))

    def fail(_connection, _cursor, statement, *_args):
        if statement.lower().startswith(f"insert into {table} "):
            raise RuntimeError("injected order creation failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected order creation failure"):
            SalesOrderCommandService(f.session_factory).create(context, body, key="recover")
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert counts(f) == before
    with f.session_factory() as session:
        assert (
            session.scalar(select(func.count()).select_from(DocumentSequence)) == sequences_before
        )
    result = invoke(f, body, "recover")
    assert result.status_code == 201
    assert result.json()["order_number"].endswith("000001")


@pytest.mark.parametrize("mode", ("same_key", "different_key", "changed_same", "changed_new"))
def test_concurrent_creation_preserves_one_order_and_explicit_conflicts(quotation_fixture, mode):
    f = quotation_fixture
    body = setup(f)
    _, context = reviewer(f)
    before = counts(f)
    barrier = Barrier(2)

    def run(index):
        data = {**body, "deposit_rate": "0.4"} if mode.startswith("changed") and index else body
        key = f"race-{index}" if mode in {"different_key", "changed_new"} else "race"
        barrier.wait(timeout=10)
        try:
            return str(
                SalesOrderCommandService(f.session_factory).create(context, data, key=key).id
            )
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, (0, 1)))
    after = counts(f)
    assert after[0] == before[0] + 1
    assert after[2:5] == tuple(value + 1 for value in before[2:5])
    assert after[-1] == before[-1] + (2 if mode == "different_key" else 1)
    if mode.startswith("changed"):
        assert (
            results.count(
                "IDEMPOTENCY_CONFLICT" if mode == "changed_same" else "ORDER_CREATION_CONFLICT"
            )
            == 1
        )
    else:
        assert results[0] == results[1]
