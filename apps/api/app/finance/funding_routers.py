from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.finance.funding import FundingEstimateResponse, FundingQuery

router = APIRouter(prefix="/api/v1/sales-orders", tags=["finance"], responses=PROBLEM_RESPONSES)
Reader = Annotated[
    RequestContext,
    Depends(
        require_permissions(
            Permission.ORDER_READ,
            Permission.EXPENSE_READ,
            Permission.RECEIVABLE_READ,
            Permission.PROFIT_READ,
        )
    ),
]


@router.get("/{order_id}/funding-estimate", response_model=FundingEstimateResponse)
def funding_estimate(
    order_id: UUID,
    context: Reader,
    session: Annotated[Session, Depends(get_database_session)],
) -> FundingEstimateResponse:
    return FundingQuery(session).get(context, order_id)
