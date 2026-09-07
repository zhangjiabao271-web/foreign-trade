from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from app.auth.tokens import LocalTestTokenIssuer, LocalTestTokenVerifier
from app.core.database import create_session_factory
from app.identity.enums import MembershipRole, MembershipStatus, OrganizationStatus, UserStatus
from app.identity.models import Organization, OrganizationMembership, User
from app.main import app
from app.platform.enums import OutboxStatus
from app.platform.models import AsyncJob, OutboxEvent
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from test_migrations import alembic_config

TEST_SECRET = "integration-test-secret-with-at-least-32-characters"
TEST_ISSUER = "https://issuer.integration.test"
TEST_AUDIENCE = "trade-workbench-integration"


@dataclass(frozen=True, slots=True)
class TenantFixture:
    client: TestClient
    issuer: LocalTestTokenIssuer
    organization_a: UUID
    organization_b: UUID
    organization_disabled: UUID
    job_a: UUID
    job_b: UUID

    def headers(
        self,
        subject: str,
        organization_id: UUID | None = None,
        *,
        token_organization_id: UUID | None = None,
        issuer: str | None = None,
        audience: str | None = None,
        expires_in: timedelta = timedelta(minutes=5),
    ) -> dict[str, str]:
        selected_organization = organization_id or self.organization_a
        token = self.issuer.issue(
            subject=subject,
            organization_id=token_organization_id,
            issuer=issuer,
            audience=audience,
            expires_in=expires_in,
        )
        return {
            "Authorization": f"Bearer {token}",
            "X-Organization-ID": str(selected_organization),
        }


def add_user(
    session: Session,
    *,
    subject: str,
    organization: Organization | None,
    role: MembershipRole = MembershipRole.ADMIN,
    user_status: UserStatus = UserStatus.ACTIVE,
    membership_status: MembershipStatus = MembershipStatus.ACTIVE,
) -> User:
    user = User(
        external_subject=subject,
        display_name=subject,
        status=user_status,
    )
    session.add(user)
    session.flush()
    if organization is not None:
        session.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role=role,
                status=membership_status,
            )
        )
    return user


def seed_tenants(factory: sessionmaker[Session]) -> tuple[UUID, UUID, UUID, UUID, UUID]:
    with factory.begin() as session:
        organization_a = Organization(name="Organization A", name_normalized="organization a")
        organization_b = Organization(name="Organization B", name_normalized="organization b")
        organization_disabled = Organization(
            name="Organization Disabled",
            name_normalized="organization disabled",
            status=OrganizationStatus.DISABLED,
        )
        session.add_all([organization_a, organization_b, organization_disabled])
        session.flush()

        user_a = add_user(session, subject="user-a", organization=organization_a)
        user_b = add_user(session, subject="user-b", organization=organization_b)
        add_user(session, subject="no-membership", organization=None)
        add_user(
            session,
            subject="disabled-user",
            organization=organization_a,
            user_status=UserStatus.DISABLED,
        )
        add_user(
            session,
            subject="inactive-membership",
            organization=organization_a,
            membership_status=MembershipStatus.DISABLED,
        )
        add_user(
            session,
            subject="viewer-a",
            organization=organization_a,
            role=MembershipRole.VIEWER,
        )
        add_user(session, subject="disabled-org-user", organization=organization_disabled)
        session.flush()

        job_a = AsyncJob(
            organization_id=organization_a.id,
            created_by=user_a.id,
            updated_by=user_a.id,
            job_type="fixture.a",
            correlation_id=uuid4(),
        )
        job_b = AsyncJob(
            organization_id=organization_b.id,
            created_by=user_b.id,
            updated_by=user_b.id,
            job_type="fixture.b",
            correlation_id=uuid4(),
        )
        session.add_all([job_a, job_b])
        session.flush()
        return (
            organization_a.id,
            organization_b.id,
            organization_disabled.id,
            job_a.id,
            job_b.id,
        )


@pytest.fixture
def tenant_fixture(test_database_url: str) -> Iterator[TenantFixture]:
    command.upgrade(alembic_config(test_database_url), "head")
    engine: Engine = create_engine(test_database_url)
    factory = create_session_factory(engine)
    organization_a, organization_b, organization_disabled, job_a, job_b = seed_tenants(factory)
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
        yield TenantFixture(
            client=client,
            issuer=issuer,
            organization_a=organization_a,
            organization_b=organization_b,
            organization_disabled=organization_disabled,
            job_a=job_a,
            job_b=job_b,
        )

    del app.state.session_factory
    del app.state.token_verifier
    engine.dispose()


