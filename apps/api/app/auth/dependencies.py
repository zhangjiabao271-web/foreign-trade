from collections.abc import Callable, Iterator
from functools import lru_cache
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission, permissions_for_role
from app.auth.tokens import LogtoTokenVerifier, TokenVerificationError, TokenVerifier, VerifiedToken
from app.core.config import get_settings
from app.core.database import create_database_engine, create_session_factory
from app.identity.enums import MembershipRole, MembershipStatus, OrganizationStatus, UserStatus
from app.identity.repositories import IdentityRepository

bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def _default_session_factory() -> sessionmaker[Session]:
    engine = create_database_engine()
    return create_session_factory(engine)


@lru_cache
def _default_token_verifier() -> TokenVerifier:
    settings = get_settings()
    return LogtoTokenVerifier(
        issuer=settings.oidc_issuer,
        audience=settings.oidc_audience,
        jwks_url=settings.oidc_jwks_url,
        signing_algorithm=settings.oidc_signing_algorithm,
    )


def get_database_session(request: Request) -> Iterator[Session]:
    factory = get_session_factory(request)
    with factory() as session:
        yield session


def get_session_factory(request: Request) -> sessionmaker[Session]:
    factory = getattr(request.app.state, "session_factory", None)
    return factory if factory is not None else _default_session_factory()


def get_token_verifier(request: Request) -> TokenVerifier:
    verifier = getattr(request.app.state, "token_verifier", None)
    return verifier if verifier is not None else _default_token_verifier()


def get_verified_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> VerifiedToken:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ApiProblem(
            401, "AUTHENTICATION_REQUIRED", "Authentication required", "A bearer token is required."
        )
    try:
        return get_token_verifier(request).verify(credentials.credentials)
    except TokenVerificationError as error:
        raise ApiProblem(
            401, "INVALID_TOKEN", "Invalid token", "The bearer token could not be verified."
        ) from error


def get_request_context(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[Session, Depends(get_database_session)],
) -> RequestContext:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ApiProblem(
            401, "AUTHENTICATION_REQUIRED", "Authentication required", "A bearer token is required."
        )

    raw_organization_id = request.headers.get("X-Organization-ID")
    if raw_organization_id is None:
        raise ApiProblem(
            400,
            "ORGANIZATION_REQUIRED",
            "Organization required",
            "Select an organization with X-Organization-ID.",
        )
    try:
        organization_id = UUID(raw_organization_id)
    except ValueError as error:
        raise ApiProblem(
            400, "INVALID_ORGANIZATION", "Invalid organization", "X-Organization-ID must be a UUID."
        ) from error

    try:
        token = get_token_verifier(request).verify(credentials.credentials)
    except TokenVerificationError as error:
        raise ApiProblem(
            401, "INVALID_TOKEN", "Invalid token", "The bearer token could not be verified."
        ) from error

    if token.organization_id is not None and token.organization_id != organization_id:
        raise ApiProblem(
            403,
            "ORGANIZATION_MISMATCH",
            "Organization mismatch",
            "The token is not valid for the selected organization.",
        )

    identity = IdentityRepository(session).find_membership(
        external_subject=token.subject,
        organization_id=organization_id,
    )
    if identity is None:
        raise ApiProblem(
            403,
            "MEMBERSHIP_REQUIRED",
            "Membership required",
            "The user is not a member of the selected organization.",
        )
    if identity.user.status != UserStatus.ACTIVE:
        raise ApiProblem(403, "USER_DISABLED", "User disabled", "The local user is disabled.")
    if identity.organization.status != OrganizationStatus.ACTIVE:
        raise ApiProblem(
            403,
            "ORGANIZATION_DISABLED",
            "Organization disabled",
            "The selected organization is disabled.",
        )
    if identity.membership.status != MembershipStatus.ACTIVE:
        raise ApiProblem(
            403,
            "MEMBERSHIP_INACTIVE",
            "Membership inactive",
            "The organization membership is not active.",
        )

    request.state.verified_organization_id = organization_id
    request.state.database_engine = session.get_bind()
    return RequestContext(
        user_id=identity.user.id,
        organization_id=organization_id,
        permissions=permissions_for_role(MembershipRole(identity.membership.role)),
        request_id=request.state.request_id,
    )


def require_permissions(
    *required: Permission,
) -> Callable[[RequestContext], RequestContext]:
    def dependency(
        context: Annotated[RequestContext, Depends(get_request_context)],
    ) -> RequestContext:
        context.require(*required)
        return context

    return dependency


def assign_request_id(request: Request) -> UUID:
    supplied = request.headers.get("X-Request-ID")
    if supplied is not None:
        try:
            return UUID(supplied)
        except ValueError:
            pass
    return uuid4()
