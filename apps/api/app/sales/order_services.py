from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.unit_of_work import UnitOfWork
from app.platform.idempotency import begin_command, complete_command
from app.platform.numbering import next_document_number
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.sales.enums import QuotationVersionStatus
from app.sales.models import (
    Quotation,
    QuotationItem,
    QuotationVersion,
    SalesOrder,
    SalesOrderItem,
)
from app.sales.order_enums import SalesOrderStatus
from app.sales.order_projections import order_response
from app.sales.order_repositories import SalesOrderRepository
from app.sales.order_schemas import (
    SalesOrderConfirm,
    SalesOrderCreate,
    SalesOrderResponse,
    SalesOrderSourceLineResponse,
)
from app.sales.services import quantize_money
from app.work.models import Activity, Task


def sales_order_not_found() -> ApiProblem:
    return ApiProblem(
        404, "SALES_ORDER_NOT_FOUND", "Sales order not found", "The sales order was not found."
    )


class SalesOrderQueryService:
    def __init__(self, repository: SalesOrderRepository) -> None:
        self._repository = repository

    def list(
        self, context: RequestContext, *, limit: int, cursor: UUID | None = None
    ) -> Sequence[SalesOrderResponse]:
        context.require(Permission.ORDER_READ)
        orders = self._repository.list_recent(
            organization_id=context.organization_id, limit=limit, cursor=cursor
        )
        items = self._repository.items_for_orders(
            organization_id=context.organization_id, sales_order_ids=[order.id for order in orders]
        )
        return [order_response(context, order, items[order.id]) for order in orders]

    def source_lines(
        self, context: RequestContext, item_ids: Sequence[UUID]
    ) -> Sequence[SalesOrderSourceLineResponse]:
        context.require(Permission.ORDER_READ)
        if len(item_ids) > 200:
            raise ApiProblem(
                422, "SOURCE_LIMIT_EXCEEDED", "Too many source lines", "At most 200 lines."
            )
        sources = self._repository.source_lines(
            organization_id=context.organization_id, item_ids=item_ids
        )
        if {item.id for item, _ in sources} != set(item_ids):
            raise sales_order_not_found()
        orders = {order.id: order for _, order in sources}
        # Disclosure binds every source-order line, not just this shipment's subset.
        items = self._repository.items_for_orders(
            organization_id=context.organization_id, sales_order_ids=list(orders)
        )
        projected = {
            order_id: order_response(context, order, items[order_id])
            for order_id, order in orders.items()
        }
        visible_lines = {item.id: item for order in projected.values() for item in order.items}
        return [
            SalesOrderSourceLineResponse(
                id=item.id,
                sales_order_id=order.id,
                order_number=order.order_number,
                order_status=SalesOrderStatus(order.status),
                sku_snapshot=item.sku_snapshot,
                description_snapshot=visible_lines[item.id].description_snapshot,
                unit_snapshot=item.unit_snapshot,
            )
            for item, order in sources
        ]

    def get(self, context: RequestContext, sales_order_id: UUID) -> SalesOrderResponse:
        context.require(Permission.ORDER_READ)
        order = self._repository.get(
            organization_id=context.organization_id, record_id=sales_order_id
        )
        if order is None:
            raise sales_order_not_found()
        items = self._repository.items(
            organization_id=context.organization_id, sales_order_id=order.id
        )
        return order_response(context, order, items)


