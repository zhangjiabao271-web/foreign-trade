from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.companies.models import Company
from app.core.unit_of_work import UnitOfWork
from app.finance.enums import (
    AllocationKind,
    PaymentKind,
    PaymentStatus,
    ReceivableInstallmentType,
    ReceivableStatus,
)
from app.finance.models import Payment, PaymentAllocation, Receivable
from app.finance.payment_content import payment_snapshot
from app.finance.repositories import PaymentRepository, ReceivableRepository
from app.finance.schemas import (
    PaymentAllocate,
    PaymentCreate,
    PaymentRecordSnapshot,
    PaymentReverse,
    ReceivableGenerate,
)
from app.fulfillment.models import ShipmentItem
from app.identity.models import Organization
from app.platform.idempotency import begin_command, complete_command
from app.platform.numbering import next_document_number
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.sales.models import SalesOrder, SalesOrderItem
from app.sales.order_enums import SalesOrderStatus
from app.sales.order_repositories import SalesOrderRepository
from app.sales.services import quantize_money
from app.sales.settlement import OrderSettlementPort
from app.work.records import record_activity

ReceivableAggregate = tuple[Receivable, Decimal]
PaymentAggregate = tuple[PaymentRecordSnapshot, Decimal, Sequence[PaymentAllocation]]


def receivable_not_found() -> ApiProblem:
    return ApiProblem(
        404, "RECEIVABLE_NOT_FOUND", "Receivable not found", "The receivable was not found."
    )


def payment_not_found() -> ApiProblem:
    return ApiProblem(404, "PAYMENT_NOT_FOUND", "Payment not found", "The payment was not found.")


def status_for_receivable(
    receivable: Receivable, allocated: Decimal, *, today: date | None = None
) -> ReceivableStatus:
    current_day = today or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    if allocated >= receivable.amount:
        return ReceivableStatus.PAID
    if allocated > 0:
        return ReceivableStatus.PARTIALLY_PAID
    if receivable.due_date < current_day:
        return ReceivableStatus.OVERDUE
    if receivable.due_date == current_day:
        return ReceivableStatus.DUE
    return ReceivableStatus.PENDING


def organization_today(session: Session, organization_id: UUID) -> date:
    timezone = session.scalar(
        select(Organization.timezone).where(Organization.id == organization_id)
    )
    return datetime.now(ZoneInfo(timezone or "Asia/Shanghai")).date()


class ReceivableQueryService:
    def __init__(self, repository: ReceivableRepository) -> None:
        self._repository = repository

    def list(
        self,
        context: RequestContext,
        *,
        sales_order_id: UUID | None,
        limit: int,
    ) -> Sequence[ReceivableAggregate]:
        context.require(Permission.RECEIVABLE_READ)
        return self._repository.list_with_allocated(
            organization_id=context.organization_id,
            sales_order_id=sales_order_id,
            limit=limit,
        )


