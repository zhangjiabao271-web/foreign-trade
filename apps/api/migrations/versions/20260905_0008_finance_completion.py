"""receivables payments and order completion

Revision ID: 20260905_0008
Revises: 20260904_0007
Create Date: 2026-09-05 06:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260905_0008"
down_revision: str | None = "20260904_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def tenant_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
    ]


def tenant_constraints(table: str) -> list[sa.Constraint]:
    return [
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=f"fk_{table}_organization",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name=f"fk_{table}_created_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "updated_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name=f"fk_{table}_updated_membership",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=f"pk_{table}"),
        sa.UniqueConstraint("organization_id", "id", name=f"uq_{table}_org_id"),
    ]


def upgrade() -> None:
    op.create_table(
        "receivables",
        sa.Column("receivable_number", sa.String(40), nullable=False),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("installment_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(24), server_default="PENDING", nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        *tenant_columns(),
        sa.CheckConstraint(
            "status IN ('PENDING', 'DUE', 'PARTIALLY_PAID', 'PAID', 'OVERDUE')",
            name="ck_receivables_status",
        ),
        sa.CheckConstraint(
            "installment_type IN ('DEPOSIT', 'BALANCE')",
            name="ck_receivables_installment",
        ),
        sa.CheckConstraint("amount > 0", name="ck_receivables_amount"),
        sa.CheckConstraint("char_length(currency_code) = 3", name="ck_receivables_currency"),
        sa.ForeignKeyConstraint(
            ["organization_id", "sales_order_id"],
            ["sales_orders.organization_id", "sales_orders.id"],
            name="fk_receivables_org_order",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id", "receivable_number", name="uq_receivables_org_number"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "sales_order_id",
            "installment_type",
            name="uq_receivables_order_installment",
        ),
        *tenant_constraints("receivables"),
    )
    op.create_index(
        "ix_receivables_org_status_due",
        "receivables",
        ["organization_id", "status", "due_date"],
    )
    op.create_index(
        "ix_receivables_org_order", "receivables", ["organization_id", "sales_order_id"]
    )

    op.create_table(
        "payments",
        sa.Column("payment_number", sa.String(40), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), server_default="RECEIPT", nullable=False),
        sa.Column("status", sa.String(16), server_default="ACTIVE", nullable=False),
        sa.Column("reversal_of_payment_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("method", sa.String(24), nullable=False),
        sa.Column("reference", sa.String(160), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reversed_at", sa.DateTime(timezone=True), nullable=True),
        *tenant_columns(),
        sa.CheckConstraint("kind IN ('RECEIPT', 'REVERSAL')", name="ck_payments_kind"),
        sa.CheckConstraint("status IN ('ACTIVE', 'REVERSED')", name="ck_payments_status"),
        sa.CheckConstraint(
            "method IN ('BANK_TRANSFER', 'CARD', 'CASH', 'OTHER')",
            name="ck_payments_method",
        ),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount"),
        sa.CheckConstraint("char_length(currency_code) = 3", name="ck_payments_currency"),
        sa.CheckConstraint(
            "(kind = 'RECEIPT' AND reversal_of_payment_id IS NULL) OR "
            "(kind = 'REVERSAL' AND reversal_of_payment_id IS NOT NULL)",
            name="ck_payments_reversal_reference",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "company_id"],
            ["companies.organization_id", "companies.id"],
            name="fk_payments_org_company",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "reversal_of_payment_id"],
            ["payments.organization_id", "payments.id"],
            name="fk_payments_org_reversal",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("organization_id", "payment_number", name="uq_payments_org_number"),
        *tenant_constraints("payments"),
    )
    op.create_index(
        "uq_payments_org_reversal",
        "payments",
        ["organization_id", "reversal_of_payment_id"],
        unique=True,
        postgresql_where=sa.text("reversal_of_payment_id IS NOT NULL"),
    )
    op.create_index(
        "ix_payments_org_company_received",
        "payments",
        ["organization_id", "company_id", "received_at"],
    )

    op.create_table(
        "payment_allocations",
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("receivable_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), server_default="ALLOCATION", nullable=False),
        sa.Column("reversal_of_allocation_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("allocated_at", sa.DateTime(timezone=True), nullable=False),
        *tenant_columns(),
        sa.CheckConstraint("kind IN ('ALLOCATION', 'REVERSAL')", name="ck_allocations_kind"),
        sa.CheckConstraint("amount > 0", name="ck_allocations_amount"),
        sa.CheckConstraint(
            "(kind = 'ALLOCATION' AND reversal_of_allocation_id IS NULL) OR "
            "(kind = 'REVERSAL' AND reversal_of_allocation_id IS NOT NULL)",
            name="ck_allocations_reversal_reference",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "payment_id"],
            ["payments.organization_id", "payments.id"],
            name="fk_allocations_org_payment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "receivable_id"],
            ["receivables.organization_id", "receivables.id"],
            name="fk_allocations_org_receivable",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "reversal_of_allocation_id"],
            ["payment_allocations.organization_id", "payment_allocations.id"],
            name="fk_allocations_org_reversal",
            ondelete="RESTRICT",
        ),
        *tenant_constraints("payment_allocations"),
    )
    op.create_index(
        "uq_payment_allocations_org_reversal",
        "payment_allocations",
        ["organization_id", "reversal_of_allocation_id"],
        unique=True,
        postgresql_where=sa.text("reversal_of_allocation_id IS NOT NULL"),
    )
    op.create_index(
        "ix_allocations_org_receivable",
        "payment_allocations",
        ["organization_id", "receivable_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_allocations_org_receivable", table_name="payment_allocations")
    op.drop_index("uq_payment_allocations_org_reversal", table_name="payment_allocations")
    op.drop_table("payment_allocations")
    op.drop_index("ix_payments_org_company_received", table_name="payments")
    op.drop_index("uq_payments_org_reversal", table_name="payments")
    op.drop_table("payments")
    op.drop_index("ix_receivables_org_order", table_name="receivables")
    op.drop_index("ix_receivables_org_status_due", table_name="receivables")
    op.drop_table("receivables")
