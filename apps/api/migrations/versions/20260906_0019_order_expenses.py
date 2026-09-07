"""Preserve incurred order expenses and append-only reversal evidence."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_0019"
down_revision = "20260906_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("expense_number", sa.String(40), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("category", sa.String(24), nullable=False),
        sa.Column("cost_treatment", sa.String(32), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("order_currency_code", sa.String(3), nullable=False),
        sa.Column("order_currency_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("incurred_on", sa.Date(), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("evidence_reference", sa.String(240), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("reversal_of_expense_id", sa.Uuid(), nullable=True),
        sa.UniqueConstraint("organization_id", "id", name="uq_expenses_org_id"),
        sa.UniqueConstraint(
            "organization_id", "sales_order_id", "id", name="uq_expenses_org_order_id"
        ),
        sa.UniqueConstraint("organization_id", "expense_number", name="uq_expenses_org_number"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "sales_order_id"],
            ["sales_orders.organization_id", "sales_orders.id"],
            name="fk_expenses_org_order",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "sales_order_id", "reversal_of_expense_id"],
            ["expenses.organization_id", "expenses.sales_order_id", "expenses.id"],
            name="fk_expenses_org_order_original",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_expenses_organization_id_created_by_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "updated_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_expenses_organization_id_updated_by_membership",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("kind IN ('EXPENSE', 'REVERSAL')", name="expense_kind"),
        sa.CheckConstraint(
            "category IN ('FREIGHT', 'INSPECTION', 'BANK_FEE', 'CUSTOMS', 'OTHER')",
            name="expense_category",
        ),
        sa.CheckConstraint(
            "cost_treatment IN ('ADDITIONAL', 'INCLUDED_IN_QUOTATION')", name="expense_treatment"
        ),
        sa.CheckConstraint(
            "amount > 0 AND exchange_rate > 0 AND order_currency_amount >= 0",
            name="expense_amounts",
        ),
        sa.CheckConstraint(
            "currency_code ~ '^[A-Z]{3}$' AND order_currency_code ~ '^[A-Z]{3}$'",
            name="expense_currencies",
        ),
        sa.CheckConstraint(
            "(kind = 'EXPENSE' AND reversal_of_expense_id IS NULL) OR "
            "(kind = 'REVERSAL' AND reversal_of_expense_id IS NOT NULL "
            "AND reversal_of_expense_id != id)",
            name="expense_reversal",
        ),
    )
    op.create_index(
        "uq_expenses_org_reversal",
        "expenses",
        ["organization_id", "reversal_of_expense_id"],
        unique=True,
        postgresql_where=sa.text("reversal_of_expense_id IS NOT NULL"),
    )
    op.create_index(
        "ix_expenses_org_order_created",
        "expenses",
        ["organization_id", "sales_order_id", "created_at", "id"],
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM expenses)")):
        raise RuntimeError("Expense facts exist; preserve them and use a forward migration")
    op.drop_table("expenses")
