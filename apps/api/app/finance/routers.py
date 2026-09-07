from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.finance.enums import PaymentKind, PaymentMethod, PaymentStatus, ReceivableInstallmentType
from app.finance.payment_text_review import (
    PaymentTextReviewRequest,
    PaymentTextReviewResponse,
    PaymentTextReviewService,
)
from app.finance.repositories import PaymentRepository, ReceivableRepository
from app.finance.schemas import (
    PaymentAllocate,
    PaymentAllocationResponse,
    PaymentCreate,
    PaymentListResponse,
    PaymentResponse,
    PaymentReverse,
    ReceivableGenerate,
    ReceivableListResponse,
    ReceivableResponse,
    SalesOrderComplete,
)
from app.finance.services import (
    PaymentAggregate,
    PaymentCommandService,
    PaymentQueryService,
    ReceivableAggregate,
    ReceivableCommandService,
    ReceivableQueryService,
    organization_today,
    status_for_receivable,
)
from app.sales.completion_services import OrderCompletionService
from app.sales.order_schemas import SalesOrderResponse

router = APIRouter(prefix="/api/v1", tags=["finance"], responses=PROBLEM_RESPONSES)
DatabaseSession = Annotated[Session, Depends(get_database_session)]
SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
ReceivableReader = Annotated[
    RequestContext, Depends(require_permissions(Permission.RECEIVABLE_READ))
]
ReceivableWriter = Annotated[
    RequestContext, Depends(require_permissions(Permission.RECEIVABLE_WRITE))
]
PaymentReader = Annotated[RequestContext, Depends(require_permissions(Permission.PAYMENT_READ))]
PaymentRecorder = Annotated[RequestContext, Depends(require_permissions(Permission.PAYMENT_RECORD))]
PaymentAllocator = Annotated[
    RequestContext, Depends(require_permissions(Permission.PAYMENT_ALLOCATE))
]
PaymentReverser = Annotated[
    RequestContext, Depends(require_permissions(Permission.PAYMENT_REVERSE))
]
OrderCompleter = Annotated[RequestContext, Depends(require_permissions(Permission.ORDER_COMPLETE))]
CommandKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]
PaymentReviewer = Annotated[
    RequestContext,
    Depends(require_permissions(Permission.PROFIT_READ, Permission.PAYMENT_READ)),
]


@router.get("/payments/{payment_id}/text-review", response_model=PaymentTextReviewResponse)
def inspect_payment_text(
    payment_id: UUID, context: PaymentReviewer, factory: SessionFactory
) -> PaymentTextReviewResponse:
    return PaymentTextReviewService(factory).inspect(context, payment_id)


@router.post("/payments/{payment_id}/text-review", response_model=PaymentTextReviewResponse)
def review_payment_text(
    payment_id: UUID,
    request: PaymentTextReviewRequest,
    context: PaymentReviewer,
    factory: SessionFactory,
    idempotency_key: CommandKey,
) -> PaymentTextReviewResponse:
    return PaymentTextReviewService(factory).decide(
        context, payment_id, request, key=idempotency_key
    )


def receivable_response(pair: ReceivableAggregate, today: date) -> ReceivableResponse:
    item, paid = pair
    return ReceivableResponse(
        id=item.id,
        receivable_number=item.receivable_number,
        sales_order_id=item.sales_order_id,
        installment_type=ReceivableInstallmentType(item.installment_type),
        status=status_for_receivable(item, paid, today=today),
        amount=item.amount,
        paid_amount=paid,
        balance=item.amount - paid,
        currency_code=item.currency_code,
        due_date=item.due_date,
        paid_at=item.paid_at,
        created_at=item.created_at,
    )


def payment_response(aggregate: PaymentAggregate) -> PaymentResponse:
    item, allocated, allocations = aggregate
    available = item.amount - allocated
    if item.kind != PaymentKind.RECEIPT or item.status != PaymentStatus.ACTIVE:
        available = Decimal("0")
    return PaymentResponse(
        id=item.id,
        payment_number=item.payment_number,
        company_id=item.company_id,
        kind=PaymentKind(item.kind),
        status=PaymentStatus(item.status),
        reversal_of_payment_id=item.reversal_of_payment_id,
        amount=item.amount,
        allocated_amount=allocated,
        available_amount=available,
        currency_code=item.currency_code,
        method=PaymentMethod(item.method),
        reference=item.reference,
        notes=item.notes,
        version=item.version,
        content_visible=item.content_visible,
        released=item.released,
        received_at=item.received_at,
        reversed_at=item.reversed_at,
        created_at=item.created_at,
        allocations=[
            PaymentAllocationResponse.model_validate(row)
            for row in sorted(allocations, key=lambda row: (row.allocated_at, row.id))
        ],
    )


