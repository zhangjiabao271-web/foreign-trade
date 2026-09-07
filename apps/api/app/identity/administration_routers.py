from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.identity.administration_queries import AdministrationQuery
from app.identity.administration_service import AdministrationService
from app.identity.schemas import (
    IdentityCommandResponse,
    IdentityVersionCommand,
    MemberCreate,
    MemberListResponse,
    MemberResponse,
    MemberRoleChange,
    OrganizationResponse,
    OrganizationUpdate,
)

router = APIRouter(
    prefix="/api/v1/organization", tags=["organization-administration"], responses=PROBLEM_RESPONSES
)
DatabaseSession = Annotated[Session, Depends(get_database_session)]
Factory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
OrganizationAdmin = Annotated[
    RequestContext, Depends(require_permissions(Permission.ORGANIZATION_MANAGE))
]
MemberAdmin = Annotated[RequestContext, Depends(require_permissions(Permission.MEMBER_MANAGE))]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=160)]
Limit = Annotated[int, Query(ge=1, le=100)]


@router.get("", response_model=OrganizationResponse)
def read_organization(context: OrganizationAdmin, session: DatabaseSession) -> OrganizationResponse:
    return AdministrationQuery(session).organization(context)


@router.post("/update", response_model=IdentityCommandResponse)
def update_organization(
    request: OrganizationUpdate, context: OrganizationAdmin, factory: Factory, key: Key
) -> IdentityCommandResponse:
    return IdentityCommandResponse(
        id=AdministrationService(factory).update_organization(
            context, request.model_dump(), key=key
        )
    )


@router.get("/members", response_model=MemberListResponse)
def list_members(
    context: MemberAdmin, session: DatabaseSession, limit: Limit = 20, cursor: UUID | None = None
) -> MemberListResponse:
    return AdministrationQuery(session).members(context, limit=limit, cursor=cursor)


@router.get("/members/{member_id}", response_model=MemberResponse)
def read_member(member_id: UUID, context: MemberAdmin, session: DatabaseSession) -> MemberResponse:
    return AdministrationQuery(session).member(context, member_id)


@router.post("/members", response_model=IdentityCommandResponse, status_code=201)
def add_member(
    request: MemberCreate, context: MemberAdmin, factory: Factory, key: Key
) -> IdentityCommandResponse:
    return IdentityCommandResponse(
        id=AdministrationService(factory).add_member(context, request.model_dump(), key=key)
    )


@router.post("/members/{member_id}/change-role", response_model=IdentityCommandResponse)
def change_member_role(
    member_id: UUID, request: MemberRoleChange, context: MemberAdmin, factory: Factory, key: Key
) -> IdentityCommandResponse:
    return IdentityCommandResponse(
        id=AdministrationService(factory).change_member(
            context, member_id, request.model_dump(), action="role_changed", key=key
        )
    )


@router.post("/members/{member_id}/disable", response_model=IdentityCommandResponse)
def disable_member(
    member_id: UUID,
    request: IdentityVersionCommand,
    context: MemberAdmin,
    factory: Factory,
    key: Key,
) -> IdentityCommandResponse:
    return IdentityCommandResponse(
        id=AdministrationService(factory).change_member(
            context, member_id, request.model_dump(), action="disabled", key=key
        )
    )


@router.post("/members/{member_id}/reactivate", response_model=IdentityCommandResponse)
def reactivate_member(
    member_id: UUID,
    request: IdentityVersionCommand,
    context: MemberAdmin,
    factory: Factory,
    key: Key,
) -> IdentityCommandResponse:
    return IdentityCommandResponse(
        id=AdministrationService(factory).change_member(
            context, member_id, request.model_dump(), action="reactivated", key=key
        )
    )
