from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.unit_of_work import UnitOfWork
from app.documents.access import require_document_targets, require_target
from app.documents.enums import DocumentLinkTargetType, DocumentVersionStatus
from app.documents.models import Document, DocumentLink, DocumentVersion
from app.documents.projections import DocumentAggregate, protected_aggregate
from app.documents.repositories import DocumentRepository
from app.documents.review import content_digest, is_released
from app.documents.schemas import (
    DocumentLinkResponse,
    DocumentResponse,
    DocumentUploadCreate,
    DocumentUploadResume,
    DocumentVersionCreate,
    DocumentVersionResponse,
)
from app.documents.storage import ObjectStorage
from app.platform.enums import AsyncJobStatus
from app.platform.idempotency import begin_command, complete_command
from app.platform.models import AsyncJob
from app.platform.outbox import OutboxMessage
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.work.models import Activity

UPLOAD_SESSION_LIFETIME = timedelta(minutes=15)
DOWNLOAD_SESSION_LIFETIME = timedelta(minutes=5)


def document_not_found() -> ApiProblem:
    return ApiProblem(
        404, "DOCUMENT_NOT_FOUND", "Document not found", "The document was not found."
    )


class DocumentQueryService:
    def __init__(self, repository: DocumentRepository) -> None:
        self._repository = repository

    def linked(
        self, context: RequestContext, *, target_type: str, target_id: UUID
    ) -> Sequence[DocumentAggregate]:
        context.require(Permission.DOCUMENT_READ)
        try:
            kind = DocumentLinkTargetType(target_type)
        except ValueError as error:
            raise ApiProblem(
                400,
                "UNSUPPORTED_DOCUMENT_TARGET",
                "Unsupported target",
                "Select a supported document target.",
            ) from error
        require_target(
            self._repository.session,
            context,
            target_type=kind,
            target_id=target_id,
            allow_finalized=True,
        )
        documents = self._repository.linked(
            organization_id=context.organization_id, target_type=target_type, target_id=target_id
        )
        ids = {document.id for document in documents}
        versions: dict[UUID, list[DocumentVersion]] = defaultdict(list)
        links: dict[UUID, list[DocumentLink]] = defaultdict(list)
        for version in self._repository.versions_for_documents(
            organization_id=context.organization_id, document_ids=ids
        ):
            versions[version.document_id].append(version)
        for link in self._repository.links_for_documents(
            organization_id=context.organization_id, document_ids=ids
        ):
            links[link.document_id].append(link)
        return [
            protected_aggregate(context, document, versions[document.id], links[document.id])
            for document in documents
        ]

    def get(self, context: RequestContext, document_id: UUID) -> DocumentAggregate:
        context.require(Permission.DOCUMENT_READ)
        document = self._repository.get(
            organization_id=context.organization_id, record_id=document_id
        )
        if document is None:
            raise document_not_found()
        require_document_targets(self._repository.session, context, document_id)
        return protected_aggregate(
            context,
            document,
            self._repository.versions(
                organization_id=context.organization_id, document_id=document.id
            ),
            self._repository.links(
                organization_id=context.organization_id, document_id=document.id
            ),
        )


