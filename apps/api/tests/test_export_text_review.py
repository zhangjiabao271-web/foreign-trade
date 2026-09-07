from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from threading import Barrier

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission, permissions_for_role
from app.export.models import CustomsDeclaration, TaxRefundCase
from app.export.services import ExportQueryService
from app.export.text_review import ExportTextReviewRequest, ExportTextReviewService
from app.identity.enums import MembershipRole
from app.platform.models import AuditLog, OutboxEvent
from app.work.models import Activity
from legacy_migration import verify_legacy_guard, verify_legacy_upgrade
from sqlalchemy import event
from test_activity_review import seed as seed_activity
from test_document_review import counts, reviewer

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)
MODELS = {"customs": CustomsDeclaration, "refund": TaxRefundCase}
SUBJECTS = {"customs": "customs_declaration", "refund": "tax_refund_case"}
RESOURCES = {"customs": "customs-declarations", "refund": "tax-refund-cases"}


def seed(f, kind):
    record_id, _ = seed_activity(f, SUBJECTS[kind])
    with f.session_factory.begin() as session:
        row = session.get(MODELS[kind], record_id)
        row.notes = "Internal cost 350"
        row.rejection_reason = "Private commercial explanation 350"
        row.external_reference = "RECEIPT-2026-001"
    return record_id


def decision(snapshot, release=True):
    return ExportTextReviewRequest(
        expected_version=snapshot.version,
        content_digest=snapshot.content_digest,
        release=release,
        reason="Reviewed all original case text",
        confirmed=True,
    )


def projection(f, context, kind, record_id):
    with f.session_factory() as session:
        query = ExportQueryService(session)
        result = getattr(query, kind)(context, record_id)[0]
        page = getattr(query, kind + "_page")(context, cursor=None, limit=50)[0]
        assert next(row for row in page if row.id == record_id).notes == result.notes
        assert not session.dirty
        return result


@pytest.mark.parametrize("kind", list(MODELS))
@pytest.mark.parametrize("role", list(MembershipRole))
def test_export_source_role_service_http_and_review_replay(quotation_fixture, kind, role):
    f = quotation_fixture
    record_id = seed(f, kind)
    subject, context = reviewer(f, role)
    headers = f.headers(subject, f.organization_a)
    privileged = Permission.PROFIT_READ in context.permissions
    readable = Permission.EXPORT_READ in context.permissions
    response = f.client.get(f"/api/v1/{RESOURCES[kind]}/{record_id}", headers=headers)
    if not readable:
        assert response.status_code == 403
        return
    assert response.status_code == 200, response.text
    result = projection(f, context, kind, record_id)
    assert result.notes == response.json()["notes"] == ("Internal cost 350" if privileged else None)
    assert result.external_reference == "RECEIPT-2026-001"
    assert result.content_visible is privileged
    service = ExportTextReviewService(f.session_factory)
    path = f"/api/v1/export-text/{kind}/{record_id}/review"
    before = counts(f)
    if not privileged:
        request = ExportTextReviewRequest(
            expected_version=1,
            content_digest="a" * 64,
            release=True,
            confirmed=True,
            reason="Unauthorized",
        )
        assert f.client.get(path, headers=headers).status_code == 403
        assert (
            f.client.post(
                path, headers=headers | {"Idempotency-Key": "denied"}, json=request.model_dump()
            ).status_code
            == 403
        )
        with pytest.raises(ApiProblem):
            service.decide(context, kind, record_id, request, key="denied")
        assert counts(f) == before
        return
    original = service.inspect(context, kind, record_id)
    request = decision(original)
    response = f.client.post(
        path, headers=headers | {"Idempotency-Key": "open"}, json=request.model_dump()
    )
    assert response.status_code == 200, response.text
    opened = service.inspect(context, kind, record_id)
    assert opened.released and opened.version == original.version + 1
    low = replace(context, permissions=permissions_for_role(MembershipRole.OPERATIONS))
    visible = projection(f, low, kind, record_id)
    assert visible.notes == "Internal cost 350"
    assert visible.rejection_reason == "Private commercial explanation 350"
    service.decide(context, kind, record_id, decision(opened, False), key="close")
    assert not service.decide(context, kind, record_id, request, key="open").released
    assert projection(f, low, kind, record_id).notes is None
    assert counts(f) == [value + 2 for value in before]
    with pytest.raises(ApiProblem) as foreign:
        service.inspect(replace(context, organization_id=f.organization_b), kind, record_id)
    assert foreign.value.status == 404
    with pytest.raises(ApiProblem) as missing_read:
        service.inspect(
            replace(context, permissions=frozenset({Permission.PROFIT_READ})), kind, record_id
        )
    assert missing_read.value.status == 403


