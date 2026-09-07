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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.content_review import ContentReleaseMixin, review_constraint
from app.core.database import Base, TenantRecordMixin, membership_actor_foreign_key


class Inquiry(ContentReleaseMixin, TenantRecordMixin, Base):
    __tablename__ = "inquiries"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        CheckConstraint("status IN ('OPEN', 'QUOTING', 'CLOSED')", name="inquiry_status"),
        ForeignKeyConstraint(
            ["organization_id", "opportunity_id"],
            ["opportunities.organization_id", "opportunities.id"],
            name="fk_inquiries_organization_id_opportunity_id_opportunities",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "company_id"],
            ["companies.organization_id", "companies.id"],
            name="fk_inquiries_organization_id_company_id_companies",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("inquiries", "created_by"),
        membership_actor_foreign_key("inquiries", "updated_by"),
        membership_actor_foreign_key("inquiries", "reviewed_by"),
        review_constraint("inquiries"),
        Index(
            "ix_inquiries_org_received_id_active",
            "organization_id",
            "received_at",
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_inquiries_org_status_received_id_active",
            "organization_id",
            "status",
            "received_at",
            "id",
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_inquiries_organization_id_status_created_at",
            "organization_id",
            "status",
            "created_at",
        ),
    )

    opportunity_id: Mapped[UUID] = mapped_column(nullable=False)
    company_id: Mapped[UUID] = mapped_column(nullable=False)
    customer_reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="OPEN")
