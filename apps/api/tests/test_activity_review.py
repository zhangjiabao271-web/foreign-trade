from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission, permissions_for_role
from app.companies.archive import CompanyArchiveQuery
from app.companies.models import Company
from app.crm.models import Lead, Opportunity
from app.crm.opportunity_services import OpportunityQueryService
from app.crm.repositories import LeadRepository
from app.crm.services import LeadQueryService
from app.export.models import CustomsDeclaration, TaxRefundCase
from app.export.services import ExportQueryService
from app.identity.enums import MembershipRole
from app.platform.models import AuditLog, OutboxEvent
from app.work.models import Activity
from app.work.review import WorkReviewRequest, WorkReviewService
from sqlalchemy import event
from test_document_review import counts, reviewer
from test_quotation_vertical_slice import create_opportunity
from test_shipment_documents_vertical_slice import create_shipment, executing_order
from test_work_review import decision

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)
SUBJECTS = ["lead", "company", "opportunity", "customs_declaration", "tax_refund_case"]
MODELS = dict(
    zip(SUBJECTS, (Lead, Company, Opportunity, CustomsDeclaration, TaxRefundCase), strict=True)
)
PERMISSIONS = dict(
    zip(
        SUBJECTS,
        (
            Permission.LEAD_READ,
            Permission.COMPANY_READ,
            Permission.OPPORTUNITY_READ,
            Permission.EXPORT_READ,
            Permission.EXPORT_READ,
        ),
        strict=True,
    )
)


def seed(f, kind):
    if kind in {"lead", "company", "opportunity"}:
        company_id, opportunity_id = create_opportunity(f)
        with f.session_factory() as session:
            lead_id = session.get(Opportunity, UUID(opportunity_id)).source_lead_id
        owner_id = {
            "lead": lead_id,
            "company": UUID(company_id),
            "opportunity": UUID(opportunity_id),
        }[kind]
    else:
        order = executing_order(f)
        shipment = create_shipment(
            f,
            [
                {"sales_order_item_id": row["id"], "quantity": row["quantity"]}
                for row in order["items"]
            ],
        )
        with f.session_factory.begin() as session:
            declaration = CustomsDeclaration(
                organization_id=f.organization_a,
                shipment_id=UUID(shipment["id"]),
                declaration_number="REVIEW-CUSTOMS",
                declared_amount=Decimal("100"),
                currency_code="USD",
                required_document_types=[],
                status="CLEARED",
            )
            session.add(declaration)
            session.flush()
            owner_id = declaration.id
            if kind == "tax_refund_case":
                refund = TaxRefundCase(
                    organization_id=f.organization_a,
                    customs_declaration_id=declaration.id,
                    case_number="REVIEW-REFUND",
                    expected_amount=Decimal("10"),
                    refunded_amount=Decimal("10"),
                    currency_code="USD",
                    required_document_types=[],
                    status="REFUNDED",
                )
                session.add(refund)
                session.flush()
                owner_id = refund.id
    with f.session_factory.begin() as session:
        row = Activity(
            organization_id=f.organization_a,
            subject_type=kind,
            subject_id=owner_id,
            activity_type="fixture.note",
            summary="Internal cost 350",
            details={"nested": {"note": "cost 350"}},
            correlation_id=uuid4(),
        )
        session.add(row)
        session.flush()
        return owner_id, row.id


def query_rows(f, context, kind, owner_id):
    with f.session_factory() as session:
        if kind == "lead":
            rows = LeadQueryService(LeadRepository(session)).get(context, owner_id)[1]
        elif kind == "company":
            rows = CompanyArchiveQuery(session).history(context, owner_id, offset=0, limit=100)
        elif kind == "opportunity":
            rows = OpportunityQueryService(session).history(context, owner_id, offset=0, limit=100)
        else:
            rows, _ = ExportQueryService(session).activities(
                context, owner_id, refund=kind == "tax_refund_case", cursor=None, limit=100
            )
        assert not session.dirty
        return rows


def timeline_path(kind, owner_id):
    if kind == "lead":
        return f"/api/v1/leads/{owner_id}"
    resource = {
        "company": "companies",
        "opportunity": "opportunities",
        "customs_declaration": "customs-declarations",
        "tax_refund_case": "tax-refund-cases",
    }[kind]
    return f"/api/v1/{resource}/{owner_id}/activities"


