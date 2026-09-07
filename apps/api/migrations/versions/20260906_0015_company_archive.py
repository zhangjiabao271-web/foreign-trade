"""Index bounded company and contact archive navigation; no business data changes."""

from alembic import op

revision = "20260906_0015"
down_revision = "20260906_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_companies_org_created_id", "companies", ["organization_id", "created_at", "id"]
    )
    op.create_index(
        "ix_contacts_org_company_created_id",
        "contacts",
        ["organization_id", "company_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_contacts_org_company_created_id", table_name="contacts")
    op.drop_index("ix_companies_org_created_id", table_name="companies")
