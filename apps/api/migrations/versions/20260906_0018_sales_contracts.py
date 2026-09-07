"""Preserve order-linked contract snapshots and exact signature evidence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260906_0018"
down_revision = "20260906_0017"
branch_labels = None
depends_on = None

OLD_TYPES = (
    "document_type IN ('COMMERCIAL_INVOICE', 'PACKING_LIST', 'BILL_OF_LADING', "
    "'CERTIFICATE_OF_ORIGIN', 'BOOKING_CONFIRMATION', 'OTHER')"
)
NEW_TYPES = (
    "document_type IN ('COMMERCIAL_INVOICE', 'PACKING_LIST', 'BILL_OF_LADING', "
    "'CERTIFICATE_OF_ORIGIN', 'BOOKING_CONFIRMATION', 'SALES_CONTRACT', 'OTHER')"
)


def upgrade() -> None:
    op.drop_constraint("ck_documents_type", "documents", type_="check")
    op.create_check_constraint("ck_documents_type", "documents", NEW_TYPES)
    op.create_table(
        "sales_contracts",
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
        sa.Column("contract_number", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("currency_code", sa.String(3), nullable=False),
        sa.Column("total", sa.Numeric(18, 4), nullable=False),
        sa.Column("commercial_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("external_reference", sa.String(160), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("signed_on", sa.Date(), nullable=True),
        sa.Column("signed_document_version_id", sa.Uuid(), nullable=True),
        sa.UniqueConstraint("organization_id", "id", name="uq_sales_contracts_org_id"),
        sa.UniqueConstraint(
            "organization_id", "contract_number", name="uq_sales_contracts_org_number"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["organization_id", "sales_order_id"],
            ["sales_orders.organization_id", "sales_orders.id"],
            name="fk_sales_contracts_org_order",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "signed_document_version_id"],
            ["document_versions.organization_id", "document_versions.id"],
            name="fk_sales_contracts_org_evidence",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_sales_contracts_organization_id_created_by_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "updated_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_sales_contracts_organization_id_updated_by_membership",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'SIGNED', 'VOIDED')", name="ck_sales_contracts_status"
        ),
        sa.CheckConstraint("total >= 0", name="ck_sales_contracts_total"),
        sa.CheckConstraint("currency_code ~ '^[A-Z]{3}$'", name="ck_sales_contracts_currency"),
        sa.CheckConstraint(
            "(status = 'SIGNED' AND signed_on IS NOT NULL "
            "AND signed_document_version_id IS NOT NULL) "
            "OR (status != 'SIGNED' AND signed_on IS NULL AND signed_document_version_id IS NULL)",
            name="ck_sales_contracts_signed_evidence",
        ),
    )
    op.create_index(
        "uq_sales_contracts_org_order_active",
        "sales_contracts",
        ["organization_id", "sales_order_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND status != 'VOIDED'"),
    )
    op.create_index(
        "ix_sales_contracts_org_order_created",
        "sales_contracts",
        ["organization_id", "sales_order_id", "created_at", "id"],
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM sales_contracts) "
            "OR EXISTS (SELECT 1 FROM documents WHERE document_type = 'SALES_CONTRACT')"
        )
    ):
        raise RuntimeError("Contract evidence exists; preserve it and use a forward migration")
    op.drop_table("sales_contracts")
    op.drop_constraint("ck_documents_type", "documents", type_="check")
    op.create_check_constraint("ck_documents_type", "documents", OLD_TYPES)
