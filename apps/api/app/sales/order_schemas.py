from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.sales.order_enums import SalesOrderStatus


class SalesOrderCreate(BaseModel):
    quotation_id: UUID
    deposit_rate: Decimal = Field(default=Decimal("0.3000"), ge=0, le=1, decimal_places=4)
    deposit_due_date: date | None = None


class SalesOrderConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class SalesOrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    quotation_item_id: UUID
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


class SalesOrderResponse(BaseModel):
    content_visible: bool = False
    released: bool = False
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: int
    order_number: str
    quotation_id: UUID
    quotation_version_id: UUID
    opportunity_id: UUID
    company_id: UUID
    status: SalesOrderStatus
    currency_code: str
    base_currency_code: str
    exchange_rate: Decimal
    payment_terms: str | None
    delivery_terms: str | None
    subtotal: Decimal
    tax_amount: Decimal
    freight_amount: Decimal
    total: Decimal
    total_cost: Decimal | None
    gross_profit: Decimal | None
    gross_margin: Decimal | None
    deposit_rate: Decimal
    deposit_amount: Decimal
    deposit_due_date: date | None
    confirmed_at: datetime | None
    created_at: datetime
    items: list[SalesOrderItemResponse] = Field(default_factory=list)


class SalesOrderSourceLineResponse(BaseModel):
    id: UUID
    sales_order_id: UUID
    order_number: str
    order_status: SalesOrderStatus
    sku_snapshot: str
    description_snapshot: str | None
    unit_snapshot: str


class SalesOrderSourceLinesResponse(BaseModel):
    items: list[SalesOrderSourceLineResponse]
    count: int


class SalesOrderListResponse(BaseModel):
    items: list[SalesOrderResponse]
    count: int
    has_more: bool
    next_cursor: UUID | None
