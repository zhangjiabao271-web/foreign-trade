"""Preserve historical Work text and default its disclosure to confidential."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_0025"
down_revision = "20260906_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("tasks", "activities"):
        op.add_column(table, sa.Column("released_digest", sa.String(64), nullable=True))
        op.add_column(table, sa.Column("reviewed_by", sa.Uuid(), nullable=True))
        op.add_column(table, sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_organization_id_reviewed_by_membership",
            table,
            "organization_memberships",
            ["organization_id", "reviewed_by"],
            ["organization_id", "user_id"],
            ondelete="RESTRICT",
        )
        op.create_check_constraint(
            op.f(f"ck_{table}_ck_{table}_review"),
            table,
            "(released_digest IS NULL OR char_length(released_digest) = 64) AND "
            "((reviewed_by IS NULL AND reviewed_at IS NULL AND released_digest IS NULL) OR "
            "(reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))",
        )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM tasks) OR EXISTS (SELECT 1 FROM activities)")
    ):
        raise RuntimeError(
            "Work evidence exists; preserve confidentiality with a forward migration."
        )
    for table in ("tasks", "activities"):
        op.drop_constraint(op.f(f"ck_{table}_ck_{table}_review"), table, type_="check")
        op.drop_constraint(
            f"fk_{table}_organization_id_reviewed_by_membership", table, type_="foreignkey"
        )
        op.drop_column(table, "reviewed_at")
        op.drop_column(table, "reviewed_by")
        op.drop_column(table, "released_digest")
