from collections.abc import Collection
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.fulfillment.enums import ShipmentStatus
from app.fulfillment.models import Shipment, ShipmentItem


def milestone_quantities(
    session: Session,
    *,
    organization_id: UUID,
    sales_order_item_ids: Collection[UUID],
    departed: bool,
) -> dict[UUID, Decimal]:
    """Public read port: aggregate execution facts, never mutate an order."""
    eligible = {
        ShipmentStatus.DEPARTED,
        ShipmentStatus.IN_TRANSIT,
        ShipmentStatus.ARRIVED,
        ShipmentStatus.DELIVERED,
    }
    if not departed:
        eligible.update({ShipmentStatus.READY, ShipmentStatus.CUSTOMS})
    rows = session.execute(
        select(ShipmentItem.sales_order_item_id, func.sum(ShipmentItem.quantity))
        .join(
            Shipment,
            (Shipment.organization_id == ShipmentItem.organization_id)
            & (Shipment.id == ShipmentItem.shipment_id),
        )
        .where(
            ShipmentItem.organization_id == organization_id,
            ShipmentItem.sales_order_item_id.in_(sales_order_item_ids),
            Shipment.status.in_(eligible),
            ShipmentItem.deleted_at.is_(None),
            Shipment.deleted_at.is_(None),
        )
        .group_by(ShipmentItem.sales_order_item_id)
    )
    return {item_id: Decimal(quantity) for item_id, quantity in rows}
