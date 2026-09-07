from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TenantRecordMixin, membership_actor_foreign_key


class AiRun(TenantRecordMixin, Base):
    __tablename__ = "ai_runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "job_id"),
        ForeignKeyConstraint(
            ["organization_id", "job_id"],
            ["async_jobs.organization_id", "async_jobs.id"],
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("ai_runs", "created_by"),
        membership_actor_foreign_key("ai_runs", "updated_by"),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')", name="ai_run_status"
        ),
        CheckConstraint(
            "intent IN ('SEARCH', 'TIMELINE', 'PROFIT', 'EMAIL_DRAFT', 'TASK_DRAFT')",
            name="ai_run_intent",
        ),
        CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND attempt_count >= 0", name="ai_run_counts"
        ),
        Index(
            "ix_ai_runs_org_creator_created", "organization_id", "created_by", "created_at", "id"
        ),
    )
    job_id: Mapped[UUID] = mapped_column(nullable=False)
    intent: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_id: Mapped[UUID | None] = mapped_column(nullable=True)
    input_summary: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    required_permissions: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="PENDING")
    output: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    references: Mapped[list[dict[str, object]]] = mapped_column(JSONB, nullable=False, default=list)
    input_tokens: Mapped[int] = mapped_column(nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(nullable=False, server_default="0")
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attempt_count: Mapped[int] = mapped_column(nullable=False, server_default="0")
    lease_id: Mapped[UUID | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiToolCall(TenantRecordMixin, Base):
    __tablename__ = "ai_tool_calls"
    __table_args__ = (
        UniqueConstraint("organization_id", "run_id", "call_id"),
        ForeignKeyConstraint(
            ["organization_id", "run_id"],
            ["ai_runs.organization_id", "ai_runs.id"],
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("ai_tool_calls", "created_by"),
        membership_actor_foreign_key("ai_tool_calls", "updated_by"),
        CheckConstraint("status IN ('SUCCEEDED', 'DENIED', 'FAILED')", name="ai_tool_status"),
        Index("ix_ai_tool_calls_org_run_created", "organization_id", "run_id", "created_at", "id"),
    )
    run_id: Mapped[UUID] = mapped_column(nullable=False)
    call_id: Mapped[str] = mapped_column(String(160), nullable=False)
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    argument_summary: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    result_summary: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)


class AiDisclosure(TenantRecordMixin, Base):
    __tablename__ = "ai_disclosures"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "run_id", "revision"),
        ForeignKeyConstraint(
            ["organization_id", "run_id"],
            ["ai_runs.organization_id", "ai_runs.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "parent_id"],
            ["ai_disclosures.organization_id", "ai_disclosures.id"],
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("ai_disclosures", "created_by"),
        membership_actor_foreign_key("ai_disclosures", "updated_by"),
        membership_actor_foreign_key("ai_disclosures", "reviewed_by"),
        CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED')", name="disclosure_status"),
        CheckConstraint("revision > 0 AND run_version > 0", name="disclosure_versions"),
        CheckConstraint("char_length(run_digest) = 64", name="disclosure_digest"),
        CheckConstraint(
            "(status = 'PENDING' AND reviewed_by IS NULL AND reviewed_at IS NULL) OR "
            "(status <> 'PENDING' AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="disclosure_decision",
        ),
        Index("ix_ai_disclosures_org_created", "organization_id", "created_at", "id"),
    )
    run_id: Mapped[UUID] = mapped_column(nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(nullable=True)
    revision: Mapped[int] = mapped_column(nullable=False)
    run_version: Mapped[int] = mapped_column(nullable=False)
    run_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    released_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="PENDING")
    reviewed_by: Mapped[UUID | None] = mapped_column(nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalRequest(TenantRecordMixin, Base):
    __tablename__ = "approval_requests"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "run_id"),
        ForeignKeyConstraint(
            ["organization_id", "run_id"],
            ["ai_runs.organization_id", "ai_runs.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "task_id"],
            ["tasks.organization_id", "tasks.id"],
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("approval_requests", "created_by"),
        membership_actor_foreign_key("approval_requests", "updated_by"),
        membership_actor_foreign_key("approval_requests", "decided_by"),
        CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED')", name="approval_status"),
        CheckConstraint(
            "(status = 'APPROVED') = (task_id IS NOT NULL)", name="approval_task_result"
        ),
        Index(
            "ix_approval_requests_org_status_created",
            "organization_id",
            "status",
            "created_at",
            "id",
        ),
    )
    run_id: Mapped[UUID] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, server_default="PENDING")
    proposed_action: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    decided_by: Mapped[UUID | None] = mapped_column(nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    task_id: Mapped[UUID | None] = mapped_column(nullable=True)
