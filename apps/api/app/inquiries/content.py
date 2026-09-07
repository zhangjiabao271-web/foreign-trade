from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.core.content_review import release_matches, review_digest
from app.inquiries.models import Inquiry
from app.inquiries.schemas import InquiryResponse


def content_digest(row: Inquiry, *, version: int | None = None) -> str:
    return review_digest(
        "inquiry",
        row.organization_id,
        row.id,
        row.version if version is None else version,
        {"description": row.description},
    )


def is_released(row: Inquiry) -> bool:
    return release_matches(row, content_digest(row))


def response(context: RequestContext, row: Inquiry) -> InquiryResponse:
    result = InquiryResponse.model_validate(row)
    result.released = is_released(row)
    result.content_visible = Permission.PROFIT_READ in context.permissions or result.released
    if not result.content_visible:
        result.description = None
    return result
