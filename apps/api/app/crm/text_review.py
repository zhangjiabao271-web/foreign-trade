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
from app.crm.content import content_digest, is_released, text_fields
from app.crm.models import Lead, Opportunity
from app.platform.idempotency import begin_command, complete_command
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.work.models import Activity

CrmTextKind = Literal["lead", "opportunity"]


class CrmTextReviewRequest(ContentReviewRequest):
    pass


class CrmTextReviewResponse(ContentReviewSnapshot):
    kind: CrmTextKind


def require_record(
    session: Session,
    context: RequestContext,
    kind: CrmTextKind,
    record_id: UUID,
    *,
    lock: bool = False,
) -> Lead | Opportunity:
    context.require(Permission.PROFIT_READ)
    if kind == "lead":
        context.require(Permission.LEAD_READ)
        model: type[Lead] | type[Opportunity] = Lead
    elif kind == "opportunity":
        context.require(Permission.OPPORTUNITY_READ)
        model = Opportunity
    else:
        raise ApiProblem(404, "CRM_TEXT_NOT_FOUND", "Not found", "Unsupported CRM record.")
    query = select(model).where(
        model.organization_id == context.organization_id,
        model.id == record_id,
        model.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update()
    row = session.scalar(query)
    if not isinstance(row, (Lead, Opportunity)):
        raise ApiProblem(404, "CRM_TEXT_NOT_FOUND", "Not found", "CRM record not found.")
    return row


def snapshot(row: Lead | Opportunity) -> CrmTextReviewResponse:
    return CrmTextReviewResponse(
        record_id=row.id,
        kind="lead" if isinstance(row, Lead) else "opportunity",
        version=row.version,
        content_digest=content_digest(row),
        text="线索备注及来源说明" if isinstance(row, Lead) else "商机丢单原因",
        details=text_fields(row),
        released=is_released(row),
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
    )


class CrmTextReviewService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def inspect(
        self, context: RequestContext, kind: CrmTextKind, record_id: UUID
    ) -> CrmTextReviewResponse:
        with self.factory() as session:
            return snapshot(require_record(session, context, kind, record_id))

    def decide(
        self,
        context: RequestContext,
        kind: CrmTextKind,
        record_id: UUID,
        request: CrmTextReviewRequest,
        *,
        key: str,
    ) -> CrmTextReviewResponse:
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
                scope="crm.text_review",
                key=key,
                payload={"kind": kind, "record_id": record_id, **request.model_dump()},
            )
            row = require_record(session, context, kind, record_id, lock=True)
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
            action = "crm.text_reviewed"
            session.add(
                Activity(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    subject_type=kind,
                    subject_id=row.id,
                    activity_type=action,
                    summary="CRM text visibility reviewed",
                    details=details,
                    correlation_id=context.request_id,
                )
            )
            AuditRecorder().record(
                session,
                context,
                action=action,
                target_type=kind,
                target_id=row.id,
                before={"released": previous},
                after={**details, "reviewed_content_digest": request.content_digest},
                reason=request.reason,
            )
            OutboxRecorder().record(
                session, context, DomainEvent(f"{action}.v1", kind, row.id, details)
            )
            complete_command(command, row.id, kind)
            session.flush()
            result = snapshot(row)
            unit.commit()
            return result
