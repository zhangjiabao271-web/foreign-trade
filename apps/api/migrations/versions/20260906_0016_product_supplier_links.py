"""Add product supplier reference terms without rewriting commercial snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_0016"
down_revision = "20260906_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_supplier_links",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_id", sa.Uuid(), nullable=False),
        sa.Column("supplier_sku", sa.String(80), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 4), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("lead_time_days", sa.Integer(), nullable=False),
        sa.Column("quoted_on", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("quotation_reference", sa.String(500), nullable=True),
        sa.UniqueConstraint("organization_id", "id"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "product_id"],
            ["products.organization_id", "products.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "supplier_id"],
            ["companies.organization_id", "companies.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_product_supplier_links_organization_id_created_by_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "updated_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_product_supplier_links_organization_id_updated_by_membership",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("unit_price >= 0", name="supplier_price_non_negative"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="supplier_currency_format"),
        sa.CheckConstraint(
            "lead_time_days >= 0 AND lead_time_days <= 3650", name="supplier_lead_time_range"
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until >= quoted_on", name="supplier_quote_date_order"
        ),
    )
    op.create_index(
        "uq_product_supplier_links_org_product_supplier_active",
        "product_supplier_links",
        ["organization_id", "product_id", "supplier_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_product_supplier_links_org_product_created",
        "product_supplier_links",
        ["organization_id", "product_id", "created_at", "id"],
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM product_supplier_links)")):
        raise RuntimeError(
            "Product supplier references exist; preserve their evidence and use a forward migration"
        )
    op.drop_table("product_supplier_links")
