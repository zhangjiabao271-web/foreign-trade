from collections.abc import Collection, Sequence
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.auth.errors import ApiProblem
from app.core.repositories import TenantRepository
from app.fulfillment.models import Shipment, ShipmentItem


class ShipmentRepository(TenantRepository[Shipment]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Shipment)

    def get_for_update(self, *, organization_id: UUID, shipment_id: UUID) -> Shipment | None:
        return self.session.scalar(
            self._select_for_organization(organization_id)
            .where(Shipment.id == shipment_id)
            .with_for_update()
        )

    def list_recent(
        self, *, organization_id: UUID, limit: int, cursor: UUID | None = None
    ) -> Sequence[Shipment]:
        statement = self._select_for_organization(organization_id)
        if cursor is not None:
            anchor = self.get(organization_id=organization_id, record_id=cursor)
            if anchor is None:
                raise ApiProblem(
                    404,
                    "SHIPMENT_NOT_FOUND",
                    "Shipment not found",
                    "The cursor shipment is unavailable. Restart the list.",
                )
            statement = statement.where(
                tuple_(Shipment.created_at, Shipment.id) < (anchor.created_at, anchor.id)
            )
        return self.session.scalars(
            statement.order_by(Shipment.created_at.desc(), Shipment.id.desc()).limit(limit)
        ).all()

    def items(self, *, organization_id: UUID, shipment_id: UUID) -> Sequence[ShipmentItem]:
        return self.session.scalars(
            select(ShipmentItem)
            .where(
                ShipmentItem.organization_id == organization_id,
                ShipmentItem.shipment_id == shipment_id,
                ShipmentItem.deleted_at.is_(None),
            )
            .order_by(ShipmentItem.created_at, ShipmentItem.id)
        ).all()

    def items_for_shipments(
        self, *, organization_id: UUID, shipment_ids: Sequence[UUID]
    ) -> dict[UUID, list[ShipmentItem]]:
        grouped: dict[UUID, list[ShipmentItem]] = {shipment_id: [] for shipment_id in shipment_ids}
        if not shipment_ids:
            return grouped
        rows = self.session.scalars(
            select(ShipmentItem)
            .where(
                ShipmentItem.organization_id == organization_id,
                ShipmentItem.shipment_id.in_(shipment_ids),
                ShipmentItem.deleted_at.is_(None),
            )
            .order_by(ShipmentItem.shipment_id, ShipmentItem.created_at, ShipmentItem.id)
        )
        for item in rows:
            grouped[item.shipment_id].append(item)
        return grouped

    def locked_items(
        self, *, organization_id: UUID, shipment_id: UUID, item_ids: Collection[UUID]
    ) -> Sequence[ShipmentItem]:
        return self.session.scalars(
            select(ShipmentItem)
            .where(
                ShipmentItem.organization_id == organization_id,
                ShipmentItem.shipment_id == shipment_id,
                ShipmentItem.id.in_(item_ids),
                ShipmentItem.deleted_at.is_(None),
            )
            .with_for_update()
        ).all()
