"""Preserve opportunity loss evidence and support bounded lists."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_0014"
down_revision = "20260906_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM opportunities WHERE status = 'LOST')")
    ):
        raise RuntimeError(
            "Legacy LOST opportunities require evidence reconciliation before migration."
        )
    op.add_column("opportunities", sa.Column("lost_reason", sa.Text()))
    op.add_column("opportunities", sa.Column("lost_at", sa.DateTime(timezone=True)))
    op.create_index(
        "ix_opportunities_org_created_id", "opportunities", ["organization_id", "created_at", "id"]
    )


def downgrade() -> None:
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM opportunities WHERE lost_reason IS NOT NULL "
            "OR lost_at IS NOT NULL)"
        )
    ):
        raise RuntimeError("Opportunity loss evidence exists; use a forward repair.")
    op.drop_index("ix_opportunities_org_created_id", table_name="opportunities")
    op.drop_column("opportunities", "lost_at")
    op.drop_column("opportunities", "lost_reason")
