"""Add purchase receiving quantities and completion timestamps without changing commitments."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_0012"
down_revision = "20260906_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM purchase_orders WHERE "
            "status IN ('PARTIALLY_RECEIVED', 'RECEIVED', 'CLOSED'))"
        )
    ):
        raise RuntimeError(
            "Legacy receipt states require evidence reconciliation before this migration; "
            "no quantities were inferred."
        )
    op.add_column("purchase_orders", sa.Column("received_at", sa.DateTime(timezone=True)))
    op.add_column("purchase_orders", sa.Column("closed_at", sa.DateTime(timezone=True)))
    op.add_column(
        "purchase_order_items",
        sa.Column("received_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "received_quantity_bounds",
        "purchase_order_items",
        "received_quantity >= 0 AND received_quantity <= quantity",
    )


def downgrade() -> None:
    # Receipt evidence must never be silently discarded during a rollback.
    connection = op.get_bind()
    if connection.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM purchase_order_items WHERE received_quantity > 0)")
    ):
        raise RuntimeError("Cannot downgrade while receipt facts exist; use a forward repair.")
    op.drop_constraint(
        op.f("ck_purchase_order_items_received_quantity_bounds"),
        "purchase_order_items",
        type_="check",
    )
    op.drop_column("purchase_order_items", "received_quantity")
    op.drop_column("purchase_orders", "closed_at")
    op.drop_column("purchase_orders", "received_at")
