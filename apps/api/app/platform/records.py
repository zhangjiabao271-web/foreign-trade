from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.platform.models import AuditLog, OutboxEvent


@dataclass(frozen=True, slots=True)
class DomainEvent:
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    payload: dict[str, object] = field(default_factory=dict)


class AuditRecorder:
    def record(
        self,
        session: Session,
        context: RequestContext,
        *,
        action: str,
        target_type: str,
        target_id: UUID | None,
        before: dict[str, object] | None = None,
        after: dict[str, object] | None = None,
        reason: str | None = None,
    ) -> AuditLog:
        audit = AuditLog(
            organization_id=context.organization_id,
            actor_user_id=context.user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            request_id=context.request_id,
            correlation_id=context.request_id,
            before_data=before,
            after_data=after,
            reason=reason,
        )
        session.add(audit)
        return audit


class OutboxRecorder:
    def record(
        self,
        session: Session,
        context: RequestContext,
        event: DomainEvent,
    ) -> OutboxEvent:
        outbox_event = OutboxEvent(
            organization_id=context.organization_id,
            created_by=context.user_id,
            updated_by=context.user_id,
            event_type=event.event_type,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            payload=event.payload,
            correlation_id=context.request_id,
        )
        session.add(outbox_event)
        return outbox_event
