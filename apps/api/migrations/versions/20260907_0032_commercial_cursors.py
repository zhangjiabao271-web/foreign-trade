"""Index bounded commercial queues and selectors without rewriting business evidence."""

import sqlalchemy as sa
from alembic import op

revision = "20260907_0032"
down_revision = "20260907_0031"
branch_labels = None
depends_on = None

INDEXES = (
    ("shipments", "ix_shipments_org_created_id_active", ["organization_id", "created_at", "id"]),
    ("quotations", "ix_quotations_org_created_id_active", ["organization_id", "created_at", "id"]),
    ("inquiries", "ix_inquiries_org_received_id_active", ["organization_id", "received_at", "id"]),
    (
        "inquiries",
        "ix_inquiries_org_status_received_id_active",
        ["organization_id", "status", "received_at", "id"],
    ),
    (
        "purchase_orders",
        "ix_purchase_orders_org_created_id_active",
        ["organization_id", "created_at", "id"],
    ),
    (
        "purchase_orders",
        "ix_purchase_orders_org_parent_created_id_active",
        ["organization_id", "sales_order_id", "created_at", "id"],
    ),
)


def upgrade() -> None:
    for table, name, columns in INDEXES:
        op.create_index(name, table, columns, postgresql_where=sa.text("deleted_at IS NULL"))


def downgrade() -> None:
    for table, name, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table)
