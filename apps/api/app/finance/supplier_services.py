from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.companies.models import Company, CompanyRole
from app.core.unit_of_work import UnitOfWork
from app.finance.services import organization_today
from app.finance.supplier_models import Payable, SupplierPayment, SupplierPaymentAllocation
from app.finance.supplier_repositories import SupplierFinanceRepository, missing
from app.finance.supplier_schemas import (
    PayableCreate,
    SupplierPaymentAllocate,
    SupplierPaymentCreate,
    SupplierVersionCommand,
)
from app.platform.idempotency import begin_command, complete_command
from app.platform.numbering import next_document_number
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.procurement.models import PurchaseOrder
from app.sales.models import SalesOrder
from app.work.records import record_activity


def conflict(code: str, detail: str) -> ApiProblem:
    return ApiProblem(409, code, "Financial command rejected", detail)


def check_version(actual: int, expected: int) -> None:
    if actual != expected:
        raise conflict(
            "VERSION_CONFLICT", "Refresh and review the financial record before retrying."
        )


def snapshot(row: Payable | SupplierPayment | SupplierPaymentAllocation) -> dict[str, object]:
    return {
        column.name: str(getattr(row, column.name))
        if getattr(row, column.name) is not None
        else None
        for column in row.__table__.columns
        if column.name not in {"organization_id", "deleted_at"}
    }


