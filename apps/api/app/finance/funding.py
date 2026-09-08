from decimal import Decimal, localcontext
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.finance.enums import AllocationKind
from app.finance.expense_models import Expense, ExpenseKind, ExpenseTreatment
from app.finance.models import PaymentAllocation, Receivable
from app.sales.models import SalesOrder
from app.sales.services import quantize_money


class FundingEstimateResponse(BaseModel):
    sales_order_id: UUID
    currency_code: str
    quoted_total_cost: Decimal
    net_additional_cost: Decimal
    net_allocated_receipts: Decimal
    estimated_funding_need: Decimal


class FundingRepository:
    def __init__(self, session: Session):
        self.session = session

    def inputs(
        self, organization_id: UUID, order_id: UUID
    ) -> tuple[str, Decimal, Decimal, Decimal]:
        # Correlated aggregates share one PostgreSQL statement snapshot; no paginated totals.
        expenses = (
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (Expense.kind == ExpenseKind.REVERSAL, -Expense.order_currency_amount),
                            else_=Expense.order_currency_amount,
                        )
                    ),
                    0,
                )
            )
            .where(
                Expense.organization_id == organization_id,
                Expense.sales_order_id == SalesOrder.id,
                Expense.order_currency_code == SalesOrder.currency_code,
                Expense.cost_treatment == ExpenseTreatment.ADDITIONAL,
                Expense.deleted_at.is_(None),
            )
            .correlate(SalesOrder)
            .scalar_subquery()
        )
        receipts = (
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                PaymentAllocation.kind == AllocationKind.REVERSAL,
                                -PaymentAllocation.amount,
                            ),
                            else_=PaymentAllocation.amount,
                        )
                    ),
                    0,
                )
            )
            .join(
                Receivable,
                (
                    (Receivable.organization_id == PaymentAllocation.organization_id)
                    & (Receivable.id == PaymentAllocation.receivable_id)
                ),
            )
            .where(
                PaymentAllocation.organization_id == organization_id,
                PaymentAllocation.deleted_at.is_(None),
                Receivable.organization_id == organization_id,
                Receivable.sales_order_id == SalesOrder.id,
                Receivable.currency_code == SalesOrder.currency_code,
                Receivable.deleted_at.is_(None),
            )
            .correlate(SalesOrder)
            .scalar_subquery()
        )
        row = self.session.execute(
            select(
                SalesOrder.currency_code,
                SalesOrder.total_cost,
                expenses,
                receipts,
            ).where(
                SalesOrder.organization_id == organization_id,
                SalesOrder.id == order_id,
                SalesOrder.deleted_at.is_(None),
            )
        ).one_or_none()
        if row is None:
            raise ApiProblem(
                404, "SALES_ORDER_NOT_FOUND", "Order not found", "The order was not found."
            )
        currency, cost, additional, allocated = row
        return currency, Decimal(cost), Decimal(additional), Decimal(allocated)


class FundingQuery:
    def __init__(self, session: Session):
        self.repository = FundingRepository(session)

    def get(self, context: RequestContext, order_id: UUID) -> FundingEstimateResponse:
        context.require(
            Permission.ORDER_READ,
            Permission.EXPENSE_READ,
            Permission.RECEIVABLE_READ,
            Permission.PROFIT_READ,
        )
        currency, cost, additional, allocated = self.repository.inputs(
            context.organization_id, order_id
        )
        with localcontext() as precision:
            precision.prec = 50
            return FundingEstimateResponse(
                sales_order_id=order_id,
                currency_code=currency,
                quoted_total_cost=quantize_money(cost),
                net_additional_cost=quantize_money(additional),
                net_allocated_receipts=quantize_money(allocated),
                estimated_funding_need=quantize_money(
                    max(cost + additional - allocated, Decimal(0))
                ),
            )
