from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.platform.enums import AsyncJobStatus, OutboxStatus


class AsyncJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    job_type: str
    status: AsyncJobStatus
    progress: Decimal
    correlation_id: UUID
    created_at: datetime


class AsyncJobListResponse(BaseModel):
    items: list[AsyncJobResponse]
    count: int


class OutboxEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    status: OutboxStatus
    attempt_count: int
    last_error: str | None
    created_at: datetime
    version: int
    correlation_id: UUID

    @field_serializer("last_error")
    def safe_error(self, value: str | None) -> str | None:
        if value is None or value == "CONSUMER_RECEIPT_TIMEOUT":
            return value
        return "EVENT_DELIVERY_FAILED"


class DeadOutboxListResponse(BaseModel):
    items: list[OutboxEventResponse]
    has_more: bool = False
    next_offset: int | None = None


class ReplayOutboxRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    reason: str = Field(min_length=1, max_length=1000)
    expected_version: int | None = Field(default=None, ge=1)
