from collections.abc import Sequence

from app.core.content_review import release_matches, review_digest
from app.procurement.models import PurchaseOrder, PurchaseOrderItem


def text_fields(row: PurchaseOrder, items: Sequence[PurchaseOrderItem]) -> dict[str, object]:
    return {
        "cancellation_reason": row.cancellation_reason,
        "cancellation_reference": row.cancellation_reference,
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
    row: PurchaseOrder, items: Sequence[PurchaseOrderItem], *, version: int | None = None
) -> str:
    return review_digest(
        row.__tablename__,
        row.organization_id,
        row.id,
        row.version if version is None else version,
        text_fields(row, items),
    )


def is_released(row: PurchaseOrder, items: Sequence[PurchaseOrderItem]) -> bool:
    return release_matches(row, content_digest(row, items))
