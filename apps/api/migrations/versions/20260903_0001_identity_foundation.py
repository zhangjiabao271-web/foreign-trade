"""Create identity foundation tables.

Revision ID: 20260903_0001
Revises:
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def identity_record_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column("updated_by", sa.Uuid(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        *identity_record_columns(),
        sa.Column("external_subject", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("email_normalized", sa.String(length=320), nullable=True),
        sa.Column("status", sa.String(length=8), nullable=False, server_default="ACTIVE"),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED')",
            name=op.f("ck_users_user_status"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_users_version_positive")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_users_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_users_updated_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("external_subject", name=op.f("uq_users_external_subject")),
    )
    op.create_index("ix_users_email_normalized", "users", ["email_normalized"])

    op.create_table(
        "organizations",
        *identity_record_columns(),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("name_normalized", sa.String(length=200), nullable=False),
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="Asia/Shanghai",
        ),
        sa.Column("status", sa.String(length=8), nullable=False, server_default="ACTIVE"),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'DISABLED')",
            name=op.f("ck_organizations_organization_status"),
        ),
        sa.CheckConstraint("version > 0", name=op.f("ck_organizations_version_positive")),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_organizations_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_organizations_updated_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organizations")),
    )

    op.create_table(
        "organization_memberships",
        *identity_record_columns(),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=10), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False, server_default="INVITED"),
        sa.CheckConstraint(
            "role IN ('ADMIN', 'MANAGER', 'SALES', 'OPERATIONS', 'FINANCE', 'VIEWER')",
            name=op.f("ck_organization_memberships_membership_role"),
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'INVITED', 'DISABLED')",
            name=op.f("ck_organization_memberships_membership_status"),
        ),
        sa.CheckConstraint(
            "version > 0",
            name=op.f("ck_organization_memberships_version_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name=op.f("fk_organization_memberships_organization_id_organizations"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_organization_memberships_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name=op.f("fk_organization_memberships_created_by_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            name=op.f("fk_organization_memberships_updated_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_organization_memberships")),
        sa.UniqueConstraint(
            "organization_id",
            "id",
            name=op.f("uq_organization_memberships_organization_id_id"),
        ),
        sa.UniqueConstraint(
            "organization_id",
            "user_id",
            name=op.f("uq_organization_memberships_organization_id_user_id"),
        ),
    )
    op.create_index(
        "ix_organization_memberships_user_id_status",
        "organization_memberships",
        ["user_id", "status"],
    )
    op.create_index(
        "ix_organization_memberships_organization_id_status",
        "organization_memberships",
        ["organization_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_organization_memberships_organization_id_status",
        table_name="organization_memberships",
    )
    op.drop_index(
        "ix_organization_memberships_user_id_status",
        table_name="organization_memberships",
    )
    op.drop_table("organization_memberships")
    op.drop_table("organizations")
    op.drop_index("ix_users_email_normalized", table_name="users")
    op.drop_table("users")
