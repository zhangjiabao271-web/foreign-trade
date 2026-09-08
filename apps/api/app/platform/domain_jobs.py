from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.platform.enums import AsyncJobStatus
from app.platform.models import AsyncJob


def _create(session: Session, context: RequestContext, job_type: str) -> UUID:
    job = AsyncJob(
        organization_id=context.organization_id,
        created_by=context.user_id,
        updated_by=context.user_id,
        job_type=job_type,
        correlation_id=context.request_id,
        max_attempts=3,
    )
    if job_type == "DOCUMENT_SCAN":
        job.status = AsyncJobStatus.PENDING
        job.progress = Decimal(0)
    session.add(job)
    session.flush()
    return job.id


def create_ai_job(session: Session, context: RequestContext) -> UUID:
    context.require(Permission.AI_RUN)
    return _create(session, context, "AI_COPILOT")


def create_document_scan_job(session: Session, context: RequestContext) -> UUID:
    context.require(Permission.DOCUMENT_WRITE)
    return _create(session, context, "DOCUMENT_SCAN")


def _locked_job(
    session: Session, *, organization_id: UUID, job_id: UUID, job_type: str
) -> AsyncJob:
    job = session.scalar(
        select(AsyncJob)
        .where(
            AsyncJob.organization_id == organization_id,
            AsyncJob.id == job_id,
            AsyncJob.job_type == job_type,
        )
        .with_for_update()
    )
    if job is None:
        raise ValueError("Domain job was not found in the expected organization and type")
    return job


def bind_ai_run(session: Session, context: RequestContext, *, job_id: UUID, run_id: UUID) -> None:
    context.require(Permission.AI_RUN)
    job = _locked_job(
        session, organization_id=context.organization_id, job_id=job_id, job_type="AI_COPILOT"
    )
    job.result_reference = f"ai-run:{run_id}"


def start_ai_attempt(
    session: Session, *, organization_id: UUID, job_id: UUID, attempt_count: int
) -> int:
    """Trusted worker: caller already owns the run lock and validated its lease."""
    job = _locked_job(
        session, organization_id=organization_id, job_id=job_id, job_type="AI_COPILOT"
    )
    job.status = AsyncJobStatus.RUNNING
    job.attempt_count = attempt_count
    return job.max_attempts


@dataclass(frozen=True, slots=True)
class AiJobOutcome:
    status: AsyncJobStatus
    retry: bool


def finish_ai_attempt(
    session: Session,
    *,
    organization_id: UUID,
    job_id: UUID,
    attempt_count: int,
    error_code: str | None,
    retryable: bool,
) -> AiJobOutcome:
    """Trusted worker result, including failures caused by revoked user authority."""
    job = _locked_job(
        session, organization_id=organization_id, job_id=job_id, job_type="AI_COPILOT"
    )
    retry = retryable and attempt_count < job.max_attempts
    if retry:
        status = AsyncJobStatus.PENDING
    else:
        status = AsyncJobStatus.FAILED if error_code else AsyncJobStatus.SUCCEEDED
    job.status = status
    job.progress = Decimal(0 if retry else 100)
    job.error_code = error_code
    return AiJobOutcome(status=status, retry=retry)


def lock_document_scan_job(session: Session, *, organization_id: UUID, job_id: UUID) -> None:
    """Lock after the document version, including before an AVAILABLE replay."""
    _locked_job(session, organization_id=organization_id, job_id=job_id, job_type="DOCUMENT_SCAN")


def complete_document_scan_job(
    session: Session, *, organization_id: UUID, job_id: UUID, version_id: UUID
) -> None:
    with session.no_autoflush:
        job = _locked_job(
            session, organization_id=organization_id, job_id=job_id, job_type="DOCUMENT_SCAN"
        )
    job.status = AsyncJobStatus.SUCCEEDED
    job.progress = Decimal(100)
    job.result_reference = f"document-version:{version_id}"
