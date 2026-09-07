from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.sales.contract_models import ContractStatus


class ContractItemSnapshot(BaseModel):
    line_number: int
    sku: str
    description: str | None
    unit: str
    quantity: Decimal
    unit_price: Decimal
    tax_amount: Decimal
    freight_amount: Decimal
    line_total: Decimal


class ContractSnapshot(BaseModel):
    order_number: str
    quotation_version_id: UUID
    seller_name: str
    customer_name: str
    payment_terms: str | None
    delivery_terms: str | None
    deposit_amount: Decimal
    deposit_due_date: date | None
    items: list[ContractItemSnapshot]


class ContractCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    external_reference: str | None = Field(default=None, max_length=160)
    notes: str | None = Field(default=None, max_length=2000)


class ContractCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=500)


class ContractUpdate(ContractCreate, ContractCommand):
    pass


class ContractSign(ContractCommand):
    signed_on: date
    document_version_id: UUID


class ContractResponse(ContractCreate):
    content_visible: bool = False
    released: bool = False
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    sales_order_id: UUID
    contract_number: str
    version: int
    status: ContractStatus
    currency_code: str
    total: Decimal
    commercial_snapshot: ContractSnapshot
    signed_on: date | None
    signed_document_version_id: UUID | None
    created_at: datetime


class ContractListResponse(BaseModel):
    items: list[ContractResponse]
    has_more: bool
    next_cursor: UUID | None
