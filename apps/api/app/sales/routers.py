from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.sales.enums import QuotationVersionStatus
from app.sales.repositories import QuotationRepository
from app.sales.schemas import (
    CustomerReviewCommand,
    CustomerReviewResult,
    QuotationCreate,
    QuotationListResponse,
    QuotationResponse,
    QuotationRevisionCreate,
    QuotationStateCommand,
    QuotationVersionResponse,
)
from app.sales.services import QuotationCommandService, QuotationQueryService
from app.work.schemas import ActivityPageResponse
from app.work.services import WorkQueryService

router = APIRouter(prefix="/api/v1/quotations", tags=["quotations"], responses=PROBLEM_RESPONSES)
DatabaseSession = Annotated[Session, Depends(get_database_session)]
SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
QuotationReader = Annotated[RequestContext, Depends(require_permissions(Permission.QUOTATION_READ))]
QuotationWriter = Annotated[
    RequestContext, Depends(require_permissions(Permission.QUOTATION_WRITE))
]
QuotationSubmitter = Annotated[
    RequestContext, Depends(require_permissions(Permission.QUOTATION_SUBMIT))
]
QuotationApprover = Annotated[
    RequestContext, Depends(require_permissions(Permission.QUOTATION_APPROVE))
]
QuotationSender = Annotated[RequestContext, Depends(require_permissions(Permission.QUOTATION_SEND))]
QuotationAccepter = Annotated[
    RequestContext, Depends(require_permissions(Permission.QUOTATION_ACCEPT))
]
CommandKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]


@router.get("", response_model=QuotationListResponse)
def list_quotations(
    context: QuotationReader,
    session: DatabaseSession,
    status: QuotationVersionStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: UUID | None = None,
) -> QuotationListResponse:
    rows = list(
        QuotationQueryService(QuotationRepository(session)).list(
            context, status=status, limit=limit + 1, cursor=cursor
        )
    )
    items = rows[:limit]
    return QuotationListResponse(
        items=items,
        count=len(items),
        has_more=len(rows) > limit,
        next_cursor=items[-1].id if len(rows) > limit else None,
    )


@router.post("", response_model=QuotationResponse, status_code=201)
def create_quotation(
    request: QuotationCreate,
    context: QuotationWriter,
    factory: SessionFactory,
    key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ] = None,
) -> QuotationResponse:
    return QuotationCommandService(factory).create(
        context, request.model_dump(exclude_unset=True), key=key
    )


@router.get("/{quotation_id}", response_model=QuotationResponse)
def read_quotation(
    quotation_id: UUID, context: QuotationReader, session: DatabaseSession
) -> QuotationResponse:
    return QuotationQueryService(QuotationRepository(session)).get(context, quotation_id)


@router.get("/{quotation_id}/activities", response_model=ActivityPageResponse)
def list_quotation_activities(
    quotation_id: UUID,
    context: QuotationReader,
    session: DatabaseSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: UUID | None = None,
) -> ActivityPageResponse:
    return WorkQueryService(session).commercial_activities(
        context, "quotation", quotation_id, limit=limit, cursor=cursor
    )


@router.post("/{quotation_id}/revisions", response_model=QuotationVersionResponse, status_code=201)
def revise_quotation(
    quotation_id: UUID,
    request: QuotationRevisionCreate,
    context: QuotationWriter,
    factory: SessionFactory,
    key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ] = None,
) -> QuotationVersionResponse:
    return QuotationCommandService(factory).revise(
        context,
        quotation_id,
        request.model_dump(exclude_unset=True),
        key=key if key is not None else str(uuid4()),
    )


@router.post("/{quotation_id}/submit", response_model=QuotationVersionResponse)
def submit_quotation(
    quotation_id: UUID,
    request: QuotationStateCommand,
    context: QuotationSubmitter,
    factory: SessionFactory,
    key: CommandKey,
) -> QuotationVersionResponse:
    return QuotationCommandService(factory).submit(context, quotation_id, request, key=key)


@router.post("/{quotation_id}/approve", response_model=QuotationVersionResponse)
def approve_quotation(
    quotation_id: UUID,
    request: QuotationStateCommand,
    context: QuotationApprover,
    factory: SessionFactory,
    key: CommandKey,
) -> QuotationVersionResponse:
    return QuotationCommandService(factory).approve(context, quotation_id, request, key=key)


@router.post("/{quotation_id}/send", response_model=QuotationVersionResponse)
def send_quotation(
    quotation_id: UUID,
    request: QuotationStateCommand,
    context: QuotationSender,
    factory: SessionFactory,
    key: CommandKey,
) -> QuotationVersionResponse:
    return QuotationCommandService(factory).send(context, quotation_id, request, key=key)


@router.post("/{quotation_id}/mark-customer-review", response_model=CustomerReviewResult)
def mark_customer_review(
    quotation_id: UUID,
    request: CustomerReviewCommand,
    context: QuotationSender,
    factory: SessionFactory,
    key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=160)],
) -> CustomerReviewResult:
    return CustomerReviewResult(
        id=QuotationCommandService(factory).mark_customer_review(
            context, quotation_id, request.model_dump(), key=key
        )
    )


@router.post("/{quotation_id}/expire", response_model=QuotationVersionResponse)
def expire_quotation(
    quotation_id: UUID,
    request: QuotationStateCommand,
    context: QuotationWriter,
    factory: SessionFactory,
    key: CommandKey,
) -> QuotationVersionResponse:
    return QuotationCommandService(factory).expire(context, quotation_id, request, key=key)


@router.post("/{quotation_id}/{command}", response_model=QuotationVersionResponse)
def resolve_quotation(
    quotation_id: UUID,
    command: Literal["accept", "reject"],
    request: QuotationStateCommand,
    context: QuotationAccepter,
    factory: SessionFactory,
    key: CommandKey,
) -> QuotationVersionResponse:
    service = QuotationCommandService(factory)
    return (
        service.accept(context, quotation_id, request, key=key)
        if command == "accept"
        else service.reject(context, quotation_id, request, key=key)
    )
