from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.crm.enums import OpportunityStatus
from app.crm.opportunity_schemas import (
    OpportunityCommand,
    OpportunityHistoryResponse,
    OpportunityListResponse,
    OpportunityResponse,
)
from app.crm.opportunity_services import OpportunityCommandService, OpportunityQueryService
from app.crm.schemas import ActivityResponse

router = APIRouter(
    prefix="/api/v1/opportunities", tags=["opportunities"], responses=PROBLEM_RESPONSES
)
Database = Annotated[Session, Depends(get_database_session)]
Factory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
Reader = Annotated[RequestContext, Depends(require_permissions(Permission.OPPORTUNITY_READ))]
Writer = Annotated[RequestContext, Depends(require_permissions(Permission.OPPORTUNITY_WRITE))]
CommandKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]


@router.get("", response_model=OpportunityListResponse)
def list_opportunities(
    context: Reader,
    session: Database,
    status: OpportunityStatus | None = None,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> OpportunityListResponse:
    rows = OpportunityQueryService(session).list(context, status=status, cursor=cursor, limit=limit)
    has_more = len(rows) > limit
    items = rows[:limit]
    return OpportunityListResponse(
        items=[OpportunityResponse.model_validate(row) for row in items],
        has_more=has_more,
        next_cursor=items[-1].id if has_more else None,
    )


@router.get("/{opportunity_id}", response_model=OpportunityResponse)
def read_opportunity(
    opportunity_id: UUID, context: Reader, session: Database
) -> OpportunityResponse:
    return OpportunityResponse.model_validate(
        OpportunityQueryService(session).get(context, opportunity_id)
    )


@router.get("/{opportunity_id}/activities", response_model=OpportunityHistoryResponse)
def opportunity_history(
    opportunity_id: UUID,
    context: Reader,
    session: Database,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> OpportunityHistoryResponse:
    rows = OpportunityQueryService(session).history(
        context, opportunity_id, offset=offset, limit=limit
    )
    return OpportunityHistoryResponse(
        items=[ActivityResponse.model_validate(row) for row in rows[:limit]],
        has_more=len(rows) > limit,
    )


@router.post("/{opportunity_id}/{command}", response_model=OpportunityResponse)
def change_opportunity(
    opportunity_id: UUID,
    command: Literal["start-negotiation", "mark-lost"],
    request: OpportunityCommand,
    context: Writer,
    factory: Factory,
    idempotency_key: CommandKey,
) -> OpportunityResponse:
    return OpportunityResponse.model_validate(
        OpportunityCommandService(factory).execute(
            context, opportunity_id, command, request.model_dump(), idempotency_key=idempotency_key
        )
    )
