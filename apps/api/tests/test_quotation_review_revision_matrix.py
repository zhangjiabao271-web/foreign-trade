from uuid import UUID

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import permissions_for_role
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership
from app.sales.enums import QuotationVersionStatus
from app.sales.models import QuotationVersion
from app.sales.services import QuotationCommandService
from sqlalchemy import select
from test_quotation_decision_roles import commercial_snapshots
from test_quotation_state_commands import context, counts, setup
from test_quotation_vertical_slice import post_ok

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration


@pytest.mark.parametrize("role", list(MembershipRole))
@pytest.mark.parametrize("state", list(QuotationVersionStatus))
@pytest.mark.parametrize("action", ("mark_customer_review", "revise"))
def test_review_revision_role_state_matrix(quotation_fixture, role, state, action):
    f = quotation_fixture
    quote_id, request = setup(f, "send")
    if state == QuotationVersionStatus.ACCEPTED:
        post_ok(f, f"/api/v1/quotations/{quote_id}/send", "quotation-manager")
        post_ok(f, f"/api/v1/quotations/{quote_id}/accept", "quotation-manager")
    else:
        # Guard isolation only: these state seeds never touch the live business database.
        with f.session_factory.begin() as session:
            session.get(QuotationVersion, request.expected_version_id).status = state
    with f.session_factory.begin() as session:
        member = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_a,
                OrganizationMembership.user_id == f.sales_user,
            )
        )
        member.role = role

    body = {"expected_version_id": str(request.expected_version_id)}
    if action == "mark_customer_review":
        body["reason"] = "Synthetic customer review evidence"
    path = "mark-customer-review" if action == "mark_customer_review" else "revisions"
    permitted = role in {MembershipRole.ADMIN, MembershipRole.MANAGER, MembershipRole.SALES}
    valid_state = state == "SENT" if action == "mark_customer_review" else state != "ACCEPTED"
    snapshots, before = commercial_snapshots(f), counts(f)
    response = f.client.post(
        f"/api/v1/quotations/{quote_id}/{path}",
        json=body,
        headers=f.headers("quotation-sales", f.organization_a) | {"Idempotency-Key": "matrix"},
    )
    if not permitted or not valid_state:
        expected_status = 403 if not permitted else 409
        expected_code = "PERMISSION_DENIED" if not permitted else "INVALID_STATE_TRANSITION"
        assert response.status_code == expected_status, response.text
        assert response.json()["code"] == expected_code
        with pytest.raises(ApiProblem) as denied:
            getattr(QuotationCommandService(f.session_factory), action)(
                context(f, permissions_for_role(role)), UUID(quote_id), body, key="service-matrix"
            )
        assert (denied.value.status, denied.value.code) == (expected_status, expected_code)
        assert commercial_snapshots(f) == snapshots
        assert counts(f) == before
        return

    assert response.status_code == (200 if action == "mark_customer_review" else 201), response.text
    assert counts(f) == tuple(value + 1 for value in before)
    with f.session_factory() as session:
        original = session.get(QuotationVersion, request.expected_version_id)
        assert original.updated_by == f.sales_user
        if action == "mark_customer_review":
            assert original.status == "CUSTOMER_REVIEW"
            assert response.json()["id"] == str(original.id)
        else:
            assert original.status == "SUPERSEDED"
            assert not original.is_current
            revised = session.get(QuotationVersion, UUID(response.json()["id"]))
            assert revised.status == "DRAFT" and revised.is_current
            assert revised.version_number == original.version_number + 1
            assert revised.quotation_id == original.quotation_id
    after, completed = counts(f), commercial_snapshots(f)
    replay = f.client.post(
        f"/api/v1/quotations/{quote_id}/{path}",
        json=body,
        headers=f.headers("quotation-sales", f.organization_a) | {"Idempotency-Key": "matrix"},
    )
    assert replay.status_code == response.status_code
    assert replay.json() == response.json()
    assert counts(f) == after
    assert commercial_snapshots(f) == completed
