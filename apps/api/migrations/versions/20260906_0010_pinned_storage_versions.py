"""Pin verified immutable object versions without deleting legacy evidence."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_0010"
down_revision = "20260905_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_versions", sa.Column("storage_version_id", sa.String(255), nullable=True)
    )


def downgrade() -> None:
    raise RuntimeError("Evidence pointers must be preserved; use a forward corrective migration.")
