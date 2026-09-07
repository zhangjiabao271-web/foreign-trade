from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    subject_type: str
    subject_id: UUID
    task_type: str
    title: str | None
    content_visible: bool = False
    released: bool = False
    status: Literal["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"]
    priority: Literal["LOW", "NORMAL", "HIGH"]
    assigned_to: UUID | None
    due_at: datetime | None
    version: int
    details: dict[str, object]


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    count: int


class TaskComplete(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    expected_version: int = Field(ge=1)
    resolution: str = Field(min_length=3, max_length=1000)


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    activity_type: str
    summary: str | None
    content_visible: bool = False
    released: bool = False
    occurred_at: datetime
    details: dict[str, object]
    correlation_id: UUID


class ActivityListResponse(BaseModel):
    items: list[ActivityResponse]
    count: int


class ActivityPageResponse(BaseModel):
    items: list[ActivityResponse]
    next_cursor: UUID | None
    has_more: bool
