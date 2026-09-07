"""Preserve procurement prose and default historical disclosure to confidential."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_0030"
down_revision = "20260906_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = "purchase_orders"
    op.add_column(table, sa.Column("released_digest", sa.String(64), nullable=True))
    op.add_column(table, sa.Column("reviewed_by", sa.Uuid(), nullable=True))
    op.add_column(table, sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_purchase_orders_organization_id_reviewed_by_membership",
        table,
        "organization_memberships",
        ["organization_id", "reviewed_by"],
        ["organization_id", "user_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_purchase_orders_ck_purchase_orders_review"),
        table,
        "(released_digest IS NULL OR char_length(released_digest) = 64) AND "
        "((reviewed_by IS NULL AND reviewed_at IS NULL AND released_digest IS NULL) OR "
        "(reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))",
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM purchase_orders)")):
        raise RuntimeError(
            "Purchase evidence exists; preserve confidentiality with a forward migration."
        )
    table = "purchase_orders"
    op.drop_constraint(op.f("ck_purchase_orders_ck_purchase_orders_review"), table, type_="check")
    op.drop_constraint(
        "fk_purchase_orders_organization_id_reviewed_by_membership", table, type_="foreignkey"
    )
    op.drop_column(table, "reviewed_at")
    op.drop_column(table, "reviewed_by")
    op.drop_column(table, "released_digest")
