from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import (
    Base,
    TenantRecordMixin,
    UUIDPrimaryKeyMixin,
    membership_actor_foreign_key,
)
from app.platform.enums import AsyncJobStatus, IdempotencyStatus, OutboxStatus


class DocumentSequence(TenantRecordMixin, Base):
    __tablename__ = "document_sequences"
    __table_args__ = (
        UniqueConstraint("organization_id", "document_type", "calendar_year"),
        CheckConstraint("calendar_year BETWEEN 2000 AND 9999", name="calendar_year_range"),
        CheckConstraint("next_value > 0", name="next_value_positive"),
        CheckConstraint("version > 0", name="version_positive"),
        membership_actor_foreign_key("document_sequences", "created_by"),
        membership_actor_foreign_key("document_sequences", "updated_by"),
    )

    document_type: Mapped[str] = mapped_column(String(50), nullable=False)
    calendar_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    next_value: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("1"))


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        membership_actor_foreign_key("audit_logs", "actor_user_id"),
        Index("ix_audit_logs_organization_id_created_at", "organization_id", "created_at"),
        Index(
            "ix_audit_logs_organization_id_target_type_target_id",
            "organization_id",
            "target_type",
            "target_id",
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    request_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    correlation_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    before_data: Mapped[dict[str, object] | None] = mapped_column("before", JSONB, nullable=True)
    after_data: Mapped[dict[str, object] | None] = mapped_column("after", JSONB, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class OutboxEvent(TenantRecordMixin, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        Index("ix_outbox_org_status_created", "organization_id", "status", "created_at"),
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'PUBLISHED', 'DEAD')",
            name="outbox_status",
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
        CheckConstraint("version > 0", name="version_positive"),
        UniqueConstraint("organization_id", "id"),
        membership_actor_foreign_key("outbox_events", "created_by"),
        membership_actor_foreign_key("outbox_events", "updated_by"),
        Index(
            "ix_outbox_events_dispatch",
            "status",
            "available_at",
            "created_at",
            postgresql_where=text("status = 'PENDING'"),
        ),
        Index(
            "ix_outbox_events_organization_id_aggregate_type_aggregate_id",
            "organization_id",
            "aggregate_type",
            "aggregate_id",
        ),
    )

    event_type: Mapped[str] = mapped_column(String(150), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=OutboxStatus.PENDING,
        server_default=OutboxStatus.PENDING.value,
    )
    attempt_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    correlation_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)


class ProcessedEvent(Base):
    __tablename__ = "processed_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["organization_id", "event_id"],
            ["outbox_events.organization_id", "outbox_events.id"],
            name="fk_processed_events_organization_id_event_id_outbox_events",
            ondelete="RESTRICT",
        ),
        Index(
            "ix_processed_events_organization_id_processed_at", "organization_id", "processed_at"
        ),
    )

    organization_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    event_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    consumer_name: Mapped[str] = mapped_column(String(150), primary_key=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class AsyncJob(TenantRecordMixin, Base):
    __tablename__ = "async_jobs"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        CheckConstraint(
            "status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')",
            name="async_job_status",
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="progress_range"),
        CheckConstraint("attempt_count >= 0", name="attempt_count_non_negative"),
        CheckConstraint("max_attempts > 0", name="max_attempts_positive"),
        CheckConstraint("version > 0", name="version_positive"),
        membership_actor_foreign_key("async_jobs", "created_by"),
        membership_actor_foreign_key("async_jobs", "updated_by"),
        Index(
            "ix_async_jobs_organization_id_status_created_at",
            "organization_id",
            "status",
            "created_at",
        ),
        Index(
            "uq_async_jobs_organization_id_idempotency_key",
            "organization_id",
            "idempotency_key",
            unique=True,
            postgresql_where=text("idempotency_key IS NOT NULL"),
        ),
    )

    job_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default=AsyncJobStatus.PENDING,
        server_default=AsyncJobStatus.PENDING.value,
    )
    progress: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        server_default=text("0"),
    )
    attempt_count: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    max_attempts: Mapped[int] = mapped_column(nullable=False, server_default=text("3"))
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    result_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=False)


class IdempotencyKey(TenantRecordMixin, Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("organization_id", "scope", "idempotency_key"),
        CheckConstraint(
            "status IN ('IN_PROGRESS', 'COMPLETED', 'FAILED')",
            name="idempotency_status",
        ),
        CheckConstraint(
            "response_status IS NULL OR response_status BETWEEN 100 AND 599",
            name="response_status_range",
        ),
        CheckConstraint("version > 0", name="version_positive"),
        membership_actor_foreign_key("idempotency_keys", "created_by"),
        membership_actor_foreign_key("idempotency_keys", "updated_by"),
        Index("ix_idempotency_keys_expires_at", "expires_at"),
    )

    scope: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(11),
        nullable=False,
        default=IdempotencyStatus.IN_PROGRESS,
        server_default=IdempotencyStatus.IN_PROGRESS.value,
    )
    response_status: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    response_body: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
