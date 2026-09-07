from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from uuid import UUID

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission, permissions_for_role
from app.crm.models import Lead, Opportunity
from app.crm.opportunity_services import OpportunityCommandService, OpportunityQueryService
from app.crm.repositories import LeadRepository
from app.crm.services import LeadCommandService, LeadQueryService
from app.crm.text_review import CrmTextReviewRequest, CrmTextReviewService
from app.identity.enums import MembershipRole
from app.platform.models import AuditLog, OutboxEvent
from app.work.models import Activity
from legacy_migration import verify_legacy_guard, verify_legacy_upgrade
from sqlalchemy import event
from test_document_review import counts, reviewer
from test_quotation_vertical_slice import create_opportunity

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def seed(f, kind):
    _, opportunity_id = create_opportunity(f)
    with f.session_factory.begin() as session:
        opportunity = session.get(Opportunity, UUID(opportunity_id))
        if kind == "lead":
            row = session.get(Lead, opportunity.source_lead_id)
            row.notes = "Internal cost 350"
            row.source = "Private sourcing note 350"
        else:
            row = opportunity
            row.lost_reason = "Internal cost 350"
        return row.id


def decision(snapshot, release=True):
    return CrmTextReviewRequest(
        expected_version=snapshot.version,
        content_digest=snapshot.content_digest,
        release=release,
        confirmed=True,
        reason="Reviewed exact CRM text",
    )


def projection(f, context, kind, record_id):
    with f.session_factory() as session:
        if kind == "lead":
            result = LeadQueryService(LeadRepository(session)).get(context, record_id)[0]
        else:
            result = OpportunityQueryService(session).get(context, record_id)
        assert not session.dirty
        return result


@pytest.mark.parametrize("kind", ["lead", "opportunity"])
@pytest.mark.parametrize("role", list(MembershipRole))
def test_crm_text_role_http_service_release_and_replay(quotation_fixture, kind, role):
    f = quotation_fixture
    record_id = seed(f, kind)
    subject, context = reviewer(f, role)
    headers = f.headers(subject, f.organization_a)
    resource = "leads" if kind == "lead" else "opportunities"
    field = "notes" if kind == "lead" else "lost_reason"
    privileged = Permission.PROFIT_READ in context.permissions
    result = f.client.get(f"/api/v1/{resource}/{record_id}", headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()[field] == ("Internal cost 350" if privileged else None)
    assert result.json()["content_visible"] is privileged
    assert getattr(projection(f, context, kind, record_id), field) == result.json()[field]
    if kind == "lead":
        assert result.json()["company_name"] == "Blue Current Imports"
        assert result.json()["source"] == ("Private sourcing note 350" if privileged else None)
    service = CrmTextReviewService(f.session_factory)
    path = f"/api/v1/crm-text/{kind}/{record_id}/review"
    before = counts(f)
    if not privileged:
        request = CrmTextReviewRequest(
            expected_version=1,
            content_digest="a" * 64,
            release=True,
            confirmed=True,
            reason="Unauthorized review",
        )
        assert f.client.get(path, headers=headers).status_code == 403
        assert (
            f.client.post(
                path, headers=headers | {"Idempotency-Key": "denied"}, json=request.model_dump()
            ).status_code
            == 403
        )
        with pytest.raises(ApiProblem):
            service.inspect(context, kind, record_id)
        with pytest.raises(ApiProblem):
            service.decide(context, kind, record_id, request, key="denied")
        assert counts(f) == before
        return
    original = service.inspect(context, kind, record_id)
    request = decision(original)
    opened = service.decide(context, kind, record_id, request, key="open")
    assert opened.released and opened.version == original.version + 1
    low = replace(context, permissions=permissions_for_role(MembershipRole.SALES))
    assert getattr(projection(f, low, kind, record_id), field) == "Internal cost 350"
    closed = service.decide(context, kind, record_id, decision(opened, False), key="close")
    assert not closed.released
    assert not service.decide(context, kind, record_id, request, key="open").released
    assert counts(f) == [value + 2 for value in before]
    with pytest.raises(ApiProblem) as foreign:
        service.inspect(replace(context, organization_id=f.organization_b), kind, record_id)
    assert foreign.value.status == 404
    with pytest.raises(ApiProblem) as missing_read:
        service.inspect(
            replace(context, permissions=frozenset({Permission.PROFIT_READ})), kind, record_id
        )
    assert missing_read.value.status == 403


@pytest.mark.parametrize("kind", ["lead", "opportunity"])
@pytest.mark.parametrize("stage", [Activity, AuditLog, OutboxEvent])
def test_crm_review_evidence_failure_rolls_back(quotation_fixture, kind, stage):
    f = quotation_fixture
    record_id = seed(f, kind)
    _, context = reviewer(f)
    service = CrmTextReviewService(f.session_factory)
    original = service.inspect(context, kind, record_id)
    before = counts(f)

    def fail(*args, **kwargs):
        raise RuntimeError("injected CRM review failure")

    event.listen(stage, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="injected CRM"):
            service.decide(context, kind, record_id, decision(original), key="failed")
    finally:
        event.remove(stage, "before_insert", fail)
    assert service.inspect(context, kind, record_id) == original
    assert counts(f) == before


def test_crm_commands_and_replays_protect_text_and_invalidate_release(quotation_fixture):
    f = quotation_fixture
    _, high = reviewer(f)
    low = replace(high, permissions=permissions_for_role(MembershipRole.SALES))
    service = LeadCommandService(f.session_factory)
    lead = service.create(
        low, {"company_name": "Visible Identity", "notes": "cost 350", "source": "private cost"}
    )
    assert lead.notes is None and lead.source is None and lead.company_name == "Visible Identity"
    review = CrmTextReviewService(f.session_factory)
    original = review.inspect(high, "lead", lead.id)
    review.decide(high, "lead", lead.id, decision(original), key="lead-open")
    for command_name in ("qualify", "contact", "respond"):
        changed = service.transition(low, lead.id, command_name)
        assert changed.notes is None and not changed.released
    converted, _, _, opportunity_id = service.convert(low, lead.id)
    assert converted.notes is None
    assert service.convert(low, lead.id)[0].notes is None
    opportunity = projection(f, low, "opportunity", opportunity_id)
    commands = OpportunityCommandService(f.session_factory)
    request = {"expected_version": opportunity.version, "reason": "cost too high 350"}
    lost = commands.execute(low, opportunity_id, "mark-lost", request, idempotency_key="loss")
    assert lost.lost_reason is None and lost.status == "LOST"
    assert (
        commands.execute(
            low, opportunity_id, "mark-lost", request, idempotency_key="loss"
        ).lost_reason
        is None
    )
    original = review.inspect(high, "opportunity", opportunity_id)
    opened = review.decide(high, "opportunity", opportunity_id, decision(original), key="lost-open")
    assert projection(f, low, "opportunity", opportunity_id).lost_reason == "cost too high 350"
    with f.session_factory.begin() as session:
        session.get(Opportunity, opportunity_id).lost_reason = "new confidential reason"
    with f.session_factory.begin() as session:
        session.get(Opportunity, opportunity_id).lost_reason = "cost too high 350"
    assert not review.inspect(high, "opportunity", opportunity_id).released
    with pytest.raises(ApiProblem) as stale:
        review.decide(high, "opportunity", opportunity_id, decision(opened), key="stale")
    assert stale.value.code == "VERSION_CONFLICT"


def test_legacy_crm_text_is_retained_default_confidential_and_downgrade_refused(quotation_fixture):
    f = quotation_fixture
    record_id = seed(f, "lead")

    def check(target):
        from sqlalchemy.orm import Session

        with Session(target) as session:
            row = session.get(Lead, record_id)
            assert row.notes == "Internal cost 350"
            assert row.source == "Private sourcing note 350"
            assert row.reviewed_at is row.reviewed_by is row.released_digest is None

    verify_legacy_upgrade(f.engine, "20260906_0025", check=check)
    verify_legacy_guard(f.engine, "20260906_0026", "20260906_0025", "CRM evidence exists")


@pytest.mark.parametrize("kind", ["lead", "opportunity"])
def test_crm_review_concurrency_confirmation_and_deleted_owner(quotation_fixture, kind):
    from datetime import UTC, datetime

    f = quotation_fixture
    record_id = seed(f, kind)
    _, context = reviewer(f)
    service = CrmTextReviewService(f.session_factory)
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

    def decide_together(release):
        barrier.wait(timeout=10)
        try:
            return service.decide(
                context, kind, record_id, decision(original, release), key=f"race-{release}"
            )
        except ApiProblem as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide_together, (True, False)))
    assert (
        len(
            [
                row
                for row in results
                if isinstance(row, ApiProblem) and row.code == "VERSION_CONFLICT"
            ]
        )
        == 1
    )
    assert len([row for row in results if not isinstance(row, ApiProblem)]) == 1
    assert counts(f) == [value + 1 for value in before]
    with f.session_factory.begin() as session:
        session.get(Lead if kind == "lead" else Opportunity, record_id).deleted_at = datetime.now(
            UTC
        )
    with pytest.raises(ApiProblem) as deleted:
        service.inspect(context, kind, record_id)
    assert deleted.value.status == 404


