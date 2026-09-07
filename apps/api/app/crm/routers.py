from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.crm.enums import LeadStatus
from app.crm.repositories import LeadRepository
from app.crm.schemas import (
    ActivityResponse,
    LeadConversionResponse,
    LeadCreate,
    LeadDetailResponse,
    LeadListResponse,
    LeadResponse,
)
from app.crm.services import LeadCommandService, LeadQueryService

router = APIRouter(prefix="/api/v1/leads", tags=["leads"], responses=PROBLEM_RESPONSES)
DatabaseSession = Annotated[Session, Depends(get_database_session)]
SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
LeadReader = Annotated[RequestContext, Depends(require_permissions(Permission.LEAD_READ))]
LeadWriter = Annotated[RequestContext, Depends(require_permissions(Permission.LEAD_WRITE))]
LeadConverter = Annotated[RequestContext, Depends(require_permissions(Permission.LEAD_CONVERT))]


@router.get("", response_model=LeadListResponse)
def list_leads(
    context: LeadReader,
    session: DatabaseSession,
    status: LeadStatus | None = None,
    query: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> LeadListResponse:
    leads = LeadQueryService(LeadRepository(session)).list(
        context,
        status=status,
        query=query,
        limit=limit,
    )
    return LeadListResponse(
        items=[LeadResponse.model_validate(lead) for lead in leads],
        count=len(leads),
    )


@router.post("", response_model=LeadResponse, status_code=201)
def create_lead(
    request: LeadCreate,
    context: LeadWriter,
    factory: SessionFactory,
) -> LeadResponse:
    lead = LeadCommandService(factory).create(
        context,
        request.model_dump(exclude_none=True),
    )
    return LeadResponse.model_validate(lead)


@router.get("/{lead_id}", response_model=LeadDetailResponse)
def read_lead(
    lead_id: UUID,
    context: LeadReader,
    session: DatabaseSession,
) -> LeadDetailResponse:
    lead, activities = LeadQueryService(LeadRepository(session)).get(context, lead_id)
    return LeadDetailResponse(
        **LeadResponse.model_validate(lead).model_dump(),
        activities=[ActivityResponse.model_validate(activity) for activity in activities],
    )


@router.post("/{lead_id}/convert", response_model=LeadConversionResponse)
def convert_lead(
    lead_id: UUID,
    context: LeadConverter,
    factory: SessionFactory,
) -> LeadConversionResponse:
    lead, company_id, contact_id, opportunity_id = LeadCommandService(factory).convert(
        context,
        lead_id,
    )
    return LeadConversionResponse(
        lead=LeadResponse.model_validate(lead),
        company_id=company_id,
        contact_id=contact_id,
        opportunity_id=opportunity_id,
    )


@router.post("/{lead_id}/{command}", response_model=LeadResponse)
def transition_lead(
    lead_id: UUID,
    command: Literal["qualify", "contact", "respond", "no-response", "disqualify"],
    context: LeadWriter,
    factory: SessionFactory,
) -> LeadResponse:
    lead = LeadCommandService(factory).transition(context, lead_id, command)
    return LeadResponse.model_validate(lead)
