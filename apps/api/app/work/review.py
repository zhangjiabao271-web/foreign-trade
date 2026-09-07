from copy import deepcopy
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.content_review import ContentReviewRequest, ContentReviewSnapshot
from app.core.unit_of_work import UnitOfWork
from app.platform.idempotency import begin_command, complete_command
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.work.activity_access import ActivitySubject, require_activity_subject
from app.work.content import content_digest, is_released
from app.work.models import Activity, Task
from app.work.services import require_order

WorkContentKind = Literal["task", "activity"]


class WorkReviewRequest(ContentReviewRequest):
    pass


class WorkReviewResponse(ContentReviewSnapshot):
    kind: WorkContentKind


def review_response(row: Task | Activity) -> WorkReviewResponse:
    return WorkReviewResponse(
        record_id=row.id,
        kind="task" if isinstance(row, Task) else "activity",
        version=row.version,
        content_digest=content_digest(row),
        text=row.title if isinstance(row, Task) else row.summary,
        details=deepcopy(row.details),
        released=is_released(row),
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
    )


def require_record(
    session: Session,
    context: RequestContext,
    order_id: UUID,
    kind: WorkContentKind,
    record_id: UUID,
    *,
    lock: bool = False,
    subject_type: ActivitySubject | Literal["sales_order"] = "sales_order",
) -> Task | Activity:
    context.require(Permission.PROFIT_READ)
    if kind == "task":
        context.require(Permission.TASK_READ)
    if subject_type == "sales_order":
        require_order(session, context, order_id, lock=lock)
    else:
        if kind != "activity":
            raise ApiProblem(404, "WORK_CONTENT_NOT_FOUND", "Not found", "Unsupported timeline.")
        require_activity_subject(session, context, subject_type, order_id, lock=lock)
    model = Task if kind == "task" else Activity
    query = select(model).where(
        model.organization_id == context.organization_id,
        model.id == record_id,
        model.subject_type == subject_type,
        model.subject_id == order_id,
        model.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update()
    row = session.scalar(query)
    if not isinstance(row, (Task, Activity)):
        raise ApiProblem(404, "WORK_CONTENT_NOT_FOUND", "Not found", "Work record not found.")
    return row


class WorkReviewService:
    def __init__(
        self,
        factory: sessionmaker[Session],
        *,
        audit: AuditRecorder | None = None,
        outbox: OutboxRecorder | None = None,
    ) -> None:
        self.factory = factory
        self.audit = audit or AuditRecorder()
        self.outbox = outbox or OutboxRecorder()

    def inspect(
        self, context: RequestContext, order_id: UUID, kind: WorkContentKind, record_id: UUID
    ) -> WorkReviewResponse:
        with self.factory() as session:
            return review_response(require_record(session, context, order_id, kind, record_id))

    def inspect_activity(
        self,
        context: RequestContext,
        subject_type: ActivitySubject,
        subject_id: UUID,
        record_id: UUID,
    ) -> WorkReviewResponse:
        with self.factory() as session:
            return review_response(
                require_record(
                    session, context, subject_id, "activity", record_id, subject_type=subject_type
                )
            )

    def decide_activity(
        self,
        context: RequestContext,
        subject_type: ActivitySubject,
        subject_id: UUID,
        record_id: UUID,
        request: WorkReviewRequest,
        *,
        key: str,
    ) -> WorkReviewResponse:
        return self._decide(
            context, subject_id, "activity", record_id, request, key=key, subject_type=subject_type
        )

    def decide(
        self,
        context: RequestContext,
        order_id: UUID,
        kind: WorkContentKind,
        record_id: UUID,
        request: WorkReviewRequest,
        *,
        key: str,
    ) -> WorkReviewResponse:
        return self._decide(context, order_id, kind, record_id, request, key=key)

    def _decide(
        self,
        context: RequestContext,
        order_id: UUID,
        kind: WorkContentKind,
        record_id: UUID,
        request: WorkReviewRequest,
        *,
        key: str,
        subject_type: ActivitySubject | Literal["sales_order"] = "sales_order",
    ) -> WorkReviewResponse:
        context.require(Permission.PROFIT_READ)
        if not request.confirmed:
            raise ApiProblem(
                422, "CONFIRMATION_REQUIRED", "Confirm review", "Confirm the decision."
            )
        with UnitOfWork(self.factory) as unit:
            session = unit.session
            command = begin_command(
                session,
                context,
                scope="work.content_review"
                if subject_type == "sales_order"
                else "work.activity_review",
                key=key,
                payload={
                    **(
                        {"order_id": order_id}
                        if subject_type == "sales_order"
                        else {"subject_type": subject_type, "subject_id": order_id}
                    ),
                    "kind": kind,
                    "record_id": record_id,
                    **request.model_dump(),
                },
            )
            row = require_record(
                session, context, order_id, kind, record_id, lock=True, subject_type=subject_type
            )
            if command.resource_id is not None:
                result = review_response(row)
                unit.commit()
                return result
            if (
                row.version != request.expected_version
                or content_digest(row) != request.content_digest
            ):
                raise ApiProblem(
                    409, "VERSION_CONFLICT", "Changed content", "Reload and review again."
                )
            previous = is_released(row)
            # SQLAlchemy increments the row version on this decision. Bind disclosure to that
            # exact resulting version so any later mutation invalidates it, even text restored back.
            row.released_digest = (
                content_digest(row, version=row.version + 1) if request.release else None
            )
            row.reviewed_by = context.user_id
            row.reviewed_at = datetime.now(UTC)
            row.updated_by = context.user_id
            details = {"record_id": str(row.id), "kind": kind, "released": request.release}
            action = "work.content_reviewed"
            session.add(
                Activity(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    subject_type=subject_type,
                    subject_id=order_id,
                    activity_type=action,
                    summary="Work content visibility reviewed",
                    details=details,
                    correlation_id=context.request_id,
                )
            )
            self.audit.record(
                session,
                context,
                action=action,
                target_type=kind,
                target_id=row.id,
                before={"released": previous},
                after={**details, "reviewed_content_digest": request.content_digest},
                reason=request.reason,
            )
            self.outbox.record(session, context, DomainEvent(f"{action}.v1", kind, row.id, details))
            complete_command(command, row.id, kind)
            session.flush()
            result = review_response(row)
            unit.commit()
            return result
