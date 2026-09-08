from datetime import UTC, datetime

import pytest
from app.auth.errors import ApiProblem
from app.identity.administration_service import AdministrationService
from app.identity.models import OrganizationMembership, User
from sqlalchemy import select
from test_identity_administration import body, command_body, counts

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice", "test_identity_administration")


@pytest.mark.parametrize("action", ["disabled", "role_changed"])
@pytest.mark.parametrize(
    "ineligible", ["member_disabled", "member_deleted", "user_disabled", "user_deleted"]
)
def test_ineligible_second_admin_cannot_bypass_last_admin_guard(admin, action, ineligible):
    f, context, member_id = admin
    service = AdministrationService(f.session_factory)
    second_id = service.add_member(context, body(role="ADMIN"), key="second-admin")
    with f.session_factory.begin() as session:
        second = session.get(OrganizationMembership, second_id)
        user = session.get(User, second.user_id)
        if ineligible == "member_disabled":
            second.status = "DISABLED"
        elif ineligible == "member_deleted":
            second.deleted_at = datetime.now(UTC)
        elif ineligible == "user_disabled":
            user.status = "DISABLED"
        else:
            user.deleted_at = datetime.now(UTC)
    before = counts(f)
    with f.session_factory() as session:
        original = dict(
            session.execute(
                select(OrganizationMembership.__table__).where(
                    OrganizationMembership.id == member_id
                )
            )
            .mappings()
            .one()
        )
    data = command_body(role="VIEWER") if action == "role_changed" else command_body()
    with pytest.raises(ApiProblem) as error:
        service.change_member(context, member_id, data, action=action, key="last-admin-attempt")
    assert error.value.code == "LAST_ADMINISTRATOR"
    assert counts(f) == before
    with f.session_factory() as session:
        current = dict(
            session.execute(
                select(OrganizationMembership.__table__).where(
                    OrganizationMembership.id == member_id
                )
            )
            .mappings()
            .one()
        )
    assert current == original
