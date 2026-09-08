"""Constrain order opportunity ownership without rewriting commercial snapshots."""

from alembic import op

revision = "20260908_0034"
down_revision = "20260907_0033"
branch_labels = None
depends_on = None

CONSTRAINT = "fk_sales_orders_org_opportunity"


def upgrade() -> None:
    # Enforce new writes before scanning historical rows. Validation failure rolls back
    # this migration; never guess a replacement opportunity or alter the stored snapshot.
    op.create_foreign_key(
        CONSTRAINT,
        "sales_orders",
        "opportunities",
        ["organization_id", "opportunity_id"],
        ["organization_id", "id"],
        ondelete="RESTRICT",
        postgresql_not_valid=True,
    )
    op.execute(f"ALTER TABLE sales_orders VALIDATE CONSTRAINT {CONSTRAINT}")


def downgrade() -> None:
    # Removes only the added guard, preserving every row and existing tenant constraint.
    op.drop_constraint(CONSTRAINT, "sales_orders", type_="foreignkey")
