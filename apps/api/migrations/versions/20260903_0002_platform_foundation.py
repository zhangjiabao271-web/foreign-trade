"""Create platform foundation tables.

Revision ID: 20260903_0002
Revises: 20260903_0001
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260903_0002"
down_revision: str | None = "20260903_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def tenant_record_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    ]


def organization_foreign_key(table_name: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id"],
        ["organizations.id"],
        name=op.f(f"fk_{table_name}_organization_id_organizations"),
        ondelete="RESTRICT",
    )


def membership_foreign_key(
    table_name: str,
    actor_column: str,
) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["organization_id", actor_column],
        ["organization_memberships.organization_id", "organization_memberships.user_id"],
        name=op.f(f"fk_{table_name}_organization_id_{actor_column}_membership"),
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    op.create_table(
        "document_sequences",
        *tenant_record_columns(),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("calendar_year", sa.SmallInteger(), nullable=False),
        sa.Column("next_value", sa.BigInteger(), nullable=False, server_default=sa.text("1")),
        sa.CheckConstraint(
            "calendar_year BETWEEN 2000 AND 9999",
            name=op.f("ck_document_sequences_calendar_year_range"),
        ),
        sa.CheckConstraint(
            "next_value > 0",
            name=op.f("ck_document_sequences_next_value_positive"),
        ),
        sa.CheckConstraint(
            "version > 0",
            name=op.f("ck_document_sequences_version_positive"),
        ),
        organization_foreign_key("document_sequences"),
        membership_foreign_key("document_sequences", "created_by"),
        membership_foreign_key("document_sequences", "updated_by"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_sequences")),
        sa.UniqueConstraint(
            "organization_id",
            "document_type",
            "calendar_year",
            name=op.f("uq_document_sequences_organization_id_document_type_calendar_year"),
        ),
    )

    op.create_table(
        "audit_logs",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("target_type", sa.String(length=100), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=True),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        organization_foreign_key("audit_logs"),
        membership_foreign_key("audit_logs", "actor_user_id"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_logs")),
    )
    op.create_index(
        "ix_audit_logs_organization_id_created_at",
        "audit_logs",
        ["organization_id", "created_at"],
    )
    op.create_index(
        "ix_audit_logs_organization_id_target_type_target_id",
        "audit_logs",
        ["organization_id", "target_type", "target_id"],
    )
    op.execute(
        """
        CREATE FUNCTION prevent_audit_log_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs is append-only' USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_append_only
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation()
        """
    )

    op.create_table(
        "outbox_events",
        *tenant_record_columns(),
        sa.Column("event_type", sa.String(length=150), nullable=False),
        sa.Column("aggregate_type", sa.String(length=100), nullable=False),
        sa.Column("aggregate_id", sa.Uuid(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=100), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'PUBLISHED', 'DEAD')",
            name=op.f("ck_outbox_events_outbox_status"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_outbox_events_attempt_count_non_negative"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_outbox_events_version_positive")),
        organization_foreign_key("outbox_events"),
        membership_foreign_key("outbox_events", "created_by"),
        membership_foreign_key("outbox_events", "updated_by"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_events")),
    )
    op.create_index(
        "ix_outbox_events_dispatch",
        "outbox_events",
        ["status", "available_at", "created_at"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "ix_outbox_events_organization_id_aggregate_type_aggregate_id",
        "outbox_events",
        ["organization_id", "aggregate_type", "aggregate_id"],
    )

    op.create_table(
        "async_jobs",
        *tenant_record_columns(),
        sa.Column("job_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="PENDING"),
        sa.Column("progress", sa.Numeric(precision=5, scale=2), nullable=False, server_default="0"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default=sa.text("3")),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("result_reference", sa.Text(), nullable=True),
        sa.Column("error_code", sa.String(length=100), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name=op.f("ck_async_jobs_async_job_status"),
        ),
        sa.CheckConstraint(
            "progress >= 0 AND progress <= 100",
            name=op.f("ck_async_jobs_progress_range"),
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name=op.f("ck_async_jobs_attempt_count_non_negative"),
        ),
        sa.CheckConstraint(
            "max_attempts > 0",
            name=op.f("ck_async_jobs_max_attempts_positive"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_async_jobs_version_positive")),
        organization_foreign_key("async_jobs"),
        membership_foreign_key("async_jobs", "created_by"),
        membership_foreign_key("async_jobs", "updated_by"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_async_jobs")),
    )
    op.create_index(
        "ix_async_jobs_organization_id_status_created_at",
        "async_jobs",
        ["organization_id", "status", "created_at"],
    )
    op.create_index(
        "uq_async_jobs_organization_id_idempotency_key",
        "async_jobs",
        ["organization_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    op.create_table(
        "idempotency_keys",
        *tenant_record_columns(),
        sa.Column("scope", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=11),
            nullable=False,
            server_default="IN_PROGRESS",
        ),
        sa.Column("response_status", sa.SmallInteger(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("resource_type", sa.String(length=100), nullable=True),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('IN_PROGRESS', 'COMPLETED', 'FAILED')",
            name=op.f("ck_idempotency_keys_idempotency_status"),
        ),
        sa.CheckConstraint(
            "response_status IS NULL OR response_status BETWEEN 100 AND 599",
            name=op.f("ck_idempotency_keys_response_status_range"),
        ),
        sa.CheckConstraint(
            "version > 0",
            name=op.f("ck_idempotency_keys_version_positive"),
        ),
        organization_foreign_key("idempotency_keys"),
        membership_foreign_key("idempotency_keys", "created_by"),
        membership_foreign_key("idempotency_keys", "updated_by"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_idempotency_keys")),
        sa.UniqueConstraint(
            "organization_id",
            "scope",
            "idempotency_key",
            name=op.f("uq_idempotency_keys_organization_id_scope_idempotency_key"),
        ),
    )
    op.create_index("ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_idempotency_keys_expires_at", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")
    op.drop_index(
        "uq_async_jobs_organization_id_idempotency_key",
        table_name="async_jobs",
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )
    op.drop_index(
        "ix_async_jobs_organization_id_status_created_at",
        table_name="async_jobs",
    )
    op.drop_table("async_jobs")
    op.drop_index(
        "ix_outbox_events_organization_id_aggregate_type_aggregate_id",
        table_name="outbox_events",
    )
    op.drop_index("ix_outbox_events_dispatch", table_name="outbox_events")
    op.drop_table("outbox_events")
    op.execute("DROP TRIGGER trg_audit_logs_append_only ON audit_logs")
    op.execute("DROP FUNCTION prevent_audit_log_mutation()")
    op.drop_index(
        "ix_audit_logs_organization_id_target_type_target_id",
        table_name="audit_logs",
    )
    op.drop_index("ix_audit_logs_organization_id_created_at", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("document_sequences")
