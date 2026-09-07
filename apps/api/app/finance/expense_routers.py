from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.finance.expense_models import Expense
from app.finance.expense_schemas import (
    ExpenseCreate,
    ExpenseListResponse,
    ExpenseResponse,
    ExpenseReverse,
    ExpenseSummary,
)
from app.finance.expense_services import ExpenseQuery, ExpenseService

router = APIRouter(
    prefix="/api/v1/sales-orders/{order_id}/expenses",
    tags=["expenses"],
    responses=PROBLEM_RESPONSES,
)
DatabaseSession = Annotated[Session, Depends(get_database_session)]
Factory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
Reader = Annotated[RequestContext, Depends(require_permissions(Permission.EXPENSE_READ))]
ProfitReader = Annotated[
    RequestContext, Depends(require_permissions(Permission.EXPENSE_READ, Permission.PROFIT_READ))
]
Writer = Annotated[RequestContext, Depends(require_permissions(Permission.EXPENSE_WRITE))]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=160)]


def response(row: Expense, reversal_id: UUID | None = None) -> ExpenseResponse:
    return ExpenseResponse.model_validate(row).model_copy(
        update={"reversed_by_expense_id": reversal_id}
    )


@router.get("", response_model=ExpenseListResponse)
def list_expenses(
    order_id: UUID,
    context: Reader,
    session: DatabaseSession,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ExpenseListResponse:
    rows, reversals = ExpenseQuery(session).list(context, order_id, cursor=cursor, limit=limit)
    page = rows[:limit]
    return ExpenseListResponse(
        items=[response(row, reversals.get(row.id)) for row in page],
        has_more=len(rows) > limit,
        next_cursor=page[-1].id if len(rows) > limit else None,
    )


@router.get("/summary", response_model=ExpenseSummary)
def expense_summary(
    order_id: UUID, context: ProfitReader, session: DatabaseSession
) -> ExpenseSummary:
    return ExpenseQuery(session).summary(context, order_id)


@router.get("/{expense_id}", response_model=ExpenseResponse)
def read_expense(
    order_id: UUID, expense_id: UUID, context: Reader, session: DatabaseSession
) -> ExpenseResponse:
    return response(*ExpenseQuery(session).get(context, order_id, expense_id))


@router.post("", response_model=ExpenseResponse, status_code=201)
def record_expense(
    order_id: UUID, request: ExpenseCreate, context: Writer, factory: Factory, key: Key
) -> ExpenseResponse:
    return response(
        ExpenseService(factory).record(context, order_id, request.model_dump(), key=key)
    )


@router.post("/{expense_id}/reverse", response_model=ExpenseResponse, status_code=201)
def reverse_expense(
    order_id: UUID,
    expense_id: UUID,
    request: ExpenseReverse,
    context: Writer,
    factory: Factory,
    key: Key,
) -> ExpenseResponse:
    return response(
        ExpenseService(factory).reverse(
            context, order_id, expense_id, request.model_dump(), key=key
        )
    )
