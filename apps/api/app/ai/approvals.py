from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session, sessionmaker

from app.ai.content import approval_response, is_released, latest_disclosure
from app.ai.models import ApprovalRequest
from app.ai.schemas import AiApprovalRequest, AiArtifact, ApprovalDecision, ApprovalResponse
from app.ai.services import get_run, record_ai_event
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.unit_of_work import UnitOfWork
from app.work.approved_tasks import create_approved_follow_up, lock_open_order


def approval_not_found() -> ApiProblem:
    return ApiProblem(404, "AI_APPROVAL_NOT_FOUND", "Approval not found", "Approval not found.")


class ApprovalService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def page(
        self, session: Session, context: RequestContext, *, cursor: UUID | None, limit: int
    ) -> list[ApprovalResponse]:
        context.require(
            Permission.AI_READ, Permission.AI_RUN, Permission.ORDER_READ, Permission.TASK_WRITE
        )
        query = select(ApprovalRequest).where(
            ApprovalRequest.organization_id == context.organization_id,
            ApprovalRequest.deleted_at.is_(None),
        )
        if Permission.AI_APPROVE not in context.permissions:
            query = query.where(ApprovalRequest.created_by == context.user_id)
        if cursor:
            anchor = self.get(session, context, cursor)
            query = query.where(
                tuple_(ApprovalRequest.created_at, ApprovalRequest.id)
                < (anchor.created_at, anchor.id)
            )
        rows = list(
            session.scalars(
                query.order_by(ApprovalRequest.created_at.desc(), ApprovalRequest.id.desc()).limit(
                    limit + 1
                )
            )
        )
        return [approval_response(context, row) for row in rows]

    def request(
        self, context: RequestContext, run_id: UUID, request: AiApprovalRequest
    ) -> ApprovalResponse:
        context.require(Permission.AI_RUN, Permission.TASK_WRITE)
        with UnitOfWork(self.factory) as unit:
            session = unit.session
            run = get_run(session, context, run_id, lock=True)
            existing = session.scalar(
                select(ApprovalRequest).where(
                    ApprovalRequest.organization_id == context.organization_id,
                    ApprovalRequest.run_id == run_id,
                )
            )
            if existing:
                unit.commit()
                return approval_response(context, existing)
            if run.version != request.expected_version:
                raise ApiProblem(409, "VERSION_CONFLICT", "Version conflict", "Reload the draft.")
            if (
                run.status != "SUCCEEDED"
                or run.intent != "TASK_DRAFT"
                or not run.output
                or not run.subject_id
            ):
                raise ApiProblem(
                    409,
                    "AI_DRAFT_REQUIRED",
                    "Draft required",
                    "A successful task draft is required.",
                )
            candidate = run.output.get("artifact")
            if Permission.PROFIT_READ not in context.permissions:
                disclosure = latest_disclosure(session, run)
                if disclosure is None or not is_released(disclosure, run):
                    raise ApiProblem(
                        409,
                        "AI_CONTENT_REVIEW_REQUIRED",
                        "Content review required",
                        "Submit the draft for content review first.",
                    )
                if (
                    request.disclosure_id != disclosure.id
                    or request.disclosure_version != disclosure.version
                ):
                    raise ApiProblem(
                        409,
                        "VERSION_CONFLICT",
                        "Changed candidate",
                        "Reload the released draft before requesting execution.",
                    )
                candidate = disclosure.candidate
            artifact = AiArtifact.model_validate(candidate)
            if not artifact.task_title or not artifact.task_title.strip():
                raise ApiProblem(
                    409, "AI_DRAFT_REQUIRED", "Draft required", "A task title is required."
                )
            approval = ApprovalRequest(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                run_id=run.id,
                proposed_action={
                    "type": "CREATE_ORDER_FOLLOW_UP",
                    "order_id": str(run.subject_id),
                    "title": artifact.task_title,
                    "assigned_to": "approving_user",
                },
            )
            session.add(approval)
            session.flush()
            record_ai_event(
                session,
                context,
                target_id=run.id,
                action="ai.approval_requested",
                details={"approval_id": str(approval.id)},
                reason=request.reason,
            )
            unit.commit()
            return approval_response(context, approval)

    def get(self, session: Session, context: RequestContext, approval_id: UUID) -> ApprovalResponse:
        return approval_response(context, self.get_record(session, context, approval_id))

    def get_record(
        self, session: Session, context: RequestContext, approval_id: UUID
    ) -> ApprovalRequest:
        context.require(Permission.AI_READ)
        approval = session.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.organization_id == context.organization_id,
                ApprovalRequest.id == approval_id,
                ApprovalRequest.deleted_at.is_(None),
            )
        )
        if approval is None:
            raise approval_not_found()
        if approval.created_by != context.user_id:
            context.require(Permission.AI_APPROVE)
        get_run(session, context, approval.run_id, private=False)
        return approval

    def decide(
        self,
        context: RequestContext,
        approval_id: UUID,
        request: ApprovalDecision,
        *,
        approve: bool,
    ) -> ApprovalResponse:
        context.require(Permission.AI_APPROVE, Permission.TASK_WRITE)
        with self.factory() as session:
            snapshot = self.get_record(session, context, approval_id)
            order_id = UUID(str(snapshot.proposed_action["order_id"]))
        with UnitOfWork(self.factory) as unit:
            session = unit.session
            # Serialize with order completion before taking the approval row lock.
            if approve and snapshot.status == "PENDING":
                lock_open_order(session, context, order_id)
            approval = session.scalar(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.organization_id == context.organization_id,
                    ApprovalRequest.id == approval_id,
                )
                .with_for_update()
            )
            if approval is None:
                raise approval_not_found()
            get_run(session, context, approval.run_id, private=False)
            target_status = "APPROVED" if approve else "REJECTED"
            if approval.status == target_status:
                unit.commit()
                return approval_response(context, approval)
            if approval.status != "PENDING" or approval.version != request.expected_version:
                raise ApiProblem(
                    409, "VERSION_CONFLICT", "Decision conflict", "Reload the approval request."
                )
            if approve:
                task = create_approved_follow_up(
                    session,
                    context,
                    order_id=order_id,
                    approval_id=approval.id,
                    title=str(approval.proposed_action["title"]),
                    reason=request.reason,
                )
                approval.task_id = task.id
            approval.status = target_status
            approval.decided_by = context.user_id
            approval.updated_by = context.user_id
            approval.decided_at = datetime.now(UTC)
            approval.reason = request.reason
            record_ai_event(
                session,
                context,
                target_id=approval.run_id,
                action="ai.approval_decided",
                details={
                    "approval_id": str(approval.id),
                    "status": target_status,
                    "task_id": str(approval.task_id) if approval.task_id else None,
                },
                reason=request.reason,
            )
            session.flush()
            unit.commit()
            return approval_response(context, approval)
