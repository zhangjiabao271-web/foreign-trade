from collections.abc import Mapping, Sequence
from uuid import UUID

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.sales.enums import QuotationVersionStatus
from app.sales.models import Quotation, QuotationItem, QuotationVersion
from app.sales.schemas import (
    QuotationItemResponse,
    QuotationListItem,
    QuotationResponse,
    QuotationVersionResponse,
)
from app.sales.text_content import is_released


def version_response(
    context: RequestContext, version: QuotationVersion, items: Sequence[QuotationItem]
) -> QuotationVersionResponse:
    response = QuotationVersionResponse(
        **QuotationVersionResponse.model_validate(version).model_dump(exclude={"items"}),
        items=[QuotationItemResponse.model_validate(item) for item in items],
    )
    response.released = is_released(version, items)
    response.content_visible = Permission.PROFIT_READ in context.permissions or response.released
    if not response.content_visible:
        response.payment_terms = None
        response.delivery_terms = None
        for item in response.items:
            item.description_snapshot = None
    if Permission.PROFIT_READ not in context.permissions:
        response.total_cost = None
        response.gross_profit = None
        response.gross_margin = None
        for item in response.items:
            item.unit_cost = None
            item.cost_currency = None
            item.cost_exchange_rate = None
            item.allocated_cost = None
            item.line_cost = None
            item.line_gross_profit = None
    return response


def quotation_response(
    context: RequestContext,
    quotation: Quotation,
    current: QuotationVersion,
    versions: Sequence[QuotationVersion],
    items_by_version: Mapping[UUID, Sequence[QuotationItem]],
) -> QuotationResponse:
    responses = [
        version_response(context, version, items_by_version[version.id]) for version in versions
    ]
    return QuotationResponse(
        id=quotation.id,
        quotation_number=quotation.quotation_number,
        inquiry_id=quotation.inquiry_id,
        opportunity_id=quotation.opportunity_id,
        company_id=quotation.company_id,
        accepted_version_id=quotation.accepted_version_id,
        current_version=next(response for response in responses if response.id == current.id),
        versions=responses,
        created_at=quotation.created_at,
    )


def quotation_list_item(
    context: RequestContext, quotation: Quotation, version: QuotationVersion
) -> QuotationListItem:
    can_read_costs = Permission.PROFIT_READ in context.permissions
    return QuotationListItem(
        id=quotation.id,
        quotation_number=quotation.quotation_number,
        company_id=quotation.company_id,
        opportunity_id=quotation.opportunity_id,
        accepted_version_id=quotation.accepted_version_id,
        version_id=version.id,
        version_number=version.version_number,
        status=QuotationVersionStatus(version.status),
        currency_code=version.currency_code,
        total=version.total,
        gross_profit=version.gross_profit if can_read_costs else None,
        gross_margin=version.gross_margin if can_read_costs else None,
        valid_until=version.valid_until,
        created_at=quotation.created_at,
    )
