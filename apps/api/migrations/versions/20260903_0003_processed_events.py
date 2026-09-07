"""Add durable idempotent event-consumer records.

Revision ID: 20260903_0003
Revises: 20260903_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260903_0003"
down_revision: str | None = "20260903_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_outbox_events_organization_id_id",
        "outbox_events",
        ["organization_id", "id"],
    )
    op.create_table(
        "processed_events",
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consumer_name", sa.String(length=150), nullable=False),
        sa.Column(
            "processed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_processed_events_organization_id_organizations",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id", "event_id"],
            ["outbox_events.organization_id", "outbox_events.id"],
            name="fk_processed_events_organization_id_event_id_outbox_events",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "organization_id",
            "event_id",
            "consumer_name",
            name="pk_processed_events",
        ),
    )
    op.create_index(
        "ix_processed_events_organization_id_processed_at",
        "processed_events",
        ["organization_id", "processed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_processed_events_organization_id_processed_at",
        table_name="processed_events",
    )
    op.drop_table("processed_events")
    op.drop_constraint(
        "uq_outbox_events_organization_id_id",
        "outbox_events",
        type_="unique",
    )