def test_valid_request_builds_context_and_preserves_request_id(
    tenant_fixture: TenantFixture,
) -> None:
    request_id = uuid4()
    headers = tenant_fixture.headers("user-a") | {"X-Request-ID": str(request_id)}

    response = tenant_fixture.client.get("/api/v1/me/context", headers=headers)

    assert response.status_code == 200
    assert response.json()["organization_id"] == str(tenant_fixture.organization_a)
    assert response.json()["request_id"] == str(request_id)
    assert response.headers["X-Request-ID"] == str(request_id)


def test_missing_token_is_rejected(tenant_fixture: TenantFixture) -> None:
    response = tenant_fixture.client.get(
        "/api/v1/me/context",
        headers={"X-Organization-ID": str(tenant_fixture.organization_a)},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "AUTHENTICATION_REQUIRED"


def test_missing_organization_is_rejected(tenant_fixture: TenantFixture) -> None:
    headers = tenant_fixture.headers("user-a")
    headers.pop("X-Organization-ID")

    response = tenant_fixture.client.get("/api/v1/me/context", headers=headers)

    assert response.status_code == 400
    assert response.json()["code"] == "ORGANIZATION_REQUIRED"


@pytest.mark.parametrize(
    ("issuer_override", "audience_override", "expires_in"),
    [
        ("https://wrong-issuer.test", None, timedelta(minutes=5)),
        (None, "wrong-audience", timedelta(minutes=5)),
        (None, None, timedelta(seconds=-1)),
    ],
)
def test_invalid_standard_token_claims_are_rejected(
    tenant_fixture: TenantFixture,
    issuer_override: str | None,
    audience_override: str | None,
    expires_in: timedelta,
) -> None:
    headers = tenant_fixture.headers(
        "user-a",
        issuer=issuer_override,
        audience=audience_override,
        expires_in=expires_in,
    )

    response = tenant_fixture.client.get("/api/v1/me/context", headers=headers)

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_TOKEN"


@pytest.mark.parametrize(
    ("subject", "organization_attr", "expected_code"),
    [
        ("no-membership", "organization_a", "MEMBERSHIP_REQUIRED"),
        ("disabled-user", "organization_a", "USER_DISABLED"),
        ("inactive-membership", "organization_a", "MEMBERSHIP_INACTIVE"),
        ("disabled-org-user", "organization_disabled", "ORGANIZATION_DISABLED"),
    ],
)
def test_local_identity_and_membership_fail_closed(
    tenant_fixture: TenantFixture,
    subject: str,
    organization_attr: str,
    expected_code: str,
) -> None:
    organization_id = getattr(tenant_fixture, organization_attr)

    response = tenant_fixture.client.get(
        "/api/v1/me/context",
        headers=tenant_fixture.headers(subject, organization_id),
    )

    assert response.status_code == 403
    assert response.json()["code"] == expected_code


def test_token_organization_must_match_selected_organization(
    tenant_fixture: TenantFixture,
) -> None:
    response = tenant_fixture.client.get(
        "/api/v1/me/context",
        headers=tenant_fixture.headers(
            "user-a",
            organization_id=tenant_fixture.organization_a,
            token_organization_id=tenant_fixture.organization_b,
        ),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "ORGANIZATION_MISMATCH"


def test_cross_tenant_primary_key_returns_not_found(tenant_fixture: TenantFixture) -> None:
    response = tenant_fixture.client.get(
        f"/api/v1/jobs/{tenant_fixture.job_b}",
        headers=tenant_fixture.headers("user-a"),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "JOB_NOT_FOUND"


def test_list_and_count_are_tenant_scoped(tenant_fixture: TenantFixture) -> None:
    response = tenant_fixture.client.get(
        "/api/v1/jobs",
        headers=tenant_fixture.headers("user-a"),
    )

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert [item["id"] for item in response.json()["items"]] == [str(tenant_fixture.job_a)]


def test_api_permission_guard_rejects_viewer(tenant_fixture: TenantFixture) -> None:
    response = tenant_fixture.client.get(
        "/api/v1/jobs",
        headers=tenant_fixture.headers("viewer-a"),
    )

    assert response.status_code == 403
    assert response.json()["code"] == "PERMISSION_DENIED"


def test_outbox_admin_pagination_replay_and_tenant_guards(tenant_fixture: TenantFixture) -> None:
    fixture = tenant_fixture
    ids: list[UUID] = []
    with app.state.session_factory.begin() as session:
        for organization_id in [fixture.organization_a] * 3 + [fixture.organization_b]:
            event = OutboxEvent(
                organization_id=organization_id,
                event_type="fixture.dead.v1",
                aggregate_type="fixture",
                aggregate_id=uuid4(),
                correlation_id=uuid4(),
                status=OutboxStatus.DEAD,
                last_error="synthetic-private-broker-error",
            )
            session.add(event)
            session.flush()
            ids.append(event.id)
    client = fixture.client
    headers = fixture.headers("user-a")
    path = "/api/v1/outbox/dead"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=fixture.headers("viewer-a")).status_code == 403
    for query in ["limit=0", "limit=101", "offset=-1"]:
        assert client.get(f"{path}?{query}", headers=headers).status_code == 422
    first = client.get(f"{path}?limit=2", headers=headers)
    assert first.status_code == 200
    page = first.json()
    assert page["has_more"] is True
    assert page["next_offset"] == 2
    second = client.get(f"{path}?limit=2&offset=2", headers=headers).json()
    assert second["has_more"] is False
    assert second["next_offset"] is None
    assert {item["id"] for item in page["items"] + second["items"]} == {
        str(event_id) for event_id in ids[:3]
    }
    assert "synthetic-private-broker-error" not in first.text
    assert page["items"][0]["last_error"] == "EVENT_DELIVERY_FAILED"
    replay_path = f"/api/v1/outbox/{ids[0]}/replay"
    body = {"reason": "Verified dependency recovery", "expected_version": 1}
    assert (
        client.post(replay_path, headers=fixture.headers("viewer-a"), json=body).status_code == 403
    )
    assert (
        client.post(f"/api/v1/outbox/{ids[3]}/replay", headers=headers, json=body).status_code
        == 404
    )
    assert client.post(replay_path, headers=headers, json={"reason": "  "}).status_code == 422
    assert (
        client.post(replay_path, headers=headers, json=body | {"expected_version": 2}).status_code
        == 409
    )
    replayed = client.post(replay_path, headers=headers, json=body)
    assert replayed.status_code == 200
    assert replayed.json()["status"] == "PENDING"
    assert replayed.json()["version"] == 2
    assert client.post(replay_path, headers=headers, json=body).status_code == 409


def test_organization_discovery_needs_token_but_not_selected_organization(
    tenant_fixture: TenantFixture,
) -> None:
    client = tenant_fixture.client
    assert client.get("/api/v1/me/organizations").status_code == 401
    invalid = client.get("/api/v1/me/organizations", headers={"Authorization": "Bearer invalid"})
    assert invalid.status_code == 401
    assert invalid.json()["code"] == "INVALID_TOKEN"
    headers = tenant_fixture.headers("user-a")
    headers.pop("X-Organization-ID")
    response = client.get("/api/v1/me/organizations", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "organization_id": str(tenant_fixture.organization_a),
                "name": "Organization A",
                "role": "ADMIN",
            }
        ]
    }