@pytest.mark.parametrize("kind", list(MODELS))
@pytest.mark.parametrize("stage", [Activity, AuditLog, OutboxEvent])
def test_export_review_failure_rolls_back_every_record(quotation_fixture, kind, stage):
    f = quotation_fixture
    record_id = seed(f, kind)
    _, context = reviewer(f)
    service = ExportTextReviewService(f.session_factory)
    original = service.inspect(context, kind, record_id)
    before = counts(f)

    def fail(*args, **kwargs):
        raise RuntimeError("injected review failure")

    event.listen(stage, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            service.decide(context, kind, record_id, decision(original), key="failed")
    finally:
        event.remove(stage, "before_insert", fail)
    assert service.inspect(context, kind, record_id) == original
    assert counts(f) == before


@pytest.mark.parametrize("kind", list(MODELS))
def test_export_content_restoration_and_deleted_owner_do_not_restore_release(
    quotation_fixture, kind
):
    f = quotation_fixture
    record_id = seed(f, kind)
    _, context = reviewer(f)
    service = ExportTextReviewService(f.session_factory)
    original = service.inspect(context, kind, record_id)
    opened = service.decide(context, kind, record_id, decision(original), key="open")
    for text in ("changed", "Internal cost 350"):
        with f.session_factory.begin() as session:
            session.get(MODELS[kind], record_id).notes = text
    assert not service.inspect(context, kind, record_id).released
    with pytest.raises(ApiProblem) as stale:
        service.decide(context, kind, record_id, decision(opened), key="stale")
    assert stale.value.code == "VERSION_CONFLICT"
    with f.session_factory.begin() as session:
        session.get(MODELS[kind], record_id).deleted_at = datetime.now(UTC)
    with pytest.raises(ApiProblem) as deleted:
        service.decide(context, kind, record_id, decision(original), key="open")
    assert deleted.value.status == 404


def test_export_legacy_upgrade_preserves_confidential_facts(quotation_fixture):
    from sqlalchemy.orm import Session

    f = quotation_fixture
    record_id = seed(f, "refund")

    def check(target):
        with Session(target) as session:
            row = session.get(TaxRefundCase, record_id)
            assert row.notes == "Internal cost 350"
            assert row.external_reference == "RECEIPT-2026-001"
            assert row.reviewed_by is row.reviewed_at is row.released_digest is None

    verify_legacy_upgrade(f.engine, "20260906_0026", check=check)
    verify_legacy_guard(f.engine, "20260906_0027", "20260906_0026", "Export evidence exists")


@pytest.mark.parametrize("kind", list(MODELS))
def test_export_review_competing_decisions_and_confirmation(quotation_fixture, kind):
    f = quotation_fixture
    record_id = seed(f, kind)
    _, context = reviewer(f)
    service = ExportTextReviewService(f.session_factory)
    original = service.inspect(context, kind, record_id)
    before = counts(f)
    with pytest.raises(ApiProblem) as unconfirmed:
        service.decide(
            context,
            kind,
            record_id,
            decision(original).model_copy(update={"confirmed": False}),
            key="unconfirmed",
        )
    assert unconfirmed.value.code == "CONFIRMATION_REQUIRED"
    barrier = Barrier(2)

    def race(release):
        barrier.wait(timeout=10)
        try:
            return service.decide(
                context, kind, record_id, decision(original, release), key=f"race-{release}"
            )
        except ApiProblem as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(race, (True, False)))
    errors = [row for row in results if isinstance(row, ApiProblem)]
    assert len(errors) == 1 and errors[0].code == "VERSION_CONFLICT"
    assert counts(f) == [value + 1 for value in before]


def test_export_create_replay_follow_up_and_transitions_protect_source(quotation_fixture):
    from datetime import date
    from uuid import UUID

    from app.export.schemas import CaseCommand, CustomsCreate, FollowUpSchedule, RefundCreate
    from app.export.services import ExportCommandService
    from test_shipment_documents_vertical_slice import create_shipment, executing_order

    f = quotation_fixture
    order = executing_order(f)
    shipment = create_shipment(
        f,
        [{"sales_order_item_id": row["id"], "quantity": row["quantity"]} for row in order["items"]],
    )
    _, high = reviewer(f)
    _, low = reviewer(f, MembershipRole.OPERATIONS)
    commands = ExportCommandService(f.session_factory)
    reviews = ExportTextReviewService(f.session_factory)
    customs_request = CustomsCreate(
        shipment_id=UUID(shipment["id"]),
        declared_amount="100",
        currency_code="USD",
        notes="Internal cost 350",
    )
    customs, _ = commands.create_customs(low, customs_request, key="create-customs")
    refund_request = RefundCreate(
        customs_declaration_id=customs.id, expected_amount="10", notes="Internal cost 350"
    )
    refund, _ = commands.create_refund(low, refund_request, key="create-refund")
    for kind, row, request in (
        ("customs", customs, customs_request),
        ("refund", refund, refund_request),
    ):
        assert row.notes is None
        create = getattr(commands, f"create_{kind}")
        assert create(low, request, key=f"create-{kind}")[0].notes is None
        original = reviews.inspect(high, kind, row.id)
        reviews.decide(high, kind, row.id, decision(original), key=f"open-{kind}")
        replay = create(low, request, key=f"create-{kind}")[0]
        assert replay.notes == "Internal cost 350"
        scheduled, _ = commands.schedule_follow_up(
            low,
            row.id,
            FollowUpSchedule(
                expected_version=replay.version,
                follow_up_date=date(2026, 9, 10),
                reason="Follow up",
            ),
            refund=kind == "refund",
        )
        assert scheduled.notes is None and not scheduled.released
        changed, _ = getattr(commands, f"{kind}_command")(
            low, row.id, "prepare", CaseCommand(expected_version=scheduled.version)
        )
        assert changed.notes is None
        assert create(low, request, key=f"create-{kind}")[0].notes is None