@pytest.mark.parametrize("kind", SUBJECTS)
@pytest.mark.parametrize("role", list(MembershipRole))
def test_timeline_role_service_http_and_human_release(quotation_fixture, kind, role):
    f = quotation_fixture
    owner_id, record_id = seed(f, kind)
    subject, context = reviewer(f, role)
    headers = f.headers(subject, f.organization_a)
    path = f"/api/v1/work/{kind}/{owner_id}/activities/{record_id}/review"
    service = WorkReviewService(f.session_factory)
    privileged = Permission.PROFIT_READ in context.permissions
    allowed = PERMISSIONS[kind] in context.permissions
    response = f.client.get(timeline_path(kind, owner_id), headers=headers)
    if not allowed:
        assert response.status_code == 403
        with pytest.raises(ApiProblem):
            query_rows(f, context, kind, owner_id)
    else:
        assert response.status_code == 200, response.text
        items = response.json()["activities" if kind == "lead" else "items"]
        item = next(row for row in items if row["id"] == str(record_id))
        assert item["summary"] == ("Internal cost 350" if privileged else None)
        assert item["content_visible"] is privileged
        row = next(row for row in query_rows(f, context, kind, owner_id) if row.id == record_id)
        assert row.summary == item["summary"]
        assert row.details == ({"nested": {"note": "cost 350"}} if privileged else {})
    before = counts(f)
    if not (allowed and privileged):
        assert f.client.get(path, headers=headers).status_code == 403
        request = WorkReviewRequest(
            expected_version=1,
            content_digest="a" * 64,
            release=True,
            reason="Unauthorized release",
            confirmed=True,
        )
        assert (
            f.client.post(
                path, headers=headers | {"Idempotency-Key": "denied"}, json=request.model_dump()
            ).status_code
            == 403
        )
        with pytest.raises(ApiProblem) as denied:
            service.inspect_activity(context, kind, owner_id, record_id)
        assert denied.value.status == 403
        with pytest.raises(ApiProblem) as denied:
            service.decide_activity(context, kind, owner_id, record_id, request, key="denied")
        assert denied.value.status == 403
        assert counts(f) == before
        return
    original = service.inspect_activity(context, kind, owner_id, record_id)
    request = decision(original)
    result = f.client.post(
        path, headers=headers | {"Idempotency-Key": "release"}, json=request.model_dump()
    )
    assert result.status_code == 200, result.text
    assert result.json()["released"]
    assert counts(f) == [value + 1 for value in before]
    low = replace(context, permissions=permissions_for_role(MembershipRole.VIEWER))
    row = next(row for row in query_rows(f, low, kind, owner_id) if row.id == record_id)
    assert row.content_visible and row.summary == original.text
    row.details["nested"]["note"] = "changed projection"
    assert service.inspect_activity(context, kind, owner_id, record_id).details == original.details
    opened = service.inspect_activity(context, kind, owner_id, record_id)
    service.decide_activity(
        context, kind, owner_id, record_id, decision(opened, False), key="close"
    )
    assert not service.decide_activity(
        context, kind, owner_id, record_id, request, key="release"
    ).released
    with pytest.raises(ApiProblem) as foreign:
        service.inspect_activity(
            replace(context, organization_id=f.organization_b), kind, owner_id, record_id
        )
    assert foreign.value.status == 404


@pytest.mark.parametrize("kind", SUBJECTS)
def test_timeline_review_rechecks_original_permission_owner_and_version(quotation_fixture, kind):
    f = quotation_fixture
    owner_id, record_id = seed(f, kind)
    _, context = reviewer(f)
    service = WorkReviewService(f.session_factory)
    original = service.inspect_activity(context, kind, owner_id, record_id)
    request = decision(original)
    service.decide_activity(context, kind, owner_id, record_id, request, key="open")
    without_read = replace(context, permissions=context.permissions - {PERMISSIONS[kind]})
    with pytest.raises(ApiProblem) as denied:
        service.decide_activity(without_read, kind, owner_id, record_id, request, key="open")
    assert denied.value.status == 403
    with f.session_factory.begin() as session:
        session.get(Activity, record_id).summary = "changed cost"
    assert not service.inspect_activity(context, kind, owner_id, record_id).released
    with pytest.raises(ApiProblem) as stale:
        service.decide_activity(context, kind, owner_id, record_id, request, key="stale")
    assert stale.value.code == "VERSION_CONFLICT"
    with f.session_factory.begin() as session:
        session.get(MODELS[kind], owner_id).deleted_at = datetime.now(UTC)
    with pytest.raises(ApiProblem) as deleted:
        service.decide_activity(context, kind, owner_id, record_id, request, key="open")
    assert deleted.value.status == 404
    with pytest.raises(ApiProblem) as unknown:
        service.inspect_activity(context, "unknown", owner_id, record_id)
    assert unknown.value.status == 404


@pytest.mark.parametrize("stage", [Activity, AuditLog, OutboxEvent])
def test_timeline_review_atomicity(quotation_fixture, stage):
    f = quotation_fixture
    owner_id, record_id = seed(f, "company")
    _, context = reviewer(f)
    service = WorkReviewService(f.session_factory)
    original = service.inspect_activity(context, "company", owner_id, record_id)
    before = counts(f)

    def fail(*args, **kwargs):
        raise RuntimeError("injected timeline failure")

    event.listen(stage, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="injected timeline"):
            service.decide_activity(
                context, "company", owner_id, record_id, decision(original), key="fail"
            )
    finally:
        event.remove(stage, "before_insert", fail)
    assert counts(f) == before
    assert service.inspect_activity(context, "company", owner_id, record_id) == original
