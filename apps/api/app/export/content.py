import hashlib
import json
from typing import overload

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.export.models import CustomsDeclaration, TaxRefundCase
from app.export.schemas import CustomsResponse, RefundResponse

type ExportCase = CustomsDeclaration | TaxRefundCase


def text_fields(row: ExportCase) -> dict[str, object]:
    return {"notes": row.notes, "rejection_reason": row.rejection_reason}


def content_digest(row: ExportCase, *, version: int | None = None) -> str:
    facts = {
        "kind": "customs" if isinstance(row, CustomsDeclaration) else "refund",
        "organization_id": str(row.organization_id),
        "id": str(row.id),
        "version": row.version if version is None else version,
        "fields": text_fields(row),
    }
    return hashlib.sha256(
        json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def is_released(row: ExportCase) -> bool:
    return (
        row.reviewed_by is not None
        and row.reviewed_at is not None
        and row.released_digest == content_digest(row)
    )


@overload
def case_response(context: RequestContext, row: CustomsDeclaration) -> CustomsResponse: ...


@overload
def case_response(context: RequestContext, row: TaxRefundCase) -> RefundResponse: ...


def case_response(context: RequestContext, row: ExportCase) -> CustomsResponse | RefundResponse:
    released = is_released(row)
    visible = Permission.PROFIT_READ in context.permissions or released
    response = (
        CustomsResponse.model_validate(row)
        if isinstance(row, CustomsDeclaration)
        else RefundResponse.model_validate(row)
    )
    return response.model_copy(
        update={
            "notes": row.notes if visible else None,
            "rejection_reason": row.rejection_reason if visible else None,
            "content_visible": visible,
            "released": released,
        }
    )
