from uuid import UUID

from pydantic import BaseModel

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.identity.enums import MembershipRole


class MyOrganizationResponse(BaseModel):
    organization_id: UUID
    name: str
    role: MembershipRole


class MyOrganizationsResponse(BaseModel):
    items: list[MyOrganizationResponse]


class ContextResponse(BaseModel):
    user_id: UUID
    organization_id: UUID
    permissions: list[Permission]
    request_id: UUID

    @classmethod
    def from_context(cls, context: RequestContext) -> "ContextResponse":
        return cls(
            user_id=context.user_id,
            organization_id=context.organization_id,
            permissions=sorted(context.permissions, key=lambda permission: permission.value),
            request_id=context.request_id,
        )