class SupplierFinanceService:
    def __init__(
        self,
        factory: sessionmaker[Session],
        *,
        audit_recorder: AuditRecorder | None = None,
        outbox_recorder: OutboxRecorder | None = None,
    ):
        self.factory = factory
        self.audit = audit_recorder or AuditRecorder()
        self.outbox = outbox_recorder or OutboxRecorder()

    def _evidence(
        self,
        session: Session,
        context: RequestContext,
        row: Payable | SupplierPayment | SupplierPaymentAllocation,
        *,
        action: str,
        reason: str,
        before: dict[str, object] | None = None,
        order_id: UUID | None = None,
    ) -> None:
        if isinstance(row, Payable):
            kind = "payable"
        elif isinstance(row, SupplierPayment):
            kind = "supplier_payment"
        else:
            kind = "supplier_payment_allocation"
        subject_type = "sales_order" if order_id else "company"
        subject_id = order_id
        if subject_id is None and isinstance(row, SupplierPayment):
            subject_id = row.supplier_company_id
        if subject_id is None:
            raise RuntimeError("Financial evidence needs an explicit business subject")
        record_activity(
            session,
            context,
            subject_type=subject_type,
            subject_id=subject_id,
            activity_type=action,
            summary=action,
            details={f"{kind}_id": str(row.id)},
        )
        self.audit.record(
            session,
            context,
            action=action,
            target_type=kind,
            target_id=row.id,
            before=before,
            after=snapshot(row),
            reason=reason,
        )
        self.outbox.record(
            session, context, DomainEvent(f"{action}.v1", kind, row.id, {f"{kind}_id": str(row.id)})
        )

    def create_payable(self, context: RequestContext, data: dict[str, object], *, key: str) -> UUID:
        context.require(Permission.PAYABLE_WRITE)
        request = PayableCreate.model_validate(data)
        with UnitOfWork(self.factory) as uow:
            session = uow.session
            command = begin_command(
                session, context, scope="payable.created", key=key, payload=request.model_dump()
            )
            if command.resource_id:
                SupplierFinanceRepository(session).payable(
                    context.organization_id, command.resource_id
                )
                uow.commit()
                return command.resource_id
            purchase = session.scalar(
                select(PurchaseOrder).where(
                    PurchaseOrder.organization_id == context.organization_id,
                    PurchaseOrder.id == request.purchase_order_id,
                    PurchaseOrder.deleted_at.is_(None),
                )
            )
            if purchase is None:
                raise missing("PURCHASE_ORDER")
            order = session.scalar(
                select(SalesOrder)
                .where(
                    SalesOrder.organization_id == context.organization_id,
                    SalesOrder.id == purchase.sales_order_id,
                    SalesOrder.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if order is None:
                raise missing("SALES_ORDER")
            purchase = session.scalar(
                select(PurchaseOrder)
                .where(
                    PurchaseOrder.organization_id == context.organization_id,
                    PurchaseOrder.id == request.purchase_order_id,
                    PurchaseOrder.deleted_at.is_(None),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if purchase is None:
                raise missing("PURCHASE_ORDER")
            if purchase.confirmed_at is None:
                raise conflict(
                    "PURCHASE_NOT_CONFIRMED",
                    "Payables require supplier-confirmed purchase evidence.",
                )
            if request.incurred_on > organization_today(session, context.organization_id):
                raise ApiProblem(
                    422,
                    "PAYABLE_DATE_IN_FUTURE",
                    "Future obligation",
                    "Record an already incurred obligation date.",
                )
            total = session.scalar(
                select(func.coalesce(func.sum(Payable.amount), 0)).where(
                    Payable.organization_id == context.organization_id,
                    Payable.purchase_order_id == purchase.id,
                    Payable.voided_at.is_(None),
                    Payable.deleted_at.is_(None),
                )
            )
            if Decimal(str(total)) + request.amount > purchase.total:
                raise conflict(
                    "PAYABLE_EXCEEDS_PURCHASE",
                    "Active payable principal cannot exceed the original purchase total.",
                )
            row = Payable(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                payable_number=next_document_number(session, context, "PAYABLE", "AP"),
                sales_order_id=purchase.sales_order_id,
                supplier_company_id=purchase.supplier_company_id,
                currency_code=purchase.currency_code,
                **request.model_dump(),
            )
            session.add(row)
            session.flush()
            session.refresh(row)
            self._evidence(
                session,
                context,
                row,
                action="payable.created",
                reason=request.reason,
                order_id=row.sales_order_id,
            )
            complete_command(command, row.id, "payable")
            uow.commit()
            return row.id

    def void_payable(
        self, context: RequestContext, payable_id: UUID, data: dict[str, object], *, key: str
    ) -> UUID:
        context.require(Permission.PAYABLE_WRITE)
        request = SupplierVersionCommand.model_validate(data)
        with UnitOfWork(self.factory) as uow:
            session = uow.session
            repository = SupplierFinanceRepository(session)
            command = begin_command(
                session,
                context,
                scope="payable.voided",
                key=key,
                payload={"payable_id": str(payable_id), **request.model_dump()},
            )
            row = repository.payable(context.organization_id, payable_id, lock=True)
            if command.resource_id:
                uow.commit()
                return row.id
            check_version(row.version, request.expected_version)
            paid = repository.paid_totals(context.organization_id, {row.id}).get(row.id, Decimal(0))
            if row.voided_at or paid != 0:
                raise conflict(
                    "PAYABLE_NOT_VOIDABLE",
                    "Only active obligations with zero net settlement may be voided.",
                )
            before = snapshot(row)
            row.voided_at = datetime.now(UTC)
            row.voided_by = context.user_id
            row.void_reason = request.reason
            row.updated_by = context.user_id
            session.flush()
            self._evidence(
                session,
                context,
                row,
                action="payable.voided",
                reason=request.reason,
                before=before,
                order_id=row.sales_order_id,
            )
            complete_command(command, row.id, "payable")
            uow.commit()
            return row.id

    def record_payment(self, context: RequestContext, data: dict[str, object], *, key: str) -> UUID:
        context.require(Permission.SUPPLIER_PAYMENT_RECORD)
        request = SupplierPaymentCreate.model_validate(data)
        with UnitOfWork(self.factory) as uow:
            session = uow.session
            command = begin_command(
                session,
                context,
                scope="supplier_payment.recorded",
                key=key,
                payload=request.model_dump(),
            )
            if command.resource_id:
                SupplierFinanceRepository(session).payment(
                    context.organization_id, command.resource_id
                )
                uow.commit()
                return command.resource_id
            supplier = session.scalar(
                select(Company)
                .where(
                    Company.organization_id == context.organization_id,
                    Company.id == request.supplier_company_id,
                    Company.deleted_at.is_(None),
                )
                .with_for_update(read=True, key_share=True)
            )
            if supplier is None:
                raise missing("SUPPLIER")
            role = session.scalar(
                select(CompanyRole).where(
                    CompanyRole.organization_id == context.organization_id,
                    CompanyRole.company_id == supplier.id,
                    CompanyRole.role == "SUPPLIER",
                )
            )
            if role is None:
                raise conflict(
                    "COMPANY_NOT_SUPPLIER", "Outgoing supplier payments require a supplier company."
                )
            if request.paid_on > organization_today(session, context.organization_id):
                raise ApiProblem(
                    422,
                    "SUPPLIER_PAYMENT_DATE_IN_FUTURE",
                    "Future payment",
                    "Record an already occurred outgoing payment date.",
                )
            row = SupplierPayment(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                payment_number=next_document_number(session, context, "SUPPLIER_PAYMENT", "SP"),
                kind="PAYMENT",
                **request.model_dump(),
            )
            session.add(row)
            session.flush()
            session.refresh(row)
            self._evidence(
                session, context, row, action="supplier_payment.recorded", reason=request.reason
            )
            complete_command(command, row.id, "supplier_payment")
            uow.commit()
            return row.id

    def allocate(
        self, context: RequestContext, payment_id: UUID, data: dict[str, object], *, key: str
    ) -> UUID:
        context.require(Permission.SUPPLIER_PAYMENT_ALLOCATE)
        request = SupplierPaymentAllocate.model_validate(data)
        with UnitOfWork(self.factory) as uow:
            session = uow.session
            repository = SupplierFinanceRepository(session)
            command = begin_command(
                session,
                context,
                scope="supplier_payment.allocated",
                key=key,
                payload={"payment_id": str(payment_id), **request.model_dump()},
            )
            payment = repository.payment(context.organization_id, payment_id, lock=True)
            if command.resource_id:
                uow.commit()
                return payment.id
            self._active_payment(repository, context, payment, request.expected_version)
            payables = {
                item.payable_id: repository.payable(
                    context.organization_id, item.payable_id, lock=True
                )
                for item in sorted(request.allocations, key=lambda item: item.payable_id)
            }
            allocated = sum(
                (a.amount for a in repository.allocations(context.organization_id, {payment.id})),
                Decimal(0),
            )
            requested = sum((item.amount for item in request.allocations), Decimal(0))
            if allocated + requested > payment.amount:
                raise conflict(
                    "SUPPLIER_PAYMENT_OVERALLOCATION",
                    "Allocation exceeds the payment available amount.",
                )
            totals = repository.paid_totals(context.organization_id, set(payables))
            for item in request.allocations:
                payable = payables[item.payable_id]
                check_version(payable.version, item.expected_version)
                if payable.voided_at:
                    raise conflict(
                        "PAYABLE_VOIDED", "A voided obligation cannot receive allocations."
                    )
                if (
                    payable.supplier_company_id != payment.supplier_company_id
                    or payable.currency_code != payment.currency_code
                ):
                    raise conflict(
                        "SUPPLIER_SETTLEMENT_MISMATCH",
                        "Payment and payable must share the same supplier and currency.",
                    )
                if totals.get(payable.id, Decimal(0)) + item.amount > payable.amount:
                    raise conflict(
                        "PAYABLE_OVERALLOCATION",
                        "Allocation exceeds the payable outstanding amount.",
                    )
            before_payment = snapshot(payment)
            for item in request.allocations:
                payable = payables[item.payable_id]
                before_payable = snapshot(payable)
                row = SupplierPaymentAllocation(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    payment_id=payment.id,
                    payable_id=payable.id,
                    kind="ALLOCATION",
                    amount=item.amount,
                    reason=request.reason,
                )
                session.add(row)
                payable.version += 1
                payable.updated_by = context.user_id
                session.flush()
                self._evidence(
                    session,
                    context,
                    row,
                    action="supplier_payment_allocation.created",
                    reason=request.reason,
                    order_id=payable.sales_order_id,
                )
                self._evidence(
                    session,
                    context,
                    payable,
                    action="payable.allocated",
                    reason=request.reason,
                    before=before_payable,
                    order_id=payable.sales_order_id,
                )
            payment.version += 1
            payment.updated_by = context.user_id
            session.flush()
            self._evidence(
                session,
                context,
                payment,
                action="supplier_payment.allocated",
                reason=request.reason,
                before=before_payment,
            )
            complete_command(command, payment.id, "supplier_payment")
            uow.commit()
            return payment.id

    def reverse(
        self, context: RequestContext, payment_id: UUID, data: dict[str, object], *, key: str
    ) -> UUID:
        context.require(Permission.SUPPLIER_PAYMENT_REVERSE)
        request = SupplierVersionCommand.model_validate(data)
        with UnitOfWork(self.factory) as uow:
            session = uow.session
            repository = SupplierFinanceRepository(session)
            command = begin_command(
                session,
                context,
                scope="supplier_payment.reversed",
                key=key,
                payload={"payment_id": str(payment_id), **request.model_dump()},
            )
            original = repository.payment(context.organization_id, payment_id, lock=True)
            if command.resource_id:
                repository.payment(context.organization_id, command.resource_id)
                uow.commit()
                return command.resource_id
            self._active_payment(repository, context, original, request.expected_version)
            allocations = repository.allocations(context.organization_id, {original.id})
            payables = {
                pid: repository.payable(context.organization_id, pid, lock=True)
                for pid in sorted({a.payable_id for a in allocations})
            }
            reverse = SupplierPayment(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                payment_number=next_document_number(session, context, "SUPPLIER_PAYMENT", "SP"),
                supplier_company_id=original.supplier_company_id,
                kind="REVERSAL",
                amount=original.amount,
                currency_code=original.currency_code,
                paid_on=organization_today(session, context.organization_id),
                method=original.method,
                reference=original.reference,
                reason=request.reason,
                reversal_of_payment_id=original.id,
            )
            session.add(reverse)
            session.flush()
            for allocation in allocations:
                payable = payables[allocation.payable_id]
                row = SupplierPaymentAllocation(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    payment_id=reverse.id,
                    payable_id=payable.id,
                    kind="REVERSAL",
                    amount=allocation.amount,
                    reason=request.reason,
                    reversal_of_allocation_id=allocation.id,
                )
                session.add(row)
                session.flush()
                self._evidence(
                    session,
                    context,
                    row,
                    action="supplier_payment_allocation.reversed",
                    reason=request.reason,
                    order_id=payable.sales_order_id,
                )
            for payable in payables.values():
                before = snapshot(payable)
                payable.version += 1
                payable.updated_by = context.user_id
                session.flush()
                self._evidence(
                    session,
                    context,
                    payable,
                    action="payable.settlement_reversed",
                    reason=request.reason,
                    before=before,
                    order_id=payable.sales_order_id,
                )
            self._evidence(
                session, context, reverse, action="supplier_payment.reversed", reason=request.reason
            )
            complete_command(command, reverse.id, "supplier_payment")
            uow.commit()
            return reverse.id

    @staticmethod
    def _active_payment(
        repository: SupplierFinanceRepository,
        context: RequestContext,
        row: SupplierPayment,
        expected: int,
    ) -> None:
        check_version(row.version, expected)
        if row.kind != "PAYMENT" or repository.reversals(context.organization_id, {row.id}):
            raise conflict(
                "SUPPLIER_PAYMENT_INACTIVE",
                "Only an unreversed original payment accepts this command.",
            )
