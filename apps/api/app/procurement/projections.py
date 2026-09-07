from collections.abc import Sequence
from decimal import Decimal

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.procurement.content import is_released
from app.procurement.enums import PurchaseOrderStatus
from app.procurement.models import PurchaseOrder, PurchaseOrderItem
from app.procurement.schemas import PurchaseOrderItemResponse, PurchaseOrderResponse
from app.sales.services import quantize_money
from app.work.content import activity_response
from app.work.models import Activity
from app.work.schemas import ActivityResponse


def purchase_order_response(
    context: RequestContext, order: PurchaseOrder, items: Sequence[PurchaseOrderItem]
) -> PurchaseOrderResponse:
    response = PurchaseOrderResponse(
        **PurchaseOrderResponse.model_validate(order).model_dump(exclude={"items"}),
        items=[PurchaseOrderItemResponse.model_validate(item) for item in items],
    )
    response.released = is_released(order, items)
    response.content_visible = Permission.PROFIT_READ in context.permissions or response.released
    if not response.content_visible:
        response.cancellation_reason = None
        response.cancellation_reference = None
        for item in response.items:
            item.description_snapshot = None
    if Permission.PROFIT_READ in context.permissions:
        retained = order.total
        if order.status == PurchaseOrderStatus.CANCELLED:
            retained = sum(
                (quantize_money(item.received_quantity * item.unit_cost) for item in items),
                Decimal("0"),
            )
        response.retained_total = retained
        response.retained_total_order_currency = quantize_money(retained * order.exchange_rate)
    else:
        response.currency_code = None
        response.exchange_rate = None
        response.total = None
        response.total_order_currency = None
        for item in response.items:
            item.unit_cost = None
            item.line_total = None
    return response


def purchase_activity_response(context: RequestContext, activity: Activity) -> ActivityResponse:
    response = activity_response(context, activity)
    if Permission.PROFIT_READ not in context.permissions:
        # Old summaries/reasons may include manager-authored pricing; retain stored evidence,
        # but never release structured purchase prices with an approved narrative.
        if not response.content_visible:
            response.summary = activity.activity_type
        result = activity.details.get("command_result")
        allowed = {
            "status",
            "version",
            "expected_delivery_date",
            "received_date",
            "received_quantities",
            "cancelled_quantities",
            "retained_received_quantities",
            "replacement_purchase_order_id",
            "replaces_purchase_order_id",
        }
        if response.content_visible:
            allowed.update({"reason", "reference", "supplier_reference"})
        projected = (
            {key: value for key, value in result.items() if key in allowed}
            if isinstance(result, dict)
            else {}
        )
        if not response.content_visible:
            response.details = {"command_result": projected}
        elif isinstance(result, dict):
            response.details["command_result"] = projected
    return response
