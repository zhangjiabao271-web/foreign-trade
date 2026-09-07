from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header

from app.auth.context import RequestContext
from app.auth.dependencies import require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.work.activity_access import ActivitySubject
from app.work.review import WorkReviewRequest, WorkReviewResponse, WorkReviewService
from app.work.routers import SessionFactory

router = APIRouter(prefix="/api/v1/work", tags=["work"], responses=PROBLEM_RESPONSES)
Reviewer = Annotated[RequestContext, Depends(require_permissions(Permission.PROFIT_READ))]


@router.get(
    "/{subject_type}/{subject_id}/activities/{record_id}/review", response_model=WorkReviewResponse
)
def inspect_activity_review(
    subject_type: ActivitySubject,
    subject_id: UUID,
    record_id: UUID,
    context: Reviewer,
    factory: SessionFactory,
) -> WorkReviewResponse:
    return WorkReviewService(factory).inspect_activity(context, subject_type, subject_id, record_id)


@router.post(
    "/{subject_type}/{subject_id}/activities/{record_id}/review", response_model=WorkReviewResponse
)
def decide_activity_review(
    subject_type: ActivitySubject,
    subject_id: UUID,
    record_id: UUID,
    request: WorkReviewRequest,
    context: Reviewer,
    factory: SessionFactory,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=120)],
) -> WorkReviewResponse:
    return WorkReviewService(factory).decide_activity(
        context, subject_type, subject_id, record_id, request, key=idempotency_key
    )
