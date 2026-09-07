from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.identity.enums import MembershipRole
from app.platform.models import AuditLog, OutboxEvent
from app.procurement.models import PurchaseOrder, PurchaseOrderItem
from app.procurement.repositories import PurchaseOrderRepository
from app.procurement.services import PurchaseOrderCommandService, PurchaseOrderQueryService
from app.procurement.text_review import PurchaseTextReviewRequest, PurchaseTextReviewService
from app.work.models import Activity
from app.work.review import WorkReviewRequest, WorkReviewService
from legacy_migration import verify_legacy_guard, verify_legacy_upgrade
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from test_commercial_text_review import request
from test_document_review import counts, reviewer
from test_purchase_receiving import confirmed_purchase, receipt

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)
SECRET = "private procurement prose"


def seed(f):
    purchase = confirmed_purchase(f)
    record_id = UUID(purchase["id"])
    with f.session_factory.begin() as session:
        row = session.get(PurchaseOrder, record_id)
        row.supplier_reference = "SUPPLIER-CONFIRM-ID"
        row.cancellation_reason = SECRET
        row.cancellation_reference = SECRET
        for item in session.scalars(
            select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == record_id)
        ):
            item.description_snapshot = SECRET
    return record_id


def read(f, context, record_id):
    with f.session_factory() as session:
        service = PurchaseOrderQueryService(PurchaseOrderRepository(session))
        result = service.get(context, record_id)
        assert result in service.list(context, limit=50)
        assert not session.dirty
        return result


@pytest.mark.parametrize("role", list(MembershipRole))
def test_purchase_source_roles_http_service_and_replay(quotation_fixture, role):
    f = quotation_fixture
    record_id = seed(f)
    subject, context = reviewer(f, role)
    service = PurchaseTextReviewService(f.session_factory)
    endpoint = f"/api/v1/purchase-orders/{record_id}/text-review"
    headers = f.headers(subject, f.organization_a)
    privileged = Permission.PROFIT_READ in context.permissions
    result = read(f, context, record_id)
    assert result.content_visible is privileged
    assert (SECRET in result.model_dump_json()) is privileged
    assert result.supplier_reference == "SUPPLIER-CONFIRM-ID"
    if not privileged:
        assert f.client.get(endpoint, headers=headers).status_code == 403
        with pytest.raises(ApiProblem) as denied:
            service.inspect(context, record_id)
        assert denied.value.status == 403
        return
    original = service.inspect(context, record_id)
    before = counts(f)
    body = request(PurchaseTextReviewRequest, original)
    opened = f.client.post(
        endpoint, headers=headers | {"Idempotency-Key": "open"}, json=body.model_dump()
    )
    assert opened.status_code == 200, opened.text
    low = replace(context, permissions=context.permissions - {Permission.PROFIT_READ})
    released = read(f, low, record_id)
    assert SECRET in released.model_dump_json() and released.total is None
    assert all(item.unit_cost is None for item in released.items)
    service.decide(
        context,
        record_id,
        request(PurchaseTextReviewRequest, service.inspect(context, record_id), False),
        key="restrict",
    )
    assert not service.decide(context, record_id, body, key="open").released
    assert SECRET not in read(f, low, record_id).model_dump_json()
    assert counts(f) == [value + 2 for value in before]
    for bad, status in (
        (replace(context, organization_id=f.organization_b), 404),
        (replace(context, permissions=frozenset({Permission.PROFIT_READ})), 403),
    ):
        with pytest.raises(ApiProblem) as rejected:
            service.inspect(bad, record_id)
        assert rejected.value.status == status