class DocumentCommandService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        storage: ObjectStorage,
        *,
        audit_recorder: AuditRecorder | None = None,
        outbox_recorder: OutboxRecorder | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._audit_recorder = audit_recorder or AuditRecorder()
        self._outbox_recorder = outbox_recorder or OutboxRecorder()

    def create_upload(
        self, context: RequestContext, data: dict[str, object], *, key: str | None = None
    ) -> tuple[
        DocumentResponse,
        Sequence[DocumentVersionResponse],
        Sequence[DocumentLinkResponse],
        str | None,
        datetime,
    ]:
        return self._create_upload(
            context, DocumentUploadCreate.model_validate(data).model_dump(), key=key
        )

    def create_version(
        self,
        context: RequestContext,
        document_id: UUID,
        data: dict[str, object],
        *,
        key: str | None = None,
    ) -> tuple[
        DocumentResponse,
        Sequence[DocumentVersionResponse],
        Sequence[DocumentLinkResponse],
        str | None,
        datetime,
    ]:
        return self._create_upload(
            context,
            DocumentVersionCreate.model_validate(data).model_dump(),
            existing_id=document_id,
            key=key,
        )

    def _create_upload(
        self,
        context: RequestContext,
        data: dict[str, object],
        *,
        existing_id: UUID | None = None,
        key: str | None = None,
    ) -> tuple[
        DocumentResponse,
        Sequence[DocumentVersionResponse],
        Sequence[DocumentLinkResponse],
        str | None,
        datetime,
    ]:
        context.require(Permission.DOCUMENT_WRITE)
        payload = {"document_id": existing_id, **data}
        # Read a committed retry before checking mutability or signing a new random key.
        # An absent command is rolled back here and created atomically below.
        if key is not None:
            with self._session_factory() as session:
                previous = begin_command(
                    session, context, scope="document.upload", key=key, payload=payload
                )
                previous_id = previous.resource_id
            if previous_id is not None:
                return self._resume_upload(context, previous_id)
        document_id = existing_id or uuid4()
        version_id = uuid4()
        object_key = f"{context.organization_id}/{document_id}/{version_id}"
        with self._session_factory() as session:
            if existing_id is None:
                targets = [
                    (DocumentLinkTargetType(str(data["target_type"])), UUID(str(data["target_id"])))
                ]
            else:
                repository = DocumentRepository(session)
                if (
                    repository.get(organization_id=context.organization_id, record_id=existing_id)
                    is None
                ):
                    raise document_not_found()
                targets = [
                    (DocumentLinkTargetType(link.target_type), link.target_id)
                    for link in repository.links(
                        organization_id=context.organization_id, document_id=existing_id
                    )
                ]
                if not targets:
                    raise document_not_found()
            for target_type, target_id in targets:
                require_target(session, context, target_type=target_type, target_id=target_id)
        self._storage.ensure_bucket()
        expires_at = datetime.now(UTC) + UPLOAD_SESSION_LIFETIME
        upload_url = self._storage.presign_upload(object_key, expires=UPLOAD_SESSION_LIFETIME)
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            command = None
            if key is not None:
                command = begin_command(
                    session, context, scope="document.upload", key=key, payload=payload
                )
                if command.resource_id is not None:
                    previous_id = command.resource_id
                    unit_of_work.commit()
                    return self._resume_upload(context, previous_id)
            for target_type, target_id in sorted(
                targets, key=lambda pair: (str(pair[0]), str(pair[1]))
            ):
                require_target(
                    session, context, target_type=target_type, target_id=target_id, lock=True
                )
            if existing_id is None:
                document = Document(
                    id=document_id,
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    title=str(data["title"]),
                    document_type=str(data["document_type"]),
                    latest_version_number=1,
                )
                links = [
                    DocumentLink(
                        organization_id=context.organization_id,
                        created_by=context.user_id,
                        updated_by=context.user_id,
                        document_id=document.id,
                        target_type=target_type,
                        target_id=target_id,
                    )
                    for target_type, target_id in targets
                ]
            else:
                repository = DocumentRepository(session)
                current = repository.get_for_update(
                    organization_id=context.organization_id, document_id=existing_id
                )
                if current is None:
                    raise document_not_found()
                document = current
                if document.version != int(str(data["expected_version"])):
                    raise ApiProblem(
                        409,
                        "VERSION_CONFLICT",
                        "Version conflict",
                        "Reload the document before replacing it.",
                    )
                document.latest_version_number += 1
                document.updated_by = context.user_id
                links = list(
                    repository.links(
                        organization_id=context.organization_id, document_id=existing_id
                    )
                )
            version = DocumentVersion(
                id=version_id,
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                document_id=document.id,
                version_number=document.latest_version_number,
                object_key=object_key,
                file_name=str(data["file_name"]),
                mime_type=str(data["mime_type"]),
                expected_size_bytes=int(str(data["size_bytes"])),
                expected_sha256=str(data["sha256"]),
            )
            session.add_all([document, version, *links])
            session.add(
                Activity(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    subject_type="document",
                    subject_id=document.id,
                    activity_type="document.upload_initiated",
                    summary=f"Upload started for {document.title}",
                    details={
                        "document_type": document.document_type,
                        "version_number": version.version_number,
                    },
                    correlation_id=context.request_id,
                )
            )
            self._audit_recorder.record(
                session,
                context,
                action="document.upload_initiated",
                target_type="document",
                target_id=document.id,
                after={"version_id": str(version.id), "version_number": version.version_number},
            )
            self._outbox_recorder.record(
                session,
                context,
                DomainEvent(
                    "document.upload_initiated.v1",
                    "document",
                    document.id,
                    {"document_id": str(document.id), "version_id": str(version.id)},
                ),
            )
            if command is not None:
                complete_command(command, version.id, "document_version")
            session.flush()
            unit_of_work.commit()
        return (*protected_aggregate(context, document, [version], links), upload_url, expires_at)

    def resume_upload(
        self,
        context: RequestContext,
        document_id: UUID,
        version_id: UUID,
        data: dict[str, object],
    ) -> tuple[
        DocumentResponse,
        Sequence[DocumentVersionResponse],
        Sequence[DocumentLinkResponse],
        str | None,
        datetime,
    ]:
        context.require(Permission.DOCUMENT_WRITE)
        return self._resume_upload(
            context,
            version_id,
            document_id=document_id,
            expected_file=DocumentUploadResume.model_validate(data),
        )

    def _resume_upload(
        self,
        context: RequestContext,
        version_id: UUID,
        *,
        signed_url: str | None = None,
        document_id: UUID | None = None,
        expected_file: DocumentUploadResume | None = None,
    ) -> tuple[
        DocumentResponse,
        Sequence[DocumentVersionResponse],
        Sequence[DocumentLinkResponse],
        str | None,
        datetime,
    ]:
        with self._session_factory() as session:
            version = session.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.organization_id == context.organization_id,
                    DocumentVersion.id == version_id,
                    DocumentVersion.deleted_at.is_(None),
                )
            )
            if version is None or (document_id is not None and version.document_id != document_id):
                raise document_not_found()
            repository = DocumentRepository(session)
            document = repository.get(
                organization_id=context.organization_id, record_id=version.document_id
            )
            if document is None:
                raise document_not_found()
            links = repository.links(
                organization_id=context.organization_id, document_id=document.id
            )
            if not links:
                raise document_not_found()
            pending = version.status == DocumentVersionStatus.PENDING_UPLOAD
            for link in links:
                require_target(
                    session,
                    context,
                    target_type=DocumentLinkTargetType(link.target_type),
                    target_id=link.target_id,
                    allow_finalized=not pending,
                )
            if pending and version.version_number != document.latest_version_number:
                raise ApiProblem(
                    409,
                    "UPLOAD_VERSION_SUPERSEDED",
                    "Superseded upload",
                    "Resume the current file version instead.",
                )
            if version.status == DocumentVersionStatus.REJECTED:
                raise ApiProblem(
                    409,
                    "INVALID_DOCUMENT_STATE",
                    "Rejected file",
                    "Create a replacement for rejected evidence.",
                )
            if expected_file is not None and (
                expected_file.file_name != version.file_name
                or expected_file.mime_type != version.mime_type
                or expected_file.size_bytes != version.expected_size_bytes
                or expected_file.sha256 != version.expected_sha256
            ):
                raise ApiProblem(
                    409,
                    "UPLOAD_FILE_MISMATCH",
                    "File mismatch",
                    "Select the original file to resume this upload.",
                )
            object_key = version.object_key
        expires_at = datetime.now(UTC) + UPLOAD_SESSION_LIFETIME
        if pending and signed_url is None:
            url = self._storage.presign_upload(object_key, expires=UPLOAD_SESSION_LIFETIME)
            # Recheck facts after the external call; completion may have won meanwhile.
            return self._resume_upload(
                context,
                version_id,
                signed_url=url,
                document_id=document_id,
                expected_file=expected_file,
            )
        return (
            *protected_aggregate(context, document, [version], links),
            signed_url if pending else None,
            expires_at,
        )

    def complete(
        self, context: RequestContext, document_id: UUID, version_id: UUID
    ) -> DocumentAggregate:
        context.require(Permission.DOCUMENT_WRITE)
        with self._session_factory() as session:
            version_snapshot = session.scalar(
                select(DocumentVersion).where(
                    DocumentVersion.organization_id == context.organization_id,
                    DocumentVersion.document_id == document_id,
                    DocumentVersion.id == version_id,
                    DocumentVersion.deleted_at.is_(None),
                )
            )
            if version_snapshot is None:
                raise document_not_found()
            object_key = version_snapshot.object_key
            expected_size = version_snapshot.expected_size_bytes
            expected_sha256 = version_snapshot.expected_sha256
            expected_mime = version_snapshot.mime_type
            storage_version_id = version_snapshot.storage_version_id
            pending_upload = version_snapshot.status == DocumentVersionStatus.PENDING_UPLOAD
            targets = [
                (DocumentLinkTargetType(link.target_type), link.target_id)
                for link in DocumentRepository(session).links(
                    organization_id=context.organization_id, document_id=document_id
                )
            ]
            for target_type, target_id in targets:
                require_target(
                    session,
                    context,
                    target_type=target_type,
                    target_id=target_id,
                    allow_finalized=not pending_upload,
                )
        stored = self._storage.inspect(object_key, version_id=storage_version_id)
        if not stored.version_id or stored.version_id == "null":
            raise ApiProblem(
                409,
                "STORAGE_VERSION_REQUIRED",
                "Versioning required",
                "Enable object versioning before completing uploads.",
            )
        if stored.size != expected_size:
            raise ApiProblem(
                409,
                "UPLOAD_SIZE_MISMATCH",
                "Upload size mismatch",
                "The uploaded object size does not match the declared file.",
            )
        if stored.sha256 != expected_sha256:
            raise ApiProblem(
                409,
                "UPLOAD_CHECKSUM_MISMATCH",
                "Upload checksum mismatch",
                "The uploaded object checksum does not match the declared file.",
            )
        if stored.content_type and stored.content_type != expected_mime:
            raise ApiProblem(
                409,
                "UPLOAD_MIME_MISMATCH",
                "Upload MIME mismatch",
                "The uploaded object MIME type does not match the declared file.",
            )
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            repository = DocumentRepository(session)
            if pending_upload:
                for target_type, target_id in sorted(
                    targets, key=lambda pair: (str(pair[0]), str(pair[1]))
                ):
                    require_target(
                        session, context, target_type=target_type, target_id=target_id, lock=True
                    )
            document = repository.get_for_update(
                organization_id=context.organization_id, document_id=document_id
            )
            version = repository.version_for_update(
                organization_id=context.organization_id, version_id=version_id
            )
            if document is None or version is None or version.document_id != document.id:
                raise document_not_found()
            if version.status in {
                DocumentVersionStatus.UPLOADED,
                DocumentVersionStatus.SCANNING,
                DocumentVersionStatus.AVAILABLE,
            }:
                if version.storage_version_id is None:
                    version.storage_version_id = stored.version_id
                    self._audit_recorder.record(
                        session,
                        context,
                        action="document.storage_version_pinned",
                        target_type="document",
                        target_id=document.id,
                        after={
                            "version_id": str(version.id),
                            "storage_version_id": stored.version_id,
                        },
                        reason="Legacy evidence checksum revalidated",
                    )
                    session.add(
                        Activity(
                            organization_id=context.organization_id,
                            created_by=context.user_id,
                            updated_by=context.user_id,
                            subject_type="document",
                            subject_id=document.id,
                            activity_type="document.storage_version_pinned",
                            summary="Legacy evidence checksum revalidated",
                            details={"version_id": str(version.id)},
                            correlation_id=context.request_id,
                        )
                    )
                    self._outbox_recorder.record(
                        session,
                        context,
                        DomainEvent(
                            "document.storage_version_pinned.v1",
                            "document",
                            document.id,
                            {"version_id": str(version.id)},
                        ),
                    )
                unit_of_work.commit()
                return protected_aggregate(
                    context,
                    document,
                    repository.versions(
                        organization_id=context.organization_id, document_id=document.id
                    ),
                    repository.links(
                        organization_id=context.organization_id, document_id=document.id
                    ),
                )
            if version.status != DocumentVersionStatus.PENDING_UPLOAD:
                raise ApiProblem(
                    409,
                    "INVALID_DOCUMENT_STATE",
                    "Invalid document state",
                    "Only a pending upload can be completed.",
                )
            now = datetime.now(UTC)
            version.status = DocumentVersionStatus.UPLOADED
            version.actual_size_bytes = stored.size
            version.actual_sha256 = stored.sha256
            version.storage_version_id = stored.version_id
            version.uploaded_at = now
            version.updated_by = context.user_id
            job = AsyncJob(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                job_type="DOCUMENT_SCAN",
                status=AsyncJobStatus.PENDING,
                progress=0,
                max_attempts=3,
                correlation_id=context.request_id,
            )
            session.add(job)
            session.flush()
            session.add(
                Activity(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    subject_type="document",
                    subject_id=document.id,
                    activity_type="document.uploaded",
                    summary=f"Upload completed for {document.title}; scan queued",
                    details={"version_id": str(version.id), "job_id": str(job.id)},
                    correlation_id=context.request_id,
                )
            )
            self._audit_recorder.record(
                session,
                context,
                action="document.uploaded",
                target_type="document",
                target_id=document.id,
                before={"status": DocumentVersionStatus.PENDING_UPLOAD},
                after={"status": DocumentVersionStatus.UPLOADED, "job_id": str(job.id)},
            )
            self._outbox_recorder.record(
                session,
                context,
                DomainEvent(
                    "document.uploaded.v1",
                    "document",
                    document.id,
                    {
                        "document_id": str(document.id),
                        "version_id": str(version.id),
                        "job_id": str(job.id),
                    },
                ),
            )
            session.flush()
            versions = repository.versions(
                organization_id=context.organization_id, document_id=document.id
            )
            links = repository.links(
                organization_id=context.organization_id, document_id=document.id
            )
            unit_of_work.commit()
            return protected_aggregate(context, document, versions, links)

    def download(
        self, context: RequestContext, document_id: UUID, *, version_id: UUID | None = None
    ) -> tuple[str, datetime]:
        pointer = self._download_pointer(context, document_id, version_id=version_id)
        selected_version_id, object_key, storage_version_id, _ = pointer
        expires_at = datetime.now(UTC) + DOWNLOAD_SESSION_LIFETIME
        url = self._storage.presign_download(
            object_key, expires=DOWNLOAD_SESSION_LIFETIME, version_id=storage_version_id
        )
        # Signing happens outside a database transaction. Recheck the exact selected version
        # before issuing the capability; a concurrent restriction must not return a fresh URL.
        current = self._download_pointer(context, document_id, version_id=selected_version_id)
        if current != pointer:
            raise ApiProblem(
                409, "VERSION_CONFLICT", "Changed evidence", "Reload the document before download."
            )
        return url, expires_at

    def _download_pointer(
        self, context: RequestContext, document_id: UUID, *, version_id: UUID | None
    ) -> tuple[UUID, str, str, str]:
        context.require(Permission.DOCUMENT_READ)
        with self._session_factory() as session:
            document = DocumentRepository(session).get(
                organization_id=context.organization_id, record_id=document_id
            )
            if document is None:
                raise document_not_found()
            require_document_targets(session, context, document_id)
            query = select(DocumentVersion).where(
                DocumentVersion.organization_id == context.organization_id,
                DocumentVersion.document_id == document.id,
                DocumentVersion.deleted_at.is_(None),
            )
            if version_id is None:
                query = query.where(
                    DocumentVersion.version_number == document.latest_version_number
                )
            else:
                query = query.where(DocumentVersion.id == version_id)
            version = session.scalar(query)
            if version is None and version_id is not None:
                raise document_not_found()
            if version is None or version.status != DocumentVersionStatus.AVAILABLE:
                raise ApiProblem(
                    409,
                    "DOCUMENT_NOT_AVAILABLE",
                    "Document not available",
                    "The selected document version has not passed scanning.",
                )
            if Permission.PROFIT_READ not in context.permissions and not is_released(
                document, version
            ):
                raise ApiProblem(
                    403,
                    "DOCUMENT_REVIEW_REQUIRED",
                    "Confidential document",
                    "An authorized reviewer must release this exact file version before download.",
                )
            object_key = version.object_key
            storage_version_id = version.storage_version_id
            if not storage_version_id or storage_version_id == "null":
                raise ApiProblem(
                    409,
                    "DOCUMENT_VERSION_UNPINNED",
                    "Verification required",
                    "Revalidate completion to pin legacy evidence before downloading.",
                )
            return version.id, object_key, storage_version_id, content_digest(document, version)


