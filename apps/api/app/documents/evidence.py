"""Read-only evidence port for commands that pin an already verified document version."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.documents.enums import DocumentType, DocumentVersionStatus
from app.documents.models import Document, DocumentLink, DocumentVersion


def require_contract_evidence(
    session: Session, context: RequestContext, order_id: UUID, version_id: UUID
) -> None:
    context.require(Permission.DOCUMENT_READ)
    version = session.scalar(
        select(DocumentVersion)
        .join(
            Document,
            (Document.organization_id == DocumentVersion.organization_id)
            & (Document.id == DocumentVersion.document_id),
        )
        .join(
            DocumentLink,
            (DocumentLink.organization_id == Document.organization_id)
            & (DocumentLink.document_id == Document.id),
        )
        .where(
            DocumentVersion.organization_id == context.organization_id,
            DocumentVersion.id == version_id,
            DocumentVersion.deleted_at.is_(None),
            Document.deleted_at.is_(None),
            DocumentLink.deleted_at.is_(None),
            Document.document_type == DocumentType.SALES_CONTRACT,
            DocumentLink.target_type == "SALES_ORDER",
            DocumentLink.target_id == order_id,
        )
        .with_for_update(of=DocumentVersion)
        .execution_options(populate_existing=True)
    )
    if version is None:
        raise ApiProblem(
            404,
            "CONTRACT_EVIDENCE_NOT_FOUND",
            "Evidence not found",
            "Choose a contract file version linked to this order.",
        )
    if (
        version.status != DocumentVersionStatus.AVAILABLE
        or not version.storage_version_id
        or version.storage_version_id == "null"
        or version.actual_sha256 != version.expected_sha256
        or version.actual_size_bytes != version.expected_size_bytes
    ):
        raise ApiProblem(
            409,
            "CONTRACT_EVIDENCE_NOT_READY",
            "Evidence not ready",
            "The selected contract version must pass verification before signing is recorded.",
        )
