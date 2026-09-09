from dataclasses import replace
from uuid import UUID

import pytest
from app.auth.errors import ApiProblem
from app.companies.models import Company, CompanyRole, Contact
from app.crm.models import Lead, Opportunity
from app.crm.opportunity_services import (
    OpportunityCommandService,
    OpportunityQueryService,
    opportunity_record,
)
from app.crm.repositories import LeadRepository
from app.crm.services import LeadCommandService
from app.identity.models import OrganizationMembership
from app.inquiries.models import Inquiry
from app.inquiries.repositories import InquiryRepository
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.work.models import Activity
from sqlalchemy import event, select
from test_document_review import reviewer
from test_inquiry_creation_idempotency import request, setup
from test_quotation_vertical_slice import create_opportunity

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration


def snapshot(f):
    with f.session_factory() as session:
        return {
            model.__tablename__: list(session.execute(select(model.__table__).order_by(model.id)))
            for model in (
                Company,
                CompanyRole,
                Contact,
                Lead,
                Opportunity,
                Inquiry,
                Activity,
                AuditLog,
                OutboxEvent,
                IdempotencyKey,
            )
        }


def test_crm_and_inquiry_direct_paths_cannot_read_foreign_facts(quotation_fixture):
    f = quotation_fixture
    body = setup(f)
    created = request(f, body, "path-source")
    assert created.status_code == 201
    inquiry_id, opportunity_id = UUID(created.json()["id"]), UUID(body["opportunity_id"])
    _, context = reviewer(f)
    foreign = replace(context, organization_id=f.organization_b)
    before = snapshot(f)
    with f.session_factory() as session:
        lead_id = session.get(Opportunity, opportunity_id).source_lead_id
        leads = LeadRepository(session)
        assert leads.get(organization_id=f.organization_b, record_id=lead_id) is None
        assert leads.get_for_update(organization_id=f.organization_b, lead_id=lead_id) is None
        assert not leads.list(organization_id=f.organization_b)
        assert leads.count(organization_id=f.organization_b) == 0
        assert not leads.search(organization_id=f.organization_b, status=None, query=None, limit=25)
        assert not leads.activities(organization_id=f.organization_b, lead_id=lead_id)
        inquiries = InquiryRepository(session)
        assert inquiries.get(organization_id=f.organization_b, record_id=inquiry_id) is None
        assert (
            inquiries.get_for_update(organization_id=f.organization_b, inquiry_id=inquiry_id)
            is None
        )
        assert not inquiries.list(organization_id=f.organization_b)
        assert inquiries.count(organization_id=f.organization_b) == 0
        assert not inquiries.search(organization_id=f.organization_b, status=None, limit=25)
        opportunities = OpportunityQueryService(session)
        assert not opportunities.list(foreign, status=None, cursor=None, limit=25)
        for operation in (
            lambda: inquiries.search(
                organization_id=f.organization_b, status=None, limit=25, cursor=inquiry_id
            ),
            lambda: opportunity_record(session, foreign, opportunity_id, lock=True),
            lambda: opportunities.get(foreign, opportunity_id),
            lambda: opportunities.list(foreign, status=None, cursor=opportunity_id, limit=25),
            lambda: opportunities.history(foreign, opportunity_id, offset=0, limit=25),
        ):
            with pytest.raises(ApiProblem) as missing:
                operation()
            assert missing.value.status == 404
    assert snapshot(f) == before


def test_inquiry_text_http_foreign_manager_denied_without_mutation(quotation_fixture):
    f = quotation_fixture
    created = request(f, setup(f), "review-source")
    assert created.status_code == 201
    path = f"/api/v1/inquiries/{created.json()['id']}/text-review"
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
    own = f.headers(subject, f.organization_a)
    foreign = f.headers(subject, f.organization_b) | {"Idempotency-Key": "foreign-inquiry-review"}
    original = f.client.get(path, headers=own)
    assert original.status_code == 200
    body = {
        "expected_version": original.json()["version"],
        "content_digest": original.json()["content_digest"],
        "release": True,
        "reason": "Synthetic cross-organization denial",
        "confirmed": True,
    }
    assert f.client.get("/api/v1/me/context", headers=foreign).status_code == 200
    before = snapshot(f)
    for method in ("GET", "POST"):
        response = f.client.request(
            method, path, headers=foreign, **({"json": body} if method == "POST" else {})
        )
        assert response.status_code == 404
        assert response.json()["code"] == "INQUIRY_TEXT_NOT_FOUND"
        assert snapshot(f) == before
    assert f.client.get(path, headers=own).json() == original.json()


@pytest.mark.parametrize(
    "action",
    [
        "create",
        "qualify",
        "disqualify",
        "contact",
        "respond",
        "no-response",
        "start-negotiation",
        "mark-lost",
    ],
)
@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
def test_each_remaining_crm_command_rolls_back_after_evidence_insert(
    quotation_fixture, action, table
):
    f = quotation_fixture
    _, context = reviewer(f)
    leads = LeadCommandService(f.session_factory)
    if action in {"start-negotiation", "mark-lost"}:
        _, record_id = create_opportunity(f)
        record_id = UUID(record_id)
        with f.session_factory.begin() as session:
            row = session.get(Opportunity, record_id)
            if action == "start-negotiation":
                # Isolated legal starting predicate; natural reachability has its own vertical test.
                row.status = "QUOTING"
                session.flush()
            version = row.version

        def invoke():
            return OpportunityCommandService(f.session_factory).execute(
                context,
                record_id,
                action,
                {"expected_version": version, "reason": "Synthetic atomicity verification"},
                idempotency_key="atomic-command",
            )
    else:
        lead = leads.create(context, {"company_name": "Atomic CRM fixture"})
        preparation = {
            "create": (),
            "qualify": (),
            "disqualify": (),
            "contact": ("qualify",),
            "respond": ("qualify", "contact"),
            "no-response": ("qualify", "contact"),
        }
        for step in preparation[action]:
            leads.transition(context, lead.id, step)

        def invoke():
            if action == "create":
                return leads.create(context, {"company_name": "Atomic new lead"})
            return leads.transition(context, lead.id, action)

    before = snapshot(f)
    inserted = []

    def fail_after_insert(_connection, _cursor, statement, *_args):
        if statement.lstrip().lower().startswith(f"insert into {table} "):
            inserted.append(table)
            raise RuntimeError("injected CRM evidence failure")

    event.listen(f.engine, "after_cursor_execute", fail_after_insert)
    try:
        with pytest.raises(RuntimeError, match="injected CRM evidence failure"):
            invoke()
    finally:
        event.remove(f.engine, "after_cursor_execute", fail_after_insert)
    assert inserted == [table]
    assert snapshot(f) == before
    result = invoke()
    assert (
        result.status
        == {
            "create": "NEW",
            "qualify": "QUALIFIED",
            "disqualify": "DISQUALIFIED",
            "contact": "CONTACTED",
            "respond": "RESPONDED",
            "no-response": "NO_RESPONSE",
            "start-negotiation": "NEGOTIATION",
            "mark-lost": "LOST",
        }[action]
    )
    after = snapshot(f)
    for evidence in ("activities", "audit_logs", "outbox_events"):
        assert len(after[evidence]) == len(before[evidence]) + 1
