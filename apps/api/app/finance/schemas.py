from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.catalog.schemas import normalize_currency
from app.finance.enums import (
    AllocationKind,
    PaymentKind,
    PaymentMethod,
    PaymentStatus,
    ReceivableInstallmentType,
    ReceivableStatus,
)


class ReceivableGenerate(BaseModel):
    deposit_due_date: date | None = None
    balance_due_date: date


class ReceivableResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    receivable_number: str
    sales_order_id: UUID
    installment_type: ReceivableInstallmentType
    status: ReceivableStatus
    amount: Decimal
    paid_amount: Decimal
    balance: Decimal
    currency_code: str
    due_date: date
    paid_at: datetime | None
    created_at: datetime


class ReceivableListResponse(BaseModel):
    items: list[ReceivableResponse]
    count: int


class PaymentCreate(BaseModel):
    company_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    currency_code: str = Field(min_length=3, max_length=3)
    method: PaymentMethod
    reference: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)
    received_at: datetime

    @field_validator("currency_code")
    @classmethod
    def normalize_currency(cls, value: str) -> str:
        return normalize_currency(value)

    @field_validator("received_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("received_at must include a timezone")
        return value


class AllocationCreate(BaseModel):
    receivable_id: UUID
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)


class PaymentAllocate(BaseModel):
    allocations: list[AllocationCreate] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_receivables(self) -> "PaymentAllocate":
        receivable_ids = [allocation.receivable_id for allocation in self.allocations]
        if len(set(receivable_ids)) != len(receivable_ids):
            raise ValueError("Each receivable may appear only once")
        return self


class PaymentReverse(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    reason: str = Field(min_length=3, max_length=500)


class PaymentAllocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_id: UUID
    receivable_id: UUID
    kind: AllocationKind
    reversal_of_allocation_id: UUID | None
    amount: Decimal
    allocated_at: datetime


class PaymentRecordSnapshot(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_number: str
    company_id: UUID
    kind: PaymentKind
    status: PaymentStatus
    reversal_of_payment_id: UUID | None
    amount: Decimal
    currency_code: str
    method: PaymentMethod
    reference: str | None
    notes: str | None
    received_at: datetime
    reversed_at: datetime | None
    created_at: datetime
    version: int = 1
    content_visible: bool = False
    released: bool = False


class PaymentResponse(PaymentRecordSnapshot):
    allocated_amount: Decimal
    available_amount: Decimal
    allocations: list[PaymentAllocationResponse] = Field(default_factory=list)


class PaymentListResponse(BaseModel):
    items: list[PaymentResponse]
    count: int
    has_more: bool = False
    next_cursor: UUID | None = None


class SalesOrderComplete(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    expected_version: int = Field(ge=1)
    financial_waiver_reason: str | None = Field(default=None, min_length=8, max_length=500)
