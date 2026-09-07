from uuid import UUID

from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.sales.order_repositories import SalesOrderRepository
from app.work.services import WorkQueryService


class OrderAssistantQueries:
    """Allowlisted read snapshots, not mutable ORM aggregates or arbitrary activity bodies."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def snapshot(
        self, context: RequestContext, order_id: UUID, *, profit: bool = False
    ) -> dict[str, object]:
        context.require(Permission.ORDER_READ)
        if profit:
            context.require(Permission.PROFIT_READ)
        order = SalesOrderRepository(self.session).get(
            organization_id=context.organization_id, record_id=order_id
        )
        if order is None:
            raise ApiProblem(404, "SALES_ORDER_NOT_FOUND", "Order not found", "Order not found.")
        result: dict[str, object] = {
            "source": {"type": "sales_order", "id": str(order.id), "version": order.version},
            "order_number": order.order_number,
            "status": order.status,
            "currency": order.currency_code,
            "total": str(order.total),
            "agreed_deposit": str(order.deposit_amount),
        }
        if profit:
            result.update(
                estimated_cost=str(order.total_cost),
                gross_profit=str(order.gross_profit),
                gross_margin=str(order.gross_margin),
                basis="Accepted quotation snapshot, not realized profit",
            )
        return result

    def timeline(self, context: RequestContext, order_id: UUID) -> dict[str, object]:
        rows = WorkQueryService(self.session).order_activities(context, order_id, 30)
        return {
            "source": {"type": "sales_order", "id": str(order_id)},
            "limit": 30,
            "events": [
                {
                    "id": str(row.id),
                    "type": row.activity_type,
                    "occurred_at": row.occurred_at.isoformat(),
                }
                for row in rows
            ],
        }
