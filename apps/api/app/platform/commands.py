from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.core.unit_of_work import UnitOfWork
from app.platform.models import AsyncJob
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder

FailureInjector = Callable[[str], None]


def _no_failure(_: str) -> None:
    return None


class PlatformCommandService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        audit_recorder: AuditRecorder | None = None,
        outbox_recorder: OutboxRecorder | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._audit_recorder = audit_recorder or AuditRecorder()
        self._outbox_recorder = outbox_recorder or OutboxRecorder()

    def create_job(
        self,
        context: RequestContext,
        *,
        job_type: str,
        failure_injector: FailureInjector = _no_failure,
    ) -> AsyncJob:
        context.require(Permission.JOB_CREATE)
        with UnitOfWork(self._session_factory) as unit_of_work:
            job = AsyncJob(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                job_type=job_type,
                correlation_id=context.request_id,
            )
            unit_of_work.session.add(job)
            unit_of_work.session.flush()
            failure_injector("business")

            self._audit_recorder.record(
                unit_of_work.session,
                context,
                action="async_job.created",
                target_type="async_job",
                target_id=job.id,
                after={"job_type": job.job_type, "status": job.status},
            )
            unit_of_work.session.flush()
            failure_injector("audit")

            self._outbox_recorder.record(
                unit_of_work.session,
                context,
                DomainEvent(
                    event_type="async_job.created.v1",
                    aggregate_type="async_job",
                    aggregate_id=job.id,
                    payload={"job_id": str(job.id), "job_type": job.job_type},
                ),
            )
            unit_of_work.session.flush()
            failure_injector("outbox")
            unit_of_work.commit()
            return job
