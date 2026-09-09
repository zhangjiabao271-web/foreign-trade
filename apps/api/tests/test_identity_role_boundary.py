from dataclasses import replace

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import permissions_for_role
from app.identity.administration_queries import AdministrationQuery
from app.identity.administration_service import AdministrationService
from app.identity.enums import MembershipRole
from app.identity.models import Organization, OrganizationMembership, User
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.work.models import Activity
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_identity_administration import body, command_body

pytest_plugins = ("test_quotation_vertical_slice", "test_identity_administration")
pytestmark = pytest.mark.integration


def snapshot(f):
    with f.session_factory() as session:
        return {
            model.__tablename__: list(session.execute(select(model.__table__).order_by(model.id)))
            for model in (
                Organization,
                User,
                OrganizationMembership,
                Activity,
                AuditLog,
                OutboxEvent,
                IdempotencyKey,
            )
        }


@pytest.mark.parametrize("role", [role for role in MembershipRole if role != MembershipRole.ADMIN])
def test_non_admin_roles_cannot_use_any_administration_entry_or_stale_authority(admin, role):
    f, previous_admin, admin_member_id = admin
    service = AdministrationService(f.session_factory)
    target = service.add_member(previous_admin, body(), key="seed-target")
    with f.session_factory.begin() as session:
        # Isolate loss of authority; not a user command bypassing last-admin protection.
        session.get(OrganizationMembership, admin_member_id).role = role
    current = replace(previous_admin, permissions=permissions_for_role(role))
    h = f.headers("identity-admin", f.organization_a) | {"Idempotency-Key": "forbidden"}
    member_path = f"/api/v1/organization/members/{target}"
    settings = command_body(name="Forbidden change", timezone="UTC")
    new_member = body(external_subject="forbidden-new-identity")
    requests = (
        ("GET", "/api/v1/organization", None),
        ("GET", "/api/v1/organization/members", None),
        ("GET", member_path, None),
        ("POST", "/api/v1/organization/update", settings),
        ("POST", "/api/v1/organization/members", new_member),
        ("POST", member_path + "/change-role", command_body(role="ADMIN")),
        ("POST", member_path + "/disable", command_body()),
        ("POST", member_path + "/reactivate", command_body()),
    )
    before = snapshot(f)
    for method, path, data in requests:
        response = f.client.request(method, path, headers=h, **({"json": data} if data else {}))
        assert response.status_code == 403
        assert response.json()["code"] == "PERMISSION_DENIED"
        assert snapshot(f) == before

    for context in (current, previous_admin):
        commands = (
            lambda context=context: service.update_organization(
                context, settings, key="denied-settings"
            ),
            lambda context=context: service.add_member(context, new_member, key="denied-member"),
            lambda context=context: service.change_member(
                context,
                target,
                command_body(role="ADMIN"),
                action="role_changed",
                key="denied-role",
            ),
            lambda context=context: service.change_member(
                context, target, command_body(), action="disabled", key="denied-disable"
            ),
            lambda context=context: service.change_member(
                context, target, command_body(), action="reactivated", key="denied-reactivate"
            ),
        )
        for command in commands:
            with pytest.raises(ApiProblem) as denied:
                command()
            assert denied.value.code == "PERMISSION_DENIED"
            assert snapshot(f) == before

    with Session() as session:
        query = AdministrationQuery(session)
        for read in (
            lambda: query.organization(current),
            lambda: query.members(current),
            lambda: query.member(current, target),
        ):
            with pytest.raises(ApiProblem) as denied:
                read()
            assert denied.value.code == "PERMISSION_DENIED"
            assert not session.in_transaction()
