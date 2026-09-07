from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.content_review import ContentReleaseMixin, review_constraint
from app.core.database import Base, TenantRecordMixin, membership_actor_foreign_key
from app.core.database_types import money_type


class ContractStatus(StrEnum):
    DRAFT = "DRAFT"
    SIGNED = "SIGNED"
    VOIDED = "VOIDED"


class SalesContract(ContentReleaseMixin, TenantRecordMixin, Base):
    __tablename__ = "sales_contracts"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_sales_contracts_org_id"),
        UniqueConstraint(
            "organization_id", "contract_number", name="uq_sales_contracts_org_number"
        ),
        ForeignKeyConstraint(
            ["organization_id", "sales_order_id"],
            ["sales_orders.organization_id", "sales_orders.id"],
            name="fk_sales_contracts_org_order",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "signed_document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_sales_contracts_org_evidence",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'SIGNED', 'VOIDED')", name="ck_sales_contracts_status"
        ),
        CheckConstraint("total >= 0", name="ck_sales_contracts_total"),
        CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="ck_sales_contracts_currency"),
        CheckConstraint(
            "(status = 'SIGNED' AND signed_on IS NOT NULL "
            "AND signed_document_version_id IS NOT NULL) "
            "OR (status != 'SIGNED' AND signed_on IS NULL AND signed_document_version_id IS NULL)",
            name="ck_sales_contracts_signed_evidence",
        ),
        membership_actor_foreign_key("sales_contracts", "created_by"),
        membership_actor_foreign_key("sales_contracts", "updated_by"),
        membership_actor_foreign_key("sales_contracts", "reviewed_by"),
        review_constraint("sales_contracts"),
        Index(
            "uq_sales_contracts_org_order_active",
            "organization_id",
            "sales_order_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND status != 'VOIDED'"),
        ),
        Index(
            "ix_sales_contracts_org_order_created",
            "organization_id",
            "sales_order_id",
            "created_at",
            "id",
        ),
    )
    sales_order_id: Mapped[UUID] = mapped_column(nullable=False)
    contract_number: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="DRAFT")
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    total: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    commercial_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    signed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    signed_document_version_id: Mapped[UUID | None] = mapped_column(nullable=True)