def mark_document_available(session: Session, message: OutboxMessage) -> None:
    organization_id = UUID(message["organization_id"])
    version_id = UUID(str(message["payload"]["version_id"]))
    job_id = UUID(str(message["payload"]["job_id"]))
    version = session.scalar(
        select(DocumentVersion)
        .where(
            DocumentVersion.organization_id == organization_id,
            DocumentVersion.id == version_id,
        )
        .with_for_update()
    )
    job = session.scalar(
        select(AsyncJob)
        .where(AsyncJob.organization_id == organization_id, AsyncJob.id == job_id)
        .with_for_update()
    )
    if version is None or job is None:
        raise ValueError("Document scan aggregate was not found in the event organization")
    if version.status == DocumentVersionStatus.AVAILABLE:
        return
    if version.status != DocumentVersionStatus.UPLOADED:
        raise ValueError("Document version is not ready for scanning")
    now = datetime.now(UTC)
    version.status = DocumentVersionStatus.AVAILABLE
    version.available_at = now
    job.status = AsyncJobStatus.SUCCEEDED
    job.progress = Decimal("100")
    job.result_reference = f"document-version:{version.id}"
    session.add(
        Activity(
            organization_id=organization_id,
            subject_type="document",
            subject_id=version.document_id,
            activity_type="document.available",
            summary="Document scan completed and version is available",
            details={"version_id": str(version.id), "job_id": str(job.id)},
            correlation_id=UUID(message["correlation_id"]),
        )
    )