@pytest.mark.parametrize("stage", [Activity, AuditLog, OutboxEvent])
def test_purchase_review_atomic_evidence(quotation_fixture, stage):
    f = quotation_fixture
    record_id = seed(f)
    _, context = reviewer(f)
    service = PurchaseTextReviewService(f.session_factory)
    original = service.inspect(context, record_id)
    before = counts(f)

    def fail(*args):
        raise RuntimeError("injected failure")

    event.listen(stage, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            service.decide(
                context, record_id, request(PurchaseTextReviewRequest, original), key="failed"
            )
    finally:
        event.remove(stage, "before_insert", fail)
    assert service.inspect(context, record_id) == original
    assert counts(f) == before


def test_purchase_review_race_stale_line_restoration_and_deleted_replay(quotation_fixture):
    f = quotation_fixture
    record_id = seed(f)
    _, context = reviewer(f)
    service = PurchaseTextReviewService(f.session_factory)
    original = service.inspect(context, record_id)
    barrier = Barrier(2)

    def race(release):
        barrier.wait(timeout=10)
        try:
            return service.decide(
                context,
                record_id,
                request(PurchaseTextReviewRequest, original, release),
                key=f"race-{release}",
            )
        except ApiProblem as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(race, (True, False)))
    errors = [row for row in results if isinstance(row, ApiProblem)]
    assert len(errors) == 1 and errors[0].code == "VERSION_CONFLICT"
    body = request(PurchaseTextReviewRequest, service.inspect(context, record_id))
    service.decide(context, record_id, body, key="open")
    for value in ("changed", SECRET):
        with f.session_factory.begin() as session:
            item = session.scalars(
                select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == record_id)
            ).first()
            item.description_snapshot = value
    assert not service.inspect(context, record_id).released
    with pytest.raises(ApiProblem) as stale:
        service.decide(context, record_id, body, key="stale")
    assert stale.value.code == "VERSION_CONFLICT"
    with f.session_factory.begin() as session:
        session.get(PurchaseOrder, record_id).deleted_at = datetime.now(UTC)
    with pytest.raises(ApiProblem) as deleted:
        service.decide(context, record_id, body, key="open")
    assert deleted.value.status == 404


def test_receiving_invalidates_source_release_and_history_is_independent(quotation_fixture):
    f = quotation_fixture
    record_id = seed(f)
    _, context = reviewer(f)
    low = replace(context, permissions=context.permissions - {Permission.PROFIT_READ})
    service = PurchaseTextReviewService(f.session_factory)
    service.decide(
        context,
        record_id,
        request(PurchaseTextReviewRequest, service.inspect(context, record_id)),
        key="source",
    )
    purchase = read(f, context, record_id).model_dump(mode="json")
    body = receipt(purchase)
    body["reference"] = SECRET
    commands = PurchaseOrderCommandService(f.session_factory)
    received = commands.receive(low, record_id, body, idempotency_key="receipt")
    assert not received.content_visible and received.total is None
    assert commands.receive(low, record_id, body, idempotency_key="receipt") == received
    with f.session_factory() as session:
        activity = session.scalars(
            select(Activity).where(
                Activity.subject_id == record_id,
                Activity.activity_type == "purchase_order.receipt_recorded",
            )
        ).one()
        activity_id = activity.id
        assert SECRET in activity.summary
    work = WorkReviewService(f.session_factory)
    original = work.inspect_activity(context, "purchase_order", record_id, activity_id)
    work.decide_activity(
        context,
        "purchase_order",
        record_id,
        activity_id,
        request(WorkReviewRequest, original),
        key="history",
    )
    with f.session_factory() as session:
        rows = PurchaseOrderQueryService(PurchaseOrderRepository(session)).activities(
            low, record_id, offset=0, limit=50
        )
        row = next(row for row in rows if row.id == activity_id)
        assert row.content_visible and SECRET in row.summary
    assert not read(f, low, record_id).content_visible
    with pytest.raises(ApiProblem) as foreign:
        work.inspect_activity(
            replace(context, organization_id=f.organization_b),
            "purchase_order",
            record_id,
            activity_id,
        )
    assert foreign.value.status == 404


def test_legacy_purchase_text_preserved_and_downgrade_refused(quotation_fixture):
    f = quotation_fixture
    record_id = seed(f)

    def check(engine):
        with Session(engine) as session:
            row = session.get(PurchaseOrder, record_id)
            assert row.released_digest is row.reviewed_by is row.reviewed_at is None
            assert row.cancellation_reason == SECRET

    verify_legacy_upgrade(f.engine, "20260906_0029", check=check)
    verify_legacy_guard(f.engine, "20260906_0030", "20260906_0029", "Purchase evidence exists")