class SalesOrderCommandService:
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

    def create(
        self, context: RequestContext, data: dict[str, object], *, key: str | None = None
    ) -> SalesOrderResponse:
        context.require(Permission.ORDER_WRITE)
        request = SalesOrderCreate.model_validate(dict(data))
        request.deposit_rate = quantize_money(request.deposit_rate)
        quotation_id = request.quotation_id
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            repository = SalesOrderRepository(session)
            command = begin_command(
                session,
                context,
                scope="sales_order.create",
                key=key if key is not None else str(uuid4()),
                payload=request.model_dump(),
            )
            if command.resource_id is not None:
                original = repository.get_for_update(
                    organization_id=context.organization_id, sales_order_id=command.resource_id
                )
                if original is None:
                    raise sales_order_not_found()
                items = repository.items(
                    organization_id=context.organization_id, sales_order_id=original.id
                )
                result = order_response(context, original, items)
                unit_of_work.commit()
                return result
            # Check the tenant-owned source before flushing a newly staged receipt.
            with session.no_autoflush:
                quotation = session.scalar(
                    select(Quotation)
                    .where(
                        Quotation.organization_id == context.organization_id,
                        Quotation.id == quotation_id,
                        Quotation.deleted_at.is_(None),
                    )
                    .with_for_update()
                )
            if quotation is None:
                raise ApiProblem(
                    404,
                    "QUOTATION_NOT_FOUND",
                    "Quotation not found",
                    "The quotation was not found.",
                )
            existing = repository.get_by_quotation(
                organization_id=context.organization_id, quotation_id=quotation.id
            )
            if existing is not None:
                if (
                    existing.deposit_rate != request.deposit_rate
                    or existing.deposit_due_date != request.deposit_due_date
                ):
                    raise ApiProblem(
                        409,
                        "ORDER_CREATION_CONFLICT",
                        "Order already exists with different deposit terms",
                        "该报价已生成订单，定金条件与本次输入不同。请打开原订单核对；重复建单不会修改原订单。",
                    )
                items = repository.items(
                    organization_id=context.organization_id, sales_order_id=existing.id
                )
                complete_command(command, existing.id, "sales_order")
                unit_of_work.commit()
                return order_response(context, existing, items)
            if quotation.accepted_version_id is None:
                raise ApiProblem(
                    409,
                    "QUOTATION_NOT_ACCEPTED",
                    "Quotation not accepted",
                    "Only an accepted quotation can create a sales order.",
                )
            version = session.scalar(
                select(QuotationVersion).where(
                    QuotationVersion.organization_id == context.organization_id,
                    QuotationVersion.quotation_id == quotation.id,
                    QuotationVersion.id == quotation.accepted_version_id,
                    QuotationVersion.status == QuotationVersionStatus.ACCEPTED,
                    QuotationVersion.deleted_at.is_(None),
                )
            )
            if version is None:
                raise RuntimeError("Quotation invariant violated: accepted version is missing")
            quotation_items = session.scalars(
                select(QuotationItem)
                .where(
                    QuotationItem.organization_id == context.organization_id,
                    QuotationItem.quotation_version_id == version.id,
                    QuotationItem.deleted_at.is_(None),
                )
                .order_by(QuotationItem.line_number)
            ).all()
            if not quotation_items:
                raise RuntimeError("Quotation invariant violated: accepted version has no items")

            deposit_rate = request.deposit_rate
            order = SalesOrder(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                order_number=self._next_number(session, context),
                quotation_id=quotation.id,
                quotation_version_id=version.id,
                opportunity_id=quotation.opportunity_id,
                company_id=quotation.company_id,
                currency_code=version.currency_code,
                base_currency_code=version.base_currency_code,
                exchange_rate=version.exchange_rate,
                payment_terms=version.payment_terms,
                delivery_terms=version.delivery_terms,
                subtotal=version.subtotal,
                tax_amount=version.tax_amount,
                freight_amount=version.freight_amount,
                total=version.total,
                total_cost=version.total_cost,
                gross_profit=version.gross_profit,
                gross_margin=version.gross_margin,
                deposit_rate=deposit_rate,
                deposit_amount=quantize_money(version.total * deposit_rate),
                deposit_due_date=request.deposit_due_date,
            )
            session.add(order)
            session.flush()
            items = [self._copy_item(session, context, order.id, item) for item in quotation_items]
            self._record_command(
                session,
                context,
                order,
                action="sales_order.created",
                summary=f"Sales order {order.order_number} created from accepted quotation",
                before=None,
                after={
                    "status": order.status,
                    "quotation_version_id": str(version.id),
                    "deposit_amount": str(order.deposit_amount),
                },
            )
            complete_command(command, order.id, "sales_order")
            unit_of_work.commit()
            return order_response(context, order, items)

    def confirm(
        self, context: RequestContext, sales_order_id: UUID, request: SalesOrderConfirm, *, key: str
    ) -> SalesOrderResponse:
        context.require(Permission.ORDER_CONFIRM)
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            repository = SalesOrderRepository(session)
            order = repository.get_for_update(
                organization_id=context.organization_id, sales_order_id=sales_order_id
            )
            if order is None:
                raise sales_order_not_found()
            command = begin_command(
                session,
                context,
                scope="sales_order.confirmed",
                key=key,
                payload={"sales_order_id": str(sales_order_id), **request.model_dump()},
            )
            if command.resource_id is not None:
                items = repository.items(
                    organization_id=context.organization_id, sales_order_id=order.id
                )
                result = order_response(context, order, items)
                unit_of_work.commit()
                return result
            if order.version != request.expected_version:
                raise ApiProblem(
                    409,
                    "VERSION_CONFLICT",
                    "Version conflict",
                    "Reload and review the current order.",
                )
            if order.confirmed_at is not None and order.status in {
                SalesOrderStatus.DEPOSIT_PENDING,
                SalesOrderStatus.EXECUTING,
            }:
                items = repository.items(
                    organization_id=context.organization_id, sales_order_id=order.id
                )
                complete_command(command, order.id, "sales_order")
                unit_of_work.commit()
                return order_response(context, order, items)
            if order.status != SalesOrderStatus.DRAFT:
                raise ApiProblem(
                    409,
                    "INVALID_STATE_TRANSITION",
                    "Invalid state transition",
                    "Only a draft sales order can be confirmed.",
                )
            now = datetime.now(UTC)
            target = (
                SalesOrderStatus.DEPOSIT_PENDING
                if order.deposit_amount > 0
                else SalesOrderStatus.EXECUTING
            )
            order.status = target
            order.confirmed_at = now
            order.updated_by = context.user_id
            session.add(
                Task(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    task_type="PROCUREMENT_PREPARATION",
                    subject_type="sales_order",
                    subject_id=order.id,
                    title=f"Prepare procurement for {order.order_number}",
                    priority="HIGH",
                    due_at=now + timedelta(days=2),
                    details={
                        "order_number": order.order_number,
                        "deposit_pending": target == SalesOrderStatus.DEPOSIT_PENDING,
                    },
                )
            )
            self._record_command(
                session,
                context,
                order,
                action="sales_order.confirmed",
                summary=f"Sales order {order.order_number} confirmed; procurement task opened",
                before={"status": SalesOrderStatus.DRAFT},
                after={"status": target, "confirmed_at": now.isoformat()},
            )
            items = repository.items(
                organization_id=context.organization_id, sales_order_id=order.id
            )
            complete_command(command, order.id, "sales_order")
            unit_of_work.commit()
            return order_response(context, order, items)

    @staticmethod
    def _copy_item(
        session: Session, context: RequestContext, order_id: UUID, source: QuotationItem
    ) -> SalesOrderItem:
        item = SalesOrderItem(
            organization_id=context.organization_id,
            created_by=context.user_id,
            updated_by=context.user_id,
            sales_order_id=order_id,
            quotation_item_id=source.id,
            line_number=source.line_number,
            product_id=source.product_id,
            sku_snapshot=source.sku_snapshot,
            description_snapshot=source.description_snapshot,
            unit_snapshot=source.unit_snapshot,
            quantity=source.quantity,
            unit_price=source.unit_price,
            unit_cost=source.unit_cost,
            cost_currency=source.cost_currency,
            cost_exchange_rate=source.cost_exchange_rate,
            tax_amount=source.tax_amount,
            freight_amount=source.freight_amount,
            allocated_cost=source.allocated_cost,
            line_subtotal=source.line_subtotal,
            line_total=source.line_total,
            line_cost=source.line_cost,
            line_gross_profit=source.line_gross_profit,
        )
        session.add(item)
        return item

    @staticmethod
    def _next_number(session: Session, context: RequestContext) -> str:
        return next_document_number(session, context, "SALES_ORDER", "SO")

    def _record_command(
        self,
        session: Session,
        context: RequestContext,
        order: SalesOrder,
        *,
        action: str,
        summary: str,
        before: dict[str, object] | None,
        after: dict[str, object],
    ) -> None:
        session.add(
            Activity(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                subject_type="sales_order",
                subject_id=order.id,
                activity_type=action,
                summary=summary,
                details={"order_number": order.order_number},
                correlation_id=context.request_id,
            )
        )
        self._audit_recorder.record(
            session,
            context,
            action=action,
            target_type="sales_order",
            target_id=order.id,
            before=before,
            after=after,
        )
        self._outbox_recorder.record(
            session,
            context,
            DomainEvent(
                f"{action}.v1",
                "sales_order",
                order.id,
                {"sales_order_id": str(order.id), "order_number": order.order_number},
            ),
        )
        session.flush()
