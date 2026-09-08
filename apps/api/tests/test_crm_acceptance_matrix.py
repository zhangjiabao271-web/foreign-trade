from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission, permissions_for_role
from app.companies.conversion_repository import ConversionRepository
from app.companies.models import Company, CompanyRole, Contact
from app.crm.enums import LeadStatus
from app.crm.models import Lead, Opportunity
from app.crm.services import LeadCommandService
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership
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


@pytest.mark.parametrize("existing_company", [False, True])
def test_different_leads_concurrently_resolve_one_customer(
    crm_fixture, monkeypatch, existing_company
):
    f = crm_fixture
    lead_ids = [responded(f), responded(f)]
    if existing_company:
        with f.session_factory.begin() as session:
            session.add(
                Company(
                    organization_id=f.organization_a,
                    created_by=f.user_a,
                    updated_by=f.user_a,
                    name="Northwind Marine",
                    name_normalized="northwind marine",
                )
            )
    before = counts(f)
    both_read = Barrier(2)
    method = "find_role" if existing_company else "find_company"
    original = getattr(ConversionRepository, method)

    def synchronized_read(self, **kwargs):
        result = original(self, **kwargs)
        if result is None:
            both_read.wait(timeout=10)
        return result

    monkeypatch.setattr(ConversionRepository, method, synchronized_read)
    service = LeadCommandService(f.session_factory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda lead_id: service.convert(context(f), lead_id), lead_ids))
    assert results[0][1] == results[1][1]
    assert results[0][2] != results[1][2]
    assert results[0][3] != results[1][3]
    increments = (0 if existing_company else 1, 1, 2, 2, 2, 2, 2)
    assert counts(f) == tuple(
        value + delta for value, delta in zip(before, increments, strict=True)
    )


def test_conversion_does_not_reactivate_an_archived_customer_role(crm_fixture):
    f = crm_fixture
    first = responded(f)
    service = LeadCommandService(f.session_factory)
    _, company_id, _, _ = service.convert(context(f), first)
    with f.session_factory.begin() as session:
        role = session.scalar(
            select(CompanyRole).where(
                CompanyRole.organization_id == f.organization_a,
                CompanyRole.company_id == company_id,
                CompanyRole.role == "CUSTOMER",
            )
        )
        role.deleted_at = datetime.now(UTC)
        role_id = role.id
    second = responded(f)
    before = counts(f)
    with pytest.raises(ApiProblem) as error:
        service.convert(context(f), second)
    assert error.value.code == "COMPANY_ROLE_INACTIVE"
    assert counts(f) == before
    with f.session_factory() as session:
        assert session.get(CompanyRole, role_id).deleted_at is not None
        lead = session.get(Lead, second)
        assert lead.status == "RESPONDED"
        assert lead.converted_company_id is None


@pytest.mark.parametrize("role", list(MembershipRole))
def test_each_role_is_enforced_for_every_lead_command(crm_fixture, role):
    f = crm_fixture
    service = LeadCommandService(f.session_factory)
    # Fixture preparation uses the trusted service context, not the role under test.
    prepared = {}
    paths_to_state = {
        "qualify": (),
        "disqualify": (),
        "contact": ("qualify",),
        "respond": ("qualify", "contact"),
        "no-response": ("qualify", "contact"),
        "convert": ("qualify", "contact", "respond"),
    }
    for command, path in paths_to_state.items():
        lead = service.create(context(f), {"company_name": f"Role {role} {command}"})
        for step in path:
            service.transition(context(f), lead.id, step)
        prepared[command] = lead.id
    with f.session_factory.begin() as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_a,
                OrganizationMembership.user_id == f.user_a,
            )
        )
        membership.role = role

    allowed = role in {MembershipRole.ADMIN, MembershipRole.MANAGER, MembershipRole.SALES}
    role_context = RequestContext(
        user_id=f.user_a,
        organization_id=f.organization_a,
        permissions=permissions_for_role(role),
        request_id=uuid4(),
    )
    for command in ("create", *paths_to_state):
        before = counts(f)
        with f.session_factory() as session:
            leads_before = session.scalar(select(func.count()).select_from(Lead))
            snapshots_before = list(
                session.execute(select(Lead.id, Lead.status, Lead.version).order_by(Lead.id))
            )
        url = (
            "/api/v1/leads"
            if command == "create"
            else f"/api/v1/leads/{prepared[command]}/{command}"
        )
        kwargs = {"json": {"company_name": f"Role {role} created"}} if command == "create" else {}
        response = f.client.post(url, headers=f.headers("crm-user-a", f.organization_a), **kwargs)
        expected_status = 403
        if allowed:
            expected_status = 201 if command == "create" else 200
        assert response.status_code == expected_status, response.text
        if not allowed:
            assert response.json()["code"] == "PERMISSION_DENIED"
            with pytest.raises(ApiProblem) as error:
                if command == "create":
                    service.create(role_context, {"company_name": "Denied direct service"})
                elif command == "convert":
                    service.convert(role_context, prepared[command])
                else:
                    service.transition(role_context, prepared[command], command)
            assert error.value.code == "PERMISSION_DENIED"
            assert counts(f) == before
            with f.session_factory() as session:
                assert session.scalar(select(func.count()).select_from(Lead)) == leads_before
                assert (
                    list(
                        session.execute(
                            select(Lead.id, Lead.status, Lead.version).order_by(Lead.id)
                        )
                    )
                    == snapshots_before
                )
        else:
            result = response.json()["lead"] if command == "convert" else response.json()
            expected_state = {
                "create": "NEW",
                "qualify": "QUALIFIED",
                "disqualify": "DISQUALIFIED",
                "contact": "CONTACTED",
                "respond": "RESPONDED",
                "no-response": "NO_RESPONSE",
                "convert": "CONVERTED",
            }[command]
            assert result["status"] == expected_state
            with f.session_factory() as session:
                persisted = session.get(Lead, UUID(result["id"]))
                assert persisted.status == expected_state
                assert persisted.updated_by == f.user_a
                assert persisted.version == (
                    1 if command == "create" else len(paths_to_state[command]) + 2
                )
            increments = (1, 1, 1, 1, 1, 1, 1) if command == "convert" else (0, 0, 0, 0, 1, 1, 1)
            assert counts(f) == tuple(
                value + delta for value, delta in zip(before, increments, strict=True)
            )


