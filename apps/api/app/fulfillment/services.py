from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.companies.enums import CompanyRoleType
from app.companies.models import Company, CompanyRole
from app.core.unit_of_work import UnitOfWork
from app.documents.enums import (
    SHIPMENT_DEPARTURE_REQUIRED_DOCUMENTS,
    DocumentLinkTargetType,
    DocumentVersionStatus,
)
from app.documents.models import Document, DocumentLink, DocumentVersion
from app.fulfillment.enums import ShipmentStatus
from app.fulfillment.models import Shipment, ShipmentItem
from app.fulfillment.repositories import ShipmentRepository
from app.fulfillment.schemas import ShipmentBook, ShipmentCreate, ShipmentDecision
from app.platform.idempotency import begin_command, complete_command
from app.platform.numbering import next_document_number
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.sales.models import SalesOrder, SalesOrderItem
from app.sales.order_enums import SalesOrderStatus
from app.sales.order_repositories import SalesOrderRepository
from app.sales.order_schemas import SalesOrderSourceLinesResponse
from app.sales.order_services import SalesOrderQueryService
from app.sales.shipping_progress import refresh_shipping_progress
from app.work.records import record_activity


def shipment_not_found() -> ApiProblem:
    return ApiProblem(
        404, "SHIPMENT_NOT_FOUND", "Shipment not found", "The shipment was not found."
    )


def missing_required_documents(
    session: Session, *, organization_id: UUID, shipment_id: UUID
) -> list[str]:
    return missing_documents_for_shipments(
        session, organization_id=organization_id, shipment_ids=[shipment_id]
    )[shipment_id]


def missing_documents_for_shipments(
    session: Session, *, organization_id: UUID, shipment_ids: Sequence[UUID]
) -> dict[UUID, list[str]]:
    available: dict[UUID, set[str]] = {shipment_id: set() for shipment_id in shipment_ids}
    if not shipment_ids:
        return {}
    rows = session.execute(
        select(DocumentLink.target_id, Document.document_type)
        .select_from(Document)
        .join(
            DocumentLink,
            (DocumentLink.organization_id == Document.organization_id)
            & (DocumentLink.document_id == Document.id),
        )
        .join(
            DocumentVersion,
            (DocumentVersion.organization_id == Document.organization_id)
            & (DocumentVersion.document_id == Document.id)
            & (DocumentVersion.version_number == Document.latest_version_number),
        )
        .where(
            Document.organization_id == organization_id,
            DocumentLink.target_type == DocumentLinkTargetType.SHIPMENT,
            DocumentLink.target_id.in_(shipment_ids),
            DocumentVersion.status == DocumentVersionStatus.AVAILABLE,
            DocumentVersion.storage_version_id.is_not(None),
            DocumentVersion.storage_version_id.not_in(["", "null"]),
            Document.deleted_at.is_(None),
            DocumentLink.deleted_at.is_(None),
            DocumentVersion.deleted_at.is_(None),
        )
    )
    for shipment_id, document_type in rows:
        available[shipment_id].add(document_type)
    return {
        shipment_id: sorted(
            document_type.value
            for document_type in SHIPMENT_DEPARTURE_REQUIRED_DOCUMENTS
            if document_type not in available_types
        )
        for shipment_id, available_types in available.items()
    }


ShipmentAggregate = tuple[Shipment, Sequence[ShipmentItem], list[str]]


