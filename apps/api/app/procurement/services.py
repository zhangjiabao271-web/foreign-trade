from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.companies.enums import CompanyRoleType
from app.companies.models import Company, CompanyRole
from app.core.unit_of_work import UnitOfWork
from app.finance.services import organization_today
from app.platform.idempotency import begin_command, complete_command
from app.platform.models import IdempotencyKey
from app.platform.numbering import next_document_number
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.procurement.enums import PurchaseOrderStatus
from app.procurement.models import PurchaseOrder, PurchaseOrderItem
from app.procurement.projections import purchase_activity_response, purchase_order_response
from app.procurement.repositories import PurchaseOrderRepository
from app.procurement.schemas import (
    PurchaseOrderAmend,
    PurchaseOrderCancel,
    PurchaseOrderClose,
    PurchaseOrderConfirm,
    PurchaseOrderCreate,
    PurchaseOrderDecision,
    PurchaseOrderReceive,
    PurchaseOrderResponse,
)
from app.sales.models import SalesOrder
from app.sales.order_enums import SalesOrderStatus
from app.sales.order_repositories import SalesOrderRepository
from app.sales.services import quantize_money, quantize_rate
from app.work.records import record_activity
from app.work.schemas import ActivityResponse


def purchase_order_not_found() -> ApiProblem:
    return ApiProblem(
        404,
        "PURCHASE_ORDER_NOT_FOUND",
        "Purchase order not found",
        "The purchase order was not found.",
    )


class PurchaseOrderQueryService:
    def __init__(self, repository: PurchaseOrderRepository) -> None:
        self._repository = repository

    def activities(
        self, context: RequestContext, purchase_order_id: UUID, *, offset: int, limit: int
    ) -> Sequence[ActivityResponse]:
        context.require(Permission.PROCUREMENT_READ)
        if (
            self._repository.get(
                organization_id=context.organization_id, record_id=purchase_order_id
            )
            is None
        ):
            raise purchase_order_not_found()
        rows = self._repository.activities(
            organization_id=context.organization_id,
            purchase_order_id=purchase_order_id,
            offset=offset,
            limit=limit,
        )
        return [purchase_activity_response(context, row) for row in rows]

    def list(
        self,
        context: RequestContext,
        *,
        limit: int,
        cursor: UUID | None = None,
        sales_order_id: UUID | None = None,
    ) -> Sequence[PurchaseOrderResponse]:
        context.require(Permission.PROCUREMENT_READ)
        orders = self._repository.list_recent(
            organization_id=context.organization_id,
            limit=limit,
            cursor=cursor,
            sales_order_id=sales_order_id,
        )
        items = self._repository.items_for_orders(
            organization_id=context.organization_id,
            purchase_order_ids=[order.id for order in orders],
        )
        return [
            purchase_order_response(
                context,
                order,
                items[order.id],
            )
            for order in orders
        ]

    def get(self, context: RequestContext, purchase_order_id: UUID) -> PurchaseOrderResponse:
        context.require(Permission.PROCUREMENT_READ)
        order = self._repository.get(
            organization_id=context.organization_id, record_id=purchase_order_id
        )
        if order is None:
            raise purchase_order_not_found()
        items = self._repository.items(
            organization_id=context.organization_id, purchase_order_id=order.id
        )
        return purchase_order_response(context, order, items)


