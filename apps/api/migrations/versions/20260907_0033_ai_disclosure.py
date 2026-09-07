"""Explicit private draft submission and preserved disclosure candidates."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260907_0033"
down_revision = "20260907_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_disclosures",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "organization_id",
            sa.Uuid(),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("updated_by", sa.Uuid()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid()),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("run_version", sa.Integer(), nullable=False),
        sa.Column("run_digest", sa.String(64), nullable=False),
        sa.Column("candidate", postgresql.JSONB(), nullable=False),
        sa.Column("released_digest", sa.String(64)),
        sa.Column("status", sa.String(12), nullable=False, server_default="PENDING"),
        sa.Column("reviewed_by", sa.Uuid()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("organization_id", "id"),
        sa.UniqueConstraint("organization_id", "run_id", "revision"),
        sa.ForeignKeyConstraint(
            ["organization_id", "run_id"],
            ["ai_runs.organization_id", "ai_runs.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "parent_id"],
            ["ai_disclosures.organization_id", "ai_disclosures.id"],
            ondelete="RESTRICT",
        ),
        *[
            sa.ForeignKeyConstraint(
                ["organization_id", actor],
                ["organization_memberships.organization_id", "organization_memberships.user_id"],
                name=f"fk_ai_disclosures_organization_id_{actor}_membership",
                ondelete="RESTRICT",
            )
            for actor in ("created_by", "updated_by", "reviewed_by")
        ],
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REJECTED')", name="disclosure_status"
        ),
        sa.CheckConstraint("revision > 0 AND run_version > 0", name="disclosure_versions"),
        sa.CheckConstraint("char_length(run_digest) = 64", name="disclosure_digest"),
        sa.CheckConstraint(
            "(status = 'PENDING' AND reviewed_by IS NULL AND reviewed_at IS NULL) OR "
            "(status <> 'PENDING' AND reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)",
            name="disclosure_decision",
        ),
    )
    op.create_index(
        "ix_ai_disclosures_org_created", "ai_disclosures", ["organization_id", "created_at", "id"]
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM ai_disclosures)")):
        raise RuntimeError("Preserve AI disclosure evidence; use a forward migration.")
    op.drop_table("ai_disclosures")
