from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission, permissions_for_role
from app.companies.archive import (
    CompanyArchiveQuery,
    CompanyArchiveRepository,
    CompanyArchiveService,
)
from app.companies.enums import CompanyRoleType
from app.companies.models import Company, CompanyRole, Contact
from app.companies.repositories import CompanyRepository
from app.companies.services import CompanyCommandService
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.work.models import Activity
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from test_company_archive import create, headers

pytest_plugins = ("test_quotation_vertical_slice",)
COMMANDS = ("create_company", "update_company", "create_contact", "update_contact", "add_role")


def snapshot(f):
    with f.session_factory() as session:
        return {
            model.__tablename__: list(session.execute(select(model.__table__).order_by(model.id)))
            for model in (
                Company,
                CompanyRole,
                Contact,
                Activity,
                AuditLog,
                OutboxEvent,
                IdempotencyKey,
            )
        }


def prepare(f, action):
    company = create(f)
    parent = f"/api/v1/companies/{company['id']}"
    contact = f.client.post(
        parent + "/contacts", headers=headers(f, "initial-contact"), json={"full_name": "Initial"}
    )
    assert contact.status_code == 201
    contact = contact.json()
    requests = {
        "create_company": (
            "POST",
            "/api/v1/companies",
            {"name": "New customer", "roles": ["CUSTOMER"]},
        ),
        "update_company": (
            "PUT",
            parent,
            {
                "name": "Updated customer",
                "expected_version": company["version"],
                "reason": "Verified update",
            },
        ),
        "create_contact": ("POST", parent + "/contacts", {"full_name": "New contact"}),
        "update_contact": (
            "PUT",
            parent + f"/contacts/{contact['id']}",
            {
                "full_name": "Updated contact",
                "expected_version": contact["version"],
                "reason": "Verified update",
            },
        ),
        "add_role": ("POST", parent + "/roles", {"role": "AGENT"}),
    }
    return UUID(company["id"]), UUID(contact["id"]), requests[action]


def invoke(f, ctx, action, company_id, contact_id, body):
    service = CompanyArchiveService(f.session_factory)
    if action == "add_role":
        return CompanyCommandService(f.session_factory).add_role(
            ctx, company_id, CompanyRoleType.AGENT
        )
    if action in {"create_company", "update_company"}:
        return service.write_company(
            ctx, body, key="matrix", company_id=company_id if action == "update_company" else None
        )
    return service.write_contact(
        ctx,
        company_id,
        body,
        key="matrix",
        contact_id=contact_id if action == "update_contact" else None,
    )


@pytest.mark.integration
@pytest.mark.parametrize("role", list(MembershipRole))
@pytest.mark.parametrize("action", COMMANDS)
def test_company_commands_enforce_six_roles_at_http_and_service(quotation_fixture, role, action):
    f = quotation_fixture
    company_id, contact_id, (method, path, body) = prepare(f, action)
    with f.session_factory.begin() as session:
        member = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_a,
                OrganizationMembership.user_id == f.sales_user,
            )
        )
        member.role = role
    ctx = RequestContext(f.sales_user, f.organization_a, permissions_for_role(role), uuid4())
    before = snapshot(f)
    if action == "add_role":
        parent = f"/api/v1/companies/{company_id}"
        for read_path in (
            "/api/v1/companies",
            parent,
            parent + "/contacts",
            parent + f"/contacts/{contact_id}",
            parent + "/activities",
        ):
            assert f.client.get(read_path, headers=headers(f)).status_code == 200
        assert snapshot(f) == before
    response = f.client.request(method, path, headers=headers(f, "matrix"), json=body)
    allowed = role in {
        MembershipRole.ADMIN,
        MembershipRole.MANAGER,
        MembershipRole.SALES,
        MembershipRole.OPERATIONS,
    }
    if not allowed:
        assert response.status_code == 403
        assert response.json()["code"] == "PERMISSION_DENIED"
        with pytest.raises(ApiProblem) as denied:
            invoke(f, ctx, action, company_id, contact_id, body)
        assert denied.value.code == "PERMISSION_DENIED"
        assert snapshot(f) == before
        return
    assert response.status_code == (200 if method == "PUT" else 201), response.text
    for field in ("name", "full_name", "role"):
        if field in body:
            assert response.json()[field] == body[field]
    after = snapshot(f)
    for table in ("activities", "audit_logs", "outbox_events"):
        assert len(after[table]) == len(before[table]) + 1
    replay = f.client.request(method, path, headers=headers(f, "matrix"), json=body)
    assert replay.status_code == response.status_code
    assert replay.json() == response.json()
    assert invoke(f, ctx, action, company_id, contact_id, body).id == UUID(response.json()["id"])
    assert snapshot(f) == after


