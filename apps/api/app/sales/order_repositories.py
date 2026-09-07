from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.auth.errors import ApiProblem
from app.core.repositories import TenantRepository
from app.sales.models import SalesOrder, SalesOrderItem


class SalesOrderRepository(TenantRepository[SalesOrder]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, SalesOrder)

    def get_by_quotation(self, *, organization_id: UUID, quotation_id: UUID) -> SalesOrder | None:
        return self.session.scalar(
            self._select_for_organization(organization_id).where(
                SalesOrder.quotation_id == quotation_id
            )
        )

    def get_for_update(self, *, organization_id: UUID, sales_order_id: UUID) -> SalesOrder | None:
        return self.session.scalar(
            self._select_for_organization(organization_id)
            .where(SalesOrder.id == sales_order_id)
            .with_for_update()
        )

    def list_recent(
        self, *, organization_id: UUID, limit: int, cursor: UUID | None = None
    ) -> Sequence[SalesOrder]:
        statement = self._select_for_organization(organization_id)
        if cursor is not None:
            anchor = self.get(organization_id=organization_id, record_id=cursor)
            if anchor is None:
                raise ApiProblem(
                    404,
                    "SALES_ORDER_NOT_FOUND",
                    "Sales order not found",
                    "The cursor order is unavailable. Restart the order list.",
                )
            statement = statement.where(
                tuple_(SalesOrder.created_at, SalesOrder.id) < (anchor.created_at, anchor.id)
            )
        return self.session.scalars(
            statement.order_by(SalesOrder.created_at.desc(), SalesOrder.id.desc()).limit(limit)
        ).all()

    def items(self, *, organization_id: UUID, sales_order_id: UUID) -> Sequence[SalesOrderItem]:
        return self.session.scalars(
            select(SalesOrderItem)
            .where(
                SalesOrderItem.organization_id == organization_id,
                SalesOrderItem.sales_order_id == sales_order_id,
                SalesOrderItem.deleted_at.is_(None),
            )
            .order_by(SalesOrderItem.line_number)
        ).all()

    def items_for_orders(
        self, *, organization_id: UUID, sales_order_ids: Sequence[UUID]
    ) -> dict[UUID, list[SalesOrderItem]]:
        grouped: dict[UUID, list[SalesOrderItem]] = {
            sales_order_id: [] for sales_order_id in sales_order_ids
        }
        if not sales_order_ids:
            return grouped
        rows = self.session.scalars(
            select(SalesOrderItem)
            .where(
                SalesOrderItem.organization_id == organization_id,
                SalesOrderItem.sales_order_id.in_(sales_order_ids),
                SalesOrderItem.deleted_at.is_(None),
            )
            .order_by(SalesOrderItem.sales_order_id, SalesOrderItem.line_number)
        )
        for item in rows:
            grouped[item.sales_order_id].append(item)
        return grouped

    def source_lines(
        self, *, organization_id: UUID, item_ids: Sequence[UUID]
    ) -> list[tuple[SalesOrderItem, SalesOrder]]:
        if not item_ids:
            return []
        rows = self.session.execute(
            select(SalesOrderItem, SalesOrder)
            .join(
                SalesOrder,
                (SalesOrder.organization_id == SalesOrderItem.organization_id)
                & (SalesOrder.id == SalesOrderItem.sales_order_id),
            )
            .where(
                SalesOrderItem.organization_id == organization_id,
                SalesOrder.organization_id == organization_id,
                SalesOrderItem.id.in_(item_ids),
                SalesOrderItem.deleted_at.is_(None),
                SalesOrder.deleted_at.is_(None),
            )
            .order_by(SalesOrder.id, SalesOrderItem.line_number, SalesOrderItem.id)
        )
        return [(item, order) for item, order in rows]

    def locked_items(
        self, *, organization_id: UUID, sales_order_id: UUID, item_ids: set[UUID]
    ) -> Sequence[SalesOrderItem]:
        return self.session.scalars(
            select(SalesOrderItem)
            .where(
                SalesOrderItem.organization_id == organization_id,
                SalesOrderItem.sales_order_id == sales_order_id,
                SalesOrderItem.id.in_(item_ids),
                SalesOrderItem.deleted_at.is_(None),
            )
            .with_for_update()
        ).all()
