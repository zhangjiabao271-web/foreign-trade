from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.procurement.repositories import PurchaseOrderRepository
from app.procurement.schemas import (
    PurchaseOrderAmend,
    PurchaseOrderCancel,
    PurchaseOrderClose,
    PurchaseOrderConfirm,
    PurchaseOrderCreate,
    PurchaseOrderDecision,
    PurchaseOrderListResponse,
    PurchaseOrderReceive,
    PurchaseOrderResponse,
)
from app.procurement.services import (
    PurchaseOrderCommandService,
    PurchaseOrderQueryService,
)
from app.work.schemas import ActivityListResponse

router = APIRouter(
    prefix="/api/v1/purchase-orders", tags=["purchase-orders"], responses=PROBLEM_RESPONSES
)
DatabaseSession = Annotated[Session, Depends(get_database_session)]
SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
PurchaseReader = Annotated[
    RequestContext, Depends(require_permissions(Permission.PROCUREMENT_READ))
]
PurchaseWriter = Annotated[
    RequestContext, Depends(require_permissions(Permission.PROCUREMENT_WRITE))
]
PurchaseApprover = Annotated[
    RequestContext,
    Depends(require_permissions(Permission.PROCUREMENT_APPROVE, Permission.PROFIT_READ)),
]
PurchaseCreator = Annotated[
    RequestContext,
    Depends(require_permissions(Permission.PROCUREMENT_WRITE, Permission.PROFIT_READ)),
]
CommandKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]


@router.get("", response_model=PurchaseOrderListResponse)
def list_purchase_orders(
    context: PurchaseReader,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: UUID | None = None,
    sales_order_id: UUID | None = None,
) -> PurchaseOrderListResponse:
    rows = PurchaseOrderQueryService(PurchaseOrderRepository(session)).list(
        context,
        limit=limit + 1,
        cursor=cursor,
        sales_order_id=sales_order_id,
    )
    orders = rows[:limit]
    return PurchaseOrderListResponse(
        items=list(orders),
        count=len(orders),
        has_more=len(rows) > limit,
        next_cursor=orders[-1].id if len(rows) > limit else None,
    )


@router.post("", response_model=PurchaseOrderResponse, status_code=201)
def create_purchase_order(
    request: PurchaseOrderCreate,
    context: PurchaseCreator,
    factory: SessionFactory,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=255,
            description="Reuse the same key and body for retries. Omission starts a new command.",
        ),
    ] = None,
) -> PurchaseOrderResponse:
    return PurchaseOrderCommandService(factory).create(
        context,
        request.model_dump(),
        idempotency_key=idempotency_key if idempotency_key is not None else str(uuid4()),
    )


@router.get("/{purchase_order_id}", response_model=PurchaseOrderResponse)
def read_purchase_order(
    purchase_order_id: UUID, context: PurchaseReader, session: DatabaseSession
) -> PurchaseOrderResponse:
    return PurchaseOrderQueryService(PurchaseOrderRepository(session)).get(
        context, purchase_order_id
    )


@router.get("/{purchase_order_id}/activities", response_model=ActivityListResponse)
def purchase_activities(
    purchase_order_id: UUID,
    context: PurchaseReader,
    session: DatabaseSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ActivityListResponse:
    rows = PurchaseOrderQueryService(PurchaseOrderRepository(session)).activities(
        context, purchase_order_id, offset=offset, limit=limit
    )
    return ActivityListResponse(items=list(rows), count=len(rows))


@router.post("/{purchase_order_id}/approve", response_model=PurchaseOrderResponse)
def approve_purchase_order(
    purchase_order_id: UUID,
    request: PurchaseOrderDecision,
    context: PurchaseApprover,
    factory: SessionFactory,
    idempotency_key: CommandKey,
) -> PurchaseOrderResponse:
    return PurchaseOrderCommandService(factory).approve(
        context, purchase_order_id, request, idempotency_key=idempotency_key
    )


@router.post("/{purchase_order_id}/send", response_model=PurchaseOrderResponse)
def send_purchase_order(
    purchase_order_id: UUID,
    request: PurchaseOrderDecision,
    context: PurchaseWriter,
    factory: SessionFactory,
    idempotency_key: CommandKey,
) -> PurchaseOrderResponse:
    return PurchaseOrderCommandService(factory).send(
        context, purchase_order_id, request, idempotency_key=idempotency_key
    )


@router.post("/{purchase_order_id}/confirm", response_model=PurchaseOrderResponse)
def confirm_purchase_order(
    purchase_order_id: UUID,
    request: PurchaseOrderConfirm,
    context: PurchaseWriter,
    factory: SessionFactory,
    idempotency_key: CommandKey,
) -> PurchaseOrderResponse:
    return PurchaseOrderCommandService(factory).confirm(
        context, purchase_order_id, request, idempotency_key=idempotency_key
    )


@router.post("/{purchase_order_id}/receive", response_model=PurchaseOrderResponse)
def receive_purchase_order(
    purchase_order_id: UUID,
    request: PurchaseOrderReceive,
    context: PurchaseWriter,
    factory: SessionFactory,
    idempotency_key: CommandKey,
) -> PurchaseOrderResponse:
    return PurchaseOrderCommandService(factory).receive(
        context, purchase_order_id, request.model_dump(), idempotency_key=idempotency_key
    )


@router.post("/{purchase_order_id}/close", response_model=PurchaseOrderResponse)
def close_purchase_order(
    purchase_order_id: UUID,
    request: PurchaseOrderClose,
    context: PurchaseWriter,
    factory: SessionFactory,
    idempotency_key: CommandKey,
) -> PurchaseOrderResponse:
    return PurchaseOrderCommandService(factory).close(
        context, purchase_order_id, request.model_dump(), idempotency_key=idempotency_key
    )


@router.post("/{purchase_order_id}/cancel", response_model=PurchaseOrderResponse)
def cancel_purchase_order(
    purchase_order_id: UUID,
    request: PurchaseOrderCancel,
    context: PurchaseApprover,
    factory: SessionFactory,
    idempotency_key: CommandKey,
) -> PurchaseOrderResponse:
    return PurchaseOrderCommandService(factory).cancel(
        context, purchase_order_id, request.model_dump(), idempotency_key=idempotency_key
    )


@router.post("/{purchase_order_id}/amend", response_model=PurchaseOrderResponse)
def amend_purchase_order(
    purchase_order_id: UUID,
    request: PurchaseOrderAmend,
    context: PurchaseApprover,
    factory: SessionFactory,
    idempotency_key: CommandKey,
) -> PurchaseOrderResponse:
    return PurchaseOrderCommandService(factory).amend(
        context, purchase_order_id, request.model_dump(), idempotency_key=idempotency_key
    )
