from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_request_context, get_verified_token
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.schemas import ContextResponse, MyOrganizationResponse, MyOrganizationsResponse
from app.auth.tokens import VerifiedToken
from app.identity.enums import MembershipRole
from app.identity.repositories import IdentityRepository

router = APIRouter(prefix="/api/v1", tags=["identity"], responses=PROBLEM_RESPONSES)


@router.get("/me/organizations", response_model=MyOrganizationsResponse)
def read_my_organizations(
    token: Annotated[VerifiedToken, Depends(get_verified_token)],
    session: Annotated[Session, Depends(get_database_session)],
) -> MyOrganizationsResponse:
    identities = IdentityRepository(session).active_memberships(
        external_subject=token.subject,
        token_organization_id=token.organization_id,
    )
    return MyOrganizationsResponse(
        items=[
            MyOrganizationResponse(
                organization_id=identity.organization.id,
                name=identity.organization.name,
                role=MembershipRole(identity.membership.role),
            )
            for identity in identities
        ]
    )


@router.get("/me/context", response_model=ContextResponse)
def read_context(
    context: Annotated[RequestContext, Depends(get_request_context)],
) -> ContextResponse:
    return ContextResponse.from_context(context)
