from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from alembic import command
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.identity.administration_service import AdministrationService
from app.identity.models import Organization, OrganizationMembership, User
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.work.models import Activity
from sqlalchemy import event, func, select
from test_migrations import alembic_config

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


@pytest.fixture
def admin(quotation_fixture):
    f = quotation_fixture
    with f.session_factory.begin() as session:
        user = User(external_subject="identity-admin", display_name="Administrator")
        session.add(user)
        session.flush()
        member = OrganizationMembership(
            organization_id=f.organization_a, user_id=user.id, role="ADMIN", status="ACTIVE"
        )
        session.add(member)
        session.flush()
        context = RequestContext(user.id, f.organization_a, frozenset(Permission), uuid4())
        return f, context, member.id


def body(**overrides):
    return {
        "external_subject": "verified-existing-logto-subject",
        "display_name": "Verified User",
        "role": "VIEWER",
        "reason": "Verified identity and access",
        **overrides,
    }


def command_body(version=1, **overrides):
    return {"expected_version": version, "reason": "Reviewed access change", **overrides}


def counts(f):
    with f.session_factory() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (
                User,
                OrganizationMembership,
                Activity,
                AuditLog,
                OutboxEvent,
                IdempotencyKey,
            )
        )


def test_admin_api_membership_lifecycle_and_revocation(admin):
    f, context, _ = admin
    headers = {**f.headers("identity-admin", f.organization_a), "Idempotency-Key": "add-once"}
    response = f.client.post("/api/v1/organization/members", headers=headers, json=body())
    assert response.status_code == 201, response.text
    member_id = response.json()["id"]
    before = counts(f)
    assert (
        f.client.post("/api/v1/organization/members", headers=headers, json=body()).json()
        == response.json()
    )
    assert counts(f) == before
    service = AdministrationService(f.session_factory)
    service.change_member(
        context, UUID(member_id), command_body(role="SALES"), action="role_changed", key="role"
    )
    service.change_member(
        context, UUID(member_id), command_body(2), action="disabled", key="disable"
    )
    denied = f.client.get(
        "/api/v1/me/context", headers=f.headers(body()["external_subject"], f.organization_a)
    )
    assert denied.status_code == 403
    service.change_member(
        context, UUID(member_id), command_body(3), action="reactivated", key="reactivate"
    )
    assert (
        f.client.get(
            "/api/v1/me/context", headers=f.headers(body()["external_subject"], f.organization_a)
        ).status_code
        == 200
    )


def test_last_admin_and_stale_context(admin):
    f, context, member_id = admin
    service = AdministrationService(f.session_factory)
    for action, data in (
        ("disabled", command_body()),
        ("role_changed", command_body(role="VIEWER")),
    ):
        with pytest.raises(ApiProblem) as error:
            service.change_member(context, member_id, data, action=action, key=str(uuid4()))
        assert error.value.code == "LAST_ADMINISTRATOR"
    service.add_member(context, body(role="ADMIN"), key="second")
    service.change_member(
        context, member_id, command_body(role="VIEWER"), action="role_changed", key="self-demote"
    )
    with pytest.raises(ApiProblem) as error:
        service.add_member(context, body(external_subject="cannot-add"), key="stale")
    assert error.value.status == 403


def test_competing_admin_demotions_keep_one_administrator(admin):
    f, first, first_id = admin
    service = AdministrationService(f.session_factory)
    second_id = service.add_member(first, body(role="ADMIN"), key="second")
    with f.session_factory() as session:
        second_user = session.get(OrganizationMembership, second_id).user_id
    second = RequestContext(second_user, first.organization_id, frozenset(Permission), uuid4())

    def run(pair):
        context, target = pair
        try:
            return service.change_member(
                context,
                target,
                command_body(role="VIEWER"),
                action="role_changed",
                key=str(uuid4()),
            )
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, [(first, second_id), (second, first_id)]))
    assert sum(isinstance(result, UUID) for result in results) == 1
    assert "PERMISSION_DENIED" in results


def test_existing_global_user_is_preserved_and_tenant_cursor_rejected(admin):
    f, context, _ = admin
    service = AdministrationService(f.session_factory)
    with f.session_factory() as session:
        existing = session.scalar(select(User).where(User.external_subject == "quotation-other"))
        original_name = existing.display_name
        foreign_id = session.scalar(
            select(OrganizationMembership.id).where(
                OrganizationMembership.organization_id == f.organization_b
            )
        )
    service.add_member(
        context,
        body(external_subject="quotation-other", display_name="Do not overwrite"),
        key="existing",
    )
    with f.session_factory() as session:
        assert (
            session.scalar(
                select(User.display_name).where(User.external_subject == "quotation-other")
            )
            == original_name
        )
    headers = f.headers("identity-admin", f.organization_a)
    for path in (f"/members/{foreign_id}", f"/members?cursor={foreign_id}"):
        assert f.client.get("/api/v1/organization" + path, headers=headers).status_code == 404
    assert (
        f.client.get(
            "/api/v1/organization/members", headers=f.headers("quotation-sales", f.organization_a)
        ).status_code
        == 403
    )


