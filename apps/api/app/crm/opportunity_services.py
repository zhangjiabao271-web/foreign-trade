from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.unit_of_work import UnitOfWork
from app.crm.content import opportunity_response
from app.crm.enums import OpportunityStatus
from app.crm.models import Opportunity
from app.crm.opportunity_schemas import OpportunityCommand, OpportunityResponse
from app.platform.idempotency import begin_command, complete_command
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.work.content import activity_response
from app.work.models import Activity
from app.work.schemas import ActivityResponse


def opportunity_record(
    session: Session, context: RequestContext, record_id: UUID, *, lock: bool = False
) -> Opportunity:
    statement = select(Opportunity).where(
        Opportunity.organization_id == context.organization_id,
        Opportunity.id == record_id,
        Opportunity.deleted_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    record = session.scalar(statement)
    if record is None:
        raise ApiProblem(
            404, "OPPORTUNITY_NOT_FOUND", "Opportunity not found", "The opportunity was not found."
        )
    return record


def record_stage(
    session: Session,
    context: RequestContext,
    record: Opportunity,
    target: OpportunityStatus,
    *,
    reason: str,
    evidence_id: UUID | None = None,
) -> None:
    previous = record.status
    record.status = target
    record.updated_by = context.user_id
    if target == OpportunityStatus.LOST:
        record.lost_at = datetime.now(UTC)
        record.lost_reason = reason
    action = "opportunity.stage_changed"
    details: dict[str, object] = {
        "status": target,
        "evidence_id": str(evidence_id) if evidence_id else None,
    }
    session.add(
        Activity(
            organization_id=context.organization_id,
            created_by=context.user_id,
            updated_by=context.user_id,
            subject_type="opportunity",
            subject_id=record.id,
            activity_type=action,
            summary=reason,
            details={"before": previous, **details},
            correlation_id=context.request_id,
        )
    )
    AuditRecorder().record(
        session,
        context,
        action=action,
        target_type="opportunity",
        target_id=record.id,
        before={"status": previous},
        after=details,
        reason=reason,
    )
    OutboxRecorder().record(
        session,
        context,
        DomainEvent(
            f"{action}.v1",
            "opportunity",
            record.id,
            {"opportunity_id": str(record.id), "status": target},
        ),
    )
    session.flush()


def advance_from_evidence(
    session: Session,
    context: RequestContext,
    opportunity_id: UUID,
    *,
    event: Literal["inquiry", "quotation", "accepted"],
    evidence_id: UUID,
) -> Opportunity:
    """CRM-owned port; shares the originating command's transaction, never commits."""
    rules = {
        "inquiry": (
            Permission.INQUIRY_WRITE,
            {OpportunityStatus.OPEN, OpportunityStatus.INQUIRY},
            OpportunityStatus.INQUIRY,
            "已记录客户询盘",
        ),
        "quotation": (
            Permission.QUOTATION_WRITE,
            {OpportunityStatus.INQUIRY, OpportunityStatus.QUOTING},
            OpportunityStatus.QUOTING,
            "已创建客户报价",
        ),
        "accepted": (
            Permission.QUOTATION_ACCEPT,
            {OpportunityStatus.QUOTING, OpportunityStatus.NEGOTIATION},
            OpportunityStatus.WON,
            "客户接受报价，商机赢单",
        ),
    }
    permission, allowed, target, reason = rules[event]
    context.require(permission)
    record = opportunity_record(session, context, opportunity_id, lock=True)
    if record.status not in allowed:
        raise ApiProblem(
            409,
            "INVALID_STATE_TRANSITION",
            "Invalid opportunity state",
            "The opportunity cannot advance from its current state.",
        )
    if record.status != target:
        record_stage(session, context, record, target, reason=reason, evidence_id=evidence_id)
    return record


class OpportunityQueryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, context: RequestContext, record_id: UUID) -> OpportunityResponse:
        context.require(Permission.OPPORTUNITY_READ)
        return opportunity_response(context, opportunity_record(self.session, context, record_id))

    def list(
        self,
        context: RequestContext,
        *,
        status: OpportunityStatus | None,
        cursor: UUID | None,
        limit: int,
    ) -> Sequence[OpportunityResponse]:
        context.require(Permission.OPPORTUNITY_READ)
        statement = select(Opportunity).where(
            Opportunity.organization_id == context.organization_id, Opportunity.deleted_at.is_(None)
        )
        if status is not None:
            statement = statement.where(Opportunity.status == status)
        if cursor is not None:
            anchor = opportunity_record(self.session, context, cursor)
            statement = statement.where(
                tuple_(Opportunity.created_at, Opportunity.id) < (anchor.created_at, anchor.id)
            )
        rows = self.session.scalars(
            statement.order_by(Opportunity.created_at.desc(), Opportunity.id.desc()).limit(
                limit + 1
            )
        ).all()
        return [opportunity_response(context, row) for row in rows]

    def history(
        self, context: RequestContext, record_id: UUID, *, offset: int, limit: int
    ) -> Sequence[ActivityResponse]:
        self.get(context, record_id)
        rows = self.session.scalars(
            select(Activity)
            .where(
                Activity.organization_id == context.organization_id,
                Activity.subject_type == "opportunity",
                Activity.subject_id == record_id,
                Activity.deleted_at.is_(None),
            )
            .order_by(Activity.occurred_at.desc(), Activity.id.desc())
            .offset(offset)
            .limit(limit + 1)
        ).all()
        return [activity_response(context, row) for row in rows]


class OpportunityCommandService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def execute(
        self,
        context: RequestContext,
        record_id: UUID,
        command: Literal["start-negotiation", "mark-lost"],
        data: dict[str, object],
        *,
        idempotency_key: str,
    ) -> OpportunityResponse:
        context.require(Permission.OPPORTUNITY_WRITE)
        request = OpportunityCommand.model_validate(data)
        with UnitOfWork(self.factory) as uow:
            key = begin_command(
                uow.session,
                context,
                scope=f"opportunity.{command}",
                key=idempotency_key,
                payload={"opportunity_id": str(record_id), **request.model_dump()},
            )
            record = opportunity_record(uow.session, context, record_id, lock=True)
            if key.resource_id is not None:
                uow.commit()
                return opportunity_response(context, record)
            if record.version != request.expected_version:
                raise ApiProblem(
                    409,
                    "VERSION_CONFLICT",
                    "Version conflict",
                    "Refresh the opportunity before submitting.",
                )
            if command == "start-negotiation":
                allowed = {OpportunityStatus.QUOTING}
                target = OpportunityStatus.NEGOTIATION
            elif command == "mark-lost":
                allowed = {
                    OpportunityStatus.OPEN,
                    OpportunityStatus.INQUIRY,
                    OpportunityStatus.QUOTING,
                    OpportunityStatus.NEGOTIATION,
                }
                target = OpportunityStatus.LOST
            else:
                raise ApiProblem(
                    422, "INVALID_COMMAND", "Invalid command", "Unsupported opportunity command."
                )
            if record.status not in allowed:
                raise ApiProblem(
                    409,
                    "INVALID_STATE_TRANSITION",
                    "Invalid opportunity state",
                    "This command is not allowed in the current state.",
                )
            record_stage(uow.session, context, record, target, reason=request.reason)
            complete_command(key, record.id, "opportunity")
            uow.commit()
            return opportunity_response(context, record)
