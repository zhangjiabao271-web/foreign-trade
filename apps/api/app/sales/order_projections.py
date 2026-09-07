from collections.abc import Sequence

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.sales.models import SalesOrder, SalesOrderItem
from app.sales.order_schemas import SalesOrderItemResponse, SalesOrderResponse
from app.sales.text_content import is_released


def order_response(
    context: RequestContext, order: SalesOrder, items: Sequence[SalesOrderItem]
) -> SalesOrderResponse:
    """Project authorized output without changing immutable commercial facts."""
    response = SalesOrderResponse(
        **SalesOrderResponse.model_validate(order).model_dump(exclude={"items"}),
        items=[SalesOrderItemResponse.model_validate(item) for item in items],
    )
    response.released = is_released(order, items)
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
