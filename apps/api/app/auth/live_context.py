from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import permissions_for_role
from app.identity.enums import MembershipRole
from app.identity.models import Organization, OrganizationMembership, User


def live_context(
    session: Session, *, organization_id: UUID, user_id: UUID, request_id: UUID
) -> RequestContext:
    """Revalidate current authority for delayed execution, never trust queued permissions."""
    role = session.scalar(
        select(OrganizationMembership.role)
        .join(User, User.id == OrganizationMembership.user_id)
        .join(Organization, Organization.id == OrganizationMembership.organization_id)
        .where(
            OrganizationMembership.organization_id == organization_id,
            OrganizationMembership.user_id == user_id,
            OrganizationMembership.status == "ACTIVE",
            OrganizationMembership.deleted_at.is_(None),
            User.status == "ACTIVE",
            User.deleted_at.is_(None),
            Organization.status == "ACTIVE",
            Organization.deleted_at.is_(None),
        )
    )
    if role is None:
        raise ApiProblem(
            403, "MEMBERSHIP_INACTIVE", "Access revoked", "Active membership is required."
        )
    return RequestContext(
        user_id=user_id,
        organization_id=organization_id,
        request_id=request_id,
        permissions=permissions_for_role(MembershipRole(role)),
    )
