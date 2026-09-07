"""Index stable receipt navigation without changing financial facts."""

from alembic import op

revision = "20260906_0017"
down_revision = "20260906_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_payments_org_received_cursor",
        "payments",
        ["organization_id", "received_at", "created_at", "id"],
    )
    op.create_index(
        "ix_payments_org_customer_currency_cursor",
        "payments",
        ["organization_id", "company_id", "currency_code", "received_at", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_payments_org_customer_currency_cursor", table_name="payments")
    op.drop_index("ix_payments_org_received_cursor", table_name="payments")
