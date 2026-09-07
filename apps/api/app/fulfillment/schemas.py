from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.fulfillment.enums import ShipmentStatus


class ShipmentItemCreate(BaseModel):
    sales_order_item_id: UUID
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)


class ShipmentCreate(BaseModel):
    forwarder_company_id: UUID | None = None
    planned_departure_date: date | None = None
    planned_arrival_date: date | None = None
    items: list[ShipmentItemCreate] = Field(min_length=1, max_length=200)


class ShipmentDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class ShipmentBook(ShipmentDecision):
    booking_reference: str = Field(min_length=1, max_length=120)


class ShipmentItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sales_order_item_id: UUID
    quantity: Decimal


class ShipmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: int
    shipment_number: str
    status: ShipmentStatus
    forwarder_company_id: UUID | None
    booking_reference: str | None
    planned_departure_date: date | None
    planned_arrival_date: date | None
    booked_at: datetime | None
    ready_at: datetime | None
    customs_at: datetime | None
    departed_at: datetime | None
    in_transit_at: datetime | None
    arrived_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime
    missing_required_documents: list[str] = Field(default_factory=list)
    items: list[ShipmentItemResponse] = Field(default_factory=list)


class ShipmentListResponse(BaseModel):
    has_more: bool
    next_cursor: UUID | None
    items: list[ShipmentResponse]
    count: int
