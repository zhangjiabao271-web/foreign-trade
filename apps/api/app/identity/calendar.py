"""Organization-owned calendar settings for business date boundaries."""

from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.errors import ApiProblem
from app.identity.models import Organization


def organization_timezone(session: Session, organization_id: UUID) -> ZoneInfo:
    timezone = session.scalar(
        select(Organization.timezone).where(
            Organization.id == organization_id, Organization.deleted_at.is_(None)
        )
    )
    if timezone is None:
        raise ApiProblem(
            404, "ORGANIZATION_NOT_FOUND", "Organization not found", "Organization not found."
        )
    return ZoneInfo(timezone)
