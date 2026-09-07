from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def normalize_currency(value: str) -> str:
    normalized = value.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError("Currency must be a three-letter ISO 4217 code")
    return normalized


class ProductCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=240)
    description: str | None = None
    unit: str = Field(min_length=1, max_length=32)
    standard_cost: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    cost_currency: str

    @field_validator("cost_currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return normalize_currency(value)


class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sku: str
    name: str
    description: str | None
    unit: str
    standard_cost: Decimal | None
    cost_currency: str | None
    version: int
    content_visible: bool = False
    released: bool = False
    created_at: datetime


class ProductListResponse(BaseModel):
    items: list[ProductResponse]
    count: int
    has_more: bool
    next_cursor: UUID | None
