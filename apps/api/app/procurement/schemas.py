from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.catalog.schemas import normalize_currency
from app.procurement.enums import PurchaseOrderStatus


class PurchaseOrderItemCreate(BaseModel):
    sales_order_item_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    unit_cost: Decimal = Field(ge=0, max_digits=18, decimal_places=4)


class PurchaseOrderCreate(BaseModel):
    sales_order_id: UUID
    supplier_company_id: UUID
    currency_code: str
    exchange_rate: Decimal = Field(gt=0, max_digits=18, decimal_places=8)
    items: list[PurchaseOrderItemCreate] = Field(min_length=1, max_length=100)

    @field_validator("currency_code")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return normalize_currency(value)


class PurchaseOrderDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class PurchaseOrderConfirm(PurchaseOrderDecision):
    supplier_reference: str | None = Field(default=None, max_length=120)
    expected_delivery_date: date


class PurchaseOrderCancel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)
    supplier_reference: str | None = Field(default=None, min_length=1, max_length=200)


class PurchaseOrderAmend(PurchaseOrderCancel):
    replacement: PurchaseOrderCreate


class PurchaseReceiptLine(BaseModel):
    purchase_order_item_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)


class PurchaseOrderReceive(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    expected_version: int = Field(ge=1)
    reference: str = Field(min_length=1, max_length=200)
    received_date: date
    items: list[PurchaseReceiptLine] = Field(min_length=1, max_length=100)


class PurchaseOrderClose(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class PurchaseOrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sales_order_item_id: UUID
    line_number: int
    sku_snapshot: str
    description_snapshot: str | None
    unit_snapshot: str
    quantity: Decimal
    received_quantity: Decimal
    unit_cost: Decimal | None
    line_total: Decimal | None


class PurchaseOrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    content_visible: bool = False
    released: bool = False
    id: UUID
    purchase_order_number: str
    sales_order_id: UUID
    supplier_company_id: UUID
    status: PurchaseOrderStatus
    currency_code: str | None
    exchange_rate: Decimal | None
    total: Decimal | None
    total_order_currency: Decimal | None
    supplier_reference: str | None
    expected_delivery_date: date | None
    approved_at: datetime | None
    approved_by: UUID | None
    sent_at: datetime | None
    confirmed_at: datetime | None
    received_at: datetime | None
    closed_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    cancellation_reference: str | None
    replaces_purchase_order_id: UUID | None
    retained_total: Decimal | None = None
    retained_total_order_currency: Decimal | None = None
    version: int
    created_at: datetime
    items: list[PurchaseOrderItemResponse] = Field(default_factory=list)


class PurchaseOrderListResponse(BaseModel):
    has_more: bool
    next_cursor: UUID | None
    items: list[PurchaseOrderResponse]
    count: int
