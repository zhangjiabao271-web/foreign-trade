from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.crm.text_review import (
    CrmTextKind,
    CrmTextReviewRequest,
    CrmTextReviewResponse,
    CrmTextReviewService,
)

router = APIRouter(prefix="/api/v1/crm-text", tags=["crm-text"], responses=PROBLEM_RESPONSES)
Reviewer = Annotated[RequestContext, Depends(require_permissions(Permission.PROFIT_READ))]
Factory = Annotated[sessionmaker[Session], Depends(get_session_factory)]


@router.get("/{kind}/{record_id}/review", response_model=CrmTextReviewResponse)
def inspect_crm_text(
    kind: CrmTextKind, record_id: UUID, context: Reviewer, factory: Factory
) -> CrmTextReviewResponse:
    return CrmTextReviewService(factory).inspect(context, kind, record_id)


@router.post("/{kind}/{record_id}/review", response_model=CrmTextReviewResponse)
def review_crm_text(
    kind: CrmTextKind,
    record_id: UUID,
    request: CrmTextReviewRequest,
    context: Reviewer,
    factory: Factory,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=120)],
) -> CrmTextReviewResponse:
    return CrmTextReviewService(factory).decide(
        context, kind, record_id, request, key=idempotency_key
    )
