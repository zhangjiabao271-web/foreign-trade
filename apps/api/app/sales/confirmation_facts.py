from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.sales.order_enums import SalesOrderStatus
from app.sales.order_repositories import SalesOrderRepository


@dataclass(frozen=True, slots=True)
class ConfirmedOrderTaskSource:
    order_id: UUID
    order_number: str
    confirmed_at: datetime
    deposit_pending: bool


def procurement_preparation_source(
    session: Session, context: RequestContext, order_id: UUID
) -> ConfirmedOrderTaskSource:
    """Read the caller's pending confirmation without changing its flush order."""
    context.require(Permission.ORDER_CONFIRM)
    with session.no_autoflush:
        order = SalesOrderRepository(session).get_for_update(
            organization_id=context.organization_id, sales_order_id=order_id
        )
    if order is None:
        raise ApiProblem(404, "SALES_ORDER_NOT_FOUND", "Order not found", "Order not found.")
    if order.confirmed_at is None or order.status not in {
        SalesOrderStatus.DEPOSIT_PENDING,
        SalesOrderStatus.EXECUTING,
    }:
        raise ApiProblem(
            409,
            "INVALID_STATE_TRANSITION",
            "Invalid state transition",
            "Procurement preparation requires an order confirmation.",
        )
    return ConfirmedOrderTaskSource(
        order_id=order.id,
        order_number=order.order_number,
        confirmed_at=order.confirmed_at,
        deposit_pending=order.status == SalesOrderStatus.DEPOSIT_PENDING,
    )
