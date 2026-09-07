from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.finance.supplier_queries import SupplierFinanceQuery
from app.finance.supplier_schemas import (
    PayableCreate,
    PayableListResponse,
    PayableResponse,
    SupplierPaymentAllocate,
    SupplierPaymentCreate,
    SupplierPaymentListResponse,
    SupplierPaymentResponse,
    SupplierVersionCommand,
)
from app.finance.supplier_services import SupplierFinanceService

router = APIRouter(prefix="/api/v1", tags=["supplier-finance"], responses=PROBLEM_RESPONSES)
DatabaseSession = Annotated[Session, Depends(get_database_session)]
Factory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
PayableReader = Annotated[RequestContext, Depends(require_permissions(Permission.PAYABLE_READ))]
PayableWriter = Annotated[RequestContext, Depends(require_permissions(Permission.PAYABLE_WRITE))]
PaymentReader = Annotated[
    RequestContext, Depends(require_permissions(Permission.SUPPLIER_PAYMENT_READ))
]
PaymentWriter = Annotated[
    RequestContext, Depends(require_permissions(Permission.SUPPLIER_PAYMENT_RECORD))
]
PaymentAllocator = Annotated[
    RequestContext, Depends(require_permissions(Permission.SUPPLIER_PAYMENT_ALLOCATE))
]
PaymentReverser = Annotated[
    RequestContext, Depends(require_permissions(Permission.SUPPLIER_PAYMENT_REVERSE))
]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=160)]
Limit = Annotated[int, Query(ge=1, le=100)]
Currency = Annotated[str | None, Query(pattern=r"^[A-Z]{3}$")]


@router.get("/payables", response_model=PayableListResponse)
def list_payables(
    context: PayableReader,
    session: DatabaseSession,
    purchase_order_id: UUID | None = None,
    supplier_company_id: UUID | None = None,
    currency_code: Currency = None,
    cursor: UUID | None = None,
    limit: Limit = 20,
) -> PayableListResponse:
    return SupplierFinanceQuery(session).payables(
        context,
        purchase_id=purchase_order_id,
        supplier_id=supplier_company_id,
        currency=currency_code,
        cursor=cursor,
        limit=limit,
    )


@router.get("/payables/{payable_id}", response_model=PayableResponse)
def read_payable(
    payable_id: UUID, context: PayableReader, session: DatabaseSession
) -> PayableResponse:
    return SupplierFinanceQuery(session).payable(context, payable_id)


@router.post("/payables", response_model=PayableResponse, status_code=201)
def create_payable(
    request: PayableCreate,
    context: PayableWriter,
    factory: Factory,
    session: DatabaseSession,
    key: Key,
) -> PayableResponse:
    resource = SupplierFinanceService(factory).create_payable(
        context, request.model_dump(), key=key
    )
    return SupplierFinanceQuery(session).payable(context, resource)


@router.post("/payables/{payable_id}/void", response_model=PayableResponse)
def void_payable(
    payable_id: UUID,
    request: SupplierVersionCommand,
    context: PayableWriter,
    factory: Factory,
    session: DatabaseSession,
    key: Key,
) -> PayableResponse:
    resource = SupplierFinanceService(factory).void_payable(
        context, payable_id, request.model_dump(), key=key
    )
    return SupplierFinanceQuery(session).payable(context, resource)


@router.get("/supplier-payments", response_model=SupplierPaymentListResponse)
def list_payments(
    context: PaymentReader,
    session: DatabaseSession,
    supplier_company_id: UUID | None = None,
    currency_code: Currency = None,
    cursor: UUID | None = None,
    limit: Limit = 20,
) -> SupplierPaymentListResponse:
    return SupplierFinanceQuery(session).payments(
        context, supplier_id=supplier_company_id, currency=currency_code, cursor=cursor, limit=limit
    )


@router.get("/supplier-payments/{payment_id}", response_model=SupplierPaymentResponse)
def read_payment(
    payment_id: UUID, context: PaymentReader, session: DatabaseSession
) -> SupplierPaymentResponse:
    return SupplierFinanceQuery(session).payment(context, payment_id)


@router.post("/supplier-payments", response_model=SupplierPaymentResponse, status_code=201)
def record_payment(
    request: SupplierPaymentCreate,
    context: PaymentWriter,
    factory: Factory,
    session: DatabaseSession,
    key: Key,
) -> SupplierPaymentResponse:
    resource = SupplierFinanceService(factory).record_payment(
        context, request.model_dump(), key=key
    )
    return SupplierFinanceQuery(session).payment(context, resource)


@router.post("/supplier-payments/{payment_id}/allocate", response_model=SupplierPaymentResponse)
def allocate_payment(
    payment_id: UUID,
    request: SupplierPaymentAllocate,
    context: PaymentAllocator,
    factory: Factory,
    session: DatabaseSession,
    key: Key,
) -> SupplierPaymentResponse:
    resource = SupplierFinanceService(factory).allocate(
        context, payment_id, request.model_dump(), key=key
    )
    return SupplierFinanceQuery(session).payment(context, resource)


@router.post(
    "/supplier-payments/{payment_id}/reverse",
    response_model=SupplierPaymentResponse,
    status_code=201,
)
def reverse_payment(
    payment_id: UUID,
    request: SupplierVersionCommand,
    context: PaymentReverser,
    factory: Factory,
    session: DatabaseSession,
    key: Key,
) -> SupplierPaymentResponse:
    resource = SupplierFinanceService(factory).reverse(
        context, payment_id, request.model_dump(), key=key
    )
    return SupplierFinanceQuery(session).payment(context, resource)
