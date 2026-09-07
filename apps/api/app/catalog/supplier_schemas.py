from datetime import date, datetime
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SupplierTerms(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    supplier_sku: str = Field(min_length=1, max_length=80)
    unit_price: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    lead_time_days: int = Field(ge=0, le=3650, strict=True)
    quoted_on: date
    valid_until: date | None = None
    quotation_reference: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def date_order(self) -> Self:
        if self.valid_until is not None and self.valid_until < self.quoted_on:
            raise ValueError("Validity must not precede the quotation date")
        return self


class SupplierLinkCreate(SupplierTerms):
    supplier_id: UUID


class SupplierLinkUpdate(SupplierTerms):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class SupplierLinkRecord(SupplierTerms):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    product_id: UUID
    supplier_id: UUID
    version: int
    created_at: datetime


class SupplierLinkResponse(SupplierLinkRecord):
    supplier_name: str


class SupplierLinkListResponse(BaseModel):
    items: list[SupplierLinkResponse]
    has_more: bool
    next_cursor: UUID | None
