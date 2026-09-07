"""Batched, organization-scoped evidence projection for controlled business targets."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.documents.enums import DocumentLinkTargetType, DocumentVersionStatus
from app.documents.models import Document, DocumentLink, DocumentVersion


def missing_document_types(
    session: Session,
    *,
    organization_id: UUID,
    target_type: DocumentLinkTargetType,
    requirements: dict[UUID, list[str]],
) -> dict[UUID, list[str]]:
    available: dict[UUID, set[str]] = {target_id: set() for target_id in requirements}
    if requirements:
        rows = session.execute(
            select(DocumentLink.target_id, Document.document_type)
            .join(
                Document,
                (Document.organization_id == DocumentLink.organization_id)
                & (Document.id == DocumentLink.document_id),
            )
            .join(
                DocumentVersion,
                (DocumentVersion.organization_id == Document.organization_id)
                & (DocumentVersion.document_id == Document.id)
                & (DocumentVersion.version_number == Document.latest_version_number),
            )
            .where(
                DocumentLink.organization_id == organization_id,
                DocumentLink.target_type == target_type,
                DocumentLink.target_id.in_(requirements),
                DocumentVersion.status == DocumentVersionStatus.AVAILABLE,
                DocumentVersion.storage_version_id.is_not(None),
                DocumentVersion.storage_version_id.not_in(["", "null"]),
                DocumentLink.deleted_at.is_(None),
                Document.deleted_at.is_(None),
                DocumentVersion.deleted_at.is_(None),
            )
        ).all()
        for target_id, document_type in rows:
            available[target_id].add(document_type)
    return {
        target_id: sorted(set(types) - available[target_id])
        for target_id, types in requirements.items()
    }
