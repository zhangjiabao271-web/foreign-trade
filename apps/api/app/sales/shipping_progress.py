from collections.abc import Collection
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.fulfillment.order_queries import milestone_quantities
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.sales.models import SalesOrder, SalesOrderItem
from app.sales.order_enums import SalesOrderStatus
from app.work.records import record_activity


def refresh_shipping_progress(
    session: Session,
    context: RequestContext,
    *,
    source_item_ids: Collection[UUID],
    departed: bool,
    audit_recorder: AuditRecorder,
    outbox_recorder: OutboxRecorder,
) -> None:
    """Sales-owned command port; caller owns the shipment transaction.

    Fulfillment supplies source IDs, not a requested order status or mutable ORM
    objects. Re-read persisted quantities through its public read port.
    """
    context.require(Permission.SHIPMENT_TRANSITION)
    order_ids = select(SalesOrderItem.sales_order_id).where(
        SalesOrderItem.organization_id == context.organization_id,
        SalesOrderItem.id.in_(source_item_ids),
        SalesOrderItem.deleted_at.is_(None),
    )
    orders = list(
        session.scalars(
            select(SalesOrder)
            .where(
                SalesOrder.organization_id == context.organization_id,
                SalesOrder.id.in_(order_ids),
                SalesOrder.deleted_at.is_(None),
            )
            .order_by(SalesOrder.id)
            .with_for_update()
        )
    )
    items = list(
        session.scalars(
            select(SalesOrderItem).where(
                SalesOrderItem.organization_id == context.organization_id,
                SalesOrderItem.sales_order_id.in_([order.id for order in orders]),
                SalesOrderItem.deleted_at.is_(None),
            )
        )
    )
    quantities = milestone_quantities(
        session,
        organization_id=context.organization_id,
        sales_order_item_ids=[item.id for item in items],
        departed=departed,
    )
    by_order: dict[UUID, list[SalesOrderItem]] = {}
    for item in items:
        by_order.setdefault(item.sales_order_id, []).append(item)
    target = SalesOrderStatus.SHIPPED if departed else SalesOrderStatus.READY_TO_SHIP
    for order in orders:
        if order.status not in {SalesOrderStatus.EXECUTING, SalesOrderStatus.READY_TO_SHIP}:
            continue
        order_items = by_order.get(order.id, [])
        complete = bool(order_items) and all(
            quantities.get(item.id, Decimal(0)) >= item.quantity for item in order_items
        )
        if not complete or order.status == target:
            continue
        before = order.status
        order.status = target
        order.updated_by = context.user_id
        action = f"sales_order.{target.value.lower()}"
        record_activity(
            session,
            context,
            subject_type="sales_order",
            subject_id=order.id,
            activity_type=action,
            summary=f"Sales order {order.order_number} reached {target.value}",
            details={"status": target},
        )
        audit_recorder.record(
            session,
            context,
            action=action,
            target_type="sales_order",
            target_id=order.id,
            before={"status": before},
            after={"status": target},
        )
        outbox_recorder.record(
            session,
            context,
            DomainEvent(
                f"{action}.v1",
                "sales_order",
                order.id,
                {"sales_order_id": str(order.id), "status": target},
            ),
        )
