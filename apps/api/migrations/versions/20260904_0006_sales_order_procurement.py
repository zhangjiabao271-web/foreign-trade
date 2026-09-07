"""sales order procurement vertical slice

Revision ID: 20260904_0006
Revises: 20260904_0005
Create Date: 2026-09-04 18:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260904_0006"
down_revision: str | None = "20260904_0005"
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
        "sales_orders",
        sa.Column("order_number", sa.String(length=40), nullable=False),
        sa.Column("quotation_id", sa.Uuid(), nullable=False),
        sa.Column("quotation_version_id", sa.Uuid(), nullable=False),
        sa.Column("opportunity_id", sa.Uuid(), nullable=False),
        sa.Column("company_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="DRAFT", nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("base_currency_code", sa.String(length=3), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("payment_terms", sa.Text(), nullable=True),
        sa.Column("delivery_terms", sa.Text(), nullable=True),
        sa.Column("subtotal", sa.Numeric(18, 4), nullable=False),
        sa.Column("tax_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("freight_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("total", sa.Numeric(18, 4), nullable=False),
        sa.Column("total_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("gross_profit", sa.Numeric(18, 4), nullable=False),
        sa.Column("gross_margin", sa.Numeric(18, 4), nullable=False),
        sa.Column("deposit_rate", sa.Numeric(18, 4), nullable=False),
        sa.Column("deposit_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("deposit_due_date", sa.Date(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        *tenant_columns(),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'CONFIRMED', 'DEPOSIT_PENDING', 'EXECUTING', "
            "'READY_TO_SHIP', 'SHIPPED', 'COMPLETED', 'CANCELLED')",
            name="ck_sales_orders_status",
        ),
        sa.CheckConstraint("char_length(currency_code) = 3", name="ck_sales_orders_currency"),
        sa.CheckConstraint(
            "char_length(base_currency_code) = 3", name="ck_sales_orders_base_currency"
        ),
        sa.CheckConstraint("exchange_rate > 0", name="ck_sales_orders_exchange_rate"),
        sa.CheckConstraint(
            "deposit_rate >= 0 AND deposit_rate <= 1", name="ck_sales_orders_deposit_rate"
        ),
        sa.CheckConstraint(
            "subtotal >= 0 AND total >= 0 AND total_cost >= 0 AND deposit_amount >= 0",
            name="ck_sales_orders_totals",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "quotation_id"],
            ["quotations.organization_id", "quotations.id"],
            name="fk_sales_orders_org_quotation",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "quotation_id", "quotation_version_id"],
            [
                "quotation_versions.organization_id",
                "quotation_versions.quotation_id",
                "quotation_versions.id",
            ],
            name="fk_sales_orders_org_quotation_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "company_id"],
            ["companies.organization_id", "companies.id"],
            name="fk_sales_orders_org_company",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("organization_id", "order_number", name="uq_sales_orders_org_number"),
        sa.UniqueConstraint("organization_id", "quotation_id", name="uq_sales_orders_org_quote"),
        *tenant_constraints("sales_orders"),
    )
    op.create_index(
        "ix_sales_orders_org_status_created",
        "sales_orders",
        ["organization_id", "status", "created_at"],
    )
    op.create_table(
        "tasks",
        sa.Column("task_type", sa.String(length=80), nullable=False),
        sa.Column("subject_type", sa.String(length=80), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="OPEN", nullable=False),
        sa.Column("priority", sa.String(length=12), server_default="NORMAL", nullable=False),
        sa.Column("assigned_to", sa.Uuid(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        *tenant_columns(),
        sa.CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'DONE', 'CANCELLED')",
            name="ck_tasks_status",
        ),
        sa.CheckConstraint("priority IN ('LOW', 'NORMAL', 'HIGH')", name="ck_tasks_priority"),
        sa.ForeignKeyConstraint(
            ["organization_id", "assigned_to"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_tasks_org_assigned_membership",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "subject_type",
            "subject_id",
            "task_type",
            name="uq_tasks_org_subject_type",
        ),
        *tenant_constraints("tasks"),
    )
    op.create_index("ix_tasks_org_status_due", "tasks", ["organization_id", "status", "due_at"])
    op.create_index(
        "ix_tasks_org_subject", "tasks", ["organization_id", "subject_type", "subject_id"]
    )
    op.create_table(
        "sales_order_items",
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("quotation_item_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("sku_snapshot", sa.String(length=80), nullable=False),
        sa.Column("description_snapshot", sa.Text(), nullable=False),
        sa.Column("unit_snapshot", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("cost_currency", sa.String(length=3), nullable=False),
        sa.Column("cost_exchange_rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("tax_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("freight_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("allocated_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("line_subtotal", sa.Numeric(18, 4), nullable=False),
        sa.Column("line_total", sa.Numeric(18, 4), nullable=False),
        sa.Column("line_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("line_gross_profit", sa.Numeric(18, 4), nullable=False),
        *tenant_columns(),
        sa.CheckConstraint("line_number > 0", name="ck_sales_order_items_line"),
        sa.CheckConstraint("quantity > 0", name="ck_sales_order_items_quantity"),
        sa.CheckConstraint(
            "unit_price >= 0 AND unit_cost >= 0 AND line_total >= 0 AND line_cost >= 0",
            name="ck_sales_order_items_amounts",
        ),
        sa.CheckConstraint("cost_exchange_rate > 0", name="ck_sales_order_items_rate"),
        sa.CheckConstraint("char_length(cost_currency) = 3", name="ck_sales_order_items_currency"),
        sa.ForeignKeyConstraint(
            ["organization_id", "sales_order_id"],
            ["sales_orders.organization_id", "sales_orders.id"],
            name="fk_sales_order_items_org_order",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "quotation_item_id"],
            ["quotation_items.organization_id", "quotation_items.id"],
            name="fk_sales_order_items_org_quote_item",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "product_id"],
            ["products.organization_id", "products.id"],
            name="fk_sales_order_items_org_product",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id", "sales_order_id", "line_number", name="uq_sales_order_items_line"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "sales_order_id",
            "quotation_item_id",
            name="uq_sales_order_items_quote_item",
        ),
        *tenant_constraints("sales_order_items"),
    )
    op.create_table(
        "purchase_orders",
        sa.Column("purchase_order_number", sa.String(length=40), nullable=False),
        sa.Column("sales_order_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_company_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="DRAFT", nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("exchange_rate", sa.Numeric(18, 8), nullable=False),
        sa.Column("total", sa.Numeric(18, 4), nullable=False),
        sa.Column("total_order_currency", sa.Numeric(18, 4), nullable=False),
        sa.Column("supplier_reference", sa.String(length=120), nullable=True),
        sa.Column("expected_delivery_date", sa.Date(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        *tenant_columns(),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'APPROVED', 'SENT', 'CONFIRMED', 'PARTIALLY_RECEIVED', "
            "'RECEIVED', 'CLOSED', 'CANCELLED')",
            name="ck_purchase_orders_status",
        ),
        sa.CheckConstraint("char_length(currency_code) = 3", name="ck_purchase_orders_currency"),
        sa.CheckConstraint("exchange_rate > 0", name="ck_purchase_orders_rate"),
        sa.CheckConstraint(
            "total >= 0 AND total_order_currency >= 0", name="ck_purchase_orders_totals"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "sales_order_id"],
            ["sales_orders.organization_id", "sales_orders.id"],
            name="fk_purchase_orders_org_sales_order",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "supplier_company_id"],
            ["companies.organization_id", "companies.id"],
            name="fk_purchase_orders_org_supplier",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "approved_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_purchase_orders_org_approver",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id", "purchase_order_number", name="uq_purchase_orders_org_number"
        ),
        *tenant_constraints("purchase_orders"),
    )
    op.create_index(
        "ix_purchase_orders_org_status_created",
        "purchase_orders",
        ["organization_id", "status", "created_at"],
    )
    op.create_index(
        "ix_purchase_orders_org_sales_order",
        "purchase_orders",
        ["organization_id", "sales_order_id"],
    )
    op.create_table(
        "purchase_order_items",
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("sales_order_item_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("sku_snapshot", sa.String(length=80), nullable=False),
        sa.Column("description_snapshot", sa.Text(), nullable=False),
        sa.Column("unit_snapshot", sa.String(length=32), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(18, 4), nullable=False),
        sa.Column("line_total", sa.Numeric(18, 4), nullable=False),
        *tenant_columns(),
        sa.CheckConstraint("line_number > 0", name="ck_purchase_order_items_line"),
        sa.CheckConstraint("quantity > 0", name="ck_purchase_order_items_quantity"),
        sa.CheckConstraint(
            "unit_cost >= 0 AND line_total >= 0", name="ck_purchase_order_items_amounts"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "purchase_order_id"],
            ["purchase_orders.organization_id", "purchase_orders.id"],
            name="fk_purchase_order_items_org_order",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "sales_order_item_id"],
            ["sales_order_items.organization_id", "sales_order_items.id"],
            name="fk_purchase_order_items_org_sales_item",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id", "purchase_order_id", "line_number", name="uq_po_items_line"
        ),
        sa.UniqueConstraint(
            "organization_id",
            "purchase_order_id",
            "sales_order_item_id",
            name="uq_po_items_sales_item",
        ),
        *tenant_constraints("purchase_order_items"),
    )


def downgrade() -> None:
    op.drop_table("purchase_order_items")
    op.drop_index("ix_purchase_orders_org_sales_order", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_org_status_created", table_name="purchase_orders")
    op.drop_table("purchase_orders")
    op.drop_table("sales_order_items")
    op.drop_index("ix_tasks_org_subject", table_name="tasks")
    op.drop_index("ix_tasks_org_status_due", table_name="tasks")
    op.drop_table("tasks")
    op.drop_index("ix_sales_orders_org_status_created", table_name="sales_orders")
    op.drop_table("sales_orders")
