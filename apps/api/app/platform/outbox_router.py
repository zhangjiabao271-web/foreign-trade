from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.platform.repositories import OutboxEventRepository
from app.platform.schemas import DeadOutboxListResponse, OutboxEventResponse, ReplayOutboxRequest
from app.platform.services import OutboxAdminService

router = APIRouter(prefix="/api/v1/outbox", tags=["outbox"], responses=PROBLEM_RESPONSES)
DatabaseSession = Annotated[Session, Depends(get_database_session)]


@router.get("/dead", response_model=DeadOutboxListResponse)
def list_dead_events(
    context: Annotated[RequestContext, Depends(require_permissions(Permission.OUTBOX_READ))],
    session: DatabaseSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> DeadOutboxListResponse:
    events = OutboxAdminService(OutboxEventRepository(session)).list_dead(
        context, offset=offset, limit=limit + 1
    )
    return DeadOutboxListResponse(
        items=[OutboxEventResponse.model_validate(event) for event in events[:limit]],
        has_more=len(events) > limit,
        next_offset=offset + limit if len(events) > limit else None,
    )


@router.post("/{event_id}/replay", response_model=OutboxEventResponse)
def replay_event(
    event_id: UUID,
    request: ReplayOutboxRequest,
    context: Annotated[RequestContext, Depends(require_permissions(Permission.OUTBOX_REPLAY))],
    session: DatabaseSession,
) -> OutboxEventResponse:
    event = OutboxAdminService(OutboxEventRepository(session)).replay(
        context,
        event_id,
        reason=request.reason,
        expected_version=request.expected_version,
    )
    return OutboxEventResponse.model_validate(event)
