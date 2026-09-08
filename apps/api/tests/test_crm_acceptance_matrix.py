from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.companies.models import Company, CompanyRole, Contact
from app.crm.enums import LeadStatus
from app.crm.models import Lead, Opportunity
from app.crm.services import LeadCommandService
from app.platform.models import AuditLog, OutboxEvent
from app.work.models import Activity
from sqlalchemy import event, func, select
from test_crm_vertical_slice import create_lead, run_command

pytestmark = pytest.mark.integration
pytest_plugins = ("test_crm_vertical_slice",)

# Independent guide5.1 expectations, not imported from the implementation transition map.
ALLOWED = {
    ("NEW", "qualify"): "QUALIFIED",
    ("NEW", "disqualify"): "DISQUALIFIED",
    ("QUALIFIED", "contact"): "CONTACTED",
    ("CONTACTED", "respond"): "RESPONDED",
    ("CONTACTED", "no-response"): "NO_RESPONSE",
    ("NO_RESPONSE", "contact"): "CONTACTED",
}


def counts(f):
    with f.session_factory() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (
                Company,
                CompanyRole,
                Contact,
                Opportunity,
                Activity,
                AuditLog,
                OutboxEvent,
            )
        )


@pytest.mark.parametrize("state", list(LeadStatus))
def test_all_lead_transition_pairs_match_guide_and_rejections_do_not_write(crm_fixture, state):
    f = crm_fixture
    for command in ("qualify", "disqualify", "contact", "respond", "no-response"):
        lead = create_lead(f)
        with f.session_factory.begin() as session:
            session.get(Lead, UUID(lead["id"])).status = state
        before = counts(f)
        response = f.client.post(
            f"/api/v1/leads/{lead['id']}/{command}",
            headers=f.headers("crm-user-a", f.organization_a),
        )
        expected = ALLOWED.get((state, command))
        if expected is None:
            assert response.status_code == 409, response.text
            assert response.json()["code"] == "INVALID_STATE_TRANSITION"
            assert counts(f) == before
        else:
            assert response.status_code == 200, response.text
            assert response.json()["status"] == expected
            assert counts(f) == (*before[:4], *(value + 1 for value in before[4:]))
        with f.session_factory() as session:
            assert session.get(Lead, UUID(lead["id"])).status == (expected or state)


def responded(f):
    lead = create_lead(f)
    for command in ("qualify", "contact", "respond"):
        run_command(f, lead["id"], command)
    return UUID(lead["id"])


def context(f):
    return RequestContext(
        user_id=f.user_a,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )


@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
def test_conversion_evidence_failure_rolls_back_all_created_objects(crm_fixture, table):
    f = crm_fixture
    lead_id = responded(f)
    before = counts(f)

    def fail(conn, cursor, statement, parameters, execution_context, executemany):
        if statement.startswith(f"INSERT INTO {table}"):
            raise RuntimeError("Injected conversion evidence failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="Injected conversion evidence failure"):
            LeadCommandService(f.session_factory).convert(context(f), lead_id)
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert counts(f) == before
    with f.session_factory() as session:
        lead = session.get(Lead, lead_id)
        assert lead.status == "RESPONDED"
        assert lead.converted_company_id is None
        assert lead.converted_contact_id is None
        assert lead.converted_opportunity_id is None
        assert lead.converted_at is None


def test_concurrent_conversion_returns_one_set_of_objects(crm_fixture):
    f = crm_fixture
    lead_id = responded(f)
    before = counts(f)
    service = LeadCommandService(f.session_factory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: service.convert(context(f), lead_id)[1:], range(2)))
    assert results[0] == results[1]
    assert counts(f) == tuple(value + 1 for value in before)
