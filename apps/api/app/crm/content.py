import hashlib
import json

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.crm.models import Lead, Opportunity
from app.crm.opportunity_schemas import OpportunityResponse
from app.crm.schemas import LeadResponse


def text_fields(row: Lead | Opportunity) -> dict[str, object]:
    if isinstance(row, Lead):
        return {"notes": row.notes, "source": row.source}
    return {"lost_reason": row.lost_reason}


def content_digest(row: Lead | Opportunity, *, version: int | None = None) -> str:
    facts = {
        "kind": "lead" if isinstance(row, Lead) else "opportunity",
        "organization_id": str(row.organization_id),
        "id": str(row.id),
        "version": row.version if version is None else version,
        "fields": text_fields(row),
    }
    return hashlib.sha256(
        json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def is_released(row: Lead | Opportunity) -> bool:
    return (
        row.reviewed_by is not None
        and row.reviewed_at is not None
        and row.released_digest == content_digest(row)
    )


def lead_response(context: RequestContext, row: Lead) -> LeadResponse:
    released = is_released(row)
    visible = Permission.PROFIT_READ in context.permissions or released
    return LeadResponse.model_validate(row).model_copy(
        update={
            "notes": row.notes if visible else None,
            "source": row.source if visible else None,
            "content_visible": visible,
            "released": released,
        }
    )


def opportunity_response(context: RequestContext, row: Opportunity) -> OpportunityResponse:
    released = is_released(row)
    visible = Permission.PROFIT_READ in context.permissions or released
    return OpportunityResponse.model_validate(row).model_copy(
        update={
            "lost_reason": row.lost_reason if visible else None,
            "content_visible": visible,
            "released": released,
        }
    )
