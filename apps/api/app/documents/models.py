from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TenantRecordMixin, membership_actor_foreign_key


class Document(TenantRecordMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_documents_org_id"),
        CheckConstraint(
            "document_type IN ('COMMERCIAL_INVOICE', 'PACKING_LIST', 'BILL_OF_LADING', "
            "'CERTIFICATE_OF_ORIGIN', 'BOOKING_CONFIRMATION', 'SALES_CONTRACT', 'OTHER')",
            name="ck_documents_type",
        ),
        CheckConstraint("latest_version_number > 0", name="ck_documents_latest_version"),
        membership_actor_foreign_key("documents", "created_by"),
        membership_actor_foreign_key("documents", "updated_by"),
        Index("ix_documents_org_type_created", "organization_id", "document_type", "created_at"),
    )

    title: Mapped[str] = mapped_column(String(240), nullable=False)
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    latest_version_number: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")


class DocumentVersion(TenantRecordMixin, Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_document_versions_org_id"),
        UniqueConstraint(
            "organization_id", "document_id", "version_number", name="uq_document_versions_number"
        ),
        CheckConstraint("version_number > 0", name="ck_document_versions_number"),
        CheckConstraint("expected_size_bytes > 0", name="ck_document_versions_size"),
        CheckConstraint(
            "status IN ('PENDING_UPLOAD', 'UPLOADED', 'SCANNING', 'AVAILABLE', 'REJECTED')",
            name="ck_document_versions_status",
        ),
        CheckConstraint("char_length(expected_sha256) = 64", name="ck_document_versions_sha256"),
        ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            name="fk_document_versions_org_document",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("document_versions", "created_by"),
        membership_actor_foreign_key("document_versions", "updated_by"),
        membership_actor_foreign_key("document_versions", "reviewed_by"),
        CheckConstraint(
            "(released_digest IS NULL OR char_length(released_digest) = 64) AND "
            "((reviewed_by IS NULL AND reviewed_at IS NULL AND released_digest IS NULL) OR "
            "(reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))",
            name="ck_document_versions_review",
        ),
        Index("ix_document_versions_org_status", "organization_id", "status", "created_at"),
    )

    document_id: Mapped[UUID] = mapped_column(nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="PENDING_UPLOAD")
    object_key: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_version_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    expected_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expected_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    actual_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    actual_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    released_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_by: Mapped[UUID | None] = mapped_column(nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DocumentLink(TenantRecordMixin, Base):
    __tablename__ = "document_links"
    __table_args__ = (
        UniqueConstraint("organization_id", "id", name="uq_document_links_org_id"),
        UniqueConstraint(
            "organization_id",
            "document_id",
            "target_type",
            "target_id",
            name="uq_document_links_target",
        ),
        CheckConstraint(
            "target_type IN ('SALES_ORDER', 'SHIPMENT', 'CUSTOMS_DECLARATION', 'TAX_REFUND_CASE')",
            name="ck_document_links_target_type",
        ),
        ForeignKeyConstraint(
            ["organization_id", "document_id"],
            ["documents.organization_id", "documents.id"],
            name="fk_document_links_org_document",
            ondelete="RESTRICT",
        ),
        membership_actor_foreign_key("document_links", "created_by"),
        membership_actor_foreign_key("document_links", "updated_by"),
        Index("ix_document_links_org_target", "organization_id", "target_type", "target_id"),
    )

    document_id: Mapped[UUID] = mapped_column(nullable=False)
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[UUID] = mapped_column(nullable=False)
