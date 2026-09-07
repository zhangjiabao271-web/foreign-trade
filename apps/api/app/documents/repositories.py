from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.repositories import TenantRepository
from app.documents.models import Document, DocumentLink, DocumentVersion


class DocumentRepository(TenantRepository[Document]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Document)

    def get_for_update(self, *, organization_id: UUID, document_id: UUID) -> Document | None:
        return self.session.scalar(
            self._select_for_organization(organization_id)
            .where(Document.id == document_id)
            .with_for_update()
        )

    def versions(self, *, organization_id: UUID, document_id: UUID) -> Sequence[DocumentVersion]:
        return self.versions_for_documents(
            organization_id=organization_id, document_ids={document_id}
        )

    def versions_for_documents(
        self, *, organization_id: UUID, document_ids: set[UUID]
    ) -> Sequence[DocumentVersion]:
        if not document_ids:
            return []
        return self.session.scalars(
            select(DocumentVersion)
            .where(
                DocumentVersion.organization_id == organization_id,
                DocumentVersion.document_id.in_(document_ids),
                DocumentVersion.deleted_at.is_(None),
            )
            .order_by(DocumentVersion.version_number.desc())
        ).all()

    def links(self, *, organization_id: UUID, document_id: UUID) -> Sequence[DocumentLink]:
        return self.links_for_documents(organization_id=organization_id, document_ids={document_id})

    def links_for_documents(
        self, *, organization_id: UUID, document_ids: set[UUID]
    ) -> Sequence[DocumentLink]:
        if not document_ids:
            return []
        return self.session.scalars(
            select(DocumentLink).where(
                DocumentLink.organization_id == organization_id,
                DocumentLink.document_id.in_(document_ids),
                DocumentLink.deleted_at.is_(None),
            )
        ).all()

    def linked(
        self, *, organization_id: UUID, target_type: str, target_id: UUID
    ) -> Sequence[Document]:
        return self.session.scalars(
            select(Document)
            .join(
                DocumentLink,
                (DocumentLink.organization_id == Document.organization_id)
                & (DocumentLink.document_id == Document.id),
            )
            .where(
                Document.organization_id == organization_id,
                DocumentLink.target_type == target_type,
                DocumentLink.target_id == target_id,
                Document.deleted_at.is_(None),
                DocumentLink.deleted_at.is_(None),
            )
            .order_by(Document.created_at.desc())
        ).all()

    def version_for_update(
        self, *, organization_id: UUID, version_id: UUID
    ) -> DocumentVersion | None:
        return self.session.scalar(
            select(DocumentVersion)
            .where(
                DocumentVersion.organization_id == organization_id,
                DocumentVersion.id == version_id,
                DocumentVersion.deleted_at.is_(None),
            )
            .with_for_update()
        )
