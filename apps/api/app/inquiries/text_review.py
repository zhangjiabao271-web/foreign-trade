from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.content_review import ContentReviewRequest, ContentReviewSnapshot
from app.core.unit_of_work import UnitOfWork
from app.inquiries.content import content_digest, is_released
from app.inquiries.models import Inquiry
from app.platform.idempotency import begin_command, complete_command
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.work.records import record_activity


class InquiryTextReviewRequest(ContentReviewRequest):
    pass


class InquiryTextReviewResponse(ContentReviewSnapshot):
    pass


def require_record(
    session: Session,
    context: RequestContext,
    record_id: UUID,
    *,
    lock: bool = False,
) -> Inquiry:
    context.require(Permission.PROFIT_READ)
    context.require(Permission.INQUIRY_READ)
    query = select(Inquiry).where(
        Inquiry.organization_id == context.organization_id,
        Inquiry.id == record_id,
        Inquiry.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update()
    row = session.scalar(query)
    if not isinstance(row, Inquiry):
        raise ApiProblem(404, "INQUIRY_TEXT_NOT_FOUND", "Not found", "Inquiry record not found.")
    return row


def snapshot(row: Inquiry) -> InquiryTextReviewResponse:
    return InquiryTextReviewResponse(
        record_id=row.id,
        version=row.version,
        content_digest=content_digest(row),
        text="询盘说明",
        details={"description": row.description},
        released=is_released(row),
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
    )


class InquiryTextReviewService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def inspect(self, context: RequestContext, record_id: UUID) -> InquiryTextReviewResponse:
        with self.factory() as session:
            return snapshot(require_record(session, context, record_id))

    def decide(
        self,
        context: RequestContext,
        record_id: UUID,
        request: InquiryTextReviewRequest,
        *,
        key: str,
    ) -> InquiryTextReviewResponse:
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
                scope="inquiry.text_review",
                key=key,
                payload={"record_id": record_id, **request.model_dump()},
            )
            row = require_record(session, context, record_id, lock=True)
            if command.resource_id is not None:
                result = snapshot(row)
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
            row.released_digest = (
                content_digest(row, version=row.version + 1) if request.release else None
            )
            row.reviewed_by = context.user_id
            row.reviewed_at = datetime.now(UTC)
            row.updated_by = context.user_id
            details = {"record_id": str(row.id), "released": request.release}
            action = "inquiry.text_reviewed"
            subject = "inquiry"
            record_activity(
                session,
                context,
                subject_type=subject,
                subject_id=row.id,
                activity_type=action,
                summary="Inquiry text visibility reviewed",
                details=details,
            )
            AuditRecorder().record(
                session,
                context,
                action=action,
                target_type=subject,
                target_id=row.id,
                before={"released": previous},
                after={**details, "reviewed_content_digest": request.content_digest},
                reason=request.reason,
            )
            OutboxRecorder().record(
                session, context, DomainEvent(f"{action}.v1", subject, row.id, details)
            )
            complete_command(command, row.id, subject)
            session.flush()
            result = snapshot(row)
            unit.commit()
            return result