class PurchaseOrderCommandService:
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
        self, context: RequestContext, data: dict[str, object], *, idempotency_key: str
    ) -> PurchaseOrderResponse:
        context.require(Permission.PROCUREMENT_WRITE, Permission.PROFIT_READ)
        data = PurchaseOrderCreate.model_validate(data).model_dump()
        with UnitOfWork(self._session_factory) as uow:
            command = begin_command(
                uow.session,
                context,
                scope="purchase_order.create",
                key=idempotency_key,
                payload=data,
            )
            if command.resource_id is not None:
                repository = PurchaseOrderRepository(uow.session)
                order = repository.get(
                    organization_id=context.organization_id, record_id=command.resource_id
                )
                if order is None:
                    raise purchase_order_not_found()
                items = repository.items(
                    organization_id=context.organization_id, purchase_order_id=order.id
                )
                uow.commit()
                return purchase_order_response(context, order, items)
            result = self._create_draft(uow.session, context, data)
            complete_command(command, result[0].id, "purchase_order")
            uow.commit()
            return purchase_order_response(context, *result)

    def _create_draft(
        self,
        session: Session,
        context: RequestContext,
        data: dict[str, object],
        *,
        replaces_purchase_order_id: UUID | None = None,
    ) -> tuple[PurchaseOrder, Sequence[PurchaseOrderItem]]:
        sales_order_id = UUID(str(data["sales_order_id"]))
        supplier_id = UUID(str(data["supplier_company_id"]))
        raw_items = data["items"]
        if not isinstance(raw_items, list):
            raise TypeError("Purchase order items must be a list")
        item_ids = {UUID(str(item["sales_order_item_id"])) for item in raw_items}
        if len(item_ids) != len(raw_items):
            raise ApiProblem(
                409,
                "DUPLICATE_SALES_ORDER_ITEM",
                "Duplicate sales order item",
                "A sales order line can appear only once in a purchase order.",
            )

        sales_order = session.scalar(
            select(SalesOrder)
            .where(
                SalesOrder.organization_id == context.organization_id,
                SalesOrder.id == sales_order_id,
                SalesOrder.deleted_at.is_(None),
            )
            .with_for_update()
        )
        if sales_order is None:
            raise ApiProblem(
                404,
                "SALES_ORDER_NOT_FOUND",
                "Sales order not found",
                "The sales order was not found.",
            )
        if sales_order.status not in {
            SalesOrderStatus.CONFIRMED,
            SalesOrderStatus.DEPOSIT_PENDING,
            SalesOrderStatus.EXECUTING,
        }:
            raise ApiProblem(
                409,
                "INVALID_STATE_TRANSITION",
                "Invalid state transition",
                "Procurement requires a confirmed sales order.",
            )
        supplier = session.scalar(
            select(Company).where(
                Company.organization_id == context.organization_id,
                Company.id == supplier_id,
                Company.deleted_at.is_(None),
            )
        )
        if supplier is None:
            raise ApiProblem(
                404,
                "SUPPLIER_NOT_FOUND",
                "Supplier not found",
                "The supplier company was not found.",
            )
        supplier_role = session.scalar(
            select(CompanyRole).where(
                CompanyRole.organization_id == context.organization_id,
                CompanyRole.company_id == supplier_id,
                CompanyRole.role == CompanyRoleType.SUPPLIER,
                CompanyRole.deleted_at.is_(None),
            )
        )
        if supplier_role is None:
            raise ApiProblem(
                409,
                "SUPPLIER_ROLE_REQUIRED",
                "Supplier role required",
                "The selected company must have the SUPPLIER role.",
            )
        sales_items = SalesOrderRepository(session).locked_items(
            organization_id=context.organization_id,
            sales_order_id=sales_order.id,
            item_ids=item_ids,
        )
        if {item.id for item in sales_items} != item_ids:
            raise ApiProblem(
                404,
                "SALES_ORDER_ITEM_NOT_FOUND",
                "Sales order item not found",
                "One or more sales order lines were not found.",
            )
        sales_item_by_id = {item.id: item for item in sales_items}
        currency_code = str(data["currency_code"]).upper()
        exchange_rate = quantize_rate(Decimal(str(data["exchange_rate"])))
        purchase_order = PurchaseOrder(
            organization_id=context.organization_id,
            created_by=context.user_id,
            updated_by=context.user_id,
            purchase_order_number=next_document_number(session, context, "PURCHASE_ORDER", "PO"),
            sales_order_id=sales_order.id,
            supplier_company_id=supplier_id,
            currency_code=currency_code,
            exchange_rate=exchange_rate,
            total=Decimal("0"),
            total_order_currency=Decimal("0"),
            replaces_purchase_order_id=replaces_purchase_order_id,
        )
        session.add(purchase_order)
        session.flush()

        items: list[PurchaseOrderItem] = []
        for line_number, raw_item in enumerate(raw_items, start=1):
            sales_item_id = UUID(str(raw_item["sales_order_item_id"]))
            sales_item = sales_item_by_id[sales_item_id]
            quantity = quantize_money(Decimal(str(raw_item["quantity"])))
            committed = self._committed_quantity(session, context.organization_id, sales_item_id)
            if committed + quantity > sales_item.quantity:
                raise ApiProblem(
                    409,
                    "PURCHASE_QUANTITY_EXCEEDED",
                    "Purchase quantity exceeded",
                    "Cumulative purchase quantity cannot exceed the sales order line.",
                )
            unit_cost = quantize_money(Decimal(str(raw_item["unit_cost"])))
            item = PurchaseOrderItem(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                purchase_order_id=purchase_order.id,
                sales_order_item_id=sales_item.id,
                line_number=line_number,
                sku_snapshot=sales_item.sku_snapshot,
                description_snapshot=sales_item.description_snapshot,
                unit_snapshot=sales_item.unit_snapshot,
                quantity=quantity,
                unit_cost=unit_cost,
                line_total=quantize_money(quantity * unit_cost),
            )
            session.add(item)
            items.append(item)

        purchase_order.total = quantize_money(
            sum((item.line_total for item in items), Decimal("0"))
        )
        purchase_order.total_order_currency = quantize_money(purchase_order.total * exchange_rate)
        self._record_command(
            session,
            context,
            purchase_order,
            action="purchase_order.created",
            summary=f"Purchase order {purchase_order.purchase_order_number} drafted",
            before=None,
            after={
                "status": purchase_order.status,
                "total": str(purchase_order.total),
                "currency_code": currency_code,
                "replaces_purchase_order_id": str(replaces_purchase_order_id)
                if replaces_purchase_order_id
                else None,
            },
        )
        return purchase_order, items

    def cancel(
        self,
        context: RequestContext,
        purchase_order_id: UUID,
        data: dict[str, object],
        *,
        idempotency_key: str,
    ) -> PurchaseOrderResponse:
        context.require(Permission.PROCUREMENT_APPROVE, Permission.PROFIT_READ)
        return self._change(
            context,
            purchase_order_id,
            PurchaseOrderCancel.model_validate(data),
            idempotency_key=idempotency_key,
        )

    def amend(
        self,
        context: RequestContext,
        purchase_order_id: UUID,
        data: dict[str, object],
        *,
        idempotency_key: str,
    ) -> PurchaseOrderResponse:
        context.require(Permission.PROCUREMENT_APPROVE, Permission.PROFIT_READ)
        return self._change(
            context,
            purchase_order_id,
            PurchaseOrderAmend.model_validate(data),
            idempotency_key=idempotency_key,
        )

    def _change(
        self,
        context: RequestContext,
        purchase_order_id: UUID,
        request: PurchaseOrderCancel | PurchaseOrderAmend,
        *,
        idempotency_key: str,
    ) -> PurchaseOrderResponse:
        amendment = isinstance(request, PurchaseOrderAmend)
        with UnitOfWork(self._session_factory) as uow:
            session = uow.session
            command = begin_command(
                session,
                context,
                scope="purchase_order.amend" if amendment else "purchase_order.cancel",
                key=idempotency_key,
                payload={"purchase_order_id": str(purchase_order_id), **request.model_dump()},
            )
            repository = PurchaseOrderRepository(session)
            if command.resource_id is not None:
                order = repository.get(
                    organization_id=context.organization_id, record_id=command.resource_id
                )
                if order is None:
                    raise purchase_order_not_found()
                items = repository.items(
                    organization_id=context.organization_id, purchase_order_id=order.id
                )
                uow.commit()
                return purchase_order_response(context, order, items)
            sales_id = session.scalar(
                select(PurchaseOrder.sales_order_id).where(
                    PurchaseOrder.organization_id == context.organization_id,
                    PurchaseOrder.id == purchase_order_id,
                    PurchaseOrder.deleted_at.is_(None),
                )
            )
            if sales_id is None:
                raise purchase_order_not_found()
            sales = session.scalar(
                select(SalesOrder)
                .where(
                    SalesOrder.organization_id == context.organization_id,
                    SalesOrder.id == sales_id,
                    SalesOrder.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if sales is None or sales.status in {
                SalesOrderStatus.COMPLETED,
                SalesOrderStatus.CANCELLED,
            }:
                raise ApiProblem(
                    409,
                    "ORDER_FINALIZED",
                    "Order finalized",
                    "Finalized sales orders cannot change procurement.",
                )
            order = repository.get_for_update(
                organization_id=context.organization_id, purchase_order_id=purchase_order_id
            )
            if order is None:
                raise purchase_order_not_found()
            self._check_version(order, request.expected_version)
            items = repository.items(
                organization_id=context.organization_id, purchase_order_id=order.id
            )
            self._cancel_remaining(session, context, order, items, request)
            result = (order, items)
            if isinstance(request, PurchaseOrderAmend):
                if request.replacement.sales_order_id != order.sales_order_id:
                    raise ApiProblem(
                        409,
                        "REPLACEMENT_ORDER_MISMATCH",
                        "Different sales order",
                        "A replacement must retain the original sales order.",
                    )
                result = self._create_draft(
                    session,
                    context,
                    request.replacement.model_dump(),
                    replaces_purchase_order_id=order.id,
                )
                self._record_command(
                    session,
                    context,
                    order,
                    action="purchase_order.replaced",
                    summary=f"采购变更生成 {result[0].purchase_order_number}：{request.reason}",
                    before={"purchase_order_id": str(order.id)},
                    after={"replacement_purchase_order_id": str(result[0].id)},
                    reason=request.reason,
                )
            complete_command(command, result[0].id, "purchase_order")
            uow.commit()
            return purchase_order_response(context, *result)

    def _cancel_remaining(
        self,
        session: Session,
        context: RequestContext,
        order: PurchaseOrder,
        items: Sequence[PurchaseOrderItem],
        request: PurchaseOrderCancel,
    ) -> None:
        if order.status not in {
            PurchaseOrderStatus.DRAFT,
            PurchaseOrderStatus.APPROVED,
            PurchaseOrderStatus.SENT,
            PurchaseOrderStatus.CONFIRMED,
            PurchaseOrderStatus.PARTIALLY_RECEIVED,
        }:
            raise ApiProblem(
                409,
                "INVALID_STATE_TRANSITION",
                "Cannot cancel",
                "Only a purchase with an open commitment can be cancelled.",
            )
        if not any(item.received_quantity < item.quantity for item in items):
            raise ApiProblem(
                409,
                "NO_OPEN_PURCHASE_QUANTITY",
                "No remaining quantity",
                "There is no unreceived commitment to cancel.",
            )
        if (
            order.status
            in {
                PurchaseOrderStatus.SENT,
                PurchaseOrderStatus.CONFIRMED,
                PurchaseOrderStatus.PARTIALLY_RECEIVED,
            }
            and not request.supplier_reference
        ):
            raise ApiProblem(
                422,
                "SUPPLIER_CANCELLATION_REFERENCE_REQUIRED",
                "Reference required",
                "Record the supplier cancellation evidence reference.",
            )
        before = {"status": order.status, "version": order.version}
        order.status = PurchaseOrderStatus.CANCELLED
        order.cancelled_at = datetime.now(UTC)
        order.cancellation_reason = request.reason
        order.cancellation_reference = request.supplier_reference
        order.updated_by = context.user_id
        order.version += 1
        self._record_command(
            session,
            context,
            order,
            action="purchase_order.cancelled",
            summary=f"取消未收货采购承诺：{request.reason}",
            before=before,
            after={
                "status": order.status,
                "version": order.version,
                "supplier_reference": request.supplier_reference,
                "cancelled_quantities": {
                    str(item.id): str(item.quantity - item.received_quantity) for item in items
                },
                "retained_received_quantities": {
                    str(item.id): str(item.received_quantity) for item in items
                },
            },
            reason=request.reason,
        )

    def approve(
        self,
        context: RequestContext,
        purchase_order_id: UUID,
        request: PurchaseOrderDecision,
        *,
        idempotency_key: str,
    ) -> PurchaseOrderResponse:
        context.require(Permission.PROCUREMENT_APPROVE, Permission.PROFIT_READ)
        return self._transition(
            context,
            purchase_order_id,
            request=request,
            idempotency_key=idempotency_key,
            expected=PurchaseOrderStatus.DRAFT,
            target=PurchaseOrderStatus.APPROVED,
            action="purchase_order.approved",
            timestamp_field="approved_at",
            approver=True,
        )

    def send(
        self,
        context: RequestContext,
        purchase_order_id: UUID,
        request: PurchaseOrderDecision,
        *,
        idempotency_key: str,
    ) -> PurchaseOrderResponse:
        context.require(Permission.PROCUREMENT_WRITE)
        return self._transition(
            context,
            purchase_order_id,
            request=request,
            idempotency_key=idempotency_key,
            expected=PurchaseOrderStatus.APPROVED,
            target=PurchaseOrderStatus.SENT,
            action="purchase_order.sent",
            timestamp_field="sent_at",
        )

    def confirm(
        self,
        context: RequestContext,
        purchase_order_id: UUID,
        request: PurchaseOrderConfirm,
        *,
        idempotency_key: str,
    ) -> PurchaseOrderResponse:
        context.require(Permission.PROCUREMENT_WRITE)
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            repository = PurchaseOrderRepository(session)
            order, command = self._begin_decision(
                session,
                context,
                purchase_order_id,
                request,
                action="purchase_order.confirmed",
                key=idempotency_key,
            )
            if command.resource_id is not None or order.status == PurchaseOrderStatus.CONFIRMED:
                if command.resource_id is None and (
                    order.supplier_reference != request.supplier_reference
                    or order.expected_delivery_date != request.expected_delivery_date
                ):
                    raise ApiProblem(
                        409,
                        "SUPPLIER_CONFIRMATION_CONFLICT",
                        "Supplier confirmation conflict",
                        "已有供应商确认号或交期与本次输入不同。请核对原采购承诺；重复确认不能修改原记录。",
                    )
                items = repository.items(
                    organization_id=context.organization_id, purchase_order_id=order.id
                )
                complete_command(command, order.id, "purchase_order")
                unit_of_work.commit()
                return purchase_order_response(context, order, items)
            if order.status != PurchaseOrderStatus.SENT:
                raise ApiProblem(
                    409,
                    "INVALID_STATE_TRANSITION",
                    "Invalid state transition",
                    "Only a sent purchase order can be supplier-confirmed.",
                )
            now = datetime.now(UTC)
            order.status = PurchaseOrderStatus.CONFIRMED
            order.supplier_reference = request.supplier_reference
            order.expected_delivery_date = request.expected_delivery_date
            order.confirmed_at = now
            order.updated_by = context.user_id
            self._record_command(
                session,
                context,
                order,
                action="purchase_order.confirmed",
                summary=f"Supplier confirmed {order.purchase_order_number}",
                before={"status": PurchaseOrderStatus.SENT},
                after={
                    "status": PurchaseOrderStatus.CONFIRMED,
                    "expected_delivery_date": str(order.expected_delivery_date),
                    "supplier_reference": order.supplier_reference,
                },
            )
            items = repository.items(
                organization_id=context.organization_id, purchase_order_id=order.id
            )
            complete_command(command, order.id, "purchase_order")
            unit_of_work.commit()
            return purchase_order_response(context, order, items)

    def receive(
        self,
        context: RequestContext,
        purchase_order_id: UUID,
        data: dict[str, object],
        *,
        idempotency_key: str,
    ) -> PurchaseOrderResponse:
        context.require(Permission.PROCUREMENT_WRITE)
        request = PurchaseOrderReceive.model_validate(data)
        ids = [line.purchase_order_item_id for line in request.items]
        if len(ids) != len(set(ids)):
            raise ApiProblem(
                422, "DUPLICATE_RECEIPT_LINE", "Duplicate line", "Select each purchase line once."
            )
        with UnitOfWork(self._session_factory) as uow:
            session = uow.session
            if request.received_date > organization_today(session, context.organization_id):
                raise ApiProblem(
                    422,
                    "RECEIPT_DATE_IN_FUTURE",
                    "Invalid date",
                    "Receipt date cannot be in the future.",
                )
            command = begin_command(
                session,
                context,
                scope="purchase_order.receive",
                key=idempotency_key,
                payload={"purchase_order_id": str(purchase_order_id), **request.model_dump()},
            )
            repository = PurchaseOrderRepository(session)
            order = repository.get_for_update(
                organization_id=context.organization_id, purchase_order_id=purchase_order_id
            )
            if order is None:
                raise purchase_order_not_found()
            items = repository.items(
                organization_id=context.organization_id, purchase_order_id=order.id
            )
            if command.resource_id is not None:
                uow.commit()
                return purchase_order_response(context, order, items)
            self._check_version(order, request.expected_version)
            if order.status not in {
                PurchaseOrderStatus.CONFIRMED,
                PurchaseOrderStatus.PARTIALLY_RECEIVED,
            }:
                raise ApiProblem(
                    409,
                    "INVALID_STATE_TRANSITION",
                    "Invalid state",
                    "Only confirmed or partly received purchases accept receipts.",
                )
            by_id = {item.id: item for item in items}
            if not set(ids) <= by_id.keys():
                raise ApiProblem(
                    404,
                    "PURCHASE_ORDER_ITEM_NOT_FOUND",
                    "Line not found",
                    "A purchase line was not found.",
                )
            before = {
                "status": order.status,
                "version": order.version,
                "received_quantities": {
                    str(item.id): str(item.received_quantity) for item in items
                },
            }
            for line in request.items:
                item = by_id[line.purchase_order_item_id]
                if item.received_quantity + line.quantity > item.quantity:
                    raise ApiProblem(
                        409,
                        "RECEIPT_QUANTITY_EXCEEDED",
                        "Quantity exceeded",
                        "Receipt exceeds the unreceived purchase quantity.",
                    )
                item.received_quantity += line.quantity
                item.updated_by = context.user_id
            order.status = PurchaseOrderStatus.PARTIALLY_RECEIVED
            if all(item.received_quantity == item.quantity for item in items):
                order.status = PurchaseOrderStatus.RECEIVED
                order.received_at = datetime.now(UTC)
            order.updated_by = context.user_id
            order.version += 1
            after: dict[str, object] = {
                "status": order.status,
                "version": order.version,
                "received_date": str(request.received_date),
                "reference": request.reference,
                "received_quantities": {
                    str(item.id): str(item.received_quantity) for item in items
                },
                "receipt_items": request.model_dump(mode="json")["items"],
            }
            self._record_command(
                session,
                context,
                order,
                action="purchase_order.receipt_recorded",
                summary=f"收货 {request.received_date} · {request.reference}："
                + "；".join(
                    f"{by_id[line.purchase_order_item_id].sku_snapshot} "
                    f"{line.quantity} {by_id[line.purchase_order_item_id].unit_snapshot}"
                    for line in request.items
                ),
                before=before,
                after=after,
            )
            complete_command(command, order.id, "purchase_order")
            uow.commit()
            return purchase_order_response(context, order, items)

    def close(
        self,
        context: RequestContext,
        purchase_order_id: UUID,
        data: dict[str, object],
        *,
        idempotency_key: str,
    ) -> PurchaseOrderResponse:
        context.require(Permission.PROCUREMENT_WRITE)
        request = PurchaseOrderClose.model_validate(data)
        with UnitOfWork(self._session_factory) as uow:
            session = uow.session
            command = begin_command(
                session,
                context,
                scope="purchase_order.close",
                key=idempotency_key,
                payload={"purchase_order_id": str(purchase_order_id), **request.model_dump()},
            )
            repository = PurchaseOrderRepository(session)
            order = repository.get_for_update(
                organization_id=context.organization_id, purchase_order_id=purchase_order_id
            )
            if order is None:
                raise purchase_order_not_found()
            items = repository.items(
                organization_id=context.organization_id, purchase_order_id=order.id
            )
            if command.resource_id is not None:
                uow.commit()
                return purchase_order_response(context, order, items)
            self._check_version(order, request.expected_version)
            if (
                order.status != PurchaseOrderStatus.RECEIVED
                or not items
                or any(item.received_quantity != item.quantity for item in items)
            ):
                raise ApiProblem(
                    409,
                    "PURCHASE_NOT_FULLY_RECEIVED",
                    "Receipt incomplete",
                    "Receive all purchase quantities before closing.",
                )
            before = {"status": order.status, "version": order.version}
            order.status = PurchaseOrderStatus.CLOSED
            order.closed_at = datetime.now(UTC)
            order.updated_by = context.user_id
            order.version += 1
            self._record_command(
                session,
                context,
                order,
                action="purchase_order.closed",
                summary=f"Purchase {order.purchase_order_number} closed: {request.reason}",
                before=before,
                after={"status": order.status, "version": order.version, "reason": request.reason},
            )
            complete_command(command, order.id, "purchase_order")
            uow.commit()
            return purchase_order_response(context, order, items)

    @staticmethod
    def _check_version(order: PurchaseOrder, expected_version: int) -> None:
        if order.version != expected_version:
            raise ApiProblem(
                409,
                "VERSION_CONFLICT",
                "Version conflict",
                "Refresh the purchase order before submitting.",
            )

    def _begin_decision(
        self,
        session: Session,
        context: RequestContext,
        purchase_order_id: UUID,
        request: PurchaseOrderDecision,
        *,
        action: str,
        key: str,
    ) -> tuple[PurchaseOrder, IdempotencyKey]:
        sales_id = session.scalar(
            select(PurchaseOrder.sales_order_id).where(
                PurchaseOrder.organization_id == context.organization_id,
                PurchaseOrder.id == purchase_order_id,
                PurchaseOrder.deleted_at.is_(None),
            )
        )
        if sales_id is None:
            raise purchase_order_not_found()
        sales = SalesOrderRepository(session).get_for_update(
            organization_id=context.organization_id, sales_order_id=sales_id
        )
        if sales is None:
            raise purchase_order_not_found()
        order = PurchaseOrderRepository(session).get_for_update(
            organization_id=context.organization_id, purchase_order_id=purchase_order_id
        )
        if order is None:
            raise purchase_order_not_found()
        command = begin_command(
            session,
            context,
            scope=action,
            key=key,
            payload={"purchase_order_id": str(purchase_order_id), **request.model_dump()},
        )
        if command.resource_id is None:
            self._check_version(order, request.expected_version)
            if sales.status in {SalesOrderStatus.COMPLETED, SalesOrderStatus.CANCELLED}:
                raise ApiProblem(
                    409,
                    "ORDER_FINALIZED",
                    "Order finalized",
                    "已完成或取消的销售订单不能新增采购审批、发送或供应商确认。",
                )
        return order, command

    def _transition(
        self,
        context: RequestContext,
        purchase_order_id: UUID,
        *,
        request: PurchaseOrderDecision,
        idempotency_key: str,
        expected: PurchaseOrderStatus,
        target: PurchaseOrderStatus,
        action: str,
        timestamp_field: str,
        approver: bool = False,
    ) -> PurchaseOrderResponse:
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            repository = PurchaseOrderRepository(session)
            order, command = self._begin_decision(
                session,
                context,
                purchase_order_id,
                request,
                action=action,
                key=idempotency_key,
            )
            if command.resource_id is not None or order.status == target:
                items = repository.items(
                    organization_id=context.organization_id, purchase_order_id=order.id
                )
                complete_command(command, order.id, "purchase_order")
                unit_of_work.commit()
                return purchase_order_response(context, order, items)
            if order.status != expected:
                raise ApiProblem(
                    409,
                    "INVALID_STATE_TRANSITION",
                    "Invalid state transition",
                    f"Purchase order cannot move from {order.status} to {target}.",
                )
            now = datetime.now(UTC)
            previous = order.status
            order.status = target
            setattr(order, timestamp_field, now)
            if approver:
                order.approved_by = context.user_id
            order.updated_by = context.user_id
            self._record_command(
                session,
                context,
                order,
                action=action,
                summary=f"Purchase order {order.purchase_order_number} moved to {target}",
                before={"status": previous},
                after={"status": target},
            )
            items = repository.items(
                organization_id=context.organization_id, purchase_order_id=order.id
            )
            complete_command(command, order.id, "purchase_order")
            unit_of_work.commit()
            return purchase_order_response(context, order, items)

    @staticmethod
    def _committed_quantity(
        session: Session, organization_id: UUID, sales_order_item_id: UUID
    ) -> Decimal:
        value = session.scalar(
            select(
                func.coalesce(
                    func.sum(
                        case(
                            (
                                PurchaseOrder.status == PurchaseOrderStatus.CANCELLED,
                                PurchaseOrderItem.received_quantity,
                            ),
                            else_=PurchaseOrderItem.quantity,
                        )
                    ),
                    0,
                )
            )
            .join(
                PurchaseOrder,
                (PurchaseOrder.organization_id == PurchaseOrderItem.organization_id)
                & (PurchaseOrder.id == PurchaseOrderItem.purchase_order_id),
            )
            .where(
                PurchaseOrderItem.organization_id == organization_id,
                PurchaseOrderItem.sales_order_item_id == sales_order_item_id,
                PurchaseOrderItem.deleted_at.is_(None),
                PurchaseOrder.deleted_at.is_(None),
            )
        )
        return Decimal(str(value))

    def _record_command(
        self,
        session: Session,
        context: RequestContext,
        order: PurchaseOrder,
        *,
        action: str,
        summary: str,
        before: dict[str, object] | None,
        after: dict[str, object],
        reason: str | None = None,
    ) -> None:
        record_activity(
            session,
            context,
            subject_type="purchase_order",
            subject_id=order.id,
            activity_type=action,
            summary=summary,
            details={
                "purchase_order_number": order.purchase_order_number,
                "sales_order_id": str(order.sales_order_id),
                "command_result": after,
            },
        )
        self._audit_recorder.record(
            session,
            context,
            action=action,
            target_type="purchase_order",
            target_id=order.id,
            before=before,
            after=after,
            reason=reason,
        )
        self._outbox_recorder.record(
            session,
            context,
            DomainEvent(
                f"{action}.v1",
                "purchase_order",
                order.id,
                {
                    "purchase_order_id": str(order.id),
                    "sales_order_id": str(order.sales_order_id),
                },
            ),
        )
        session.flush()
