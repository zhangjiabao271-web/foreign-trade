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
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TenantRecordMixin, membership_actor_foreign_key
from app.core.database_types import exchange_rate_type, money_type


class ExpenseKind(StrEnum):
    EXPENSE = "EXPENSE"
    REVERSAL = "REVERSAL"


class ExpenseCategory(StrEnum):
    FREIGHT = "FREIGHT"
    INSPECTION = "INSPECTION"
    BANK_FEE = "BANK_FEE"
    CUSTOMS = "CUSTOMS"
    OTHER = "OTHER"


class ExpenseTreatment(StrEnum):
    ADDITIONAL = "ADDITIONAL"
    INCLUDED_IN_QUOTATION = "INCLUDED_IN_QUOTATION"


class Expense(TenantRecordMixin, Base):
    __tablename__ = "expenses"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_expenses_org_id"),
        UniqueConstraint(
            "organization_id", "sales_order_id", "id", name="uq_expenses_org_order_id"
        ),
        UniqueConstraint("organization_id", "expense_number", name="uq_expenses_org_number"),
        ForeignKeyConstraint(
            ["organization_id", "sales_order_id"],
            ["sales_orders.organization_id", "sales_orders.id"],
            name="fk_expenses_org_order",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["organization_id", "sales_order_id", "reversal_of_expense_id"],
            ["expenses.organization_id", "expenses.sales_order_id", "expenses.id"],
            name="fk_expenses_org_order_original",
            ondelete="RESTRICT",
        ),
        CheckConstraint("kind IN ('EXPENSE', 'REVERSAL')", name="expense_kind"),
        CheckConstraint(
            "category IN ('FREIGHT', 'INSPECTION', 'BANK_FEE', 'CUSTOMS', 'OTHER')",
            name="expense_category",
        ),
        CheckConstraint(
            "cost_treatment IN ('ADDITIONAL', 'INCLUDED_IN_QUOTATION')", name="expense_treatment"
        ),
        CheckConstraint(
            "amount > 0 AND exchange_rate > 0 AND order_currency_amount >= 0",
            name="expense_amounts",
        ),
        CheckConstraint(
            "currency_code ~ '^[A-Z]{3}$' AND order_currency_code ~ '^[A-Z]{3}$'",
            name="expense_currencies",
        ),
        CheckConstraint(
            "(kind = 'EXPENSE' AND reversal_of_expense_id IS NULL) OR "
            "(kind = 'REVERSAL' AND reversal_of_expense_id IS NOT NULL "
            "AND reversal_of_expense_id != id)",
            name="expense_reversal",
        ),
        membership_actor_foreign_key("expenses", "created_by"),
        membership_actor_foreign_key("expenses", "updated_by"),
        Index(
            "uq_expenses_org_reversal",
            "organization_id",
            "reversal_of_expense_id",
            unique=True,
            postgresql_where=text("reversal_of_expense_id IS NOT NULL"),
        ),
        Index(
            "ix_expenses_org_order_created", "organization_id", "sales_order_id", "created_at", "id"
        ),
    )
    sales_order_id: Mapped[UUID] = mapped_column(nullable=False)
    expense_number: Mapped[str] = mapped_column(String(40), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(24), nullable=False)
    cost_treatment: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    exchange_rate: Mapped[Decimal] = mapped_column(exchange_rate_type(), nullable=False)
    order_currency_code: Mapped[str] = mapped_column(String(3), nullable=False)
    order_currency_amount: Mapped[Decimal] = mapped_column(money_type(), nullable=False)
    incurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence_reference: Mapped[str] = mapped_column(String(240), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    reversal_of_expense_id: Mapped[UUID | None] = mapped_column(nullable=True)