class ShipmentQueryService:
    def __init__(self, repository: ShipmentRepository) -> None:
        self._repository = repository

    def list(
        self, context: RequestContext, *, limit: int, cursor: UUID | None = None
    ) -> Sequence[ShipmentAggregate]:
        context.require(Permission.SHIPMENT_READ)
        shipments = self._repository.list_recent(
            organization_id=context.organization_id, limit=limit, cursor=cursor
        )
        shipment_ids = [shipment.id for shipment in shipments]
        items = self._repository.items_for_shipments(
            organization_id=context.organization_id, shipment_ids=shipment_ids
        )
        missing = missing_documents_for_shipments(
            self._repository.session,
            organization_id=context.organization_id,
            shipment_ids=shipment_ids,
        )
        return [(shipment, items[shipment.id], missing[shipment.id]) for shipment in shipments]

    def get(self, context: RequestContext, shipment_id: UUID) -> ShipmentAggregate:
        context.require(Permission.SHIPMENT_READ)
        shipment = self._repository.get(
            organization_id=context.organization_id, record_id=shipment_id
        )
        if shipment is None:
            raise shipment_not_found()
        return self._aggregate(context, shipment)

    def source_lines(
        self, context: RequestContext, shipment_id: UUID
    ) -> SalesOrderSourceLinesResponse:
        context.require(Permission.SHIPMENT_READ)
        context.require(Permission.ORDER_READ)
        shipment = self._repository.get(
            organization_id=context.organization_id, record_id=shipment_id
        )
        if shipment is None:
            raise shipment_not_found()
        shipment_items = self._repository.items(
            organization_id=context.organization_id, shipment_id=shipment.id
        )
        items = SalesOrderQueryService(SalesOrderRepository(self._repository.session)).source_lines(
            context, [item.sales_order_item_id for item in shipment_items]
        )
        return SalesOrderSourceLinesResponse(items=list(items), count=len(items))

    def _aggregate(self, context: RequestContext, shipment: Shipment) -> ShipmentAggregate:
        return (
            shipment,
            self._repository.items(
                organization_id=context.organization_id, shipment_id=shipment.id
            ),
            missing_required_documents(
                self._repository.session,
                organization_id=context.organization_id,
                shipment_id=shipment.id,
            ),
        )


