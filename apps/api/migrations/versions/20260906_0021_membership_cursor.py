"""Organization-scoped membership cursor index; no business data changes."""

from alembic import op

revision = "20260906_0021"
down_revision = "20260906_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_memberships_org_created_id",
        "organization_memberships",
        ["organization_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_memberships_org_created_id", table_name="organization_memberships")
