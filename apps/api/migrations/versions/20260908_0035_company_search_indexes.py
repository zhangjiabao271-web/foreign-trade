"""Index existing literal and full-text company search without changing business rows."""

import sqlalchemy as sa
from alembic import op

revision = "20260908_0035"
down_revision = "20260908_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pg_trgm is bundled with PostgreSQL; deployment requires extension authority.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    for field, name in (
        ("name", "ix_companies_name_trgm_active"),
        ("name_normalized", "ix_companies_normalized_trgm_active"),
    ):
        op.create_index(
            name,
            "companies",
            [field],
            postgresql_using="gin",
            postgresql_ops={field: "gin_trgm_ops"},
            postgresql_where=sa.text("deleted_at IS NULL"),
        )
    op.create_index(
        "ix_companies_name_fts_active",
        "companies",
        [sa.text("to_tsvector('simple'::regconfig, name::text)")],
        postgresql_using="gin",
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    for name in (
        "ix_companies_name_fts_active",
        "ix_companies_normalized_trgm_active",
        "ix_companies_name_trgm_active",
    ):
        op.drop_index(name, table_name="companies")
    # Do not drop a shared extension which may predate this migration.
