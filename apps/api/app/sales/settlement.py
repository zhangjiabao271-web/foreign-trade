"""Sales-owned settlement port; callers hold the order lock in their unit of work."""

from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.sales.models import SalesOrder
from app.sales.order_enums import SalesOrderStatus
from app.work.models import Activity


class OrderSettlementPort:
    def __init__(self, audit: AuditRecorder, outbox: OutboxRecorder) -> None:
        self.audit = audit
        self.outbox = outbox

    def record_allocation(
        self,
        session: Session,
        context: RequestContext,
        order: SalesOrder,
        *,
        deposit: bool,
        settled: bool,
        reversed: bool,
        payment_id: str,
        amount: str,
        reason: str | None = None,
    ) -> None:
        if order.organization_id != context.organization_id:
            raise ApiProblem(404, "SALES_ORDER_NOT_FOUND", "Order not found", "Order not found.")
        previous = order.status
        if deposit and settled and not reversed and previous == SalesOrderStatus.DEPOSIT_PENDING:
            order.status = SalesOrderStatus.EXECUTING
        elif deposit and not settled and reversed and previous == SalesOrderStatus.EXECUTING:
            order.status = SalesOrderStatus.DEPOSIT_PENDING
        order.updated_by = context.user_id
        action = "sales_order.payment_reversed" if reversed else "sales_order.payment_allocated"
        details = {"payment_id": payment_id, "amount": amount, "deposit": deposit}
        session.add(
            Activity(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                subject_type="sales_order",
                subject_id=order.id,
                activity_type=action,
                summary=f"Payment allocation for {order.order_number}",
                details=details,
                correlation_id=context.request_id,
            )
        )
        self.audit.record(
            session,
            context,
            action=action,
            target_type="sales_order",
            target_id=order.id,
            before={"status": previous},
            after={"status": order.status, **details},
            reason=reason,
        )
        self.outbox.record(
            session,
            context,
            DomainEvent(
                f"{action}.v1",
                "sales_order",
                order.id,
                {"sales_order_id": str(order.id), **details},
            ),
        )
