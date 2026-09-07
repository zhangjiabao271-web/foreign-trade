from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.sales.text_review import (
    CommercialTextKind,
    CommercialTextReviewRequest,
    CommercialTextReviewResponse,
    CommercialTextReviewService,
)

router = APIRouter(
    prefix="/api/v1/commercial-text", tags=["commercial-text"], responses=PROBLEM_RESPONSES
)
Reviewer = Annotated[RequestContext, Depends(require_permissions(Permission.PROFIT_READ))]
Factory = Annotated[sessionmaker[Session], Depends(get_session_factory)]


@router.get("/{kind}/{record_id}/review", response_model=CommercialTextReviewResponse)
def inspect_commercial_text(
    kind: CommercialTextKind, record_id: UUID, context: Reviewer, factory: Factory
) -> CommercialTextReviewResponse:
    return CommercialTextReviewService(factory).inspect(context, kind, record_id)


@router.post("/{kind}/{record_id}/review", response_model=CommercialTextReviewResponse)
def review_commercial_text(
    kind: CommercialTextKind,
    record_id: UUID,
    request: CommercialTextReviewRequest,
    context: Reviewer,
    factory: Factory,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=120)],
) -> CommercialTextReviewResponse:
    return CommercialTextReviewService(factory).decide(
        context, kind, record_id, request, key=idempotency_key
    )
