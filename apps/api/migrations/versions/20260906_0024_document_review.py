"""Default historical and new document versions to confidential; preserve binary evidence."""

import sqlalchemy as sa
from alembic import op

revision = "20260906_0024"
down_revision = "20260906_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_versions", sa.Column("released_digest", sa.String(64), nullable=True))
    op.add_column("document_versions", sa.Column("reviewed_by", sa.Uuid(), nullable=True))
    op.add_column(
        "document_versions", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_document_versions_organization_id_reviewed_by_membership",
        "document_versions",
        "organization_memberships",
        ["organization_id", "reviewed_by"],
        ["organization_id", "user_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        op.f("ck_document_versions_ck_document_versions_review"),
        "document_versions",
        "(released_digest IS NULL OR char_length(released_digest) = 64) AND "
        "((reviewed_by IS NULL AND reviewed_at IS NULL AND released_digest IS NULL) OR "
        "(reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))",
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM document_versions)")):
        raise RuntimeError(
            "Document evidence exists; preserve confidentiality with a forward migration."
        )
    op.drop_constraint(
        op.f("ck_document_versions_ck_document_versions_review"), "document_versions", type_="check"
    )
    op.drop_constraint(
        "fk_document_versions_organization_id_reviewed_by_membership",
        "document_versions",
        type_="foreignkey",
    )
    op.drop_column("document_versions", "reviewed_at")
    op.drop_column("document_versions", "reviewed_by")
    op.drop_column("document_versions", "released_digest")
