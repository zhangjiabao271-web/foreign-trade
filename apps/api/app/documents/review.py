import hashlib
import json
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.unit_of_work import UnitOfWork
from app.documents.access import require_document_targets
from app.documents.enums import DocumentVersionStatus
from app.documents.models import Document, DocumentVersion
from app.documents.repositories import DocumentRepository
from app.platform.idempotency import begin_command, complete_command
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.work.models import Activity


class DocumentReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=1)
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    release: bool
    reason: str = Field(min_length=3, max_length=1000)
    confirmed: bool


class DocumentReviewResponse(BaseModel):
    version_id: UUID
    version: int
    content_digest: str
    released: bool
    reviewed_by: UUID | None
    reviewed_at: datetime | None


def content_digest(document: Document, version: DocumentVersion) -> str:
    facts = {
        "document_id": str(document.id),
        "version_id": str(version.id),
        "title": document.title,
        "type": document.document_type,
        "file_name": version.file_name,
        "mime_type": version.mime_type,
        "size": version.actual_size_bytes,
        "sha256": version.actual_sha256,
        "expected_size": version.expected_size_bytes,
        "expected_sha256": version.expected_sha256,
        "storage_version_id": version.storage_version_id,
        "object_key": version.object_key,
    }
    return hashlib.sha256(
        json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def is_released(document: Document, version: DocumentVersion) -> bool:
    return (
        version.status == DocumentVersionStatus.AVAILABLE
        and bool(version.storage_version_id)
        and version.storage_version_id != "null"
        and version.reviewed_by is not None
        and version.reviewed_at is not None
        and version.released_digest == content_digest(document, version)
    )


def review_response(document: Document, version: DocumentVersion) -> DocumentReviewResponse:
    return DocumentReviewResponse(
        version_id=version.id,
        version=version.version,
        content_digest=content_digest(document, version),
        released=is_released(document, version),
        reviewed_by=version.reviewed_by,
        reviewed_at=version.reviewed_at,
    )


class DocumentReviewService:
    def __init__(
        self,
        factory: sessionmaker[Session],
        *,
        audit: AuditRecorder | None = None,
        outbox: OutboxRecorder | None = None,
    ) -> None:
        self.factory = factory
        self.audit = audit or AuditRecorder()
        self.outbox = outbox or OutboxRecorder()

    def inspect(
        self, context: RequestContext, document_id: UUID, version_id: UUID
    ) -> DocumentReviewResponse:
        context.require(Permission.DOCUMENT_READ)
        context.require(Permission.PROFIT_READ)
        with self.factory() as session:
            repository = DocumentRepository(session)
            document = repository.get(
                organization_id=context.organization_id, record_id=document_id
            )
            versions = repository.versions(
                organization_id=context.organization_id, document_id=document_id
            )
            version = next((row for row in versions if row.id == version_id), None)
            if document is None or version is None:
                raise ApiProblem(404, "DOCUMENT_NOT_FOUND", "Not found", "Document not found.")
            require_document_targets(session, context, document_id)
            return review_response(document, version)

    def decide(
        self,
        context: RequestContext,
        document_id: UUID,
        version_id: UUID,
        request: DocumentReviewRequest,
        *,
        key: str,
    ) -> DocumentReviewResponse:
        context.require(Permission.DOCUMENT_READ)
        context.require(Permission.PROFIT_READ)
        if not request.confirmed:
            raise ApiProblem(
                422, "CONFIRMATION_REQUIRED", "Confirm review", "Confirm the decision."
            )
        with UnitOfWork(self.factory) as unit:
            session = unit.session
            command = begin_command(
                session,
                context,
                scope="document.review",
                key=key,
                payload={
                    "document_id": document_id,
                    "version_id": version_id,
                    **request.model_dump(),
                },
            )
            repository = DocumentRepository(session)
            document = repository.get_for_update(
                organization_id=context.organization_id, document_id=document_id
            )
            version = repository.version_for_update(
                organization_id=context.organization_id, version_id=version_id
            )
            if document is None or version is None or version.document_id != document.id:
                raise ApiProblem(404, "DOCUMENT_NOT_FOUND", "Not found", "Document not found.")
            require_document_targets(session, context, document_id)
            if command.resource_id is not None:
                result = review_response(document, version)
                unit.commit()
                return result
            if (
                version.version != request.expected_version
                or content_digest(document, version) != request.content_digest
            ):
                raise ApiProblem(
                    409,
                    "VERSION_CONFLICT",
                    "Changed evidence",
                    "Reload and review this exact file version.",
                )
            if request.release and (
                version.status != DocumentVersionStatus.AVAILABLE
                or not version.storage_version_id
                or version.storage_version_id == "null"
                or not version.actual_sha256
                or version.actual_sha256 != version.expected_sha256
                or version.actual_size_bytes != version.expected_size_bytes
            ):
                raise ApiProblem(
                    409,
                    "DOCUMENT_NOT_AVAILABLE",
                    "Unverified evidence",
                    "Only verified, pinned files may be released.",
                )
            previous = is_released(document, version)
            version.released_digest = request.content_digest if request.release else None
            version.reviewed_by = context.user_id
            version.reviewed_at = datetime.now(UTC)
            version.updated_by = context.user_id
            action = "document.visibility_reviewed"
            details = {"version_id": str(version.id), "released": request.release}
            session.add(
                Activity(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    subject_type="document",
                    subject_id=document.id,
                    activity_type=action,
                    summary="Document version visibility reviewed",
                    details=details,
                    correlation_id=context.request_id,
                )
            )
            self.audit.record(
                session,
                context,
                action=action,
                target_type="document_version",
                target_id=version.id,
                before={"released": previous},
                after={**details, "content_digest": request.content_digest},
                reason=request.reason,
            )
            self.outbox.record(
                session,
                context,
                DomainEvent(
                    f"{action}.v1",
                    "document",
                    document.id,
                    details,
                ),
            )
            complete_command(command, version.id, "document_version")
            session.flush()
            result = review_response(document, version)
            unit.commit()
            return result
