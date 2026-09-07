from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.sales.order_repositories import SalesOrderRepository
from app.sales.order_schemas import (
    SalesOrderConfirm,
    SalesOrderCreate,
    SalesOrderListResponse,
    SalesOrderResponse,
)
from app.sales.order_services import SalesOrderCommandService, SalesOrderQueryService

router = APIRouter(
    prefix="/api/v1/sales-orders", tags=["sales-orders"], responses=PROBLEM_RESPONSES
)
DatabaseSession = Annotated[Session, Depends(get_database_session)]
SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
OrderReader = Annotated[RequestContext, Depends(require_permissions(Permission.ORDER_READ))]
OrderWriter = Annotated[RequestContext, Depends(require_permissions(Permission.ORDER_WRITE))]
OrderConfirmer = Annotated[RequestContext, Depends(require_permissions(Permission.ORDER_CONFIRM))]


@router.get("", response_model=SalesOrderListResponse)
def list_sales_orders(
    context: OrderReader,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: UUID | None = None,
) -> SalesOrderListResponse:
    orders = SalesOrderQueryService(SalesOrderRepository(session)).list(
        context, limit=limit + 1, cursor=cursor
    )
    page = list(orders[:limit])
    has_more = len(orders) > limit
    return SalesOrderListResponse(
        items=page,
        count=len(page),
        has_more=has_more,
        next_cursor=page[-1].id if has_more else None,
    )


@router.post("", response_model=SalesOrderResponse, status_code=201)
def create_sales_order(
    request: SalesOrderCreate,
    context: OrderWriter,
    factory: SessionFactory,
    key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ] = None,
) -> SalesOrderResponse:
    return SalesOrderCommandService(factory).create(context, request.model_dump(), key=key)


@router.get("/{sales_order_id}", response_model=SalesOrderResponse)
def read_sales_order(
    sales_order_id: UUID, context: OrderReader, session: DatabaseSession
) -> SalesOrderResponse:
    return SalesOrderQueryService(SalesOrderRepository(session)).get(context, sales_order_id)


@router.post("/{sales_order_id}/confirm", response_model=SalesOrderResponse)
def confirm_sales_order(
    sales_order_id: UUID,
    request: SalesOrderConfirm,
    context: OrderConfirmer,
    factory: SessionFactory,
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)],
) -> SalesOrderResponse:
    return SalesOrderCommandService(factory).confirm(context, sales_order_id, request, key=key)
