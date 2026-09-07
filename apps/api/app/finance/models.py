from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    Date,
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
from app.core.database_types import money_type


class Receivable(TenantRecordMixin, Base):
    __tablename__ = "receivables"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_receivables_org_id"),
        UniqueConstraint("organization_id", "receivable_number", name="uq_receivables_org_number"),
        UniqueConstraint(
            "organization_id",
            "sales_order_id",
            "installment_type",
            name="uq_receivables_order_installment",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'DUE', 'PARTIALLY_PAID', 'PAID', 'OVERDUE')",
            name="ck_receivables_status",
        ),
        CheckConstraint(
            "installment_type IN ('DEPOSIT', 'BALANCE')",
            name="ck_receivables_installment",
        ),
        CheckConstraint("amount > 0", name="ck_receivables_amount"),
        CheckConstraint("char_length(currency_code) = 3", name="ck_receivables_currency"),
        ForeignKeyConstraint(
            ["organization_id", "sales_order_id"],
            ["sales_orders.organization_id", "sales_orders.id"],
            name="fk_receivables_org_order",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("receivables", "created_by"),
        membership_actor_foreign_key("receivables", "updated_by"),
        Index("ix_receivables_org_status_due", "organization_id", "status", "due_date"),
        Index("ix_receivables_org_order", "organization_id", "sales_order_id"),
    )

    receivable_number: Mapped[str] = mapped_column(String(40), nullable=False)
    sales_order_id: Mapped[UUID] = mapped_column(nullable=False)
    installment_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="PENDING")
    amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Payment(ContentReleaseMixin, TenantRecordMixin, Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_payments_org_id"),
        UniqueConstraint("organization_id", "payment_number", name="uq_payments_org_number"),
        CheckConstraint("kind IN ('RECEIPT', 'REVERSAL')", name="ck_payments_kind"),
        CheckConstraint("status IN ('ACTIVE', 'REVERSED')", name="ck_payments_status"),
        CheckConstraint(
            "method IN ('BANK_TRANSFER', 'CARD', 'CASH', 'OTHER')",
            name="ck_payments_method",
        ),
        CheckConstraint("amount > 0", name="ck_payments_amount"),
        CheckConstraint("char_length(currency_code) = 3", name="ck_payments_currency"),
        CheckConstraint(
            "(kind = 'RECEIPT' AND reversal_of_payment_id IS NULL) OR "
            "(kind = 'REVERSAL' AND reversal_of_payment_id IS NOT NULL)",
            name="ck_payments_reversal_reference",
        ),
        ForeignKeyConstraint(
            ["organization_id", "company_id"],
            ["companies.organization_id", "companies.id"],
            name="fk_payments_org_company",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "reversal_of_payment_id"],
            ["payments.organization_id", "payments.id"],
            name="fk_payments_org_reversal",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("payments", "created_by"),
        membership_actor_foreign_key("payments", "updated_by"),
        membership_actor_foreign_key("payments", "reviewed_by"),
        review_constraint("payments"),
        Index(
            "uq_payments_org_reversal",
            "organization_id",
            "reversal_of_payment_id",
            unique=True,
            postgresql_where=text("reversal_of_payment_id IS NOT NULL"),
        ),
        Index("ix_payments_org_company_received", "organization_id", "company_id", "received_at"),
        Index(
            "ix_payments_org_received_cursor", "organization_id", "received_at", "created_at", "id"
        ),
        Index(
            "ix_payments_org_customer_currency_cursor",
            "organization_id",
            "company_id",
            "currency_code",
            "received_at",
            "created_at",
            "id",
        ),
    )

    payment_number: Mapped[str] = mapped_column(String(40), nullable=False)
    company_id: Mapped[UUID] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="RECEIPT")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="ACTIVE")
    reversal_of_payment_id: Mapped[UUID | None] = mapped_column(nullable=True)
    amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    method: Mapped[str] = mapped_column(String(24), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(160), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentAllocation(TenantRecordMixin, Base):
    __tablename__ = "payment_allocations"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_payment_allocations_org_id"),
        CheckConstraint("kind IN ('ALLOCATION', 'REVERSAL')", name="ck_allocations_kind"),
        CheckConstraint("amount > 0", name="ck_allocations_amount"),
        CheckConstraint(
            "(kind = 'ALLOCATION' AND reversal_of_allocation_id IS NULL) OR "
            "(kind = 'REVERSAL' AND reversal_of_allocation_id IS NOT NULL)",
            name="ck_allocations_reversal_reference",
        ),
        ForeignKeyConstraint(
            ["organization_id", "payment_id"],
            ["payments.organization_id", "payments.id"],
            name="fk_allocations_org_payment",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "receivable_id"],
            ["receivables.organization_id", "receivables.id"],
            name="fk_allocations_org_receivable",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "reversal_of_allocation_id"],
            ["payment_allocations.organization_id", "payment_allocations.id"],
            name="fk_allocations_org_reversal",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("payment_allocations", "created_by"),
        membership_actor_foreign_key("payment_allocations", "updated_by"),
        Index(
            "uq_payment_allocations_org_reversal",
            "organization_id",
            "reversal_of_allocation_id",
            unique=True,
            postgresql_where=text("reversal_of_allocation_id IS NOT NULL"),
        ),
        Index("ix_allocations_org_receivable", "organization_id", "receivable_id"),
    )

    payment_id: Mapped[UUID] = mapped_column(nullable=False)
    receivable_id: Mapped[UUID] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, server_default="ALLOCATION")
    reversal_of_allocation_id: Mapped[UUID | None] = mapped_column(nullable=True)
    amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    allocated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
