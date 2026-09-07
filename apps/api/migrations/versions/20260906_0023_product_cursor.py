"""Support stable tenant product directory navigation without changing product facts."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_0023"
down_revision = "20260906_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_products_org_name_id_active",
        "products",
        ["organization_id", "name", "id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_products_org_name_id_active", table_name="products")
