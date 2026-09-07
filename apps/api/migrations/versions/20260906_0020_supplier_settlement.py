"""Preserve supplier payable, payment and allocation facts without inferred backfill."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_0020"
down_revision = "20260906_0019"
branch_labels = None
depends_on = None


def base_columns():
    return [
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
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    ]


def tenant_constraints(table):
    prefix = "supplier_allocations" if table == "supplier_payment_allocations" else table
    return [
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        *[
            sa.ForeignKeyConstraint(
                ["organization_id", actor],
                ["organization_memberships.organization_id", "organization_memberships.user_id"],
                name=f"fk_{prefix}_organization_id_{actor}_membership",
                ondelete="RESTRICT",
            )
            for actor in ("created_by", "updated_by")
        ],
    ]


def tenant_reference(column, target):
    return sa.ForeignKeyConstraint(
        ["organization_id", column],
        [f"{target}.organization_id", f"{target}.id"],
        ondelete="RESTRICT",
    )


def upgrade() -> None:
    op.create_table(
        "payables",
        *base_columns(),
        sa.Column("payable_number", sa.String(40), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_company_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("incurred_on", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(240), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_by", sa.Uuid(), nullable=True),
        sa.Column("void_reason", sa.String(500), nullable=True),
        sa.UniqueConstraint("organization_id", "id", name="uq_payables_org_id"),
        sa.UniqueConstraint("organization_id", "payable_number", name="uq_payables_org_number"),
        *tenant_constraints("payables"),
        tenant_reference("purchase_order_id", "purchase_orders"),
        tenant_reference("sales_order_id", "sales_orders"),
        tenant_reference("supplier_company_id", "companies"),
        sa.ForeignKeyConstraint(
            ["organization_id", "voided_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_payables_organization_id_voided_by_membership",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("amount > 0", name="positive_amount"),
        sa.CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="currency"),
        sa.CheckConstraint(
            "(voided_at IS NULL AND voided_by IS NULL AND void_reason IS NULL) OR "
            "(voided_at IS NOT NULL AND voided_by IS NOT NULL AND void_reason IS NOT NULL)",
            name="void_evidence",
        ),
    )
    op.create_index(
        "ix_payables_org_purchase_cursor",
        "payables",
        ["organization_id", "purchase_order_id", "created_at", "id"],
    )
    op.create_index(
        "ix_payables_org_supplier_cursor",
        "payables",
        ["organization_id", "supplier_company_id", "currency_code", "created_at", "id"],
    )
    op.create_table(
        "supplier_payments",
        *base_columns(),
        sa.Column("payment_number", sa.String(40), nullable=False),
        sa.Column("supplier_company_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("method", sa.String(24), nullable=False),
        sa.Column("reference", sa.String(240), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("reversal_of_payment_id", sa.Uuid(), nullable=True),
        sa.UniqueConstraint("organization_id", "id", name="uq_supplier_payments_org_id"),
        sa.UniqueConstraint(
            "organization_id", "payment_number", name="uq_supplier_payments_org_number"
        ),
        *tenant_constraints("supplier_payments"),
        tenant_reference("supplier_company_id", "companies"),
        tenant_reference("reversal_of_payment_id", "supplier_payments"),
        sa.CheckConstraint("amount > 0", name="positive_amount"),
        sa.CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="currency"),
        sa.CheckConstraint("method IN ('BANK_TRANSFER', 'CARD', 'CASH', 'OTHER')", name="method"),
        sa.CheckConstraint(
            "(kind = 'PAYMENT' AND reversal_of_payment_id IS NULL) OR "
            "(kind = 'REVERSAL' AND reversal_of_payment_id IS NOT NULL "
            "AND reversal_of_payment_id != id)",
            name="reversal",
        ),
    )
    op.create_index(
        "uq_supplier_payments_org_reversal",
        "supplier_payments",
        ["organization_id", "reversal_of_payment_id"],
        unique=True,
        postgresql_where=sa.text("reversal_of_payment_id IS NOT NULL"),
    )
    op.create_index(
        "ix_supplier_payments_org_supplier_cursor",
        "supplier_payments",
        ["organization_id", "supplier_company_id", "currency_code", "created_at", "id"],
    )
    op.create_table(
        "supplier_payment_allocations",
        *base_columns(),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("payable_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("reversal_of_allocation_id", sa.Uuid(), nullable=True),
        sa.UniqueConstraint("organization_id", "id", name="uq_supplier_allocations_org_id"),
        *tenant_constraints("supplier_payment_allocations"),
        tenant_reference("payment_id", "supplier_payments"),
        tenant_reference("payable_id", "payables"),
        tenant_reference("reversal_of_allocation_id", "supplier_payment_allocations"),
        sa.CheckConstraint("amount > 0", name="positive_amount"),
        sa.CheckConstraint(
            "(kind = 'ALLOCATION' AND reversal_of_allocation_id IS NULL) OR "
            "(kind = 'REVERSAL' AND reversal_of_allocation_id IS NOT NULL "
            "AND reversal_of_allocation_id != id)",
            name="reversal",
        ),
    )
    op.create_index(
        "uq_supplier_allocations_org_reversal",
        "supplier_payment_allocations",
        ["organization_id", "reversal_of_allocation_id"],
        unique=True,
        postgresql_where=sa.text("reversal_of_allocation_id IS NOT NULL"),
    )
    op.create_index(
        "ix_supplier_allocations_org_payable",
        "supplier_payment_allocations",
        ["organization_id", "payable_id"],
    )
    op.create_index(
        "ix_supplier_allocations_org_payment",
        "supplier_payment_allocations",
        ["organization_id", "payment_id"],
    )


def downgrade() -> None:
    for table in ("payables", "supplier_payments", "supplier_payment_allocations"):
        if op.get_bind().scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")):
            raise RuntimeError("Supplier financial facts exist; use a forward migration")
    for table in ("supplier_payment_allocations", "supplier_payments", "payables"):
        op.drop_table(table)
