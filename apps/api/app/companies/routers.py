from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.companies.schemas import CompanyRoleRequest, CompanyRoleResponse
from app.companies.services import CompanyCommandService

router = APIRouter(prefix="/api/v1/companies", tags=["companies"], responses=PROBLEM_RESPONSES)
SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
CompanyWriter = Annotated[RequestContext, Depends(require_permissions(Permission.COMPANY_WRITE))]


@router.post("/{company_id}/roles", response_model=CompanyRoleResponse, status_code=201)
def add_company_role(
    company_id: UUID,
    request: CompanyRoleRequest,
    context: CompanyWriter,
    factory: SessionFactory,
) -> CompanyRoleResponse:
    role = CompanyCommandService(factory).add_role(context, company_id, request.role)
    return CompanyRoleResponse.model_validate(role)
