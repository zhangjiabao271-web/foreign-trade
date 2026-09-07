from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.identity.enums import MembershipStatus, OrganizationStatus, UserStatus
from app.identity.models import Organization, OrganizationMembership, User


@dataclass(frozen=True, slots=True)
class MembershipIdentity:
    user: User
    organization: Organization
    membership: OrganizationMembership


class IdentityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def active_memberships(
        self, *, external_subject: str, token_organization_id: UUID | None
    ) -> list[MembershipIdentity]:
        """Identity-only discovery, restricted to the authenticated subject."""
        query = (
            select(User, Organization, OrganizationMembership)
            .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
            .join(Organization, Organization.id == OrganizationMembership.organization_id)
            .where(
                User.external_subject == external_subject,
                User.status == UserStatus.ACTIVE,
                User.deleted_at.is_(None),
                Organization.status == OrganizationStatus.ACTIVE,
                Organization.deleted_at.is_(None),
                OrganizationMembership.status == MembershipStatus.ACTIVE,
                OrganizationMembership.deleted_at.is_(None),
            )
            .order_by(Organization.name, Organization.id)
        )
        if token_organization_id is not None:
            query = query.where(OrganizationMembership.organization_id == token_organization_id)
        return [
            MembershipIdentity(user=row[0], organization=row[1], membership=row[2])
            for row in self._session.execute(query)
        ]

    def find_membership(
        self,
        *,
        external_subject: str,
        organization_id: UUID,
    ) -> MembershipIdentity | None:
        statement = (
            select(User, Organization, OrganizationMembership)
            .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
            .join(Organization, Organization.id == OrganizationMembership.organization_id)
            .where(
                User.external_subject == external_subject,
                User.deleted_at.is_(None),
                Organization.id == organization_id,
                Organization.deleted_at.is_(None),
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.deleted_at.is_(None),
            )
        )
        row = self._session.execute(statement).one_or_none()
        if row is None:
            return None
        return MembershipIdentity(user=row[0], organization=row[1], membership=row[2])
