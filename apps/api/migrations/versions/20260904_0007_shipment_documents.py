"""shipment documents vertical slice

Revision ID: 20260904_0007
Revises: 20260904_0006
Create Date: 2026-09-04 23:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_0007"
down_revision: str | None = "20260904_0006"
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
        "shipments",
        sa.Column("shipment_number", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), server_default="PLANNING", nullable=False),
        sa.Column("forwarder_company_id", sa.Uuid(), nullable=True),
        sa.Column("booking_reference", sa.String(120), nullable=True),
        sa.Column("planned_departure_date", sa.Date(), nullable=True),
        sa.Column("planned_arrival_date", sa.Date(), nullable=True),
        sa.Column("booked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("customs_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("departed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("in_transit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        *tenant_columns(),
        sa.CheckConstraint(
            "status IN ('PLANNING', 'BOOKED', 'READY', 'CUSTOMS', 'DEPARTED', "
            "'IN_TRANSIT', 'ARRIVED', 'DELIVERED')",
            name="ck_shipments_status",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "forwarder_company_id"],
            ["companies.organization_id", "companies.id"],
            name="fk_shipments_org_forwarder",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("organization_id", "shipment_number", name="uq_shipments_org_number"),
        *tenant_constraints("shipments"),
    )
    op.create_index(
        "ix_shipments_org_status_created", "shipments", ["organization_id", "status", "created_at"]
    )
    op.create_table(
        "documents",
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("document_type", sa.String(40), nullable=False),
        sa.Column("latest_version_number", sa.Integer(), server_default="1", nullable=False),
        *tenant_columns(),
        sa.CheckConstraint(
            "document_type IN ('COMMERCIAL_INVOICE', 'PACKING_LIST', 'BILL_OF_LADING', "
            "'CERTIFICATE_OF_ORIGIN', 'BOOKING_CONFIRMATION', 'OTHER')",
            name="ck_documents_type",
        ),
        sa.CheckConstraint("latest_version_number > 0", name="ck_documents_latest_version"),
        *tenant_constraints("documents"),
    )
    op.create_index(
        "ix_documents_org_type_created",
        "documents",
        ["organization_id", "document_type", "created_at"],
    )
    op.create_table(
        "shipment_items",
        sa.Column("shipment_id", sa.Uuid(), nullable=False),
        sa.Column("sales_order_item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        *tenant_columns(),
        sa.CheckConstraint("quantity > 0", name="ck_shipment_items_quantity"),
        sa.ForeignKeyConstraint(
            ["organization_id", "shipment_id"],
            ["shipments.organization_id", "shipments.id"],
            name="fk_shipment_items_org_shipment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "sales_order_item_id"],
            ["sales_order_items.organization_id", "sales_order_items.id"],
            name="fk_shipment_items_org_sales_item",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id", "shipment_id", "sales_order_item_id", name="uq_shipment_items_line"
        ),
        *tenant_constraints("shipment_items"),
    )
    op.create_index(
        "ix_shipment_items_org_sales_item",
        "shipment_items",
        ["organization_id", "sales_order_item_id"],
    )
    op.create_table(
        "document_versions",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), server_default="PENDING_UPLOAD", nullable=False),
        sa.Column("object_key", sa.String(500), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(120), nullable=False),
        sa.Column("expected_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("expected_sha256", sa.String(64), nullable=False),
        sa.Column("actual_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("actual_sha256", sa.String(64), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_reason", sa.Text(), nullable=True),
        *tenant_columns(),
        sa.CheckConstraint("version_number > 0", name="ck_document_versions_number"),
        sa.CheckConstraint("expected_size_bytes > 0", name="ck_document_versions_size"),
        sa.CheckConstraint(
            "status IN ('PENDING_UPLOAD', 'UPLOADED', 'SCANNING', 'AVAILABLE', 'REJECTED')",
            name="ck_document_versions_status",
        ),
        sa.CheckConstraint("char_length(expected_sha256) = 64", name="ck_document_versions_sha256"),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            name="fk_document_versions_org_document",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id", "document_id", "version_number", name="uq_document_versions_number"
        ),
        *tenant_constraints("document_versions"),
    )
    op.create_index(
        "ix_document_versions_org_status",
        "document_versions",
        ["organization_id", "status", "created_at"],
    )
    op.create_table(
        "document_links",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("target_type", sa.String(32), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        *tenant_columns(),
        sa.CheckConstraint(
            "target_type IN ('SALES_ORDER', 'SHIPMENT', 'CUSTOMS_DECLARATION', 'TAX_REFUND_CASE')",
            name="ck_document_links_target_type",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            name="fk_document_links_org_document",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "organization_id",
            "document_id",
            "target_type",
            "target_id",
            name="uq_document_links_target",
        ),
        *tenant_constraints("document_links"),
    )
    op.create_index(
        "ix_document_links_org_target",
        "document_links",
        ["organization_id", "target_type", "target_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_links_org_target", table_name="document_links")
    op.drop_table("document_links")
    op.drop_index("ix_document_versions_org_status", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_index("ix_shipment_items_org_sales_item", table_name="shipment_items")
    op.drop_table("shipment_items")
    op.drop_index("ix_documents_org_type_created", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_shipments_org_status_created", table_name="shipments")
    op.drop_table("shipments")
