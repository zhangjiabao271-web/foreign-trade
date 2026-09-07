from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AiIntent(StrEnum):
    SEARCH = "SEARCH"
    TIMELINE = "TIMELINE"
    PROFIT = "PROFIT"
    EMAIL_DRAFT = "EMAIL_DRAFT"
    TASK_DRAFT = "TASK_DRAFT"


class AiRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intent: AiIntent
    subject_id: UUID | None = None
    search_term: str | None = Field(default=None, min_length=2, max_length=80)

    @model_validator(mode="after")
    def require_target(self) -> Self:
        if self.intent == AiIntent.SEARCH:
            if self.search_term is None or self.subject_id is not None:
                raise ValueError("Search requires a search term and no subject ID")
        elif self.subject_id is None or self.search_term is not None:
            raise ValueError("This intent requires an order ID and no search term")
        return self


class AiArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    inferences: list[str] = Field(max_length=8)
    draft: str = Field(max_length=5000)
    task_title: str | None = Field(max_length=240)


class AiRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    job_id: UUID
    intent: AiIntent
    subject_id: UUID | None
    status: str
    model: str
    prompt_version: str
    input_summary: dict[str, object] | None
    output: dict[str, object] | None
    references: list[dict[str, object]]
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: Decimal | None
    error_code: str | None
    created_at: datetime
    version: int
    content_protected: bool = False
    released_disclosure_id: UUID | None = None
    released_disclosure_version: int | None = None


class AiRunList(BaseModel):
    items: list[AiRunResponse]
    next_cursor: str | None
    has_more: bool


class AiToolCallResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tool_name: str
    argument_summary: dict[str, object] | None
    result_summary: dict[str, object] | None
    status: str
    error_code: str | None
    created_at: datetime


class ApprovalDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=3, max_length=1000)


class AiApprovalRequest(ApprovalDecision):
    disclosure_id: UUID | None = None
    disclosure_version: int | None = Field(default=None, ge=1)


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    run_id: UUID
    status: str
    proposed_action: dict[str, object] | None
    decided_by: UUID | None
    decided_at: datetime | None
    reason: str | None
    task_id: UUID | None
    created_at: datetime
    version: int


class ApprovalList(BaseModel):
    items: list[ApprovalResponse]
    next_cursor: str | None
    has_more: bool


class AiDisclosureSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class AiDisclosureDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=1)
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    release: bool
    confirmed: bool
    reason: str = Field(min_length=3, max_length=1000)


class AiDisclosureRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate: AiArtifact


class AiDisclosureResponse(BaseModel):
    id: UUID
    run_id: UUID
    parent_id: UUID | None
    revision: int
    version: int
    status: str
    current: bool
    candidate: AiArtifact | None
    content_digest: str | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    created_at: datetime


class AiDisclosureList(BaseModel):
    items: list[AiDisclosureResponse]
    next_cursor: str | None
    has_more: bool
