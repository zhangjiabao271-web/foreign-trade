from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.content_review import ContentReleaseMixin, review_constraint
from app.core.database import Base, TenantRecordMixin, membership_actor_foreign_key
from app.core.database_types import money_type


class CustomsDeclaration(ContentReleaseMixin, TenantRecordMixin, Base):
    __tablename__ = "customs_declarations"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_customs_org_id"),
        UniqueConstraint("organization_id", "shipment_id", name="uq_customs_org_shipment"),
        UniqueConstraint("organization_id", "declaration_number", name="uq_customs_org_number"),
        ForeignKeyConstraint(
            ["organization_id", "shipment_id"],
            ["shipments.organization_id", "shipments.id"],
            name="fk_customs_org_shipment",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("customs_declarations", "created_by"),
        membership_actor_foreign_key("customs_declarations", "updated_by"),
        membership_actor_foreign_key("customs_declarations", "reviewed_by"),
        review_constraint("customs_declarations"),
        CheckConstraint(
            "status IN ('DRAFT','DOCUMENTS_PENDING','READY','SUBMITTED','CLEARED','REJECTED')",
            name="ck_customs_status",
        ),
        CheckConstraint("declared_amount > 0", name="ck_customs_amount"),
        CheckConstraint("char_length(currency_code) = 3", name="ck_customs_currency"),
        Index("ix_customs_org_status_due", "organization_id", "status", "follow_up_date"),
    )
    declaration_number: Mapped[str] = mapped_column(String(40), nullable=False)
    shipment_id: Mapped[UUID] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="DRAFT")
    declared_amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    required_document_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    submitted_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    cleared_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class TaxRefundCase(ContentReleaseMixin, TenantRecordMixin, Base):
    __tablename__ = "tax_refund_cases"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_refund_org_id"),
        UniqueConstraint("organization_id", "customs_declaration_id", name="uq_refund_org_customs"),
        UniqueConstraint("organization_id", "case_number", name="uq_refund_org_number"),
        ForeignKeyConstraint(
            ["organization_id", "customs_declaration_id"],
            ["customs_declarations.organization_id", "customs_declarations.id"],
            name="fk_refund_org_customs",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("tax_refund_cases", "created_by"),
        membership_actor_foreign_key("tax_refund_cases", "updated_by"),
        membership_actor_foreign_key("tax_refund_cases", "reviewed_by"),
        review_constraint("tax_refund_cases"),
        CheckConstraint(
            "status IN ('NOT_READY','DOCUMENTS_PENDING','READY','SUBMITTED',"
            "'PROCESSING','REFUNDED','REJECTED')",
            name="ck_refund_status",
        ),
        CheckConstraint("expected_amount > 0", name="ck_refund_expected"),
        CheckConstraint(
            "refunded_amount >= 0 AND refunded_amount <= expected_amount", name="ck_refund_actual"
        ),
        CheckConstraint("char_length(currency_code) = 3", name="ck_refund_currency"),
        Index("ix_refund_org_status_due", "organization_id", "status", "follow_up_date"),
    )
    case_number: Mapped[str] = mapped_column(String(40), nullable=False)
    customs_declaration_id: Mapped[UUID] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="NOT_READY")
    expected_amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    refunded_amount: Mapped[Decimal] = mapped_column(
        money_type(), nullable=False, server_default="0"
    )
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    required_document_types: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    external_reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    submitted_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    refunded_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    follow_up_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
