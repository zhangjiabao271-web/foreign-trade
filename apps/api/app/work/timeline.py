from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.auth.errors import ApiProblem
from app.work.models import Activity


def activity_page(
    session: Session,
    *,
    organization_id: UUID,
    subject_type: str,
    subject_id: UUID,
    cursor: UUID | None,
    limit: int,
) -> tuple[Sequence[Activity], bool]:
    """The caller must authorize and resolve the owning business object first."""
    query = select(Activity).where(
        Activity.organization_id == organization_id,
        Activity.subject_type == subject_type,
        Activity.subject_id == subject_id,
        Activity.deleted_at.is_(None),
    )
    if cursor is not None:
        anchor = session.scalar(query.where(Activity.id == cursor))
        if anchor is None:
            raise ApiProblem(400, "INVALID_CURSOR", "Invalid cursor", "Reload this timeline.")
        query = query.where(
            tuple_(Activity.occurred_at, Activity.id) < (anchor.occurred_at, anchor.id)
        )
    rows = session.scalars(
        query.order_by(Activity.occurred_at.desc(), Activity.id.desc()).limit(limit + 1)
    ).all()
    return rows[:limit], len(rows) > limit
