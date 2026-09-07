from collections.abc import Iterator
from dataclasses import dataclass
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.auth.tokens import LocalTestTokenIssuer, LocalTestTokenVerifier
from app.companies.models import Company, CompanyRole, Contact
from app.core.database import create_session_factory
from app.crm.models import Lead, Opportunity
from app.crm.services import LeadCommandService
from app.identity.enums import MembershipRole, MembershipStatus
from app.identity.models import Organization, OrganizationMembership, User
from app.main import app
from app.platform.models import AuditLog, OutboxEvent
from app.platform.records import DomainEvent, OutboxRecorder
from app.work.models import Activity
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from test_migrations import alembic_config

TEST_SECRET = "crm-integration-secret-with-at-least-32-characters"
TEST_ISSUER = "https://issuer.crm.integration.test"
TEST_AUDIENCE = "trade-workbench-crm-integration"


@dataclass(frozen=True, slots=True)
class CrmFixture:
    engine: Engine
    session_factory: sessionmaker[Session]
    client: TestClient
    issuer: LocalTestTokenIssuer
    organization_a: UUID
    organization_b: UUID
    user_a: UUID

    def headers(self, subject: str, organization_id: UUID) -> dict[str, str]:
        token = self.issuer.issue(subject=subject)
        return {
            "Authorization": f"Bearer {token}",
            "X-Organization-ID": str(organization_id),
        }


def seed_identity(factory: sessionmaker[Session]) -> tuple[UUID, UUID, UUID]:
    with factory.begin() as session:
        organization_a = Organization(name="Organization A", name_normalized="organization a")
        organization_b = Organization(name="Organization B", name_normalized="organization b")
        user_a = User(external_subject="crm-user-a", display_name="CRM User A")
        user_b = User(external_subject="crm-user-b", display_name="CRM User B")
        viewer_a = User(external_subject="crm-viewer-a", display_name="CRM Viewer A")
        session.add_all([organization_a, organization_b, user_a, user_b, viewer_a])
        session.flush()
        session.add_all(
            [
                OrganizationMembership(
                    organization_id=organization_a.id,
                    user_id=user_a.id,
                    role=MembershipRole.SALES,
                    status=MembershipStatus.ACTIVE,
                ),
                OrganizationMembership(
                    organization_id=organization_b.id,
                    user_id=user_b.id,
                    role=MembershipRole.SALES,
                    status=MembershipStatus.ACTIVE,
                ),
                OrganizationMembership(
                    organization_id=organization_a.id,
                    user_id=viewer_a.id,
                    role=MembershipRole.VIEWER,
                    status=MembershipStatus.ACTIVE,
                ),
            ]
        )
        session.flush()
        return organization_a.id, organization_b.id, user_a.id


@pytest.fixture
def crm_fixture(test_database_url: str) -> Iterator[CrmFixture]:
    command.upgrade(alembic_config(test_database_url), "head")
    engine = create_engine(test_database_url)
    factory = create_session_factory(engine)
    organization_a, organization_b, user_a = seed_identity(factory)
    issuer = LocalTestTokenIssuer(
        secret=TEST_SECRET,
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
    )
    app.state.session_factory = factory
    app.state.token_verifier = LocalTestTokenVerifier(
        secret=TEST_SECRET,
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
    )
    with TestClient(app) as client:
        yield CrmFixture(
            engine=engine,
            session_factory=factory,
            client=client,
            issuer=issuer,
            organization_a=organization_a,
            organization_b=organization_b,
            user_a=user_a,
        )
    del app.state.session_factory
    del app.state.token_verifier
    engine.dispose()