class ReceivableCommandService:
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

    def generate_for_order(
        self, context: RequestContext, sales_order_id: UUID, data: dict[str, object]
    ) -> Sequence[ReceivableAggregate]:
        context.require(Permission.RECEIVABLE_WRITE)
        data = ReceivableGenerate.model_validate(data).model_dump()
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            order = SalesOrderRepository(session).get_for_update(
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
            if order.status in {
                SalesOrderStatus.DRAFT,
                SalesOrderStatus.CANCELLED,
                SalesOrderStatus.COMPLETED,
            }:
                raise ApiProblem(
                    409,
                    "ORDER_NOT_CONFIRMED",
                    "Order not confirmed",
                    "Receivables require a confirmed, active sales order.",
                )
            repository = ReceivableRepository(session)
            existing = repository.locked_for_order(
                organization_id=context.organization_id,
                sales_order_id=order.id,
            )
            if existing:
                requested_deposit_due = data.get("deposit_due_date") or order.deposit_due_date
                requested_balance_due = data["balance_due_date"]
                for receivable in existing:
                    expected_due = (
                        requested_deposit_due
                        if receivable.installment_type == ReceivableInstallmentType.DEPOSIT
                        else requested_balance_due
                    )
                    if receivable.due_date != expected_due:
                        raise ApiProblem(
                            409,
                            "RECEIVABLES_ALREADY_GENERATED",
                            "Receivables already generated",
                            "Existing receivable dates cannot be changed by retrying generation.",
                        )
                totals = repository.allocated_totals(
                    organization_id=context.organization_id,
                    receivable_ids={receivable.id for receivable in existing},
                )
                unit_of_work.commit()
                return [(item, totals.get(item.id, Decimal("0"))) for item in existing]

            installments: list[tuple[ReceivableInstallmentType, Decimal, date]] = []
            if order.deposit_amount > 0:
                deposit_due = data.get("deposit_due_date") or order.deposit_due_date
                if not isinstance(deposit_due, date):
                    raise ApiProblem(
                        400,
                        "DEPOSIT_DUE_DATE_REQUIRED",
                        "Deposit due date required",
                        "A deposit receivable requires a due date.",
                    )
                installments.append(
                    (ReceivableInstallmentType.DEPOSIT, order.deposit_amount, deposit_due)
                )
            balance = quantize_money(order.total - order.deposit_amount)
            balance_due = data["balance_due_date"]
            if not isinstance(balance_due, date):
                raise TypeError("Balance due date must be a date")
            if balance > 0:
                installments.append((ReceivableInstallmentType.BALANCE, balance, balance_due))
            if not installments:
                raise ApiProblem(
                    409,
                    "ZERO_VALUE_ORDER",
                    "Zero value order",
                    "A zero-value order does not create receivables.",
                )

            receivables: list[Receivable] = []
            for installment_type, amount, due_date in installments:
                receivable = Receivable(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    receivable_number=self._next_number(session, context),
                    sales_order_id=order.id,
                    installment_type=installment_type,
                    status=ReceivableStatus.PENDING,
                    amount=amount,
                    currency_code=order.currency_code,
                    due_date=due_date,
                )
                receivable.status = status_for_receivable(
                    receivable,
                    Decimal("0"),
                    today=organization_today(session, context.organization_id),
                )
                session.add(receivable)
                session.flush()
                self._record_receivable(
                    session,
                    context,
                    receivable,
                    action="receivable.created",
                    before=None,
                    after={
                        "status": receivable.status,
                        "amount": str(receivable.amount),
                        "installment_type": receivable.installment_type,
                    },
                )
                receivables.append(receivable)
            record_activity(
                session,
                context,
                subject_type="sales_order",
                subject_id=order.id,
                activity_type="receivables.generated",
                summary=f"Generated {len(receivables)} receivables for {order.order_number}",
                details={"receivable_ids": [str(item.id) for item in receivables]},
            )
            unit_of_work.commit()
            return [(item, Decimal("0")) for item in receivables]

    def refresh_statuses(self, context: RequestContext) -> Sequence[ReceivableAggregate]:
        context.require(Permission.RECEIVABLE_WRITE)
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            repository = ReceivableRepository(session)
            today = organization_today(session, context.organization_id)
            receivables = session.scalars(
                select(Receivable)
                .where(
                    Receivable.organization_id == context.organization_id,
                    Receivable.deleted_at.is_(None),
                    or_(
                        and_(
                            Receivable.status == ReceivableStatus.PENDING,
                            Receivable.due_date <= today,
                        ),
                        and_(
                            Receivable.status == ReceivableStatus.DUE, Receivable.due_date < today
                        ),
                    ),
                )
                .order_by(Receivable.id)
                .limit(500)
                .with_for_update()
            ).all()
            totals = repository.allocated_totals(
                organization_id=context.organization_id,
                receivable_ids={receivable.id for receivable in receivables},
            )
            for receivable in receivables:
                previous = receivable.status
                target = status_for_receivable(
                    receivable,
                    totals.get(receivable.id, Decimal("0")),
                    today=today,
                )
                if previous == target:
                    continue
                receivable.status = target
                receivable.updated_by = context.user_id
                self._record_receivable(
                    session,
                    context,
                    receivable,
                    action="receivable.status_refreshed",
                    before={"status": previous},
                    after={"status": target},
                )
            unit_of_work.commit()
            return [(item, totals.get(item.id, Decimal("0"))) for item in receivables]

    def _record_receivable(
        self,
        session: Session,
        context: RequestContext,
        receivable: Receivable,
        *,
        action: str,
        before: dict[str, object] | None,
        after: dict[str, object],
    ) -> None:
        record_activity(
            session,
            context,
            subject_type="receivable",
            subject_id=receivable.id,
            activity_type=action,
            summary=f"{receivable.receivable_number} changed to {receivable.status}",
            details={"sales_order_id": str(receivable.sales_order_id)},
        )
        self._audit_recorder.record(
            session,
            context,
            action=action,
            target_type="receivable",
            target_id=receivable.id,
            before=before,
            after=after,
        )
        self._outbox_recorder.record(
            session,
            context,
            DomainEvent(
                f"{action}.v1",
                "receivable",
                receivable.id,
                {
                    "receivable_id": str(receivable.id),
                    "sales_order_id": str(receivable.sales_order_id),
                },
            ),
        )
        session.flush()

    @staticmethod
    def _next_number(session: Session, context: RequestContext) -> str:
        return next_document_number(session, context, "RECEIVABLE", "AR")


class PaymentQueryService:
    def __init__(self, repository: PaymentRepository) -> None:
        self._repository = repository

    def list(
        self,
        context: RequestContext,
        *,
        limit: int,
        company_id: UUID | None = None,
        currency_code: str | None = None,
        query: str | None = None,
        cursor: UUID | None = None,
    ) -> Sequence[PaymentAggregate]:
        context.require(Permission.PAYMENT_READ)
        payments = self._repository.list_recent(
            organization_id=context.organization_id,
            limit=limit,
            company_id=company_id,
            currency_code=currency_code,
            query=query,
            cursor=cursor,
        )
        allocations = self._repository.allocations_for_payments(
            organization_id=context.organization_id,
            payment_ids={payment.id for payment in payments},
        )
        by_payment: dict[UUID, list[PaymentAllocation]] = {payment.id: [] for payment in payments}
        for allocation in allocations:
            by_payment[allocation.payment_id].append(allocation)
        return [
            (
                payment_snapshot(context, payment),
                sum((item.amount for item in by_payment[payment.id]), Decimal("0")),
                by_payment[payment.id],
            )
            for payment in payments
        ]

    def get(self, context: RequestContext, payment_id: UUID) -> PaymentAggregate:
        context.require(Permission.PAYMENT_READ)
        payment = self._repository.get(
            organization_id=context.organization_id, record_id=payment_id
        )
        if payment is None:
            raise payment_not_found()
        return self._aggregate(context, payment)

    def _aggregate(self, context: RequestContext, payment: Payment) -> PaymentAggregate:
        allocations = self._repository.allocations(
            organization_id=context.organization_id, payment_id=payment.id
        )
        return (
            payment_snapshot(context, payment),
            sum((item.amount for item in allocations), Decimal("0")),
            allocations,
        )


class PaymentCommandService:
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
    ) -> PaymentAggregate:
        context.require(Permission.PAYMENT_RECORD)
        data = PaymentCreate.model_validate(data).model_dump()
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            command_record = begin_command(
                session, context, scope="payment.record", key=idempotency_key, payload=data
            )
            if command_record.resource_id is not None:
                result = PaymentQueryService(PaymentRepository(session)).get(
                    context, command_record.resource_id
                )
                unit_of_work.commit()
                return result
            company_id = UUID(str(data["company_id"]))
            company = session.scalar(
                select(Company).where(
                    Company.organization_id == context.organization_id,
                    Company.id == company_id,
                    Company.deleted_at.is_(None),
                )
            )
            if company is None:
                raise ApiProblem(
                    404, "COMPANY_NOT_FOUND", "Company not found", "The company was not found."
                )
            payment = Payment(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                payment_number=next_document_number(session, context, "PAYMENT", "PAY"),
                company_id=company.id,
                kind=PaymentKind.RECEIPT,
                status=PaymentStatus.ACTIVE,
                amount=quantize_money(Decimal(str(data["amount"]))),
                currency_code=str(data["currency_code"]).upper(),
                method=str(data["method"]),
                reference=data.get("reference"),
                notes=data.get("notes"),
                received_at=data["received_at"],
            )
            session.add(payment)
            session.flush()
            self._record_payment(
                session,
                context,
                payment,
                action="payment.recorded",
                before=None,
                after={
                    "status": payment.status,
                    "amount": str(payment.amount),
                    "currency_code": payment.currency_code,
                },
            )
            complete_command(command_record, payment.id, "payment")
            unit_of_work.commit()
            return payment_snapshot(context, payment), Decimal("0"), []

    def allocate(
        self,
        context: RequestContext,
        payment_id: UUID,
        data: dict[str, object],
        *,
        idempotency_key: str,
    ) -> PaymentAggregate:
        context.require(Permission.PAYMENT_ALLOCATE)
        data = PaymentAllocate.model_validate(data).model_dump()
        raw_allocations = data["allocations"]
        if not isinstance(raw_allocations, list):
            raise TypeError("Allocations must be a list")
        receivable_ids = {UUID(str(item["receivable_id"])) for item in raw_allocations}
        if len(receivable_ids) != len(raw_allocations):
            raise ApiProblem(
                409,
                "DUPLICATE_RECEIVABLE_ALLOCATION",
                "Duplicate receivable allocation",
                "A receivable may appear only once in one allocation command.",
            )

        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            command_record = begin_command(
                session,
                context,
                scope=f"payment.allocate:{payment_id}",
                key=idempotency_key,
                payload=data,
            )
            if command_record.resource_id is not None:
                result = PaymentQueryService(PaymentRepository(session)).get(
                    context, command_record.resource_id
                )
                unit_of_work.commit()
                return result
            payment_repository = PaymentRepository(session)
            payment = payment_repository.get_for_update(
                organization_id=context.organization_id, payment_id=payment_id
            )
            if payment is None:
                raise payment_not_found()
            if payment.kind != PaymentKind.RECEIPT or payment.status != PaymentStatus.ACTIVE:
                raise ApiProblem(
                    409,
                    "PAYMENT_NOT_ALLOCATABLE",
                    "Payment not allocatable",
                    "Only an active receipt can be allocated.",
                )
            used = payment_repository.allocated_amount(
                organization_id=context.organization_id, payment_id=payment.id
            )
            requested = sum(
                (quantize_money(Decimal(str(item["amount"]))) for item in raw_allocations),
                Decimal("0"),
            )
            if used + requested > payment.amount:
                raise ApiProblem(
                    409,
                    "PAYMENT_ALLOCATION_EXCEEDED",
                    "Payment allocation exceeded",
                    "Allocations cannot exceed the payment's available amount.",
                )

            receivable_repository = ReceivableRepository(session)
            orders = self._lock_receivable_orders(session, context, receivable_ids)
            receivables = receivable_repository.locked(
                organization_id=context.organization_id, ids=receivable_ids
            )
            if {item.id for item in receivables} != receivable_ids:
                raise receivable_not_found()
            if len(orders) != len({item.sales_order_id for item in receivables}):
                raise ApiProblem(
                    409, "ORDER_LINK_INVALID", "Order link invalid", "Order unavailable."
                )
            for receivable in receivables:
                order = orders[receivable.sales_order_id]
                if order.status == SalesOrderStatus.CANCELLED:
                    raise ApiProblem(
                        409,
                        "ORDER_CANCELLED",
                        "Order cancelled",
                        "Cannot allocate to a cancelled order.",
                    )
                if receivable.currency_code != payment.currency_code:
                    raise ApiProblem(
                        409,
                        "PAYMENT_CURRENCY_MISMATCH",
                        "Payment currency mismatch",
                        "Payment and receivable currencies must match.",
                    )
                if order.company_id != payment.company_id:
                    raise ApiProblem(
                        409,
                        "PAYMENT_COMPANY_MISMATCH",
                        "Payment company mismatch",
                        "Payment and receivable must belong to the same customer.",
                    )
            current_totals = receivable_repository.allocated_totals(
                organization_id=context.organization_id, receivable_ids=receivable_ids
            )
            amount_by_id = {
                UUID(str(item["receivable_id"])): quantize_money(Decimal(str(item["amount"])))
                for item in raw_allocations
            }
            now = datetime.now(UTC)
            allocations: list[PaymentAllocation] = []
            for receivable in receivables:
                amount = amount_by_id[receivable.id]
                current = current_totals.get(receivable.id, Decimal("0"))
                if current + amount > receivable.amount:
                    raise ApiProblem(
                        409,
                        "RECEIVABLE_ALLOCATION_EXCEEDED",
                        "Receivable allocation exceeded",
                        "Allocations cannot exceed the receivable balance.",
                    )
                allocation = PaymentAllocation(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    payment_id=payment.id,
                    receivable_id=receivable.id,
                    kind=AllocationKind.ALLOCATION,
                    amount=amount,
                    allocated_at=now,
                )
                session.add(allocation)
                allocations.append(allocation)
                previous = receivable.status
                new_total = current + amount
                receivable.status = status_for_receivable(
                    receivable,
                    new_total,
                    today=organization_today(session, context.organization_id),
                )
                receivable.paid_at = now if receivable.status == ReceivableStatus.PAID else None
                receivable.updated_by = context.user_id
                self._record_receivable_change(
                    session,
                    context,
                    receivable,
                    before={"status": previous, "allocated": str(current)},
                    after={"status": receivable.status, "allocated": str(new_total)},
                )
                order = orders[receivable.sales_order_id]
                OrderSettlementPort(self._audit_recorder, self._outbox_recorder).record_allocation(
                    session,
                    context,
                    order,
                    deposit=receivable.installment_type == ReceivableInstallmentType.DEPOSIT,
                    settled=receivable.status == ReceivableStatus.PAID,
                    reversed=False,
                    payment_id=str(payment.id),
                    amount=str(amount),
                )
            session.flush()
            self._record_payment(
                session,
                context,
                payment,
                action="payment.allocated",
                before={"allocated_amount": str(used)},
                after={"allocated_amount": str(used + requested)},
            )
            all_allocations = payment_repository.allocations(
                organization_id=context.organization_id, payment_id=payment.id
            )
            complete_command(command_record, payment.id, "payment")
            unit_of_work.commit()
            return payment_snapshot(context, payment), used + requested, all_allocations

    def reverse(
        self, context: RequestContext, payment_id: UUID, *, reason: str
    ) -> PaymentAggregate:
        context.require(Permission.PAYMENT_REVERSE)
        reason = PaymentReverse(reason=reason).reason
        with UnitOfWork(self._session_factory) as unit_of_work:
            session = unit_of_work.session
            payment_repository = PaymentRepository(session)
            original = payment_repository.get_for_update(
                organization_id=context.organization_id, payment_id=payment_id
            )
            if original is None:
                raise payment_not_found()
            if original.kind != PaymentKind.RECEIPT:
                raise ApiProblem(
                    409,
                    "REVERSAL_PAYMENT_NOT_REVERSIBLE",
                    "Reversal is not reversible",
                    "A reversal fact cannot itself be reversed.",
                )
            if original.status == PaymentStatus.REVERSED:
                reversal = payment_repository.reversal_for(
                    organization_id=context.organization_id, payment_id=original.id
                )
                if reversal is None:
                    raise ApiProblem(
                        409,
                        "PAYMENT_REVERSAL_INCONSISTENT",
                        "Payment reversal inconsistent",
                        "The original is reversed but its reversal fact is missing.",
                    )
                allocated = payment_repository.allocated_amount(
                    organization_id=context.organization_id, payment_id=reversal.id
                )
                unit_of_work.commit()
                return (
                    payment_snapshot(context, reversal),
                    allocated,
                    payment_repository.allocations(
                        organization_id=context.organization_id,
                        payment_id=reversal.id,
                    ),
                )

            original_allocations = [
                item
                for item in payment_repository.allocations(
                    organization_id=context.organization_id, payment_id=original.id
                )
                if item.kind == AllocationKind.ALLOCATION
            ]
            receivable_ids = {item.receivable_id for item in original_allocations}
            receivable_repository = ReceivableRepository(session)
            orders = self._lock_receivable_orders(session, context, receivable_ids)
            if any(order.status == SalesOrderStatus.COMPLETED for order in orders.values()):
                raise ApiProblem(
                    409,
                    "PAYMENT_REVERSAL_REQUIRES_REVIEW",
                    "Payment reversal requires review",
                    "A completed order requires a compensating workflow before payment reversal.",
                )
            receivables = receivable_repository.locked(
                organization_id=context.organization_id, ids=receivable_ids
            )
            receivable_by_id = {item.id: item for item in receivables}
            if any(
                item.installment_type == ReceivableInstallmentType.DEPOSIT
                and self._order_has_shipments(session, context.organization_id, item.sales_order_id)
                for item in receivables
            ):
                raise ApiProblem(
                    409,
                    "PAYMENT_REVERSAL_REQUIRES_REVIEW",
                    "Payment reversal requires review",
                    "A deposit cannot be reversed after shipment planning has started.",
                )
            current_totals = receivable_repository.allocated_totals(
                organization_id=context.organization_id, receivable_ids=receivable_ids
            )
            now = datetime.now(UTC)
            reversal = Payment(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                payment_number=next_document_number(session, context, "PAYMENT_REVERSAL", "REV"),
                company_id=original.company_id,
                kind=PaymentKind.REVERSAL,
                status=PaymentStatus.ACTIVE,
                reversal_of_payment_id=original.id,
                amount=original.amount,
                currency_code=original.currency_code,
                method=original.method,
                reference=original.reference,
                notes=f"Reversal: {reason}",
                received_at=now,
            )
            session.add(reversal)
            session.flush()
            reversal_allocations: list[PaymentAllocation] = []
            for original_allocation in original_allocations:
                reversal_allocation = PaymentAllocation(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    payment_id=reversal.id,
                    receivable_id=original_allocation.receivable_id,
                    kind=AllocationKind.REVERSAL,
                    reversal_of_allocation_id=original_allocation.id,
                    amount=original_allocation.amount,
                    allocated_at=now,
                )
                session.add(reversal_allocation)
                reversal_allocations.append(reversal_allocation)
                receivable = receivable_by_id[original_allocation.receivable_id]
                previous_total = current_totals[receivable.id]
                new_total = previous_total - original_allocation.amount
                current_totals[receivable.id] = new_total
                previous_status = receivable.status
                receivable.status = status_for_receivable(
                    receivable,
                    new_total,
                    today=organization_today(session, context.organization_id),
                )
                receivable.paid_at = None
                receivable.updated_by = context.user_id
                self._record_receivable_change(
                    session,
                    context,
                    receivable,
                    before={"status": previous_status, "allocated": str(previous_total)},
                    after={"status": receivable.status, "allocated": str(new_total)},
                    reason=reason,
                )
                order = orders[receivable.sales_order_id]
                OrderSettlementPort(self._audit_recorder, self._outbox_recorder).record_allocation(
                    session,
                    context,
                    order,
                    deposit=receivable.installment_type == ReceivableInstallmentType.DEPOSIT,
                    settled=receivable.status == ReceivableStatus.PAID,
                    reversed=True,
                    payment_id=str(reversal.id),
                    amount=str(original_allocation.amount),
                    reason=reason,
                )
            original.status = PaymentStatus.REVERSED
            original.reversed_at = now
            original.updated_by = context.user_id
            self._record_payment(
                session,
                context,
                original,
                action="payment.reversed",
                before={"status": PaymentStatus.ACTIVE},
                after={"status": original.status, "reversal_payment_id": str(reversal.id)},
                reason=reason,
            )
            self._record_payment(
                session,
                context,
                reversal,
                action="payment.reversal_recorded",
                before=None,
                after={"reversal_of_payment_id": str(original.id)},
                reason=reason,
            )
            unit_of_work.commit()
            return (
                payment_snapshot(context, reversal),
                sum((item.amount for item in reversal_allocations), Decimal("0")),
                reversal_allocations,
            )

    @staticmethod
    def _lock_receivable_orders(
        session: Session, context: RequestContext, receivable_ids: set[UUID]
    ) -> dict[UUID, SalesOrder]:
        order_ids = select(Receivable.sales_order_id).where(
            Receivable.organization_id == context.organization_id,
            Receivable.id.in_(receivable_ids),
            Receivable.deleted_at.is_(None),
        )
        orders = session.scalars(
            select(SalesOrder)
            .where(
                SalesOrder.organization_id == context.organization_id,
                SalesOrder.id.in_(order_ids),
                SalesOrder.deleted_at.is_(None),
            )
            .order_by(SalesOrder.id)
            .with_for_update()
        ).all()
        return {order.id: order for order in orders}

    def _record_receivable_change(
        self,
        session: Session,
        context: RequestContext,
        receivable: Receivable,
        *,
        before: dict[str, object],
        after: dict[str, object],
        reason: str | None = None,
    ) -> None:
        record_activity(
            session,
            context,
            subject_type="receivable",
            subject_id=receivable.id,
            activity_type="receivable.allocation_changed",
            summary=f"Allocation changed for {receivable.receivable_number}",
            details={"sales_order_id": str(receivable.sales_order_id)},
        )
        self._audit_recorder.record(
            session,
            context,
            action="receivable.allocation_changed",
            target_type="receivable",
            target_id=receivable.id,
            before=before,
            after=after,
            reason=reason,
        )
        self._outbox_recorder.record(
            session,
            context,
            DomainEvent(
                "receivable.allocation_changed.v1",
                "receivable",
                receivable.id,
                {"receivable_id": str(receivable.id)},
            ),
        )

    def _record_payment(
        self,
        session: Session,
        context: RequestContext,
        payment: Payment,
        *,
        action: str,
        before: dict[str, object] | None,
        after: dict[str, object],
        reason: str | None = None,
    ) -> None:
        record_activity(
            session,
            context,
            subject_type="payment",
            subject_id=payment.id,
            activity_type=action,
            summary=f"Payment fact {payment.payment_number}: {action}",
            details={"company_id": str(payment.company_id)},
        )
        self._audit_recorder.record(
            session,
            context,
            action=action,
            target_type="payment",
            target_id=payment.id,
            before=before,
            after=after,
            reason=reason,
        )
        self._outbox_recorder.record(
            session,
            context,
            DomainEvent(
                f"{action}.v1",
                "payment",
                payment.id,
                {"payment_id": str(payment.id), "kind": payment.kind},
            ),
        )
        session.flush()

    @staticmethod
    def _order_has_shipments(session: Session, organization_id: UUID, sales_order_id: UUID) -> bool:
        return bool(
            session.scalar(
                select(func.count())
                .select_from(ShipmentItem)
                .join(
                    SalesOrderItem,
                    (SalesOrderItem.organization_id == ShipmentItem.organization_id)
                    & (SalesOrderItem.id == ShipmentItem.sales_order_item_id),
                )
                .where(
                    ShipmentItem.organization_id == organization_id,
                    SalesOrderItem.sales_order_id == sales_order_id,
                    ShipmentItem.deleted_at.is_(None),
                )
            )
        )
