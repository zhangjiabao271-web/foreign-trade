import hashlib
import json

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.finance.models import Payment
from app.finance.schemas import PaymentRecordSnapshot


def content_digest(row: Payment, *, version: int | None = None) -> str:
    facts = {
        "kind": "payment",
        "organization_id": str(row.organization_id),
        "id": str(row.id),
        "version": row.version if version is None else version,
        "notes": row.notes,
    }
    return hashlib.sha256(
        json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def is_released(row: Payment) -> bool:
    return (
        row.reviewed_by is not None
        and row.reviewed_at is not None
        and row.released_digest == content_digest(row)
    )


def payment_snapshot(context: RequestContext, row: Payment) -> PaymentRecordSnapshot:
    released = is_released(row)
    visible = Permission.PROFIT_READ in context.permissions or released
    return PaymentRecordSnapshot.model_validate(row).model_copy(
        update={
            "notes": row.notes if visible else None,
            "content_visible": visible,
            "released": released,
        }
    )
