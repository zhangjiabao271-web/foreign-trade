from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.auth.errors import ApiProblem
from app.core.repositories import TenantRepository
from app.procurement.models import PurchaseOrder, PurchaseOrderItem
from app.work.models import Activity


class PurchaseOrderRepository(TenantRepository[PurchaseOrder]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, PurchaseOrder)

    def activities(
        self, *, organization_id: UUID, purchase_order_id: UUID, offset: int, limit: int
    ) -> Sequence[Activity]:
        return self.session.scalars(
            select(Activity)
            .where(
                Activity.organization_id == organization_id,
                Activity.subject_type == "purchase_order",
                Activity.subject_id == purchase_order_id,
                Activity.deleted_at.is_(None),
            )
            .order_by(Activity.occurred_at.desc(), Activity.id)
            .offset(offset)
            .limit(limit)
        ).all()

    def get_for_update(
        self, *, organization_id: UUID, purchase_order_id: UUID
    ) -> PurchaseOrder | None:
        return self.session.scalar(
            self._select_for_organization(organization_id)
            .where(PurchaseOrder.id == purchase_order_id)
            .with_for_update()
        )

    def list_recent(
        self,
        *,
        organization_id: UUID,
        limit: int,
        cursor: UUID | None = None,
        sales_order_id: UUID | None = None,
    ) -> Sequence[PurchaseOrder]:
        statement = self._select_for_organization(organization_id)
        if sales_order_id is not None:
            statement = statement.where(PurchaseOrder.sales_order_id == sales_order_id)
        if cursor is not None:
            anchor = self.get(organization_id=organization_id, record_id=cursor)
            if anchor is None or (
                sales_order_id is not None and anchor.sales_order_id != sales_order_id
            ):
                raise ApiProblem(
                    404,
                    "PURCHASE_ORDER_NOT_FOUND",
                    "Purchase order not found",
                    "The cursor purchase is unavailable. Restart the list.",
                )
            statement = statement.where(
                tuple_(PurchaseOrder.created_at, PurchaseOrder.id) < (anchor.created_at, anchor.id)
            )
        return self.session.scalars(
            statement.order_by(PurchaseOrder.created_at.desc(), PurchaseOrder.id.desc()).limit(
                limit
            )
        ).all()

    def items_for_orders(
        self, *, organization_id: UUID, purchase_order_ids: Sequence[UUID]
    ) -> dict[UUID, list[PurchaseOrderItem]]:
        grouped: dict[UUID, list[PurchaseOrderItem]] = {
            order_id: [] for order_id in purchase_order_ids
        }
        if not purchase_order_ids:
            return grouped
        rows = self.session.scalars(
            select(PurchaseOrderItem)
            .where(
                PurchaseOrderItem.organization_id == organization_id,
                PurchaseOrderItem.purchase_order_id.in_(purchase_order_ids),
                PurchaseOrderItem.deleted_at.is_(None),
            )
            .order_by(PurchaseOrderItem.purchase_order_id, PurchaseOrderItem.line_number)
        )
        for item in rows:
            grouped[item.purchase_order_id].append(item)
        return grouped

    def items(
        self, *, organization_id: UUID, purchase_order_id: UUID
    ) -> Sequence[PurchaseOrderItem]:
        return self.session.scalars(
            select(PurchaseOrderItem)
            .where(
                PurchaseOrderItem.organization_id == organization_id,
                PurchaseOrderItem.purchase_order_id == purchase_order_id,
                PurchaseOrderItem.deleted_at.is_(None),
            )
            .order_by(PurchaseOrderItem.line_number)
        ).all()
