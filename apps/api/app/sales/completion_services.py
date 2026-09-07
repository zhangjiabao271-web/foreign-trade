from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.unit_of_work import UnitOfWork
from app.finance.repositories import ReceivableRepository
from app.finance.schemas import SalesOrderComplete
from app.fulfillment.enums import ShipmentStatus
from app.fulfillment.models import Shipment, ShipmentItem
from app.fulfillment.services import missing_required_documents
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.sales.order_enums import SalesOrderStatus
from app.sales.order_projections import order_response
from app.sales.order_repositories import SalesOrderRepository
from app.sales.order_schemas import SalesOrderResponse
from app.work.models import Activity, Task


class OrderCompletionService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        audit_recorder: AuditRecorder | None = None,
        outbox_recorder: OutboxRecorder | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._audit_recorder = audit_recorder or AuditRecorder()
        self._outbox_recorder = outbox_recorder or OutboxRecorder()

    def complete(
        self, context: RequestContext, sales_order_id: UUID, data: dict[str, object]
    ) -> SalesOrderResponse:
        context.require(Permission.ORDER_COMPLETE)
        data = SalesOrderComplete.model_validate(data).model_dump()
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            repository = SalesOrderRepository(session)
            order = repository.get_for_update(
                organization_id=context.organization_id,
                sales_order_id=sales_order_id,
            )
            if order is None:
                raise ApiProblem(
                    404,
                    "SALES_ORDER_NOT_FOUND",
                    "Sales order not found",
                    "The sales order was not found.",
                )
            if order.status == SalesOrderStatus.COMPLETED:
                items = repository.items(
                    organization_id=context.organization_id, sales_order_id=order.id
                )
                unit_of_work.commit()
                return order_response(context, order, items)
            if order.version != int(str(data["expected_version"])):
                raise ApiProblem(
                    409,
                    "VERSION_CONFLICT",
                    "Version conflict",
                    "The sales order changed; reload it before completing.",
                )
            if order.status != SalesOrderStatus.SHIPPED:
                raise ApiProblem(
                    409,
                    "ORDER_NOT_SHIPPED",
                    "Order not shipped",
                    "The order must be fully shipped before completion.",
                )
            items = repository.items(
                organization_id=context.organization_id, sales_order_id=order.id
            )
            item_ids = {item.id for item in items}
            delivered_rows = session.execute(
                select(ShipmentItem.sales_order_item_id, func.sum(ShipmentItem.quantity))
                .join(
                    Shipment,
                    (Shipment.organization_id == ShipmentItem.organization_id)
                    & (Shipment.id == ShipmentItem.shipment_id),
                )
                .where(
                    ShipmentItem.organization_id == context.organization_id,
                    ShipmentItem.sales_order_item_id.in_(item_ids),
                    ShipmentItem.deleted_at.is_(None),
                    Shipment.deleted_at.is_(None),
                    Shipment.status == ShipmentStatus.DELIVERED,
                )
                .group_by(ShipmentItem.sales_order_item_id)
            ).all()
            delivered = {item_id: Decimal(str(quantity)) for item_id, quantity in delivered_rows}
            if any(delivered.get(item.id, Decimal("0")) != item.quantity for item in items):
                raise ApiProblem(
                    409,
                    "ORDER_NOT_DELIVERED",
                    "Order not delivered",
                    "Every order line must be fully delivered before completion.",
                )
            shipment_ids = set(
                session.scalars(
                    select(ShipmentItem.shipment_id)
                    .where(
                        ShipmentItem.organization_id == context.organization_id,
                        ShipmentItem.sales_order_item_id.in_(item_ids),
                        ShipmentItem.deleted_at.is_(None),
                    )
                    .distinct()
                )
            )
            if any(
                missing_required_documents(
                    session,
                    organization_id=context.organization_id,
                    shipment_id=shipment_id,
                )
                for shipment_id in shipment_ids
            ):
                raise ApiProblem(
                    409,
                    "ORDER_DOCUMENTS_INCOMPLETE",
                    "Order documents incomplete",
                    "Every shipment must retain its required available documents.",
                )
            receivable_repository = ReceivableRepository(session)
            receivables = receivable_repository.locked_for_order(
                organization_id=context.organization_id,
                sales_order_id=order.id,
            )
            if sum((item.amount for item in receivables), Decimal("0")) != order.total:
                raise ApiProblem(
                    409,
                    "RECEIVABLES_NOT_GENERATED",
                    "Receivables not generated",
                    "Receivables must cover the full order total before completion.",
                )
            totals = receivable_repository.allocated_totals(
                organization_id=context.organization_id,
                receivable_ids={item.id for item in receivables},
            )
            unpaid = [
                item for item in receivables if totals.get(item.id, Decimal("0")) < item.amount
            ]
            waiver_reason = data.get("financial_waiver_reason")
            if unpaid and not waiver_reason:
                raise ApiProblem(
                    409,
                    "ORDER_RECEIVABLES_UNPAID",
                    "Order receivables unpaid",
                    "All receivables must be paid or explicitly waived by an authorized manager.",
                )
            if unpaid:
                context.require(Permission.ORDER_FINANCE_WAIVE)
            blocking_tasks = session.scalar(
                select(func.count())
                .select_from(Task)
                .where(
                    Task.organization_id == context.organization_id,
                    Task.subject_type == "sales_order",
                    Task.subject_id == order.id,
                    Task.status.in_(["OPEN", "IN_PROGRESS"]),
                    Task.deleted_at.is_(None),
                )
            )
            if blocking_tasks:
                raise ApiProblem(
                    409,
                    "ORDER_HAS_BLOCKING_TASKS",
                    "Order has blocking tasks",
                    "Resolve open order tasks before completion.",
                )
            previous = order.status
            order.status = SalesOrderStatus.COMPLETED
            order.updated_by = context.user_id
            session.add(
                Activity(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    subject_type="sales_order",
                    subject_id=order.id,
                    activity_type="sales_order.completed",
                    summary=f"Sales order {order.order_number} completed",
                    details={"financial_waiver": bool(unpaid)},
                    correlation_id=context.request_id,
                )
            )
            self._audit_recorder.record(
                session,
                context,
                action="sales_order.completed",
                target_type="sales_order",
                target_id=order.id,
                before={"status": previous},
                after={"status": order.status, "financial_waiver": bool(unpaid)},
                reason=str(waiver_reason) if waiver_reason else None,
            )
            self._outbox_recorder.record(
                session,
                context,
                DomainEvent(
                    "sales_order.completed.v1",
                    "sales_order",
                    order.id,
                    {"sales_order_id": str(order.id), "order_number": order.order_number},
                ),
            )
            session.flush()
            unit_of_work.commit()
            return order_response(context, order, items)
