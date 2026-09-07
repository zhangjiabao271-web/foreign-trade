from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.inquiries.text_review import (
    InquiryTextReviewRequest,
    InquiryTextReviewResponse,
    InquiryTextReviewService,
)

router = APIRouter(prefix="/api/v1/inquiries", tags=["inquiry-text"], responses=PROBLEM_RESPONSES)
Reviewer = Annotated[
    RequestContext, Depends(require_permissions(Permission.PROFIT_READ, Permission.INQUIRY_READ))
]
Factory = Annotated[sessionmaker[Session], Depends(get_session_factory)]


@router.get("/{record_id}/text-review", response_model=InquiryTextReviewResponse)
def inspect_inquiry_text(
    record_id: UUID, context: Reviewer, factory: Factory
) -> InquiryTextReviewResponse:
    return InquiryTextReviewService(factory).inspect(context, record_id)


@router.post("/{record_id}/text-review", response_model=InquiryTextReviewResponse)
def review_inquiry_text(
    record_id: UUID,
    request: InquiryTextReviewRequest,
    context: Reviewer,
    factory: Factory,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=120)],
) -> InquiryTextReviewResponse:
    return InquiryTextReviewService(factory).decide(
        context, record_id, request, key=idempotency_key
    )
