from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.catalog.text_review import (
    ProductTextReviewRequest,
    ProductTextReviewResponse,
    ProductTextReviewService,
)

router = APIRouter(prefix="/api/v1/products", tags=["product-text"], responses=PROBLEM_RESPONSES)
Reviewer = Annotated[
    RequestContext, Depends(require_permissions(Permission.PROFIT_READ, Permission.PRODUCT_READ))
]
Factory = Annotated[sessionmaker[Session], Depends(get_session_factory)]


@router.get("/{record_id}/text-review", response_model=ProductTextReviewResponse)
def inspect_product_text(
    record_id: UUID, context: Reviewer, factory: Factory
) -> ProductTextReviewResponse:
    return ProductTextReviewService(factory).inspect(context, record_id)


@router.post("/{record_id}/text-review", response_model=ProductTextReviewResponse)
def review_product_text(
    record_id: UUID,
    request: ProductTextReviewRequest,
    context: Reviewer,
    factory: Factory,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=120)],
) -> ProductTextReviewResponse:
    return ProductTextReviewService(factory).decide(
        context, record_id, request, key=idempotency_key
    )
