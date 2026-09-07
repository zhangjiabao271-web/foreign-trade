"""Index organization-scoped operational backlog; preserve all event facts."""

from alembic import op

revision = "20260906_0022"
down_revision = "20260906_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_outbox_org_status_created", "outbox_events", ["organization_id", "status", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_outbox_org_status_created", table_name="outbox_events")