@router.get("/receivables", response_model=ReceivableListResponse)
def list_receivables(
    context: ReceivableReader,
    session: DatabaseSession,
    sales_order_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ReceivableListResponse:
    rows = ReceivableQueryService(ReceivableRepository(session)).list(
        context,
        sales_order_id=sales_order_id,
        limit=limit,
    )
    today = organization_today(session, context.organization_id)
    return ReceivableListResponse(
        items=[receivable_response(row, today) for row in rows], count=len(rows)
    )


@router.post(
    "/sales-orders/{sales_order_id}/generate-receivables", response_model=ReceivableListResponse
)
def generate_receivables(
    sales_order_id: UUID,
    request: ReceivableGenerate,
    context: ReceivableWriter,
    factory: SessionFactory,
    session: DatabaseSession,
) -> ReceivableListResponse:
    rows = ReceivableCommandService(factory).generate_for_order(
        context, sales_order_id, request.model_dump()
    )
    today = organization_today(session, context.organization_id)
    return ReceivableListResponse(
        items=[receivable_response(row, today) for row in rows], count=len(rows)
    )


@router.post("/receivables/refresh-statuses", response_model=ReceivableListResponse)
def refresh_receivables(
    context: ReceivableWriter,
    factory: SessionFactory,
    session: DatabaseSession,
) -> ReceivableListResponse:
    rows = ReceivableCommandService(factory).refresh_statuses(context)
    today = organization_today(session, context.organization_id)
    return ReceivableListResponse(
        items=[receivable_response(row, today) for row in rows], count=len(rows)
    )


@router.get("/payments", response_model=PaymentListResponse)
def list_payments(
    context: PaymentReader,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    company_id: UUID | None = None,
    currency_code: Annotated[str | None, Query(pattern=r"^[A-Z]{3}$")] = None,
    query: Annotated[str | None, Query(max_length=160)] = None,
    cursor: UUID | None = None,
) -> PaymentListResponse:
    rows = PaymentQueryService(PaymentRepository(session)).list(
        context,
        limit=limit + 1,
        company_id=company_id,
        currency_code=currency_code,
        query=query,
        cursor=cursor,
    )
    page = rows[:limit]
    has_more = len(rows) > limit
    return PaymentListResponse(
        items=[payment_response(row) for row in page],
        count=len(page),
        has_more=has_more,
        next_cursor=page[-1][0].id if has_more else None,
    )


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
def read_payment(
    payment_id: UUID, context: PaymentReader, session: DatabaseSession
) -> PaymentResponse:
    return payment_response(
        PaymentQueryService(PaymentRepository(session)).get(context, payment_id)
    )


@router.post("/payments", response_model=PaymentResponse, status_code=201)
def record_payment(
    request: PaymentCreate,
    context: PaymentRecorder,
    factory: SessionFactory,
    idempotency_key: CommandKey,
) -> PaymentResponse:
    return payment_response(
        PaymentCommandService(factory).create(
            context,
            request.model_dump(),
            idempotency_key=idempotency_key,
        )
    )


@router.post("/payments/{payment_id}/allocate", response_model=PaymentResponse)
def allocate_payment(
    payment_id: UUID,
    request: PaymentAllocate,
    context: PaymentAllocator,
    factory: SessionFactory,
    idempotency_key: CommandKey,
) -> PaymentResponse:
    return payment_response(
        PaymentCommandService(factory).allocate(
            context,
            payment_id,
            request.model_dump(),
            idempotency_key=idempotency_key,
        )
    )


@router.post("/payments/{payment_id}/reverse", response_model=PaymentResponse)
def reverse_payment(
    payment_id: UUID,
    request: PaymentReverse,
    context: PaymentReverser,
    factory: SessionFactory,
) -> PaymentResponse:
    return payment_response(
        PaymentCommandService(factory).reverse(context, payment_id, reason=request.reason)
    )


@router.post("/sales-orders/{sales_order_id}/complete", response_model=SalesOrderResponse)
def complete_order(
    sales_order_id: UUID,
    request: SalesOrderComplete,
    context: OrderCompleter,
    factory: SessionFactory,
) -> SalesOrderResponse:
    return OrderCompletionService(factory).complete(context, sales_order_id, request.model_dump())