@pytest.mark.parametrize("role", list(MembershipRole))
def test_purchase_history_review_requires_original_right_and_exact_subject(quotation_fixture, role):
    f = quotation_fixture
    record_id = seed(f)
    subject, context = reviewer(f, role)
    with f.session_factory.begin() as session:
        row = Activity(
            organization_id=f.organization_a,
            subject_type="purchase_order",
            subject_id=record_id,
            activity_type="fixture.note",
            correlation_id=context.request_id,
            summary=SECRET,
            details={"note": SECRET, "command_result": {"total": "350", "reference": SECRET}},
        )
        session.add(row)
        session.flush()
        activity_id = row.id
    endpoint = f"/api/v1/work/purchase_order/{record_id}/activities/{activity_id}/review"
    headers = f.headers(subject, f.organization_a)
    service = WorkReviewService(f.session_factory)
    if Permission.PROFIT_READ not in context.permissions:
        assert f.client.get(endpoint, headers=headers).status_code == 403
        with pytest.raises(ApiProblem) as denied:
            service.inspect_activity(context, "purchase_order", record_id, activity_id)
        assert denied.value.status == 403
        return
    original = service.inspect_activity(context, "purchase_order", record_id, activity_id)
    response = f.client.post(
        endpoint,
        headers=headers | {"Idempotency-Key": "history"},
        json=request(WorkReviewRequest, original).model_dump(),
    )
    assert response.status_code == 200 and response.json()["released"]
    low = replace(context, permissions=context.permissions - {Permission.PROFIT_READ})
    with f.session_factory() as session:
        rows = PurchaseOrderQueryService(PurchaseOrderRepository(session)).activities(
            low, record_id, offset=0, limit=50
        )
        released = next(row for row in rows if row.id == activity_id)
        assert released.details["command_result"] == {"reference": SECRET}
        assert session.get(Activity, activity_id).details["command_result"]["total"] == "350"
    with pytest.raises(ApiProblem) as denied:
        service.inspect_activity(
            replace(context, permissions=frozenset({Permission.PROFIT_READ})),
            "purchase_order",
            record_id,
            activity_id,
        )
    assert denied.value.status == 403
    with f.session_factory.begin() as session:
        session.get(PurchaseOrder, record_id).deleted_at = datetime.now(UTC)
    with pytest.raises(ApiProblem) as missing:
        service.decide_activity(
            context,
            "purchase_order",
            record_id,
            activity_id,
            request(WorkReviewRequest, original),
            key="history",
        )
    assert missing.value.status == 404


def test_replacement_starts_confidential_and_keeps_source_facts(quotation_fixture):
    from test_purchase_changes import change_request, replacement

    f = quotation_fixture
    record_id = seed(f)
    _, context = reviewer(f)
    low = replace(context, permissions=context.permissions - {Permission.PROFIT_READ})
    service = PurchaseTextReviewService(f.session_factory)
    service.decide(
        context,
        record_id,
        request(PurchaseTextReviewRequest, service.inspect(context, record_id)),
        key="source",
    )
    purchase = read(f, context, record_id).model_dump(mode="json")
    body = {**change_request(purchase), "replacement": replacement(purchase)}
    commands = PurchaseOrderCommandService(f.session_factory)
    changed = commands.amend(context, record_id, body, idempotency_key="amend")
    assert changed.replaces_purchase_order_id == record_id
    assert not read(f, low, changed.id).content_visible
    assert not read(f, low, record_id).content_visible
    assert commands.amend(context, record_id, body, idempotency_key="amend") == changed
    with f.session_factory() as session:
        old = session.scalars(
            select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == record_id)
        ).all()
        assert all(item.description_snapshot == SECRET for item in old)
        assert str(session.get(PurchaseOrder, record_id).total) == purchase["total"]
