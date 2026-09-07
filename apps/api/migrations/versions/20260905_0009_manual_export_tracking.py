"""manual_export_tracking

Revision ID: 20260905_0009
Revises: 20260905_0008
Create Date: 2026-09-05 19:55:05.694895
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260905_0009"
down_revision: str | None = "20260905_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "customs_declarations",
        sa.Column("declaration_number", sa.String(length=40), nullable=False),
        sa.Column("shipment_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="DRAFT", nullable=False),
        sa.Column("declared_amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column(
            "required_document_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("external_reference", sa.String(length=160), nullable=True),
        sa.Column("submitted_on", sa.Date(), nullable=True),
        sa.Column("cleared_on", sa.Date(), nullable=True),
        sa.Column("follow_up_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('DRAFT','DOCUMENTS_PENDING','READY','SUBMITTED','CLEARED','REJECTED')",
            name=op.f("ck_customs_declarations_ck_customs_status"),
        ),
        sa.CheckConstraint(
            "char_length(currency_code) = 3",
            name=op.f("ck_customs_declarations_ck_customs_currency"),
        ),
        sa.CheckConstraint(
            "declared_amount > 0", name=op.f("ck_customs_declarations_ck_customs_amount")
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_customs_declarations_organization_id_created_by_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "shipment_id"],
            ["shipments.organization_id", "shipments.id"],
            name="fk_customs_org_shipment",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "updated_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_customs_declarations_organization_id_updated_by_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_customs_declarations_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customs_declarations")),
        sa.UniqueConstraint("organization_id", "declaration_number", name="uq_customs_org_number"),
        sa.UniqueConstraint("organization_id", "id", name="uq_customs_org_id"),
        sa.UniqueConstraint("organization_id", "shipment_id", name="uq_customs_org_shipment"),
    )
    op.create_index(
        "ix_customs_org_status_due",
        "customs_declarations",
        ["organization_id", "status", "follow_up_date"],
        unique=False,
    )
    op.create_table(
        "tax_refund_cases",
        sa.Column("case_number", sa.String(length=40), nullable=False),
        sa.Column("customs_declaration_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=24), server_default="NOT_READY", nullable=False),
        sa.Column("expected_amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column(
            "refunded_amount", sa.Numeric(precision=18, scale=4), server_default="0", nullable=False
        ),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column(
            "required_document_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("external_reference", sa.String(length=160), nullable=True),
        sa.Column("submitted_on", sa.Date(), nullable=True),
        sa.Column("refunded_on", sa.Date(), nullable=True),
        sa.Column("follow_up_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('NOT_READY','DOCUMENTS_PENDING','READY','SUBMITTED',"
            "'PROCESSING','REFUNDED','REJECTED')",
            name=op.f("ck_tax_refund_cases_ck_refund_status"),
        ),
        sa.CheckConstraint(
            "char_length(currency_code) = 3", name=op.f("ck_tax_refund_cases_ck_refund_currency")
        ),
        sa.CheckConstraint(
            "expected_amount > 0", name=op.f("ck_tax_refund_cases_ck_refund_expected")
        ),
        sa.CheckConstraint(
            "refunded_amount >= 0 AND refunded_amount <= expected_amount",
            name=op.f("ck_tax_refund_cases_ck_refund_actual"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "created_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_tax_refund_cases_organization_id_created_by_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "customs_declaration_id"],
            ["customs_declarations.organization_id", "customs_declarations.id"],
            name="fk_refund_org_customs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "updated_by"],
            ["organization_memberships.organization_id", "organization_memberships.user_id"],
            name="fk_tax_refund_cases_organization_id_updated_by_membership",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_tax_refund_cases_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tax_refund_cases")),
        sa.UniqueConstraint("organization_id", "case_number", name="uq_refund_org_number"),
        sa.UniqueConstraint(
            "organization_id", "customs_declaration_id", name="uq_refund_org_customs"
        ),
        sa.UniqueConstraint("organization_id", "id", name="uq_refund_org_id"),
    )
    op.create_index(
        "ix_refund_org_status_due",
        "tax_refund_cases",
        ["organization_id", "status", "follow_up_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_refund_org_status_due", table_name="tax_refund_cases")
    op.drop_table("tax_refund_cases")
    op.drop_index("ix_customs_org_status_due", table_name="customs_declarations")
    op.drop_table("customs_declarations")
