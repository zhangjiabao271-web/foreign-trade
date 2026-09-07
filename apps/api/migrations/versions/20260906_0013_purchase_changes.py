"""Preserve cancellation and replacement purchase evidence."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_0013"
down_revision = "20260906_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("purchase_orders", sa.Column("cancelled_at", sa.DateTime(timezone=True)))
    op.add_column("purchase_orders", sa.Column("cancellation_reason", sa.Text()))
    op.add_column("purchase_orders", sa.Column("cancellation_reference", sa.String(200)))
    op.add_column("purchase_orders", sa.Column("replaces_purchase_order_id", sa.Uuid()))
    op.create_unique_constraint(
        "uq_purchase_orders_replacement",
        "purchase_orders",
        ["organization_id", "replaces_purchase_order_id"],
    )
    op.create_foreign_key(
        "fk_purchase_orders_replaces",
        "purchase_orders",
        "purchase_orders",
        ["organization_id", "replaces_purchase_order_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM purchase_orders WHERE cancelled_at IS NOT NULL "
            "OR replaces_purchase_order_id IS NOT NULL)"
        )
    ):
        raise RuntimeError("Cancellation/replacement evidence exists; use a forward repair.")
    op.drop_constraint("fk_purchase_orders_replaces", "purchase_orders", type_="foreignkey")
    op.drop_constraint("uq_purchase_orders_replacement", "purchase_orders", type_="unique")
    for name in (
        "replaces_purchase_order_id",
        "cancellation_reference",
        "cancellation_reason",
        "cancelled_at",
    ):
        op.drop_column("purchase_orders", name)
