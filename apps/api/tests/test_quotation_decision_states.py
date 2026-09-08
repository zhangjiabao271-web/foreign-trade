import pytest
from app.sales.enums import QuotationVersionStatus
from app.sales.models import QuotationVersion
from test_quotation_decision_roles import commercial_snapshots
from test_quotation_state_commands import ACTIONS, counts, invoke, setup
from test_quotation_vertical_slice import post_ok, state_request

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration

ALLOWED_STATES = {
    "submit": {"DRAFT"},
    "approve": {"INTERNAL_REVIEW"},
    "send": {"INTERNAL_REVIEW"},
    "accept": {"SENT", "CUSTOMER_REVIEW", "ACCEPTED"},
    "reject": {"SENT", "CUSTOMER_REVIEW"},
    "expire": {"DRAFT", "INTERNAL_REVIEW", "SENT", "CUSTOMER_REVIEW"},
}
TARGETS = {
    "submit": "INTERNAL_REVIEW",
    "approve": "INTERNAL_REVIEW",
    "send": "SENT",
    "accept": "ACCEPTED",
    "reject": "REJECTED",
    "expire": "EXPIRED",
}


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("state", list(QuotationVersionStatus))
def test_decision_state_matrix_preserves_rejected_facts(quotation_fixture, action, state):
    f = quotation_fixture
    quote_id, request = setup(f, "send")
    if state == QuotationVersionStatus.ACCEPTED:
        # Build a coherent accepted pointer and won opportunity through real commands.
        post_ok(f, f"/api/v1/quotations/{quote_id}/send", "quotation-manager")
        post_ok(f, f"/api/v1/quotations/{quote_id}/accept", "quotation-manager")
    else:
        # Disposable-only state preparation isolates each transition guard.
        with f.session_factory.begin() as session:
            session.get(QuotationVersion, request.expected_version_id).status = state
    request = state_request(f, quote_id)
    before = counts(f)
    snapshots = commercial_snapshots(f)
    response = invoke(f, quote_id, action, request.model_dump(mode="json"), key="state-matrix")
    if state not in ALLOWED_STATES[action]:
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "INVALID_STATE_TRANSITION"
        assert commercial_snapshots(f) == snapshots
        assert counts(f) == before
        return

    assert response.status_code == 200, response.text
    assert response.json()["status"] == TARGETS[action]
    with f.session_factory() as session:
        assert session.get(QuotationVersion, request.expected_version_id).status == TARGETS[action]
    no_op = action == "approve" or (action == "accept" and state == "ACCEPTED")
    increment = 0 if no_op else (2 if action == "accept" else 1)
    assert counts(f) == (*(value + increment for value in before[:3]), before[3] + 1)
    if no_op:
        assert commercial_snapshots(f) == snapshots


def test_unapproved_review_cannot_be_sent(quotation_fixture):
    f = quotation_fixture
    quote_id, request = setup(f, "approve")
    snapshots, before = commercial_snapshots(f), counts(f)
    response = invoke(f, quote_id, "send", request.model_dump(mode="json"))
    assert response.status_code == 409
    assert response.json()["code"] == "INVALID_STATE_TRANSITION"
    assert commercial_snapshots(f) == snapshots
    assert counts(f) == before
