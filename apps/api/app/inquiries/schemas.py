from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.inquiries.enums import InquiryStatus


class InquiryCreate(BaseModel):
    opportunity_id: UUID
    company_id: UUID
    customer_reference: str | None = Field(default=None, max_length=120)
    description: str = Field(min_length=1)
    received_at: datetime


class InquiryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    opportunity_id: UUID
    company_id: UUID
    customer_reference: str | None
    description: str | None
    received_at: datetime
    status: InquiryStatus
    version: int
    content_visible: bool = False
    released: bool = False
    created_at: datetime


class InquiryListResponse(BaseModel):
    has_more: bool
    next_cursor: UUID | None
    items: list[InquiryResponse]
    count: int
