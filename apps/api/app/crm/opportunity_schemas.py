from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.crm.enums import OpportunityStatus
from app.crm.schemas import ActivityResponse


class OpportunityCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class OpportunityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    company_id: UUID
    contact_id: UUID | None
    source_lead_id: UUID
    name: str
    status: OpportunityStatus
    lost_reason: str | None
    content_visible: bool = False
    released: bool = False
    lost_at: datetime | None
    version: int
    created_at: datetime


class OpportunityListResponse(BaseModel):
    items: list[OpportunityResponse]
    has_more: bool
    next_cursor: UUID | None


class OpportunityHistoryResponse(BaseModel):
    items: list[ActivityResponse]
    has_more: bool