def create_lead(fixture: CrmFixture) -> dict[str, object]:
    response = fixture.client.post(
        "/api/v1/leads",
        headers=fixture.headers("crm-user-a", fixture.organization_a),
        json={
            "company_name": "Northwind Marine",
            "contact_name": "Ada Zhou",
            "email": "Ada@Northwind.Example",
            "phone": "+86 138 0000 0000",
            "country_code": "CN",
            "source": "trade-fair",
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json())


def run_command(fixture: CrmFixture, lead_id: str, command_name: str) -> dict[str, object]:
    response = fixture.client.post(
        f"/api/v1/leads/{lead_id}/{command_name}",
        headers=fixture.headers("crm-user-a", fixture.organization_a),
    )
    assert response.status_code == 200
    return cast(dict[str, object], response.json())


@pytest.mark.integration
def test_complete_lead_conversion_and_multiple_company_roles(crm_fixture: CrmFixture) -> None:
    lead = create_lead(crm_fixture)
    lead_id = str(lead["id"])
    assert run_command(crm_fixture, lead_id, "qualify")["status"] == "QUALIFIED"
    assert run_command(crm_fixture, lead_id, "contact")["status"] == "CONTACTED"
    assert run_command(crm_fixture, lead_id, "respond")["status"] == "RESPONDED"

    conversion = crm_fixture.client.post(
        f"/api/v1/leads/{lead_id}/convert",
        headers=crm_fixture.headers("crm-user-a", crm_fixture.organization_a),
    )
    assert conversion.status_code == 200
    result = conversion.json()
    assert result["lead"]["status"] == "CONVERTED"

    repeated = crm_fixture.client.post(
        f"/api/v1/leads/{lead_id}/convert",
        headers=crm_fixture.headers("crm-user-a", crm_fixture.organization_a),
    )
    assert repeated.status_code == 200
    assert repeated.json() == result

    supplier_role = crm_fixture.client.post(
        f"/api/v1/companies/{result['company_id']}/roles",
        headers=crm_fixture.headers("crm-user-a", crm_fixture.organization_a),
        json={"role": "SUPPLIER"},
    )
    assert supplier_role.status_code == 201
    repeated_role = crm_fixture.client.post(
        f"/api/v1/companies/{result['company_id']}/roles",
        headers=crm_fixture.headers("crm-user-a", crm_fixture.organization_a),
        json={"role": "SUPPLIER"},
    )
    assert repeated_role.status_code == 201
    assert repeated_role.json()["id"] == supplier_role.json()["id"]

    with crm_fixture.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Company)) == 1
        assert session.scalar(select(func.count()).select_from(Contact)) == 1
        assert session.scalar(select(func.count()).select_from(Opportunity)) == 1
        roles = set(
            session.scalars(
                select(CompanyRole.role).where(
                    CompanyRole.organization_id == crm_fixture.organization_a
                )
            )
        )
        assert roles == {"CUSTOMER", "SUPPLIER"}
        assert session.scalar(select(func.count()).select_from(Activity)) == 6
        assert session.scalar(select(func.count()).select_from(AuditLog)) == 6
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 6


@pytest.mark.integration
def test_invalid_transition_has_no_partial_write(crm_fixture: CrmFixture) -> None:
    lead = create_lead(crm_fixture)
    before_id = UUID(str(lead["id"]))
    with crm_fixture.session_factory() as session:
        before_counts = (
            session.scalar(select(func.count()).select_from(Activity)),
            session.scalar(select(func.count()).select_from(AuditLog)),
            session.scalar(select(func.count()).select_from(OutboxEvent)),
        )

    response = crm_fixture.client.post(
        f"/api/v1/leads/{before_id}/respond",
        headers=crm_fixture.headers("crm-user-a", crm_fixture.organization_a),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE_TRANSITION"

    with crm_fixture.session_factory() as session:
        persisted = session.get(Lead, before_id)
        after_counts = (
            session.scalar(select(func.count()).select_from(Activity)),
            session.scalar(select(func.count()).select_from(AuditLog)),
            session.scalar(select(func.count()).select_from(OutboxEvent)),
        )
    assert persisted is not None
    assert persisted.status == "NEW"
    assert after_counts == before_counts


@pytest.mark.integration
def test_lead_paths_are_tenant_scoped_and_writes_require_permission(
    crm_fixture: CrmFixture,
) -> None:
    lead = create_lead(crm_fixture)
    lead_id = str(lead["id"])
    organization_b_headers = crm_fixture.headers("crm-user-b", crm_fixture.organization_b)

    list_response = crm_fixture.client.get("/api/v1/leads", headers=organization_b_headers)
    assert list_response.status_code == 200
    assert list_response.json() == {"items": [], "count": 0}

    for path in (
        f"/api/v1/leads/{lead_id}",
        f"/api/v1/leads/{lead_id}/qualify",
        f"/api/v1/leads/{lead_id}/convert",
    ):
        method = (
            crm_fixture.client.get
            if path == f"/api/v1/leads/{lead_id}"
            else crm_fixture.client.post
        )
        response = method(path, headers=organization_b_headers)
        assert response.status_code == 404
        assert response.json()["code"] == "LEAD_NOT_FOUND"

    viewer_response = crm_fixture.client.post(
        "/api/v1/leads",
        headers=crm_fixture.headers("crm-viewer-a", crm_fixture.organization_a),
        json={"company_name": "Blocked Write"},
    )
    assert viewer_response.status_code == 403
    assert viewer_response.json()["code"] == "PERMISSION_DENIED"


class FailingOutboxRecorder(OutboxRecorder):
    def record(
        self,
        session: Session,
        context: RequestContext,
        event: DomainEvent,
    ) -> OutboxEvent:
        raise RuntimeError("injected outbox failure")


@pytest.mark.integration
def test_lead_write_rolls_back_when_outbox_write_fails(crm_fixture: CrmFixture) -> None:
    service = LeadCommandService(
        crm_fixture.session_factory,
        outbox_recorder=FailingOutboxRecorder(),
    )
    context = RequestContext(
        user_id=crm_fixture.user_a,
        organization_id=crm_fixture.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )

    with pytest.raises(RuntimeError, match="injected outbox failure"):
        service.create(context, {"company_name": "Rollback Company"})

    with crm_fixture.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Lead)) == 0
        assert session.scalar(select(func.count()).select_from(Activity)) == 0
        assert session.scalar(select(func.count()).select_from(AuditLog)) == 0
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 0