@pytest.mark.parametrize(
    "subject",
    [
        "unmapped-subject",
        "no-membership",
        "disabled-user",
        "inactive-membership",
        "disabled-org-user",
    ],
)
def test_organization_discovery_hides_inactive_identities(
    tenant_fixture: TenantFixture,
    subject: str,
) -> None:
    response = tenant_fixture.client.get(
        "/api/v1/me/organizations", headers=tenant_fixture.headers(subject)
    )
    assert response.status_code == 200
    assert response.json() == {"items": []}


def test_organization_discovery_limits_multi_membership_by_token_claim(
    tenant_fixture: TenantFixture,
) -> None:
    with app.state.session_factory.begin() as session:
        user = session.scalar(select(User).where(User.external_subject == "user-a"))
        session.add(
            OrganizationMembership(
                organization_id=tenant_fixture.organization_b,
                user_id=user.id,
                role=MembershipRole.VIEWER,
                status=MembershipStatus.ACTIVE,
            )
        )
    client = tenant_fixture.client
    response = client.get("/api/v1/me/organizations", headers=tenant_fixture.headers("user-a"))
    assert [item["role"] for item in response.json()["items"]] == ["ADMIN", "VIEWER"]
    restricted = client.get(
        "/api/v1/me/organizations",
        headers=tenant_fixture.headers(
            "user-a",
            token_organization_id=tenant_fixture.organization_b,
        ),
    )
    assert [item["organization_id"] for item in restricted.json()["items"]] == [
        str(tenant_fixture.organization_b)
    ]


@pytest.mark.parametrize("model", [User, Organization, OrganizationMembership])
def test_organization_discovery_hides_soft_deleted_identity(
    tenant_fixture: TenantFixture,
    model: type[User] | type[Organization] | type[OrganizationMembership],
) -> None:
    with app.state.session_factory.begin() as session:
        user = session.scalar(select(User).where(User.external_subject == "user-a"))
        if model is User:
            record = user
        elif model is Organization:
            record = session.get(Organization, tenant_fixture.organization_a)
        else:
            record = session.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == tenant_fixture.organization_a,
                    OrganizationMembership.user_id == user.id,
                )
            )
        record.deleted_at = datetime.now(UTC)
    response = tenant_fixture.client.get(
        "/api/v1/me/organizations", headers=tenant_fixture.headers("user-a")
    )
    assert response.status_code == 200
    assert response.json() == {"items": []}
