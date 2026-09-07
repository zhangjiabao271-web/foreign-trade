from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.finance.expense_models import ExpenseCategory, ExpenseKind, ExpenseTreatment


class ExpenseCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    category: ExpenseCategory
    cost_treatment: ExpenseTreatment
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    exchange_rate: Decimal = Field(gt=0, max_digits=18, decimal_places=8)
    incurred_on: date
    description: str = Field(min_length=3, max_length=500)
    evidence_reference: str = Field(min_length=3, max_length=240)
    reason: str = Field(min_length=3, max_length=500)


class ExpenseReverse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


class ExpenseResponse(ExpenseCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version: int
    sales_order_id: UUID
    expense_number: str
    kind: ExpenseKind
    order_currency_code: str
    order_currency_amount: Decimal
    reversal_of_expense_id: UUID | None
    reversed_by_expense_id: UUID | None = None
    created_at: datetime


class ExpenseListResponse(BaseModel):
    items: list[ExpenseResponse]
    has_more: bool
    next_cursor: UUID | None


class ExpenseSummary(BaseModel):
    order_currency_code: str
    net_additional_cost: Decimal
    net_included_cost: Decimal
    quoted_gross_profit: Decimal
    adjusted_forecast_gross_profit: Decimal
