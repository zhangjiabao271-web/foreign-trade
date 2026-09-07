from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.documents.enums import DocumentLinkTargetType, DocumentType, DocumentVersionStatus


class DocumentUploadCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    document_type: DocumentType
    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(gt=0, le=25 * 1024 * 1024)
    sha256: str = Field(min_length=64, max_length=64)
    target_type: DocumentLinkTargetType
    target_id: UUID

    @field_validator("sha256")
    @classmethod
    def normalize_sha256(cls, value: str) -> str:
        normalized = value.lower()
        if any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError("sha256 must be hexadecimal")
        return normalized


class DocumentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_number: int
    status: DocumentVersionStatus
    file_name: str | None
    mime_type: str | None
    content_visible: bool = False
    released: bool = False
    expected_size_bytes: int
    expected_sha256: str
    actual_size_bytes: int | None
    actual_sha256: str | None
    uploaded_at: datetime | None
    available_at: datetime | None
    rejected_reason: str | None


class DocumentUploadResume(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(gt=0, le=25 * 1024 * 1024)
    sha256: str = Field(min_length=64, max_length=64)

    @field_validator("sha256")
    @classmethod
    def checksum(cls, value: str) -> str:
        return DocumentUploadCreate.normalize_sha256(value)


class DocumentVersionCreate(DocumentUploadResume):
    expected_version: int = Field(ge=1)


class DocumentLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    target_type: DocumentLinkTargetType
    target_id: UUID


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str | None
    document_type: DocumentType
    latest_version_number: int
    version: int
    created_at: datetime
    versions: list[DocumentVersionResponse] = Field(default_factory=list)
    links: list[DocumentLinkResponse] = Field(default_factory=list)


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    count: int


class UploadSessionResponse(BaseModel):
    document: DocumentResponse
    version_id: UUID
    upload_url: str | None
    expires_at: datetime


class DownloadSessionResponse(BaseModel):
    download_url: str
    expires_at: datetime
