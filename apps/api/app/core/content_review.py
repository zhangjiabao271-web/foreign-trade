"""Shared disclosure metadata and wire fields; domains retain access and transaction ownership."""

import hashlib
import json
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


class ContentReleaseMixin:
    released_digest: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_by: Mapped[UUID | None] = mapped_column(nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def review_constraint(table: str) -> CheckConstraint:
    return CheckConstraint(
        "(released_digest IS NULL OR char_length(released_digest) = 64) AND "
        "((reviewed_by IS NULL AND reviewed_at IS NULL AND released_digest IS NULL) OR "
        "(reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL))",
        name=f"ck_{table}_review",
    )


class ContentReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=1)
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    release: bool
    reason: str = Field(min_length=3, max_length=1000)
    confirmed: bool


class ContentReviewSnapshot(BaseModel):
    record_id: UUID
    version: int
    content_digest: str
    text: str
    details: dict[str, object]
    released: bool
    reviewed_by: UUID | None
    reviewed_at: datetime | None


def review_digest(
    kind: str, organization_id: UUID, record_id: UUID, version: int, fields: dict[str, object]
) -> str:
    """Pure content binding; callers retain ownership, permissions and transactions."""
    content = {
        "kind": kind,
        "organization_id": str(organization_id),
        "id": str(record_id),
        "version": version,
        "fields": fields,
    }
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def release_matches(row: ContentReleaseMixin, digest: str) -> bool:
    return (
        row.reviewed_by is not None
        and row.reviewed_at is not None
        and row.released_digest == digest
    )
