from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.platform.enums import OutboxStatus
from app.platform.models import AsyncJob, OutboxEvent
from app.platform.records import AuditRecorder
from app.platform.repositories import AsyncJobRepository, OutboxEventRepository


class AsyncJobQueryService:
    def __init__(self, repository: AsyncJobRepository) -> None:
        self._repository = repository

    def get(self, context: RequestContext, job_id: UUID) -> AsyncJob:
        context.require(Permission.JOB_READ)
        job = self._repository.get(
            organization_id=context.organization_id,
            record_id=job_id,
        )
        if job is None:
            raise ApiProblem(404, "JOB_NOT_FOUND", "Job not found", "The job was not found.")
        return job

    def list(self, context: RequestContext) -> Sequence[AsyncJob]:
        context.require(Permission.JOB_READ)
        return self._repository.list(organization_id=context.organization_id)

    def count(self, context: RequestContext) -> int:
        context.require(Permission.JOB_READ)
        return self._repository.count(organization_id=context.organization_id)


class OutboxAdminService:
    def __init__(
        self,
        repository: OutboxEventRepository,
        audit_recorder: AuditRecorder | None = None,
    ) -> None:
        self._repository = repository
        self._audit_recorder = audit_recorder or AuditRecorder()

    def list_dead(
        self, context: RequestContext, *, offset: int = 0, limit: int = 25
    ) -> Sequence[OutboxEvent]:
        context.require(Permission.OUTBOX_READ)
        return self._repository.list_dead(
            organization_id=context.organization_id, offset=offset, limit=limit
        )

    def replay(
        self,
        context: RequestContext,
        event_id: UUID,
        *,
        reason: str,
        expected_version: int | None = None,
    ) -> OutboxEvent:
        context.require(Permission.OUTBOX_REPLAY)
        reason = reason.strip()
        if not 1 <= len(reason) <= 1000:
            raise ApiProblem(
                422,
                "REPLAY_REASON_REQUIRED",
                "Reason required",
                "Provide a replay reason of 1 to 1000 characters.",
            )
        try:
            event = self._repository.get_for_update(
                organization_id=context.organization_id, record_id=event_id
            )
            if event is None:
                raise ApiProblem(
                    404, "OUTBOX_EVENT_NOT_FOUND", "Event not found", "The event was not found."
                )
            if event.status != OutboxStatus.DEAD:
                raise ApiProblem(
                    409,
                    "OUTBOX_EVENT_NOT_DEAD",
                    "Event is not dead",
                    "Only dead events can be replayed.",
                )
            if expected_version is not None and event.version != expected_version:
                raise ApiProblem(
                    409,
                    "VERSION_CONFLICT",
                    "Version conflict",
                    "Refresh before replaying this event.",
                )
            previous_version = event.version
            event.status = OutboxStatus.PENDING
            event.attempt_count = 0
            event.available_at = datetime.now(UTC)
            event.locked_at = None
            event.locked_by = None
            event.last_error = None
            event.updated_by = context.user_id
            event.version += 1
            self._audit_recorder.record(
                self._repository.session,
                context,
                action="outbox_event.replayed",
                target_type="outbox_event",
                target_id=event.id,
                before={"status": OutboxStatus.DEAD.value, "version": previous_version},
                after={"status": OutboxStatus.PENDING.value, "version": event.version},
                reason=reason,
            )
            self._repository.session.commit()
            return event
        except Exception:
            self._repository.session.rollback()
            raise
