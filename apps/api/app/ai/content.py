"""Read projections only: private ownership and content authority are separate checks."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.models import AiDisclosure, AiRun, AiToolCall, ApprovalRequest
from app.ai.schemas import AiRunResponse, AiToolCallResponse, ApprovalResponse
from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.core.content_review import review_digest


def run_digest(run: AiRun) -> str:
    return review_digest(
        "ai_run",
        run.organization_id,
        run.id,
        run.version,
        {
            "status": run.status,
            "input": run.input_summary,
            "output": run.output,
            "references": run.references,
            "permissions": run.required_permissions,
        },
    )


def latest_disclosure(session: Session, run: AiRun) -> AiDisclosure | None:
    return session.scalar(
        select(AiDisclosure)
        .where(
            AiDisclosure.organization_id == run.organization_id,
            AiDisclosure.run_id == run.id,
            AiDisclosure.deleted_at.is_(None),
        )
        .order_by(AiDisclosure.revision.desc())
        .limit(1)
    )


def candidate_digest(row: AiDisclosure) -> str:
    return review_digest(
        "ai_disclosure",
        row.organization_id,
        row.id,
        row.revision,
        {
            "run_digest": row.run_digest,
            "candidate": row.candidate,
        },
    )


def is_released(row: AiDisclosure, run: AiRun) -> bool:
    return (
        row.status == "APPROVED"
        and row.run_digest == run_digest(run)
        and row.released_digest == candidate_digest(row)
    )


def project_run(
    context: RequestContext, run: AiRun, disclosure: AiDisclosure | None
) -> AiRunResponse:
    result = AiRunResponse.model_validate(run)
    if Permission.PROFIT_READ in context.permissions:
        return result
    released = disclosure.candidate if disclosure and is_released(disclosure, run) else None
    return result.model_copy(
        update={
            "input_summary": None,
            "output": {"artifact": released} if released else None,
            "references": [],
            "estimated_cost_usd": None,
            "content_protected": released is None,
            "released_disclosure_id": disclosure.id if released and disclosure else None,
            "released_disclosure_version": disclosure.version if released and disclosure else None,
        }
    )


def run_responses(
    session: Session, context: RequestContext, runs: list[AiRun]
) -> list[AiRunResponse]:
    disclosures = {}
    if runs and Permission.PROFIT_READ not in context.permissions:
        rows = session.scalars(
            select(AiDisclosure)
            .where(
                AiDisclosure.organization_id == context.organization_id,
                AiDisclosure.run_id.in_([run.id for run in runs]),
                AiDisclosure.deleted_at.is_(None),
            )
            .distinct(AiDisclosure.run_id)
            .order_by(AiDisclosure.run_id, AiDisclosure.revision.desc())
        )
        disclosures = {row.run_id: row for row in rows}
    return [project_run(context, run, disclosures.get(run.id)) for run in runs]


def run_response(session: Session, context: RequestContext, run: AiRun) -> AiRunResponse:
    return run_responses(session, context, [run])[0]


def call_response(context: RequestContext, row: AiToolCall) -> AiToolCallResponse:
    result = AiToolCallResponse.model_validate(row)
    if Permission.PROFIT_READ not in context.permissions:
        return result.model_copy(
            update={
                "argument_summary": None,
                "result_summary": None,
                "tool_name": row.tool_name
                if row.tool_name
                in {"read_order", "order_timeline", "order_profit", "search_companies"}
                else "restricted_tool",
            }
        )
    return result


def approval_response(context: RequestContext, row: ApprovalRequest) -> ApprovalResponse:
    result = ApprovalResponse.model_validate(row)
    if Permission.PROFIT_READ not in context.permissions:
        return result.model_copy(update={"proposed_action": None, "reason": None})
    return result