@pytest.mark.integration
@pytest.mark.parametrize("action", COMMANDS)
@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
def test_every_company_write_rolls_back_after_evidence_insert(quotation_fixture, action, table):
    f = quotation_fixture
    company_id, contact_id, (_, _, body) = prepare(f, action)
    ctx = RequestContext(f.sales_user, f.organization_a, frozenset(Permission), uuid4())
    before = snapshot(f)
    inserted = []

    def fail_after_insert(_connection, _cursor, statement, *_args):
        if statement.lstrip().lower().startswith(f"insert into {table} "):
            inserted.append(table)
            raise RuntimeError("injected company evidence failure")

    event.listen(f.engine, "after_cursor_execute", fail_after_insert)
    try:
        with pytest.raises(RuntimeError, match="injected company evidence failure"):
            invoke(f, ctx, action, company_id, contact_id, body)
    finally:
        event.remove(f.engine, "after_cursor_execute", fail_after_insert)
    assert inserted == [table]
    assert snapshot(f) == before
    result = invoke(f, ctx, action, company_id, contact_id, body)
    after = snapshot(f)
    for evidence in ("activities", "audit_logs", "outbox_events"):
        assert len(after[evidence]) == len(before[evidence]) + 1
    assert invoke(f, ctx, action, company_id, contact_id, body).id == result.id
    assert snapshot(f) == after


@pytest.mark.parametrize("operation", ["get", "list", "contacts", "contact", "history"])
def test_company_reads_require_service_permission_before_sql(operation):
    ctx = RequestContext(
        uuid4(), uuid4(), frozenset(Permission) - {Permission.COMPANY_READ}, uuid4()
    )
    company_id, contact_id = uuid4(), uuid4()
    with Session() as session:
        query = CompanyArchiveQuery(session)
        calls = {
            "get": lambda: query.get(ctx, company_id),
            "list": lambda: query.list(ctx, query=None, role=None, cursor=None, limit=25),
            "contacts": lambda: query.contacts(ctx, company_id, cursor=None, limit=25),
            "contact": lambda: query.contact(ctx, company_id, contact_id),
            "history": lambda: query.history(ctx, company_id, offset=0, limit=25),
        }
        with pytest.raises(ApiProblem) as denied:
            calls[operation]()
        assert denied.value.code == "PERMISSION_DENIED"
        assert not session.in_transaction()


@pytest.mark.integration
def test_company_repositories_scope_each_foreign_read(quotation_fixture):
    f = quotation_fixture
    company_id, contact_id, _ = prepare(f, "add_role")
    before = snapshot(f)
    with f.session_factory() as session:
        repository = CompanyArchiveRepository(session)
        for operation in (
            lambda: repository.company(f.organization_b, company_id),
            lambda: repository.contact(f.organization_b, company_id, contact_id),
            lambda: repository.companies(
                f.organization_b, query=None, role=None, cursor=company_id, limit=25
            ),
            lambda: repository.contacts(f.organization_b, company_id, cursor=contact_id, limit=25),
        ):
            with pytest.raises(ApiProblem) as denied:
                operation()
            assert denied.value.status == 404
        assert not repository.companies(
            f.organization_b, query="Northern", role=CompanyRoleType.SUPPLIER, cursor=None, limit=25
        )
        assert repository.roles(f.organization_b, [company_id]) == {company_id: []}
        assert not repository.contacts(f.organization_b, company_id, cursor=None, limit=25)
        assert not repository.history(f.organization_b, company_id, offset=0, limit=25)
        command_repository = CompanyRepository(session)
        assert (
            command_repository.get_for_update(
                organization_id=f.organization_b, company_id=company_id
            )
            is None
        )
        assert (
            command_repository.find_role(
                organization_id=f.organization_b, company_id=company_id, role="CUSTOMER"
            )
            is None
        )
    assert snapshot(f) == before
