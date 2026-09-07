from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.inquiries.enums import InquiryStatus
from app.inquiries.repositories import InquiryRepository
from app.inquiries.schemas import InquiryCreate, InquiryListResponse, InquiryResponse
from app.inquiries.services import InquiryCommandService, InquiryQueryService

router = APIRouter(prefix="/api/v1/inquiries", tags=["inquiries"], responses=PROBLEM_RESPONSES)
DatabaseSession = Annotated[Session, Depends(get_database_session)]
SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
InquiryReader = Annotated[RequestContext, Depends(require_permissions(Permission.INQUIRY_READ))]
InquiryWriter = Annotated[RequestContext, Depends(require_permissions(Permission.INQUIRY_WRITE))]


@router.get("", response_model=InquiryListResponse)
def list_inquiries(
    context: InquiryReader,
    session: DatabaseSession,
    status: InquiryStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: UUID | None = None,
) -> InquiryListResponse:
    rows = InquiryQueryService(InquiryRepository(session)).list(
        context, status=status, limit=limit + 1, cursor=cursor
    )
    inquiries = rows[:limit]
    return InquiryListResponse(
        items=[InquiryResponse.model_validate(inquiry) for inquiry in inquiries],
        count=len(inquiries),
        has_more=len(rows) > limit,
        next_cursor=inquiries[-1].id if len(rows) > limit else None,
    )


@router.post("", response_model=InquiryResponse, status_code=201)
def create_inquiry(
    request: InquiryCreate,
    context: InquiryWriter,
    factory: SessionFactory,
    key: Annotated[
        str | None, Header(alias="Idempotency-Key", min_length=1, max_length=255)
    ] = None,
) -> InquiryResponse:
    inquiry = InquiryCommandService(factory).create(context, request.model_dump(), key=key)
    return InquiryResponse.model_validate(inquiry)


@router.get("/{inquiry_id}", response_model=InquiryResponse)
def read_inquiry(
    inquiry_id: UUID, context: InquiryReader, session: DatabaseSession
) -> InquiryResponse:
    inquiry = InquiryQueryService(InquiryRepository(session)).get(context, inquiry_id)
    return InquiryResponse.model_validate(inquiry)
