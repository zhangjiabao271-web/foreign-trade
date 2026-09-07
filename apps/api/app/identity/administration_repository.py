from uuid import UUID

from sqlalchemy import func, literal, select, tuple_
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.identity.models import Organization, OrganizationMembership, User


def identity_missing() -> ApiProblem:
    return ApiProblem(404, "IDENTITY_NOT_FOUND", "Not found", "Organization resource not found.")


class AdministrationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def organization(self, organization_id: UUID, *, lock: bool = False) -> Organization:
        statement = select(Organization).where(
            Organization.id == organization_id,
            Organization.deleted_at.is_(None),
            Organization.status == "ACTIVE",
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        row = self.session.scalar(statement)
        if row is None:
            raise identity_missing()
        return row

    def authorize_admin(self, context: RequestContext) -> Organization:
        organization = self.organization(context.organization_id, lock=True)
        administrator = self.session.scalar(
            select(OrganizationMembership.id)
            .join(User, User.id == OrganizationMembership.user_id)
            .where(
                OrganizationMembership.organization_id == context.organization_id,
                OrganizationMembership.user_id == context.user_id,
                OrganizationMembership.role == "ADMIN",
                OrganizationMembership.status == "ACTIVE",
                OrganizationMembership.deleted_at.is_(None),
                User.status == "ACTIVE",
                User.deleted_at.is_(None),
            )
        )
        if administrator is None:
            raise ApiProblem(
                403,
                "PERMISSION_DENIED",
                "Permission denied",
                "An active administrator is required.",
            )
        return organization

    def member(self, organization_id: UUID, member_id: UUID) -> tuple[OrganizationMembership, User]:
        row = self.session.execute(
            select(OrganizationMembership, User)
            .join(User, User.id == OrganizationMembership.user_id)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.id == member_id,
                OrganizationMembership.deleted_at.is_(None),
            )
        ).one_or_none()
        if row is None:
            raise identity_missing()
        return row[0], row[1]

    def eligible_admin_count(self, organization_id: UUID) -> int:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(OrganizationMembership)
                .join(User, User.id == OrganizationMembership.user_id)
                .where(
                    OrganizationMembership.organization_id == organization_id,
                    OrganizationMembership.role == "ADMIN",
                    OrganizationMembership.status == "ACTIVE",
                    OrganizationMembership.deleted_at.is_(None),
                    User.status == "ACTIVE",
                    User.deleted_at.is_(None),
                )
            )
            or 0
        )

    def members(
        self, organization_id: UUID, *, limit: int, cursor: UUID | None
    ) -> list[tuple[OrganizationMembership, User]]:
        if not 1 <= limit <= 100:
            raise ValueError("Member page size must be between 1 and 100")
        statement = (
            select(OrganizationMembership, User)
            .join(User, User.id == OrganizationMembership.user_id)
            .where(
                OrganizationMembership.organization_id == organization_id,
                OrganizationMembership.deleted_at.is_(None),
            )
        )
        if cursor is not None:
            anchor, _ = self.member(organization_id, cursor)
            statement = statement.where(
                tuple_(OrganizationMembership.created_at, OrganizationMembership.id)
                < tuple_(literal(anchor.created_at), literal(anchor.id))
            )
        rows = self.session.execute(
            statement.order_by(
                OrganizationMembership.created_at.desc(), OrganizationMembership.id.desc()
            ).limit(limit + 1)
        )
        return [(row[0], row[1]) for row in rows]
