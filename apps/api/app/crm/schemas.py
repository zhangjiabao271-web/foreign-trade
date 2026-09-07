from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.crm.enums import LeadStatus


class LeadCreate(BaseModel):
    company_name: str = Field(min_length=1, max_length=240)
    contact_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=80)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    source: str | None = Field(default=None, max_length=120)
    notes: str | None = None


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    activity_type: str
    summary: str | None
    content_visible: bool = False
    released: bool = False
    occurred_at: datetime


class LeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_name: str
    contact_name: str | None
    email: str | None
    phone: str | None
    country_code: str | None
    source: str | None
    notes: str | None
    content_visible: bool = False
    released: bool = False
    status: LeadStatus
    converted_company_id: UUID | None
    converted_contact_id: UUID | None
    converted_opportunity_id: UUID | None
    converted_at: datetime | None
    version: int
    created_at: datetime


class LeadDetailResponse(LeadResponse):
    activities: list[ActivityResponse]


class LeadListResponse(BaseModel):
    items: list[LeadResponse]
    count: int


class LeadConversionResponse(BaseModel):
    lead: LeadResponse
    company_id: UUID
    contact_id: UUID
    opportunity_id: UUID
