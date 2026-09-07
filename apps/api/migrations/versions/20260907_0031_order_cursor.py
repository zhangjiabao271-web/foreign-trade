"""Index stable tenant order navigation without changing business facts."""

import sqlalchemy as sa
from alembic import op

revision = "20260907_0031"
down_revision = "20260906_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_sales_orders_org_created_id_active",
        "sales_orders",
        ["organization_id", "created_at", "id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_sales_orders_org_created_id_active", table_name="sales_orders")
