"""controlled_copilot

Revision ID: 20260906_0011
Revises: 20260906_0010
Create Date: 2026-09-06 01:20:09.915499
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260906_0011"
down_revision: str | None = "20260906_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        op.f("uq_async_jobs_organization_id_id"), "async_jobs", ["organization_id", "id"]
    )
    op.create_table(
        "ai_runs",
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("intent", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=True),
        sa.Column("input_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("required_permissions", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="PENDING", nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("references", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lease_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "intent IN ('SEARCH', 'TIMELINE', 'PROFIT', 'EMAIL_DRAFT', 'TASK_DRAFT')",
            name=op.f("ck_ai_runs_ai_run_intent"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED')",
            name=op.f("ck_ai_runs_ai_run_status"),
        ),
        sa.CheckConstraint(
            "input_tokens >= 0 AND output_tokens >= 0 AND attempt_count >= 0",
            name=op.f("ck_ai_runs_ai_run_counts"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_ai_runs_organization_id_created_by_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "job_id"],
            ["async_jobs.organization_id", "async_jobs.id"],
            name=op.f("fk_ai_runs_organization_id_job_id_async_jobs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "updated_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_ai_runs_organization_id_updated_by_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_ai_runs_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_runs")),
        sa.UniqueConstraint("organization_id", "id", name=op.f("uq_ai_runs_organization_id_id")),
        sa.UniqueConstraint(
            "organization_id", "job_id", name=op.f("uq_ai_runs_organization_id_job_id")
        ),
    )
    op.create_index(
        "ix_ai_runs_org_creator_created",
        "ai_runs",
        ["organization_id", "created_by", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "ai_tool_calls",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("call_id", sa.String(length=160), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("argument_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "status IN ('SUCCEEDED', 'DENIED', 'FAILED')",
            name=op.f("ck_ai_tool_calls_ai_tool_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_ai_tool_calls_organization_id_created_by_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "run_id"],
            ["ai_runs.organization_id", "ai_runs.id"],
            name=op.f("fk_ai_tool_calls_organization_id_run_id_ai_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "updated_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_ai_tool_calls_organization_id_updated_by_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_ai_tool_calls_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_tool_calls")),
        sa.UniqueConstraint(
            "organization_id",
            "run_id",
            "call_id",
            name=op.f("uq_ai_tool_calls_organization_id_run_id_call_id"),
        ),
    )
    op.create_index(
        "ix_ai_tool_calls_org_run_created",
        "ai_tool_calls",
        ["organization_id", "run_id", "created_at", "id"],
        unique=False,
    )
    op.create_table(
        "approval_requests",
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=12), server_default="PENDING", nullable=False),
        sa.Column("proposed_action", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.CheckConstraint(
            "(status = 'APPROVED') = (task_id IS NOT NULL)",
            name=op.f("ck_approval_requests_approval_task_result"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')",
            name=op.f("ck_approval_requests_approval_status"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_approval_requests_organization_id_created_by_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "decided_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_approval_requests_organization_id_decided_by_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "run_id"],
            ["ai_runs.organization_id", "ai_runs.id"],
            name=op.f("fk_approval_requests_organization_id_run_id_ai_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "task_id"],
            ["tasks.organization_id", "tasks.id"],
            name=op.f("fk_approval_requests_organization_id_task_id_tasks"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "updated_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_approval_requests_organization_id_updated_by_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_approval_requests_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_approval_requests")),
        sa.UniqueConstraint(
            "organization_id", "id", name=op.f("uq_approval_requests_organization_id_id")
        ),
        sa.UniqueConstraint(
            "organization_id", "run_id", name=op.f("uq_approval_requests_organization_id_run_id")
        ),
    )
    op.create_index(
        "ix_approval_requests_org_status_created",
        "approval_requests",
        ["organization_id", "status", "created_at", "id"],
        unique=False,
    )


def downgrade() -> None:
    raise RuntimeError("Preserve AI and approval audit evidence; use a forward correction.")
