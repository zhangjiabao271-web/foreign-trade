from uuid import UUID

import pytest
from app.ai.approvals import ApprovalService
from app.ai.disclosure import AiDisclosureService
from app.ai.models import AiDisclosure, AiRun
from app.ai.schemas import (
    AiApprovalRequest,
    AiDisclosureDecision,
    AiDisclosureRevision,
    AiDisclosureSubmit,
    AiRunCreate,
    ApprovalDecision,
)
from app.ai.services import AiCommandService, AiQueryService, get_run
from app.auth.errors import ApiProblem
from app.core.config import Settings
from sqlalchemy import select
from test_ai_copilot import prepare_approval
from test_ai_disclosure import SAFE
from test_ai_disclosure_atomicity import snapshot
from test_document_review import reviewer
from test_sales_foreign_commands import foreign_manager

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def test_all_ai_http_and_service_tenant_paths_preserve_private_facts(quotation_fixture):
    f = quotation_fixture
    order, approval = prepare_approval(f)  # Scripted provider; no paid or external call.
    foreign = foreign_manager(f)
    _, owner = reviewer(f)
    run_id, approval_id = UUID(approval["run_id"]), UUID(approval["id"])
    with f.session_factory() as session:
        run_version = session.get(AiRun, run_id).version
        disclosure_id = session.scalar(select(AiDisclosure.id).where(AiDisclosure.run_id == run_id))
    reviews = AiDisclosureService(f.session_factory)
    preview = reviews.inspect(owner, disclosure_id)
    create = AiRunCreate(intent="TASK_DRAFT", subject_id=UUID(order["id"]))
    submit = AiDisclosureSubmit(expected_version=run_version)
    request = AiApprovalRequest(expected_version=run_version, reason="Synthetic request")
    decide = ApprovalDecision(expected_version=approval["version"], reason="Synthetic decision")
    release = AiDisclosureDecision(
        expected_version=preview.version,
        content_digest=preview.content_digest,
        release=True,
        confirmed=True,
        reason="Synthetic content decision",
    )
    revise = AiDisclosureRevision(
        expected_version=preview.version,
        content_digest=preview.content_digest,
        candidate=SAFE,
    )
    headers = f.headers("quotation-other", f.organization_b)
    before = snapshot(f)
    paths = (
        f"runs/{run_id}",
        f"runs/{run_id}/tool-calls",
        f"approvals/{approval_id}",
        f"disclosures/{disclosure_id}",
        f"runs?cursor={run_id}",
        f"approvals?cursor={approval_id}",
        f"disclosures?cursor={disclosure_id}",
    )
    for path in paths:
        response = f.client.get(f"/api/v1/ai/{path}", headers=headers)
        assert response.status_code == 404, response.text
    for path in ("runs", "approvals", "disclosures"):
        response = f.client.get(f"/api/v1/ai/{path}", headers=headers)
        assert response.status_code == 200
        assert response.json() == {"items": [], "next_cursor": None, "has_more": False}
    for path, body in (
        ("runs", create),
        (f"runs/{run_id}/submit-disclosure", submit),
        (f"runs/{run_id}/request-approval", request),
        (f"approvals/{approval_id}/approve", decide),
        (f"approvals/{approval_id}/reject", decide),
        (f"disclosures/{disclosure_id}/decide", release),
        (f"disclosures/{disclosure_id}/revise", revise),
    ):
        response = f.client.post(
            f"/api/v1/ai/{path}",
            headers=headers | {"Idempotency-Key": "foreign-http"},
            json=body.model_dump(mode="json"),
        )
        assert response.status_code == 404, response.text
    approvals = ApprovalService(f.session_factory)
    calls = (
        lambda: AiCommandService(f.session_factory, Settings()).create(foreign, create, key="c"),
        lambda: reviews.submit(foreign, run_id, submit, key="s"),
        lambda: reviews.inspect(foreign, disclosure_id),
        lambda: reviews.change(foreign, disclosure_id, release, key="d"),
        lambda: reviews.change(foreign, disclosure_id, revise, key="r"),
        lambda: reviews.page(foreign, cursor=disclosure_id, limit=1),
        lambda: approvals.request(foreign, run_id, request),
        lambda: approvals.decide(foreign, approval_id, decide, approve=True),
        lambda: approvals.decide(foreign, approval_id, decide, approve=False),
    )
    for call in calls:
        with pytest.raises(ApiProblem) as denied:
            call()
        assert denied.value.status == 404
    with f.session_factory() as session:
        query = AiQueryService(session)
        for call in (
            lambda: query.get(foreign, run_id),
            lambda: query.calls(foreign, run_id),
            lambda: query.page(foreign, cursor=run_id, limit=1),
            lambda: approvals.get(session, foreign, approval_id),
            lambda: approvals.page(session, foreign, cursor=approval_id, limit=1),
            lambda: reviews.load(session, foreign, disclosure_id),
            lambda: get_run(session, foreign, run_id, lock=True, private=False),
        ):
            with pytest.raises(ApiProblem) as denied:
                call()
            assert denied.value.status == 404
        assert query.page(foreign, cursor=None, limit=1) == []
        assert approvals.page(session, foreign, cursor=None, limit=1) == []
    assert reviews.page(foreign, cursor=None, limit=1) == []
    assert snapshot(f) == before