@pytest.mark.parametrize("operation", ["create", "settings", "role", "disable", "reactivate"])
@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
def test_every_evidence_failure_rolls_back(admin, operation, table):
    f, context, _ = admin
    service = AdministrationService(f.session_factory)
    target = (
        service.add_member(context, body(), key="setup")
        if operation in {"role", "disable", "reactivate"}
        else None
    )
    if operation == "reactivate":
        service.change_member(
            context, target, command_body(), action="disabled", key="setup-disable"
        )
    before = counts(f)

    def fail(conn, cursor, statement, parameters, execution_context, executemany):
        if statement.startswith(f"INSERT INTO {table}"):
            raise RuntimeError("Injected identity evidence failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="Injected identity evidence failure"):
            if operation == "create":
                service.add_member(context, body(), key="failing")
            elif operation == "settings":
                service.update_organization(
                    context, command_body(name="Changed", timezone="UTC"), key="failing"
                )
            else:
                action = {
                    "role": "role_changed",
                    "disable": "disabled",
                    "reactivate": "reactivated",
                }[operation]
                data = command_body(2 if operation == "reactivate" else 1)
                if operation == "role":
                    data["role"] = "MANAGER"
                service.change_member(context, target, data, action=action, key="failing")
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert counts(f) == before
    with f.session_factory() as session:
        if target:
            member = session.get(OrganizationMembership, target)
            assert member.role == "VIEWER"
            assert member.status == ("DISABLED" if operation == "reactivate" else "ACTIVE")
        else:
            assert session.get(Organization, f.organization_a).name == "Sales Organization A"


def test_settings_versions_replay_and_invalid_input(admin):
    f, context, _ = admin
    headers = {**f.headers("identity-admin", f.organization_a), "Idempotency-Key": "settings-once"}
    data = command_body(name="Reviewed Organization", timezone="Europe/Paris")
    response = f.client.post("/api/v1/organization/update", headers=headers, json=data)
    assert response.status_code == 200, response.text
    before = counts(f)
    assert (
        f.client.post("/api/v1/organization/update", headers=headers, json=data).json()
        == response.json()
    )
    assert counts(f) == before
    current = f.client.get("/api/v1/organization", headers=headers).json()
    assert current["version"] == 2 and current["timezone"] == "Europe/Paris"
    headers["Idempotency-Key"] = "new-settings-key"
    assert (
        f.client.post("/api/v1/organization/update", headers=headers, json=data).status_code == 409
    )
    for changes in ({"timezone": "Not/A_Timezone"}, {"status": "DISABLED"}, {"name": " "}):
        assert (
            f.client.post(
                "/api/v1/organization/update", headers=headers, json={**data, **changes}
            ).status_code
            == 422
        )
    assert counts(f) == before


def test_membership_page_cursor_and_foreign_command(admin):
    f, context, _ = admin
    headers = {
        **f.headers("identity-admin", f.organization_a),
        "Idempotency-Key": "foreign-command",
    }
    page = f.client.get("/api/v1/organization/members?limit=2", headers=headers).json()
    assert page["has_more"] and len(page["items"]) == 2
    following = f.client.get(
        f"/api/v1/organization/members?limit=2&cursor={page['next_cursor']}", headers=headers
    ).json()
    assert not {row["id"] for row in page["items"]} & {row["id"] for row in following["items"]}
    with f.session_factory() as session:
        foreign = session.scalar(
            select(OrganizationMembership.id).where(
                OrganizationMembership.organization_id == f.organization_b
            )
        )
    before = counts(f)
    for action in ("disable", "reactivate", "change-role"):
        data = command_body(role="ADMIN") if action == "change-role" else command_body()
        response = f.client.post(
            f"/api/v1/organization/members/{foreign}/{action}", headers=headers, json=data
        )
        assert response.status_code == 404
    assert counts(f) == before


@pytest.mark.parametrize("deleted", [False, True])
def test_global_disabled_or_deleted_identity_cannot_be_granted_or_reactivated(admin, deleted):
    from datetime import UTC, datetime

    f, context, _ = admin
    service = AdministrationService(f.session_factory)
    target = service.add_member(context, body(), key="setup")
    service.change_member(context, target, command_body(), action="disabled", key="disable")
    with f.session_factory.begin() as session:
        user = session.scalar(
            select(User).where(User.external_subject == body()["external_subject"])
        )
        if deleted:
            user.deleted_at = datetime.now(UTC)
        else:
            user.status = "DISABLED"
    before = counts(f)
    for operation in ("add", "reactivate"):
        with pytest.raises(ApiProblem) as error:
            if operation == "add":
                service.add_member(context, body(), key="forbidden-add")
            else:
                service.change_member(
                    context,
                    target,
                    command_body(2),
                    action="reactivated",
                    key="forbidden-reactivate",
                )
        assert error.value.code == "IDENTITY_UNAVAILABLE"
    assert counts(f) == before


def test_0020_identity_records_survive_index_upgrade_and_downgrade(admin):
    f, context, member_id = admin
    config = alembic_config(f.engine.url.render_as_string(hide_password=False))
    before = counts(f)
    command.downgrade(config, "20260906_0020")
    command.upgrade(config, "head")
    command.check(config)
    assert counts(f) == before
    with f.session_factory() as session:
        assert session.get(OrganizationMembership, member_id).role == "ADMIN"
