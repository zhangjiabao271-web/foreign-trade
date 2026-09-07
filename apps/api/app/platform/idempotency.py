import hashlib
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.platform.models import IdempotencyKey


def begin_command(
    session: Session,
    context: RequestContext,
    *,
    scope: str,
    key: str,
    payload: dict[str, object],
) -> IdempotencyKey:
    if not key.strip() or len(key) > 255:
        raise ApiProblem(422, "INVALID_IDEMPOTENCY_KEY", "Invalid key", "Provide a command key.")
    lock_digest = hashlib.sha256(f"{context.organization_id}:{scope}:{key}".encode()).digest()
    lock_id = int.from_bytes(lock_digest[:8], "big", signed=True)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
    request_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
    existing = session.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.organization_id == context.organization_id,
            IdempotencyKey.scope == scope,
            IdempotencyKey.idempotency_key == key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ApiProblem(
                409,
                "IDEMPOTENCY_CONFLICT",
                "Command key conflict",
                "This command key was already used for a different request.",
            )
        return existing
    record = IdempotencyKey(
        organization_id=context.organization_id,
        created_by=context.user_id,
        updated_by=context.user_id,
        scope=scope,
        idempotency_key=key,
        request_hash=request_hash,
        status="IN_PROGRESS",
        expires_at=datetime.now(UTC) + timedelta(days=3650),
    )
    session.add(record)
    return record


def complete_command(record: IdempotencyKey, resource_id: UUID, resource_type: str) -> None:
    record.status = "COMPLETED"
    record.resource_id = resource_id
    record.resource_type = resource_type
