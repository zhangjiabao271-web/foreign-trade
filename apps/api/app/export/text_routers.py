from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.export.text_review import (
    ExportTextKind,
    ExportTextReviewRequest,
    ExportTextReviewResponse,
    ExportTextReviewService,
)

router = APIRouter(prefix="/api/v1/export-text", tags=["export-text"], responses=PROBLEM_RESPONSES)
Reviewer = Annotated[RequestContext, Depends(require_permissions(Permission.PROFIT_READ))]
Factory = Annotated[sessionmaker[Session], Depends(get_session_factory)]


@router.get("/{kind}/{record_id}/review", response_model=ExportTextReviewResponse)
def inspect_export_text(
    kind: ExportTextKind, record_id: UUID, context: Reviewer, factory: Factory
) -> ExportTextReviewResponse:
    return ExportTextReviewService(factory).inspect(context, kind, record_id)


@router.post("/{kind}/{record_id}/review", response_model=ExportTextReviewResponse)
def review_export_text(
    kind: ExportTextKind,
    record_id: UUID,
    request: ExportTextReviewRequest,
    context: Reviewer,
    factory: Factory,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=120)],
) -> ExportTextReviewResponse:
    return ExportTextReviewService(factory).decide(
        context, kind, record_id, request, key=idempotency_key
    )
