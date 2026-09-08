from collections.abc import Sequence
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.fulfillment.models import Shipment, ShipmentItem
from app.fulfillment.repositories import ShipmentRepository
from app.fulfillment.schemas import (
    ShipmentBook,
    ShipmentCreate,
    ShipmentDecision,
    ShipmentItemResponse,
    ShipmentListResponse,
    ShipmentResponse,
)
from app.fulfillment.services import ShipmentCommandService, ShipmentQueryService
from app.sales.order_schemas import SalesOrderSourceLinesResponse
from app.work.schemas import ActivityPageResponse
from app.work.services import WorkQueryService

router = APIRouter(prefix="/api/v1/shipments", tags=["shipments"], responses=PROBLEM_RESPONSES)
DatabaseSession = Annotated[Session, Depends(get_database_session)]
SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
ShipmentReader = Annotated[RequestContext, Depends(require_permissions(Permission.SHIPMENT_READ))]
ShipmentWriter = Annotated[RequestContext, Depends(require_permissions(Permission.SHIPMENT_WRITE))]
ShipmentOperator = Annotated[
    RequestContext, Depends(require_permissions(Permission.SHIPMENT_TRANSITION))
]
CommandKey = Annotated[str, Header(min_length=1, max_length=255)]


def shipment_response(
    shipment: Shipment, items: Sequence[ShipmentItem], missing: list[str]
) -> ShipmentResponse:
    return ShipmentResponse(
        **ShipmentResponse.model_validate(shipment).model_dump(
            exclude={"items", "missing_required_documents"}
        ),
        items=[ShipmentItemResponse.model_validate(item) for item in items],
        missing_required_documents=missing,
    )


@router.get("", response_model=ShipmentListResponse)
def list_shipments(
    context: ShipmentReader,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: UUID | None = None,
) -> ShipmentListResponse:
    rows = ShipmentQueryService(ShipmentRepository(session)).list(
        context, limit=limit + 1, cursor=cursor
    )
    aggregates = rows[:limit]
    return ShipmentListResponse(
        items=[shipment_response(*aggregate) for aggregate in aggregates],
        count=len(aggregates),
        has_more=len(rows) > limit,
        next_cursor=aggregates[-1][0].id if len(rows) > limit else None,
    )


@router.post("", response_model=ShipmentResponse, status_code=201)
def create_shipment(
    request: ShipmentCreate,
    context: ShipmentWriter,
    factory: SessionFactory,
    idempotency_key: Annotated[
        str | None,
        Header(
            min_length=1,
            max_length=255,
            description="Reuse for unchanged retries; omission requests a new shipment.",
        ),
    ] = None,
) -> ShipmentResponse:
    return shipment_response(
        *ShipmentCommandService(factory).create(
            context,
            request.model_dump(),
            idempotency_key=idempotency_key if idempotency_key is not None else str(uuid4()),
        )
    )


@router.get("/{shipment_id}", response_model=ShipmentResponse)
def read_shipment(
    shipment_id: UUID, context: ShipmentReader, session: DatabaseSession
) -> ShipmentResponse:
    return shipment_response(
        *ShipmentQueryService(ShipmentRepository(session)).get(context, shipment_id)
    )


@router.get("/{shipment_id}/activities", response_model=ActivityPageResponse)
def list_shipment_activities(
    shipment_id: UUID,
    context: ShipmentReader,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: UUID | None = None,
) -> ActivityPageResponse:
    return WorkQueryService(session).commercial_activities(
        context, "shipment", shipment_id, limit=limit, cursor=cursor
    )


@router.get("/{shipment_id}/source-lines", response_model=SalesOrderSourceLinesResponse)
def read_shipment_source_lines(
    shipment_id: UUID,
    context: Annotated[
        RequestContext,
        Depends(require_permissions(Permission.SHIPMENT_READ, Permission.ORDER_READ)),
    ],
    session: DatabaseSession,
) -> SalesOrderSourceLinesResponse:
    return ShipmentQueryService(ShipmentRepository(session)).source_lines(context, shipment_id)


@router.post("/{shipment_id}/book", response_model=ShipmentResponse)
def book_shipment(
    shipment_id: UUID,
    request: ShipmentBook,
    context: ShipmentOperator,
    factory: SessionFactory,
    idempotency_key: CommandKey,
) -> ShipmentResponse:
    return shipment_response(
        *ShipmentCommandService(factory).book(
            context, shipment_id, request, idempotency_key=idempotency_key
        )
    )


def transition(
    shipment_id: UUID,
    context: RequestContext,
    factory: sessionmaker[Session],
    command: str,
    request: ShipmentDecision,
    idempotency_key: str,
) -> ShipmentResponse:
    service = ShipmentCommandService(factory)
    handler = getattr(service, command)
    return shipment_response(
        *handler(context, shipment_id, request, idempotency_key=idempotency_key)
    )


@router.post("/{shipment_id}/ready", response_model=ShipmentResponse)
def ready_shipment(
    shipment_id: UUID,
    context: ShipmentOperator,
    factory: SessionFactory,
    request: ShipmentDecision,
    idempotency_key: CommandKey,
) -> ShipmentResponse:
    return transition(shipment_id, context, factory, "ready", request, idempotency_key)


@router.post("/{shipment_id}/enter-customs", response_model=ShipmentResponse)
def enter_customs(
    shipment_id: UUID,
    context: ShipmentOperator,
    factory: SessionFactory,
    request: ShipmentDecision,
    idempotency_key: CommandKey,
) -> ShipmentResponse:
    return transition(shipment_id, context, factory, "enter_customs", request, idempotency_key)


@router.post("/{shipment_id}/depart", response_model=ShipmentResponse)
def depart_shipment(
    shipment_id: UUID,
    context: ShipmentOperator,
    factory: SessionFactory,
    request: ShipmentDecision,
    idempotency_key: CommandKey,
) -> ShipmentResponse:
    return transition(shipment_id, context, factory, "depart", request, idempotency_key)


@router.post("/{shipment_id}/start-transit", response_model=ShipmentResponse)
def start_transit(
    shipment_id: UUID,
    context: ShipmentOperator,
    factory: SessionFactory,
    request: ShipmentDecision,
    idempotency_key: CommandKey,
) -> ShipmentResponse:
    return transition(shipment_id, context, factory, "start_transit", request, idempotency_key)


@router.post("/{shipment_id}/arrive", response_model=ShipmentResponse)
def arrive_shipment(
    shipment_id: UUID,
    context: ShipmentOperator,
    factory: SessionFactory,
    request: ShipmentDecision,
    idempotency_key: CommandKey,
) -> ShipmentResponse:
    return transition(shipment_id, context, factory, "arrive", request, idempotency_key)


@router.post("/{shipment_id}/deliver", response_model=ShipmentResponse)
def deliver_shipment(
    shipment_id: UUID,
    context: ShipmentOperator,
    factory: SessionFactory,
    request: ShipmentDecision,
    idempotency_key: CommandKey,
) -> ShipmentResponse:
    return transition(shipment_id, context, factory, "deliver", request, idempotency_key)
