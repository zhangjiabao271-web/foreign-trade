"""Inquiry-owned progression within the originating quotation transaction."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.inquiries.enums import InquiryStatus
from app.inquiries.repositories import InquiryRepository


def record_quotation_created(session: Session, context: RequestContext, inquiry_id: UUID) -> None:
    """Caller owns quotation evidence, transaction and the existing inquiry-first lock order."""
    context.require(Permission.QUOTATION_WRITE)
    inquiry = InquiryRepository(session).get_for_update(
        organization_id=context.organization_id, inquiry_id=inquiry_id
    )
    if inquiry is None:
        raise ApiProblem(
            404, "INQUIRY_NOT_FOUND", "Inquiry not found", "The inquiry was not found."
        )
    if inquiry.status not in {InquiryStatus.OPEN, InquiryStatus.QUOTING}:
        raise ApiProblem(
            409,
            "INVALID_STATE_TRANSITION",
            "Invalid inquiry state",
            "A closed inquiry cannot be advanced by quotation creation.",
        )
    inquiry.status = InquiryStatus.QUOTING
    inquiry.updated_by = context.user_id
