from uuid import UUID

import pytest
from app.ai.approvals import ApprovalService
from app.ai.schemas import ApprovalDecision
from app.auth.errors import ApiProblem
from app.identity.enums import MembershipRole
from test_ai_copilot import prepare_approval
from test_ai_disclosure_atomicity import snapshot
from test_document_review import reviewer

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


@pytest.mark.parametrize("role", list(MembershipRole))
@pytest.mark.parametrize("approve", [True, False])
def test_content_review_authority_does_not_grant_execution_decision(
    quotation_fixture, role, approve
):
    f = quotation_fixture
    order, approval = prepare_approval(f)
    subject, context = reviewer(f, role)
    body = ApprovalDecision(
        expected_version=approval["version"], reason="Synthetic independent execution decision"
    )
    action = "approve" if approve else "reject"
    path = f"/api/v1/ai/approvals/{approval['id']}/{action}"
    before = snapshot(f)
    response = f.client.post(
        path,
        headers=f.headers(subject, f.organization_a),
        json=body.model_dump(mode="json"),
    )
    service = ApprovalService(f.session_factory)
    # Policy expectation is independent of the application's permission lookup.
    if role not in {MembershipRole.ADMIN, MembershipRole.MANAGER}:
        assert response.status_code == 403
        with pytest.raises(ApiProblem) as denied:
            service.decide(context, UUID(approval["id"]), body, approve=approve)
        assert denied.value.status == 403
        assert snapshot(f) == before
        return

    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == ("APPROVED" if approve else "REJECTED")
    after = snapshot(f)
    for table in (
        "sales_orders",
        "sales_order_items",
        "ai_runs",
        "ai_tool_calls",
        "ai_disclosures",
    ):
        assert after[table] == before[table]
    assert len(after["tasks"]) == len(before["tasks"]) + int(approve)
    for table in ("activities", "audit_logs", "outbox_events"):
        assert len(after[table]) == len(before[table]) + (2 if approve else 1)
    if approve:
        task = next(row for row in after["tasks"] if str(row["id"]) == result["task_id"])
        assert task["subject_id"] == UUID(order["id"])
        assert task["assigned_to"] == context.user_id
        assert task["task_type"] == f"AI_FOLLOW_UP:{approval['id']}"
    else:
        assert result["task_id"] is None
    replay = service.decide(context, UUID(approval["id"]), body, approve=approve)
    assert replay.model_dump(mode="json") == result
    assert snapshot(f) == after
