from uuid import UUID

from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.identity.administration_repository import AdministrationRepository
from app.identity.models import OrganizationMembership, User
from app.identity.schemas import MemberListResponse, MemberResponse, OrganizationResponse


def member_response(member: OrganizationMembership, user: User) -> MemberResponse:
    return MemberResponse.model_validate(
        {
            "id": member.id,
            "user_id": user.id,
            "version": member.version,
            "external_subject": user.external_subject,
            "display_name": user.display_name,
            "user_status": user.status,
            "role": member.role,
            "status": member.status,
            "created_at": member.created_at,
        }
    )


class AdministrationQuery:
    def __init__(self, session: Session) -> None:
        self.repository = AdministrationRepository(session)

    def organization(self, context: RequestContext) -> OrganizationResponse:
        context.require(Permission.ORGANIZATION_MANAGE)
        return OrganizationResponse.model_validate(
            self.repository.organization(context.organization_id)
        )

    def member(self, context: RequestContext, member_id: UUID) -> MemberResponse:
        context.require(Permission.MEMBER_MANAGE)
        membership, user = self.repository.member(context.organization_id, member_id)
        return member_response(membership, user)

    def members(
        self, context: RequestContext, *, limit: int = 20, cursor: UUID | None = None
    ) -> MemberListResponse:
        context.require(Permission.MEMBER_MANAGE)
        rows = self.repository.members(context.organization_id, limit=limit, cursor=cursor)
        items = [member_response(member, user) for member, user in rows[:limit]]
        more = len(rows) > limit
        return MemberListResponse(
            items=items, has_more=more, next_cursor=items[-1].id if more else None
        )
