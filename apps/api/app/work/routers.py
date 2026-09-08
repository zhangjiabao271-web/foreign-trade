from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.work.review import (
    WorkContentKind,
    WorkReviewRequest,
    WorkReviewResponse,
    WorkReviewService,
)
from app.work.schemas import (
    ActivityListResponse,
    ActivityPageResponse,
    TaskComplete,
    TaskListResponse,
    TaskResponse,
)
from app.work.services import TaskCommandService, WorkQueryService

router = APIRouter(prefix="/api/v1/sales-orders", tags=["work"], responses=PROBLEM_RESPONSES)
DatabaseSession = Annotated[Session, Depends(get_database_session)]
SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
Reader = Annotated[RequestContext, Depends(require_permissions(Permission.ORDER_READ))]
Writer = Annotated[RequestContext, Depends(require_permissions(Permission.TASK_WRITE))]


@router.get("/{order_id}/tasks", response_model=TaskListResponse)
def list_order_tasks(order_id: UUID, context: Reader, session: DatabaseSession) -> TaskListResponse:
    rows = WorkQueryService(session).order_tasks(context, order_id)
    return TaskListResponse(items=list(rows), count=len(rows))


@router.get("/{order_id}/activities", response_model=ActivityListResponse)
def list_order_activities(
    order_id: UUID,
    context: Reader,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ActivityListResponse:
    rows = WorkQueryService(session).order_activities(context, order_id, limit)
    return ActivityListResponse(items=list(rows), count=len(rows))


@router.get("/{order_id}/activity-history", response_model=ActivityPageResponse)
def page_order_activities(
    order_id: UUID,
    context: Reader,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: UUID | None = None,
) -> ActivityPageResponse:
    return WorkQueryService(session).commercial_activities(
        context, "sales_order", order_id, limit=limit, cursor=cursor
    )


@router.post("/{order_id}/tasks/{task_id}/complete", response_model=TaskResponse)
def complete_order_task(
    order_id: UUID,
    task_id: UUID,
    request: TaskComplete,
    context: Writer,
    factory: SessionFactory,
) -> TaskResponse:
    return TaskCommandService(factory).complete_order_task(context, order_id, task_id, request)


@router.get("/{order_id}/work/{kind}/{record_id}/review", response_model=WorkReviewResponse)
def inspect_work_review(
    order_id: UUID, kind: WorkContentKind, record_id: UUID, context: Reader, factory: SessionFactory
) -> WorkReviewResponse:
    return WorkReviewService(factory).inspect(context, order_id, kind, record_id)


@router.post("/{order_id}/work/{kind}/{record_id}/review", response_model=WorkReviewResponse)
def decide_work_review(
    order_id: UUID,
    kind: WorkContentKind,
    record_id: UUID,
    request: WorkReviewRequest,
    context: Reader,
    factory: SessionFactory,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=120)],
) -> WorkReviewResponse:
    return WorkReviewService(factory).decide(
        context, order_id, kind, record_id, request, key=idempotency_key
    )
