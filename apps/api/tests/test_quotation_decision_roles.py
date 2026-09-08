from uuid import UUID

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import permissions_for_role
from app.crm.models import Opportunity
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership
from app.sales.models import Quotation, QuotationItem, QuotationVersion
from app.sales.services import QuotationCommandService
from sqlalchemy import select
from test_quotation_state_commands import ACTIONS, context, counts, invoke, setup

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration


def commercial_snapshots(f):
    with f.session_factory() as session:
        return tuple(
            list(session.execute(select(model.__table__).order_by(model.id)).mappings())
            for model in (Quotation, QuotationVersion, QuotationItem, Opportunity)
        )


@pytest.mark.parametrize("role", list(MembershipRole))
@pytest.mark.parametrize("action", ACTIONS)
def test_all_six_decision_commands_enforce_each_role_and_preserve_denied_facts(
    quotation_fixture, role, action
):
    f = quotation_fixture
    quote_id, request = setup(f, action)
    with f.session_factory.begin() as session:
        member = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_a,
                OrganizationMembership.user_id == f.sales_user,
            )
        )
        member.role = role

    permitted = role in {MembershipRole.ADMIN, MembershipRole.MANAGER} or (
        role == MembershipRole.SALES and action != "approve"
    )
    before = counts(f)
    snapshots = commercial_snapshots(f)
    body = request.model_dump(mode="json")
    response = invoke(f, quote_id, action, body, subject="quotation-sales")
    if not permitted:
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "PERMISSION_DENIED"
        with pytest.raises(ApiProblem) as denied:
            getattr(QuotationCommandService(f.session_factory), action)(
                context(f, permissions_for_role(role)), UUID(quote_id), request, key="denied"
            )
        assert denied.value.status == 403
        assert commercial_snapshots(f) == snapshots
        assert counts(f) == before
        return

    assert response.status_code == 200, response.text
    expected = {
        "submit": "INTERNAL_REVIEW",
        "approve": "INTERNAL_REVIEW",
        "send": "SENT",
        "accept": "ACCEPTED",
        "reject": "REJECTED",
        "expire": "EXPIRED",
    }[action]
    assert response.json()["status"] == expected
    with f.session_factory() as session:
        version = session.get(QuotationVersion, request.expected_version_id)
        assert version.status == expected
        assert version.updated_by == f.sales_user
    after = counts(f)
    increment = 2 if action == "accept" else 1
    assert after == (*(value + increment for value in before[:3]), before[3] + 1)
    replay_snapshots = commercial_snapshots(f)
    replay = invoke(f, quote_id, action, body, subject="quotation-sales")
    assert replay.status_code == 200
    assert replay.json() == response.json()
    assert commercial_snapshots(f) == replay_snapshots
    assert counts(f) == after