class ShipmentCommandService:
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
    ) -> ShipmentAggregate:
        context.require(Permission.SHIPMENT_WRITE)
        data = ShipmentCreate.model_validate(data).model_dump()
        raw_items = data["items"]
        if not isinstance(raw_items, list):
            raise TypeError("Shipment items must be a list")
        item_ids = [UUID(str(item["sales_order_item_id"])) for item in raw_items]
        if len(set(item_ids)) != len(item_ids):
            raise ApiProblem(
                409,
                "DUPLICATE_SALES_ORDER_ITEM",
                "Duplicate sales order item",
                "A sales order line can appear only once in a shipment.",
            )
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            command = begin_command(
                session, context, scope="shipment.create", key=idempotency_key, payload=data
            )
            if command.resource_id is not None:
                repository = ShipmentRepository(session)
                shipment = repository.get(
                    organization_id=context.organization_id, record_id=command.resource_id
                )
                if shipment is None:
                    raise shipment_not_found()
                replay_items = repository.items(
                    organization_id=context.organization_id, shipment_id=shipment.id
                )
                missing = missing_required_documents(
                    session, organization_id=context.organization_id, shipment_id=shipment.id
                )
                unit_of_work.commit()
                return shipment, replay_items, missing
            # Discover IDs without caching unlocked ORM rows. All writers acquire
            # parent orders before lines, in stable order, then revalidate sources.
            source_orders = {
                item_id: order_id
                for item_id, order_id in session.execute(
                    select(SalesOrderItem.id, SalesOrderItem.sales_order_id).where(
                        SalesOrderItem.organization_id == context.organization_id,
                        SalesOrderItem.id.in_(item_ids),
                        SalesOrderItem.deleted_at.is_(None),
                    )
                )
            }
            if set(source_orders) != set(item_ids):
                raise ApiProblem(
                    404,
                    "SALES_ORDER_ITEM_NOT_FOUND",
                    "Sales order item not found",
                    "One or more sales order lines were not found.",
                )
            order_ids = set(source_orders.values())
            sales_orders = session.scalars(
                select(SalesOrder)
                .where(
                    SalesOrder.organization_id == context.organization_id,
                    SalesOrder.id.in_(order_ids),
                    SalesOrder.deleted_at.is_(None),
                )
                .order_by(SalesOrder.id)
                .with_for_update()
            ).all()
            if {order.id for order in sales_orders} != order_ids:
                raise ApiProblem(
                    404,
                    "SALES_ORDER_NOT_FOUND",
                    "Sales order not found",
                    "One or more sales orders were not found.",
                )
            sales_items = session.scalars(
                select(SalesOrderItem)
                .where(
                    SalesOrderItem.organization_id == context.organization_id,
                    SalesOrderItem.id.in_(item_ids),
                    SalesOrderItem.deleted_at.is_(None),
                )
                .order_by(SalesOrderItem.id)
                .with_for_update()
            ).all()
            if {item.id: item.sales_order_id for item in sales_items} != source_orders:
                raise ApiProblem(
                    404,
                    "SALES_ORDER_ITEM_NOT_FOUND",
                    "Sales order item not found",
                    "One or more sales order lines were not found.",
                )
            if any(
                order.status not in {SalesOrderStatus.EXECUTING, SalesOrderStatus.READY_TO_SHIP}
                for order in sales_orders
            ):
                raise ApiProblem(
                    409,
                    "ORDER_NOT_EXECUTING",
                    "Order not executing",
                    "Shipment planning requires an executing sales order with no pending deposit.",
                )
            self._require_forwarder_role(
                session,
                context,
                UUID(str(data["forwarder_company_id"]))
                if data.get("forwarder_company_id")
                else None,
            )
            sales_by_id = {item.id: item for item in sales_items}
            shipment = Shipment(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                shipment_number=next_document_number(session, context, "SHIPMENT", "SHP"),
                forwarder_company_id=data.get("forwarder_company_id"),
                planned_departure_date=data.get("planned_departure_date"),
                planned_arrival_date=data.get("planned_arrival_date"),
            )
            session.add(shipment)
            session.flush()
            items: list[ShipmentItem] = []
            committed_by_item = {
                item_id: quantity
                for item_id, quantity in session.execute(
                    select(ShipmentItem.sales_order_item_id, func.sum(ShipmentItem.quantity))
                    .where(
                        ShipmentItem.organization_id == context.organization_id,
                        ShipmentItem.sales_order_item_id.in_(item_ids),
                        ShipmentItem.deleted_at.is_(None),
                    )
                    .group_by(ShipmentItem.sales_order_item_id)
                )
            }
            for raw_item in raw_items:
                sales_item_id = UUID(str(raw_item["sales_order_item_id"]))
                quantity = Decimal(str(raw_item["quantity"]))
                committed = committed_by_item.get(sales_item_id, Decimal(0))
                if Decimal(str(committed)) + quantity > sales_by_id[sales_item_id].quantity:
                    raise ApiProblem(
                        409,
                        "SHIPMENT_QUANTITY_EXCEEDED",
                        "Shipment quantity exceeded",
                        "Cumulative shipment quantity cannot exceed the sales order quantity.",
                    )
                item = ShipmentItem(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    shipment_id=shipment.id,
                    sales_order_item_id=sales_item_id,
                    quantity=quantity,
                )
                session.add(item)
                items.append(item)
            self._record_command(
                session,
                context,
                shipment,
                action="shipment.created",
                before=None,
                after={"status": ShipmentStatus.PLANNING, "item_count": len(items)},
            )
            complete_command(command, shipment.id, "shipment")
            session.flush()
            created_items = ShipmentRepository(session).items(
                organization_id=context.organization_id, shipment_id=shipment.id
            )
            unit_of_work.commit()
            return (
                shipment,
                created_items,
                sorted(
                    document_type.value for document_type in SHIPMENT_DEPARTURE_REQUIRED_DOCUMENTS
                ),
            )

    def book(
        self,
        context: RequestContext,
        shipment_id: UUID,
        request: ShipmentBook,
        *,
        idempotency_key: str,
    ) -> ShipmentAggregate:
        return self._transition(
            context,
            shipment_id,
            request=request,
            idempotency_key=idempotency_key,
            expected=ShipmentStatus.PLANNING,
            target=ShipmentStatus.BOOKED,
            timestamp_field="booked_at",
            updates={"booking_reference": request.booking_reference},
        )

    def ready(
        self,
        context: RequestContext,
        shipment_id: UUID,
        request: ShipmentDecision,
        *,
        idempotency_key: str,
    ) -> ShipmentAggregate:
        return self._transition(
            context,
            shipment_id,
            expected=ShipmentStatus.BOOKED,
            request=request,
            idempotency_key=idempotency_key,
            target=ShipmentStatus.READY,
            timestamp_field="ready_at",
            require_documents=True,
            refresh_orders=True,
        )

    def enter_customs(
        self,
        context: RequestContext,
        shipment_id: UUID,
        request: ShipmentDecision,
        *,
        idempotency_key: str,
    ) -> ShipmentAggregate:
        return self._transition(
            context,
            shipment_id,
            expected=ShipmentStatus.READY,
            request=request,
            idempotency_key=idempotency_key,
            target=ShipmentStatus.CUSTOMS,
            timestamp_field="customs_at",
            require_documents=True,
        )

    def depart(
        self,
        context: RequestContext,
        shipment_id: UUID,
        request: ShipmentDecision,
        *,
        idempotency_key: str,
    ) -> ShipmentAggregate:
        return self._transition(
            context,
            shipment_id,
            expected=ShipmentStatus.CUSTOMS,
            request=request,
            idempotency_key=idempotency_key,
            target=ShipmentStatus.DEPARTED,
            timestamp_field="departed_at",
            require_documents=True,
            refresh_orders=True,
        )

    def start_transit(
        self,
        context: RequestContext,
        shipment_id: UUID,
        request: ShipmentDecision,
        *,
        idempotency_key: str,
    ) -> ShipmentAggregate:
        return self._transition(
            context,
            shipment_id,
            expected=ShipmentStatus.DEPARTED,
            request=request,
            idempotency_key=idempotency_key,
            target=ShipmentStatus.IN_TRANSIT,
            timestamp_field="in_transit_at",
        )

    def arrive(
        self,
        context: RequestContext,
        shipment_id: UUID,
        request: ShipmentDecision,
        *,
        idempotency_key: str,
    ) -> ShipmentAggregate:
        return self._transition(
            context,
            shipment_id,
            expected=ShipmentStatus.IN_TRANSIT,
            request=request,
            idempotency_key=idempotency_key,
            target=ShipmentStatus.ARRIVED,
            timestamp_field="arrived_at",
        )

    def deliver(
        self,
        context: RequestContext,
        shipment_id: UUID,
        request: ShipmentDecision,
        *,
        idempotency_key: str,
    ) -> ShipmentAggregate:
        return self._transition(
            context,
            shipment_id,
            expected=ShipmentStatus.ARRIVED,
            request=request,
            idempotency_key=idempotency_key,
            target=ShipmentStatus.DELIVERED,
            timestamp_field="delivered_at",
        )

    def _transition(
        self,
        context: RequestContext,
        shipment_id: UUID,
        *,
        request: ShipmentDecision,
        idempotency_key: str,
        expected: ShipmentStatus,
        target: ShipmentStatus,
        timestamp_field: str,
        updates: dict[str, object] | None = None,
        require_documents: bool = False,
        refresh_orders: bool = False,
    ) -> ShipmentAggregate:
        context.require(Permission.SHIPMENT_TRANSITION)
        request = type(request).model_validate(request.model_dump())
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            # Order completion/procurement own the parent lock first. Acquire
            # all parents before the shipment, including non-refresh milestones.
            # Select only IDs here so the Sales port reads fresh ORM state later.
            source_order_ids = (
                select(SalesOrderItem.sales_order_id)
                .join(
                    ShipmentItem,
                    (ShipmentItem.organization_id == SalesOrderItem.organization_id)
                    & (ShipmentItem.sales_order_item_id == SalesOrderItem.id),
                )
                .where(
                    ShipmentItem.organization_id == context.organization_id,
                    ShipmentItem.shipment_id == shipment_id,
                    ShipmentItem.deleted_at.is_(None),
                    SalesOrderItem.deleted_at.is_(None),
                )
            )
            parent_states = dict(
                session.execute(
                    select(SalesOrder.id, SalesOrder.status)
                    .where(
                        SalesOrder.organization_id == context.organization_id,
                        SalesOrder.id.in_(source_order_ids),
                        SalesOrder.deleted_at.is_(None),
                    )
                    .order_by(SalesOrder.id)
                    .with_for_update()
                )
                .tuples()
                .all()
            )
            repository = ShipmentRepository(session)
            shipment = repository.get_for_update(
                organization_id=context.organization_id, shipment_id=shipment_id
            )
            if shipment is None:
                raise shipment_not_found()
            command = begin_command(
                session,
                context,
                scope=f"shipment.{target.value.lower()}",
                key=idempotency_key,
                payload={"shipment_id": shipment_id, **request.model_dump()},
            )
            items = repository.items(
                organization_id=context.organization_id, shipment_id=shipment.id
            )
            missing = missing_required_documents(
                session, organization_id=context.organization_id, shipment_id=shipment.id
            )
            if command.resource_id is not None:
                unit_of_work.commit()
                return shipment, items, missing
            if shipment.version != request.expected_version:
                raise ApiProblem(
                    409,
                    "VERSION_CONFLICT",
                    "Shipment changed",
                    "Refresh the shipment before making a new decision.",
                )
            self._validate_execution_sources(session, context, items, parent_states)
            if shipment.status == target:
                if updates and any(
                    getattr(shipment, field) != value for field, value in updates.items()
                ):
                    raise ApiProblem(
                        409,
                        "BOOKING_REFERENCE_CONFLICT",
                        "Booking reference conflict",
                        "The original booking reference cannot be replaced by a retry.",
                    )
                complete_command(command, shipment.id, "shipment")
                unit_of_work.commit()
                return shipment, items, missing
            if shipment.status != expected:
                raise ApiProblem(
                    409,
                    "INVALID_STATE_TRANSITION",
                    "Invalid state transition",
                    f"Shipment must be {expected.value} before it can become {target.value}.",
                )
            if require_documents and missing:
                raise ApiProblem(
                    409,
                    "SHIPMENT_DOCUMENTS_INCOMPLETE",
                    "Shipment documents incomplete",
                    f"Missing required documents: {', '.join(missing)}.",
                )
            now = datetime.now(UTC)
            shipment.status = target
            setattr(shipment, timestamp_field, now)
            shipment.updated_by = context.user_id
            for field, value in (updates or {}).items():
                setattr(shipment, field, value)
            self._record_command(
                session,
                context,
                shipment,
                action=f"shipment.{target.value.lower()}",
                before={"status": expected},
                after={"status": target, timestamp_field: now.isoformat()},
            )
            if refresh_orders:
                refresh_shipping_progress(
                    session,
                    context,
                    source_item_ids=[item.sales_order_item_id for item in items],
                    departed=target == ShipmentStatus.DEPARTED,
                    audit_recorder=self._audit_recorder,
                    outbox_recorder=self._outbox_recorder,
                )
            complete_command(command, shipment.id, "shipment")
            session.flush()
            unit_of_work.commit()
            return shipment, items, missing

    @staticmethod
    def _validate_execution_sources(
        session: Session,
        context: RequestContext,
        items: Sequence[ShipmentItem],
        parent_states: dict[UUID, str],
    ) -> None:
        source_ids = {item.sales_order_item_id for item in items}
        sources = session.scalars(
            select(SalesOrderItem).where(
                SalesOrderItem.organization_id == context.organization_id,
                SalesOrderItem.id.in_(source_ids),
                SalesOrderItem.deleted_at.is_(None),
            )
        ).all()
        if (
            not sources
            or {source.id for source in sources} != source_ids
            or {source.sales_order_id for source in sources} != set(parent_states)
        ):
            raise ApiProblem(
                404,
                "SALES_ORDER_ITEM_NOT_FOUND",
                "Shipment source not found",
                "One or more active source lines or parent orders were not found.",
            )
        if any(
            state in {SalesOrderStatus.COMPLETED, SalesOrderStatus.CANCELLED}
            for state in parent_states.values()
        ):
            raise ApiProblem(
                409,
                "ORDER_FINALIZED",
                "Order finalized",
                "Finalized orders cannot acquire new shipment milestones.",
            )
        if any(
            state
            not in {
                SalesOrderStatus.EXECUTING,
                SalesOrderStatus.READY_TO_SHIP,
                SalesOrderStatus.SHIPPED,
            }
            for state in parent_states.values()
        ):
            raise ApiProblem(
                409,
                "ORDER_NOT_EXECUTING",
                "Order not executing",
                "Shipment milestones require executing orders with no pending deposit.",
            )
        quantities = dict(
            session.execute(
                select(ShipmentItem.sales_order_item_id, func.sum(ShipmentItem.quantity))
                .where(
                    ShipmentItem.organization_id == context.organization_id,
                    ShipmentItem.sales_order_item_id.in_(source_ids),
                    ShipmentItem.deleted_at.is_(None),
                )
                .group_by(ShipmentItem.sales_order_item_id)
            )
            .tuples()
            .all()
        )
        if any(quantities[source.id] > source.quantity for source in sources):
            raise ApiProblem(
                409,
                "SHIPMENT_QUANTITY_EXCEEDED",
                "Shipment quantity exceeded",
                "Cumulative shipment quantity cannot exceed the sales order quantity.",
            )

    @staticmethod
    def _require_forwarder_role(
        session: Session, context: RequestContext, forwarder_id: UUID | None
    ) -> None:
        if forwarder_id is None:
            return
        company_id = session.scalar(
            select(Company.id).where(
                Company.organization_id == context.organization_id,
                Company.id == forwarder_id,
                Company.deleted_at.is_(None),
            )
        )
        if company_id is None:
            raise ApiProblem(
                404,
                "FORWARDER_NOT_FOUND",
                "Forwarder not found",
                "The selected forwarding company was not found.",
            )
        role = session.scalar(
            select(CompanyRole).where(
                CompanyRole.organization_id == context.organization_id,
                CompanyRole.company_id == forwarder_id,
                CompanyRole.role == CompanyRoleType.FORWARDER,
                CompanyRole.deleted_at.is_(None),
            )
        )
        if role is None:
            raise ApiProblem(
                409,
                "FORWARDER_ROLE_REQUIRED",
                "Forwarder role required",
                "The selected company must have the FORWARDER role.",
            )

    def _record_command(
        self,
        session: Session,
        context: RequestContext,
        shipment: Shipment,
        *,
        action: str,
        before: dict[str, object] | None,
        after: dict[str, object],
    ) -> None:
        record_activity(
            session,
            context,
            subject_type="shipment",
            subject_id=shipment.id,
            activity_type=action,
            summary=f"Shipment {shipment.shipment_number}: {action}",
            details={"shipment_number": shipment.shipment_number},
        )
        self._audit_recorder.record(
            session,
            context,
            action=action,
            target_type="shipment",
            target_id=shipment.id,
            before=before,
            after=after,
        )
        self._outbox_recorder.record(
            session,
            context,
            DomainEvent(
                f"{action}.v1",
                "shipment",
                shipment.id,
                {"shipment_id": str(shipment.id), "shipment_number": shipment.shipment_number},
            ),
        )
