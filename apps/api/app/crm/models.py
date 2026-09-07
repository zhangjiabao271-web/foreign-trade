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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.content_review import ContentReleaseMixin, review_constraint
from app.core.database import Base, TenantRecordMixin, membership_actor_foreign_key


class Lead(ContentReleaseMixin, TenantRecordMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (
        membership_actor_foreign_key("leads", "reviewed_by"),
        review_constraint("leads"),
        UniqueConstraint("organization_id", "id"),
        CheckConstraint(
            "status IN ('NEW', 'QUALIFIED', 'CONTACTED', 'RESPONDED', "
            "'NO_RESPONSE', 'CONVERTED', 'DISQUALIFIED')",
            name="lead_status",
        ),
        ForeignKeyConstraint(
            ["organization_id", "converted_company_id"],
            ["companies.organization_id", "companies.id"],
            name="fk_leads_organization_id_converted_company_id_companies",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "converted_contact_id"],
            ["contacts.organization_id", "contacts.id"],
            name="fk_leads_organization_id_converted_contact_id_contacts",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "converted_opportunity_id"],
            ["opportunities.organization_id", "opportunities.id"],
            name="fk_leads_organization_id_converted_opportunity_id_opportunities",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        membership_actor_foreign_key("leads", "created_by"),
        membership_actor_foreign_key("leads", "updated_by"),
        Index(
            "ix_leads_organization_id_status_created_at", "organization_id", "status", "created_at"
        ),
    )

    company_name: Mapped[str] = mapped_column(String(240), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_normalized: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="NEW")
    converted_company_id: Mapped[UUID | None] = mapped_column(nullable=True)
    converted_contact_id: Mapped[UUID | None] = mapped_column(nullable=True)
    converted_opportunity_id: Mapped[UUID | None] = mapped_column(nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Opportunity(ContentReleaseMixin, TenantRecordMixin, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        membership_actor_foreign_key("opportunities", "reviewed_by"),
        review_constraint("opportunities"),
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "source_lead_id"),
        CheckConstraint(
            "status IN ('OPEN', 'INQUIRY', 'QUOTING', 'NEGOTIATION', 'WON', 'LOST')",
            name="opportunity_status",
        ),
        ForeignKeyConstraint(
            ["organization_id", "company_id"],
            ["companies.organization_id", "companies.id"],
            name="fk_opportunities_organization_id_company_id_companies",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "contact_id"],
            ["contacts.organization_id", "contacts.id"],
            name="fk_opportunities_organization_id_contact_id_contacts",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "source_lead_id"],
            ["leads.organization_id", "leads.id"],
            name="fk_opportunities_organization_id_source_lead_id_leads",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("opportunities", "created_by"),
        membership_actor_foreign_key("opportunities", "updated_by"),
        Index("ix_opportunities_org_created_id", "organization_id", "created_at", "id"),
    )

    company_id: Mapped[UUID] = mapped_column(nullable=False)
    contact_id: Mapped[UUID | None] = mapped_column(nullable=True)
    source_lead_id: Mapped[UUID] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="OPEN")
    lost_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    lost_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