def test_every_lead_command_rejects_foreign_ids_without_writes(crm_fixture):
    f = crm_fixture
    lead_id = responded(f)
    before = counts(f)
    for command in ("qualify", "disqualify", "contact", "respond", "no-response", "convert"):
        response = f.client.post(
            f"/api/v1/leads/{lead_id}/{command}",
            headers=f.headers("crm-user-b", f.organization_b),
        )
        assert response.status_code == 404
        assert response.json()["code"] == "LEAD_NOT_FOUND"
        assert counts(f) == before


@pytest.mark.parametrize("state", list(LeadStatus))
def test_conversion_entry_and_replay_for_every_lead_state(crm_fixture, state):
    f = crm_fixture
    lead_id = responded(f)
    service = LeadCommandService(f.session_factory)
    prior_ids = None
    if state == LeadStatus.CONVERTED:
        prior_ids = service.convert(context(f), lead_id)[1:]
    else:
        with f.session_factory.begin() as session:
            session.get(Lead, lead_id).status = state
    before = counts(f)
    response = f.client.post(
        f"/api/v1/leads/{lead_id}/convert",
        headers=f.headers("crm-user-a", f.organization_a),
    )
    if state == LeadStatus.RESPONDED:
        assert response.status_code == 200
        assert response.json()["lead"]["status"] == "CONVERTED"
        assert counts(f) == tuple(value + 1 for value in before)
    elif state == LeadStatus.CONVERTED:
        assert response.status_code == 200
        result = response.json()
        assert (
            tuple(UUID(result[key]) for key in ("company_id", "contact_id", "opportunity_id"))
            == prior_ids
        )
        assert counts(f) == before
    else:
        assert response.status_code == 409
        assert response.json()["code"] == "INVALID_STATE_TRANSITION"
        assert counts(f) == before
        with f.session_factory() as session:
            lead = session.get(Lead, lead_id)
            assert lead.status == state
            assert lead.converted_company_id is None


def test_lead_search_and_status_filters_preserve_tenant_scope_and_facts(crm_fixture):
    f = crm_fixture

    def create(subject, organization, company, contact):
        response = f.client.post(
            "/api/v1/leads",
            headers=f.headers(subject, organization),
            json={"company_name": company, "contact_name": contact},
        )
        assert response.status_code == 201, response.text
        return response.json()["id"]

    matching = create("crm-user-a", f.organization_a, "Search Harbor", "Ada")
    other_state = create("crm-user-a", f.organization_a, "Search Harbor", "Ben")
    contact_match = create("crm-user-a", f.organization_a, "Different Company", "Harbor Agent")
    foreign = create("crm-user-b", f.organization_b, "Search Harbor", "Ada")
    run_command(f, matching, "qualify")
    foreign_transition = f.client.post(
        f"/api/v1/leads/{foreign}/qualify",
        headers=f.headers("crm-user-b", f.organization_b),
    )
    assert foreign_transition.status_code == 200
    before = counts(f)
    with f.session_factory() as session:
        snapshots = list(
            session.execute(select(Lead.id, Lead.status, Lead.version).order_by(Lead.id))
        )

    cases = [
        ({"query": "hArBoR"}, {matching, other_state, contact_match}),
        ({"query": "harbor", "status": "QUALIFIED"}, {matching}),
        ({"query": "harbor", "status": "NEW"}, {other_state, contact_match}),
        ({"query": "ada"}, {matching}),
        ({"status": "QUALIFIED"}, {matching}),
        ({"query": "absent-company"}, set()),
    ]
    for params, expected_ids in cases:
        response = f.client.get(
            "/api/v1/leads", headers=f.headers("crm-user-a", f.organization_a), params=params
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert {row["id"] for row in body["items"]} == expected_ids
        assert body["count"] == len(expected_ids)
        with f.session_factory() as session:
            for row in body["items"]:
                assert session.get(Lead, UUID(row["id"])).organization_id == f.organization_a

    foreign_response = f.client.get(
        "/api/v1/leads",
        headers=f.headers("crm-user-b", f.organization_b),
        params={"query": "harbor", "status": "QUALIFIED"},
    )
    assert foreign_response.status_code == 200
    assert {row["id"] for row in foreign_response.json()["items"]} == {foreign}
    assert foreign_response.json()["count"] == 1
    assert counts(f) == before
    with f.session_factory() as session:
        assert (
            list(session.execute(select(Lead.id, Lead.status, Lead.version).order_by(Lead.id)))
            == snapshots
        )
