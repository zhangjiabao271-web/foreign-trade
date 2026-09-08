from uuid import UUID

from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.work.models import Activity


def _stage_activity(
    session: Session,
    *,
    organization_id: UUID,
    actor_id: UUID | None,
    correlation_id: UUID,
    subject_type: str,
    subject_id: UUID,
    activity_type: str,
    summary: str,
    details: dict[str, object],
) -> None:
    session.add(
        Activity(
            organization_id=organization_id,
            created_by=actor_id,
            updated_by=actor_id,
            subject_type=subject_type,
            subject_id=subject_id,
            activity_type=activity_type,
            summary=summary,
            details=details,
            correlation_id=correlation_id,
        )
    )


def record_activity(
    session: Session,
    context: RequestContext,
    *,
    subject_type: str,
    subject_id: UUID,
    activity_type: str,
    summary: str,
    details: dict[str, object],
) -> None:
    """Stage evidence for an authorized domain command, including recorded AI denials."""
    _stage_activity(
        session,
        organization_id=context.organization_id,
        actor_id=context.user_id,
        correlation_id=context.request_id,
        subject_type=subject_type,
        subject_id=subject_id,
        activity_type=activity_type,
        summary=summary,
        details=details,
    )


def record_system_activity(
    session: Session,
    *,
    organization_id: UUID,
    correlation_id: UUID,
    subject_type: str,
    subject_id: UUID,
    activity_type: str,
    summary: str,
    details: dict[str, object],
) -> None:
    """Stage trusted event evidence without attributing it to a human actor."""
    _stage_activity(
        session,
        organization_id=organization_id,
        actor_id=None,
        correlation_id=correlation_id,
        subject_type=subject_type,
        subject_id=subject_id,
        activity_type=activity_type,
        summary=summary,
        details=details,
    )