@pytest.mark.parametrize("kind", ["lead", "opportunity"])
def test_crm_source_list_and_http_review_tenant_boundary(quotation_fixture, kind):
    f = quotation_fixture
    record_id = seed(f, kind)
    subject, context = reviewer(f)
    low_subject, _ = reviewer(f, MembershipRole.SALES)
    headers = f.headers(subject, f.organization_a)
    low_headers = f.headers(low_subject, f.organization_a)
    resource = "leads" if kind == "lead" else "opportunities"
    field = "notes" if kind == "lead" else "lost_reason"
    path = f"/api/v1/crm-text/{kind}/{record_id}/review"

    def listed_text():
        response = f.client.get(f"/api/v1/{resource}", headers=low_headers)
        assert response.status_code == 200, response.text
        return next(row[field] for row in response.json()["items"] if row["id"] == str(record_id))

    assert listed_text() is None
    original = CrmTextReviewService(f.session_factory).inspect(context, kind, record_id)
    request = decision(original).model_dump()
    foreign = f.headers(subject, f.organization_b)
    # Give this reviewer active membership in both tenants to test resource isolation,
    # rather than rejection by the membership gate.
    with f.session_factory.begin() as session:
        from app.identity.models import OrganizationMembership

        session.add(
            OrganizationMembership(
                organization_id=f.organization_b,
                user_id=context.user_id,
                role=MembershipRole.MANAGER,
                status="ACTIVE",
            )
        )
    assert f.client.get(path, headers=foreign).status_code == 404
    assert (
        f.client.post(
            path, headers=foreign | {"Idempotency-Key": "foreign-source-review"}, json=request
        ).status_code
        == 404
    )
    response = f.client.post(
        path, headers=headers | {"Idempotency-Key": "http-source-review"}, json=request
    )
    assert response.status_code == 200, response.text
    assert response.json()["released"]
    assert listed_text() == "Internal cost 350"
