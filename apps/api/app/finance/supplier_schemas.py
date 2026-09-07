from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.finance.enums import PaymentMethod


class FinancialInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    reason: str = Field(min_length=3, max_length=500)


class PayableCreate(FinancialInput):
    purchase_order_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    incurred_on: date
    due_date: date
    reference: str = Field(min_length=3, max_length=240)
    description: str = Field(min_length=3, max_length=500)


class SupplierVersionCommand(FinancialInput):
    expected_version: int = Field(ge=1)


class SupplierPaymentCreate(FinancialInput):
    supplier_company_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    currency_code: str = Field(pattern=r"^[A-Z]{3}$")
    paid_on: date
    method: PaymentMethod
    reference: str = Field(min_length=3, max_length=240)


class SupplierAllocationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    payable_id: UUID
    expected_version: int = Field(ge=1)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)


class SupplierPaymentAllocate(SupplierVersionCommand):
    allocations: list[SupplierAllocationInput] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_payables(self) -> "SupplierPaymentAllocate":
        if len({row.payable_id for row in self.allocations}) != len(self.allocations):
            raise ValueError("Each payable may appear only once per command")
        return self


class PayableResponse(PayableCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version: int
    payable_number: str
    sales_order_id: UUID
    supplier_company_id: UUID
    currency_code: str
    created_at: datetime
    voided_at: datetime | None
    void_reason: str | None
    paid_amount: Decimal
    balance: Decimal
    status: Literal["PENDING", "DUE", "OVERDUE", "PARTIALLY_PAID", "PAID", "VOIDED"]


class SupplierAllocationResponse(FinancialInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    payment_id: UUID
    payable_id: UUID
    kind: Literal["ALLOCATION", "REVERSAL"]
    amount: Decimal
    reversal_of_allocation_id: UUID | None
    created_at: datetime


class SupplierPaymentResponse(SupplierPaymentCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version: int
    payment_number: str
    kind: Literal["PAYMENT", "REVERSAL"]
    reversal_of_payment_id: UUID | None
    reversed_by_payment_id: UUID | None
    created_at: datetime
    allocated_amount: Decimal
    available_amount: Decimal
    allocations: list[SupplierAllocationResponse]


class PayableListResponse(BaseModel):
    items: list[PayableResponse]
    has_more: bool
    next_cursor: UUID | None


class SupplierPaymentListResponse(BaseModel):
    items: list[SupplierPaymentResponse]
    has_more: bool
    next_cursor: UUID | None
