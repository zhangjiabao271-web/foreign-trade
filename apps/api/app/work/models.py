from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.content_review import ContentReleaseMixin, review_constraint
from app.core.database import Base, TenantRecordMixin, membership_actor_foreign_key


class Activity(ContentReleaseMixin, TenantRecordMixin, Base):
    __tablename__ = "activities"
    __table_args__ = (
        membership_actor_foreign_key("activities", "reviewed_by"),
        review_constraint("activities"),
        membership_actor_foreign_key("activities", "created_by"),
        membership_actor_foreign_key("activities", "updated_by"),
        Index(
            "ix_activities_organization_id_subject_created_at",
            "organization_id",
            "subject_type",
            "subject_id",
            "created_at",
        ),
    )

    subject_type: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(nullable=False)
    activity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    details: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    correlation_id: Mapped[UUID] = mapped_column(nullable=False)


class Task(ContentReleaseMixin, TenantRecordMixin, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        membership_actor_foreign_key("tasks", "reviewed_by"),
        review_constraint("tasks"),
        UniqueConstraint("organization_id", "id", name="uq_tasks_org_id"),
        UniqueConstraint(
            "organization_id",
            "subject_type",
            "subject_id",
            "task_type",
            name="uq_tasks_org_subject_type",
        ),
        CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'DONE', 'CANCELLED')",
            name="ck_tasks_status",
        ),
        CheckConstraint("priority IN ('LOW', 'NORMAL', 'HIGH')", name="ck_tasks_priority"),
        ForeignKeyConstraint(
            ["organization_id", "assigned_to"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_tasks_org_assigned_membership",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("tasks", "created_by"),
        membership_actor_foreign_key("tasks", "updated_by"),
        Index("ix_tasks_org_status_due", "organization_id", "status", "due_at"),
        Index("ix_tasks_org_subject", "organization_id", "subject_type", "subject_id"),
    )

    task_type: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(80), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="OPEN")
    priority: Mapped[str] = mapped_column(String(12), nullable=False, server_default="NORMAL")
    assigned_to: Mapped[UUID | None] = mapped_column(nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    details: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
