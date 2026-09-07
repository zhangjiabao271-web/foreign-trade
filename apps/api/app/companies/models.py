from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TenantRecordMixin, membership_actor_foreign_key


class Company(TenantRecordMixin, Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        Index(
            "uq_companies_organization_id_name_normalized_active",
            "organization_id",
            "name_normalized",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        membership_actor_foreign_key("companies", "created_by"),
        membership_actor_foreign_key("companies", "updated_by"),
        Index("ix_companies_org_created_id", "organization_id", "created_at", "id"),
    )

    name: Mapped[str] = mapped_column(String(240), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(240), nullable=False)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)


class CompanyRole(TenantRecordMixin, Base):
    __tablename__ = "company_roles"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        UniqueConstraint("organization_id", "company_id", "role"),
        CheckConstraint(
            "role IN ('CUSTOMER', 'SUPPLIER', 'FORWARDER', 'AGENT')",
            name="company_role",
        ),
        ForeignKeyConstraint(
            ["organization_id", "company_id"],
            ["companies.organization_id", "companies.id"],
            name="fk_company_roles_organization_id_company_id_companies",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("company_roles", "created_by"),
        membership_actor_foreign_key("company_roles", "updated_by"),
    )

    company_id: Mapped[UUID] = mapped_column(nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)


class Contact(TenantRecordMixin, Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("organization_id", "id"),
        ForeignKeyConstraint(
            ["organization_id", "company_id"],
            ["companies.organization_id", "companies.id"],
            name="fk_contacts_organization_id_company_id_companies",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("contacts", "created_by"),
        membership_actor_foreign_key("contacts", "updated_by"),
        Index("ix_contacts_organization_id_company_id", "organization_id", "company_id"),
        Index(
            "ix_contacts_org_company_created_id",
            "organization_id",
            "company_id",
            "created_at",
            "id",
        ),
    )

    company_id: Mapped[UUID] = mapped_column(nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    email_normalized: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(160), nullable=True)
