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
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TenantRecordMixin, membership_actor_foreign_key
from app.core.database_types import money_type


class Payable(TenantRecordMixin, Base):
    __tablename__ = "payables"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_payables_org_id"),
        UniqueConstraint("organization_id", "payable_number", name="uq_payables_org_number"),
        ForeignKeyConstraint(
            ["organization_id", "purchase_order_id"],
            ["purchase_orders.organization_id", "purchase_orders.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "sales_order_id"],
            ["sales_orders.organization_id", "sales_orders.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "supplier_company_id"],
            ["companies.organization_id", "companies.id"],
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("payables", "created_by"),
        membership_actor_foreign_key("payables", "updated_by"),
        membership_actor_foreign_key("payables", "voided_by"),
        CheckConstraint("amount > 0", name="positive_amount"),
        CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="currency"),
        CheckConstraint(
            "(voided_at IS NULL AND voided_by IS NULL AND void_reason IS NULL) OR "
            "(voided_at IS NOT NULL AND voided_by IS NOT NULL AND void_reason IS NOT NULL)",
            name="void_evidence",
        ),
        Index(
            "ix_payables_org_purchase_cursor",
            "organization_id",
            "purchase_order_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_payables_org_supplier_cursor",
            "organization_id",
            "supplier_company_id",
            "currency_code",
            "created_at",
            "id",
        ),
    )
    payable_number: Mapped[str] = mapped_column(String(40), nullable=False)
    purchase_order_id: Mapped[UUID] = mapped_column(nullable=False)
    sales_order_id: Mapped[UUID] = mapped_column(nullable=False)
    supplier_company_id: Mapped[UUID] = mapped_column(nullable=False)
    amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    incurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    reference: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_by: Mapped[UUID | None] = mapped_column(nullable=True)
    void_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class SupplierPayment(TenantRecordMixin, Base):
    __tablename__ = "supplier_payments"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_supplier_payments_org_id"),
        UniqueConstraint(
            "organization_id", "payment_number", name="uq_supplier_payments_org_number"
        ),
        ForeignKeyConstraint(
            ["organization_id", "supplier_company_id"],
            ["companies.organization_id", "companies.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "reversal_of_payment_id"],
            ["supplier_payments.organization_id", "supplier_payments.id"],
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("supplier_payments", "created_by"),
        membership_actor_foreign_key("supplier_payments", "updated_by"),
        CheckConstraint("amount > 0", name="positive_amount"),
        CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="currency"),
        CheckConstraint("method IN ('BANK_TRANSFER', 'CARD', 'CASH', 'OTHER')", name="method"),
        CheckConstraint(
            "(kind = 'PAYMENT' AND reversal_of_payment_id IS NULL) OR "
            "(kind = 'REVERSAL' AND reversal_of_payment_id IS NOT NULL "
            "AND reversal_of_payment_id != id)",
            name="reversal",
        ),
        Index(
            "uq_supplier_payments_org_reversal",
            "organization_id",
            "reversal_of_payment_id",
            unique=True,
            postgresql_where=text("reversal_of_payment_id IS NOT NULL"),
        ),
        Index(
            "ix_supplier_payments_org_supplier_cursor",
            "organization_id",
            "supplier_company_id",
            "currency_code",
            "created_at",
            "id",
        ),
    )
    payment_number: Mapped[str] = mapped_column(String(40), nullable=False)
    supplier_company_id: Mapped[UUID] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    method: Mapped[str] = mapped_column(String(24), nullable=False)
    reference: Mapped[str] = mapped_column(String(240), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    reversal_of_payment_id: Mapped[UUID | None] = mapped_column(nullable=True)


class SupplierPaymentAllocation(TenantRecordMixin, Base):
    __tablename__ = "supplier_payment_allocations"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_supplier_allocations_org_id"),
        ForeignKeyConstraint(
            ["organization_id", "payment_id"],
            ["supplier_payments.organization_id", "supplier_payments.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "payable_id"],
            ["payables.organization_id", "payables.id"],
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "reversal_of_allocation_id"],
            ["supplier_payment_allocations.organization_id", "supplier_payment_allocations.id"],
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("supplier_allocations", "created_by"),
        membership_actor_foreign_key("supplier_allocations", "updated_by"),
        CheckConstraint("amount > 0", name="positive_amount"),
        CheckConstraint(
            "(kind = 'ALLOCATION' AND reversal_of_allocation_id IS NULL) OR "
            "(kind = 'REVERSAL' AND reversal_of_allocation_id IS NOT NULL "
            "AND reversal_of_allocation_id != id)",
            name="reversal",
        ),
        Index(
            "uq_supplier_allocations_org_reversal",
            "organization_id",
            "reversal_of_allocation_id",
            unique=True,
            postgresql_where=text("reversal_of_allocation_id IS NOT NULL"),
        ),
        Index("ix_supplier_allocations_org_payable", "organization_id", "payable_id"),
        Index("ix_supplier_allocations_org_payment", "organization_id", "payment_id"),
    )
    payment_id: Mapped[UUID] = mapped_column(nullable=False)
    payable_id: Mapped[UUID] = mapped_column(nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    reversal_of_allocation_id: Mapped[UUID | None] = mapped_column(nullable=True)
