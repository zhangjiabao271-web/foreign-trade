from collections.abc import Sequence

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.core.content_review import release_matches, review_digest
from app.sales.contract_models import SalesContract
from app.sales.contract_schemas import ContractResponse
from app.sales.models import QuotationItem, QuotationVersion, SalesOrder, SalesOrderItem

CommercialRecord = QuotationVersion | SalesOrder | SalesContract
CommercialItems = Sequence[QuotationItem | SalesOrderItem]


def text_fields(row: CommercialRecord, items: CommercialItems = ()) -> dict[str, object]:
    if isinstance(row, SalesContract):
        return {"notes": row.notes, "commercial_snapshot": row.commercial_snapshot}
    return {
        "payment_terms": row.payment_terms,
        "delivery_terms": row.delivery_terms,
        "items": [
            {
                "id": str(item.id),
                "version": item.version,
                "line_number": item.line_number,
                "description": item.description_snapshot,
            }
            for item in sorted(items, key=lambda item: (item.line_number, item.id))
        ],
    }


def content_digest(
    row: CommercialRecord, items: CommercialItems = (), *, version: int | None = None
) -> str:
    return review_digest(
        row.__tablename__,
        row.organization_id,
        row.id,
        row.version if version is None else version,
        text_fields(row, items),
    )


def is_released(row: CommercialRecord, items: CommercialItems = ()) -> bool:
    return release_matches(row, content_digest(row, items))


def contract_response(context: RequestContext, row: SalesContract) -> ContractResponse:
    result = ContractResponse.model_validate(row)
    result.released = is_released(row)
    result.content_visible = Permission.PROFIT_READ in context.permissions or result.released
    if not result.content_visible:
        result.notes = None
        result.commercial_snapshot.payment_terms = None
        result.commercial_snapshot.delivery_terms = None
        for item in result.commercial_snapshot.items:
            item.description = None
    return result
