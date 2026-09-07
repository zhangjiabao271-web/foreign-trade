from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.core.config import get_settings
from app.documents.repositories import DocumentRepository
from app.documents.review import (
    DocumentReviewRequest,
    DocumentReviewResponse,
    DocumentReviewService,
)
from app.documents.schemas import (
    DocumentListResponse,
    DocumentResponse,
    DocumentUploadCreate,
    DocumentUploadResume,
    DocumentVersionCreate,
    DownloadSessionResponse,
    UploadSessionResponse,
)
from app.documents.services import DocumentCommandService, DocumentQueryService
from app.documents.storage import MinioObjectStorage, ObjectStorage

router = APIRouter(prefix="/api/v1/documents", tags=["documents"], responses=PROBLEM_RESPONSES)
DatabaseSession = Annotated[Session, Depends(get_database_session)]
SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
DocumentReader = Annotated[RequestContext, Depends(require_permissions(Permission.DOCUMENT_READ))]
DocumentWriter = Annotated[RequestContext, Depends(require_permissions(Permission.DOCUMENT_WRITE))]


def get_object_storage() -> ObjectStorage:
    return MinioObjectStorage(get_settings())


ObjectStorageDependency = Annotated[ObjectStorage, Depends(get_object_storage)]
DocumentReviewer = Annotated[
    RequestContext, Depends(require_permissions(Permission.DOCUMENT_READ, Permission.PROFIT_READ))
]


@router.get("/{document_id}/versions/{version_id}/review", response_model=DocumentReviewResponse)
def inspect_document_review(
    document_id: UUID, version_id: UUID, context: DocumentReviewer, factory: SessionFactory
) -> DocumentReviewResponse:
    return DocumentReviewService(factory).inspect(context, document_id, version_id)


@router.post("/{document_id}/versions/{version_id}/review", response_model=DocumentReviewResponse)
def review_document_version(
    document_id: UUID,
    version_id: UUID,
    request: DocumentReviewRequest,
    context: DocumentReviewer,
    factory: SessionFactory,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=255)],
) -> DocumentReviewResponse:
    return DocumentReviewService(factory).decide(
        context, document_id, version_id, request, key=idempotency_key
    )


@router.get("", response_model=DocumentListResponse)
def list_documents(
    context: DocumentReader,
    session: DatabaseSession,
    target_type: Annotated[str, Query(min_length=1, max_length=32)],
    target_id: UUID,
) -> DocumentListResponse:
    aggregates = DocumentQueryService(DocumentRepository(session)).linked(
        context, target_type=target_type, target_id=target_id
    )
    return DocumentListResponse(
        items=[aggregate[0] for aggregate in aggregates], count=len(aggregates)
    )


@router.post("/upload-sessions", response_model=UploadSessionResponse, status_code=201)
def create_upload_session(
    request: DocumentUploadCreate,
    context: DocumentWriter,
    factory: SessionFactory,
    storage: ObjectStorageDependency,
    idempotency_key: Annotated[str | None, Header(min_length=1, max_length=255)] = None,
) -> UploadSessionResponse:
    document, versions, links, upload_url, expires_at = DocumentCommandService(
        factory, storage
    ).create_upload(context, request.model_dump(), key=idempotency_key)
    return UploadSessionResponse(
        document=document,
        version_id=versions[0].id,
        upload_url=upload_url,
        expires_at=expires_at,
    )


@router.post("/{document_id}/versions/{version_id}/complete", response_model=DocumentResponse)
def complete_upload(
    document_id: UUID,
    version_id: UUID,
    context: DocumentWriter,
    factory: SessionFactory,
    storage: ObjectStorageDependency,
) -> DocumentResponse:
    return DocumentCommandService(factory, storage).complete(context, document_id, version_id)[0]


@router.post(
    "/{document_id}/version-upload-sessions", response_model=UploadSessionResponse, status_code=201
)
def create_version_upload_session(
    document_id: UUID,
    request: DocumentVersionCreate,
    context: DocumentWriter,
    factory: SessionFactory,
    storage: ObjectStorageDependency,
    idempotency_key: Annotated[str | None, Header(min_length=1, max_length=255)] = None,
) -> UploadSessionResponse:
    document, versions, links, url, expires = DocumentCommandService(
        factory, storage
    ).create_version(context, document_id, request.model_dump(), key=idempotency_key)
    return UploadSessionResponse(
        document=document,
        version_id=versions[0].id,
        upload_url=url,
        expires_at=expires,
    )


@router.post(
    "/{document_id}/versions/{version_id}/upload-session", response_model=UploadSessionResponse
)
def resume_upload_session(
    document_id: UUID,
    version_id: UUID,
    request: DocumentUploadResume,
    context: DocumentWriter,
    factory: SessionFactory,
    storage: ObjectStorageDependency,
) -> UploadSessionResponse:
    document, versions, links, url, expires = DocumentCommandService(
        factory, storage
    ).resume_upload(context, document_id, version_id, request.model_dump())
    return UploadSessionResponse(
        document=document,
        version_id=version_id,
        upload_url=url,
        expires_at=expires,
    )


@router.get("/{document_id}", response_model=DocumentResponse)
def read_document(
    document_id: UUID, context: DocumentReader, session: DatabaseSession
) -> DocumentResponse:
    return DocumentQueryService(DocumentRepository(session)).get(context, document_id)[0]


@router.post("/{document_id}/download-session", response_model=DownloadSessionResponse)
def create_download_session(
    document_id: UUID,
    context: DocumentReader,
    factory: SessionFactory,
    storage: ObjectStorageDependency,
) -> DownloadSessionResponse:
    url, expires_at = DocumentCommandService(factory, storage).download(context, document_id)
    return DownloadSessionResponse(download_url=url, expires_at=expires_at)


@router.post(
    "/{document_id}/versions/{version_id}/download-session", response_model=DownloadSessionResponse
)
def create_version_download_session(
    document_id: UUID,
    version_id: UUID,
    context: DocumentReader,
    factory: SessionFactory,
    storage: ObjectStorageDependency,
) -> DownloadSessionResponse:
    url, expires_at = DocumentCommandService(factory, storage).download(
        context, document_id, version_id=version_id
    )
    return DownloadSessionResponse(download_url=url, expires_at=expires_at)
