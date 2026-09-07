from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.catalog.schemas import normalize_currency
from app.sales.enums import QuotationVersionStatus


class QuotationItemInput(BaseModel):
    product_id: UUID
    description: str | None = None
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    unit_price: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    unit_cost: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    cost_currency: str | None = None
    cost_exchange_rate: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=8)
    tax_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)
    freight_amount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=18, decimal_places=4)
    allocated_cost: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)

    @field_validator("cost_currency")
    @classmethod
    def validate_optional_currency(cls, value: str | None) -> str | None:
        return normalize_currency(value) if value is not None else None


class QuotationCreate(BaseModel):
    inquiry_id: UUID
    currency_code: str
    base_currency_code: str
    exchange_rate: Decimal = Field(gt=0, max_digits=18, decimal_places=8)
    valid_until: date
    payment_terms: str | None = None
    delivery_terms: str | None = None
    items: list[QuotationItemInput] = Field(min_length=1, max_length=100)

    @field_validator("currency_code", "base_currency_code")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return normalize_currency(value)


class QuotationRevisionItemInput(QuotationItemInput):
    source_item_id: UUID | None = None


class QuotationRevisionCreate(BaseModel):
    expected_version_id: UUID | None = None
    currency_code: str | None = None
    base_currency_code: str | None = None
    exchange_rate: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=8)
    valid_until: date | None = None
    payment_terms: str | None = None
    delivery_terms: str | None = None
    items: list[QuotationRevisionItemInput] | None = Field(
        default=None, min_length=1, max_length=100
    )

    @field_validator("currency_code", "base_currency_code")
    @classmethod
    def validate_optional_version_currency(cls, value: str | None) -> str | None:
        return normalize_currency(value) if value is not None else None


class QuotationItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    line_number: int
    product_id: UUID
    sku_snapshot: str
    description_snapshot: str | None
    unit_snapshot: str
    quantity: Decimal
    unit_price: Decimal
    unit_cost: Decimal | None
    cost_currency: str | None
    cost_exchange_rate: Decimal | None
    tax_amount: Decimal
    freight_amount: Decimal
    allocated_cost: Decimal | None
    line_subtotal: Decimal
    line_total: Decimal
    line_cost: Decimal | None
    line_gross_profit: Decimal | None


class QuotationVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    quotation_id: UUID
    version_number: int
    version: int = 1
    content_visible: bool = False
    released: bool = False
    status: QuotationVersionStatus
    is_current: bool
    currency_code: str
    base_currency_code: str
    exchange_rate: Decimal
    valid_until: date
    payment_terms: str | None
    delivery_terms: str | None
    subtotal: Decimal
    tax_amount: Decimal
    freight_amount: Decimal
    total: Decimal
    total_cost: Decimal | None
    gross_profit: Decimal | None
    gross_margin: Decimal | None
    submitted_at: datetime | None
    approved_at: datetime | None
    approved_by: UUID | None
    sent_at: datetime | None
    accepted_at: datetime | None
    items: list[QuotationItemResponse] = Field(default_factory=list)


class QuotationResponse(BaseModel):
    id: UUID
    quotation_number: str
    inquiry_id: UUID
    opportunity_id: UUID
    company_id: UUID
    accepted_version_id: UUID | None
    current_version: QuotationVersionResponse
    versions: list[QuotationVersionResponse]
    created_at: datetime


class QuotationListItem(BaseModel):
    id: UUID
    quotation_number: str
    company_id: UUID
    opportunity_id: UUID
    accepted_version_id: UUID | None
    version_id: UUID
    version_number: int
    status: QuotationVersionStatus
    currency_code: str
    total: Decimal
    gross_profit: Decimal | None
    gross_margin: Decimal | None
    valid_until: date
    created_at: datetime


class QuotationListResponse(BaseModel):
    has_more: bool
    next_cursor: UUID | None
    items: list[QuotationListItem]
    count: int


class CustomerReviewCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version_id: UUID
    reason: str = Field(min_length=1, max_length=500)


class CustomerReviewResult(BaseModel):
    id: UUID


class QuotationStateCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version_id: UUID
    expected_version: int = Field(ge=1)
