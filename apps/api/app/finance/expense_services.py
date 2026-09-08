from collections.abc import Sequence
from decimal import Decimal, localcontext
from uuid import UUID

from sqlalchemy import case, func, select, tuple_
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.unit_of_work import UnitOfWork
from app.finance.expense_models import Expense, ExpenseKind, ExpenseTreatment
from app.finance.expense_schemas import ExpenseCreate, ExpenseReverse, ExpenseSummary
from app.finance.services import organization_today
from app.platform.idempotency import begin_command, complete_command
from app.platform.numbering import next_document_number
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.sales.models import SalesOrder
from app.sales.services import quantize_money
from app.work.records import record_activity


class ExpenseRepository:
    def __init__(self, session: Session):
        self.session = session

    def order(self, organization_id: UUID, order_id: UUID, *, lock: bool = False) -> SalesOrder:
        query = select(SalesOrder).where(
            SalesOrder.organization_id == organization_id,
            SalesOrder.id == order_id,
            SalesOrder.deleted_at.is_(None),
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self.session.scalar(query)
        if row is None:
            raise ApiProblem(
                404, "SALES_ORDER_NOT_FOUND", "Order not found", "The order was not found."
            )
        return row

    def get(
        self, organization_id: UUID, order_id: UUID, expense_id: UUID, *, lock: bool = False
    ) -> Expense:
        query = select(Expense).where(
            Expense.organization_id == organization_id,
            Expense.sales_order_id == order_id,
            Expense.id == expense_id,
            Expense.deleted_at.is_(None),
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self.session.scalar(query)
        if row is None:
            raise ApiProblem(
                404,
                "EXPENSE_NOT_FOUND",
                "Expense not found",
                "The expense was not found for this order.",
            )
        return row

    def list(
        self, organization_id: UUID, order_id: UUID, *, limit: int, cursor: UUID | None
    ) -> Sequence[Expense]:
        query = select(Expense).where(
            Expense.organization_id == organization_id,
            Expense.sales_order_id == order_id,
            Expense.deleted_at.is_(None),
        )
        if cursor:
            anchor = self.get(organization_id, order_id, cursor)
            query = query.where(
                tuple_(Expense.created_at, Expense.id) < (anchor.created_at, anchor.id)
            )
        return self.session.scalars(
            query.order_by(Expense.created_at.desc(), Expense.id.desc()).limit(limit + 1)
        ).all()

    def reversals(self, organization_id: UUID, order_id: UUID, ids: set[UUID]) -> dict[UUID, UUID]:
        if not ids:
            return {}
        rows = self.session.execute(
            select(Expense.reversal_of_expense_id, Expense.id).where(
                Expense.organization_id == organization_id,
                Expense.sales_order_id == order_id,
                Expense.reversal_of_expense_id.in_(ids),
                Expense.deleted_at.is_(None),
            )
        ).all()
        return {original: reversal for original, reversal in rows}

    def net_costs(self, organization_id: UUID, order_id: UUID) -> dict[str, Decimal]:
        effect = case(
            (Expense.kind == ExpenseKind.REVERSAL, -Expense.order_currency_amount),
            else_=Expense.order_currency_amount,
        )
        rows = self.session.execute(
            select(Expense.cost_treatment, func.sum(effect))
            .where(
                Expense.organization_id == organization_id,
                Expense.sales_order_id == order_id,
                Expense.deleted_at.is_(None),
            )
            .group_by(Expense.cost_treatment)
        ).all()
        return {treatment: quantize_money(Decimal(str(total))) for treatment, total in rows}


class ExpenseQuery:
    def __init__(self, session: Session):
        self.repository = ExpenseRepository(session)

    def list(
        self, context: RequestContext, order_id: UUID, *, limit: int, cursor: UUID | None
    ) -> tuple[Sequence[Expense], dict[UUID, UUID]]:
        context.require(Permission.EXPENSE_READ)
        self.repository.order(context.organization_id, order_id)
        rows = self.repository.list(context.organization_id, order_id, limit=limit, cursor=cursor)
        return rows, self.repository.reversals(
            context.organization_id, order_id, {row.id for row in rows}
        )

    def get(
        self, context: RequestContext, order_id: UUID, expense_id: UUID
    ) -> tuple[Expense, UUID | None]:
        context.require(Permission.EXPENSE_READ)
        self.repository.order(context.organization_id, order_id)
        row = self.repository.get(context.organization_id, order_id, expense_id)
        return row, self.repository.reversals(context.organization_id, order_id, {expense_id}).get(
            expense_id
        )

    def summary(self, context: RequestContext, order_id: UUID) -> ExpenseSummary:
        context.require(Permission.EXPENSE_READ, Permission.PROFIT_READ)
        order = self.repository.order(context.organization_id, order_id)
        totals = self.repository.net_costs(context.organization_id, order_id)
        additional = totals.get(ExpenseTreatment.ADDITIONAL, Decimal("0.0000"))
        return ExpenseSummary(
            order_currency_code=order.currency_code,
            net_additional_cost=additional,
            net_included_cost=totals.get(ExpenseTreatment.INCLUDED_IN_QUOTATION, Decimal("0.0000")),
            quoted_gross_profit=order.gross_profit,
            adjusted_forecast_gross_profit=quantize_money(order.gross_profit - additional),
        )


class ExpenseService:
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

    def record(
        self, context: RequestContext, order_id: UUID, data: dict[str, object], *, key: str
    ) -> Expense:
        context.require(Permission.EXPENSE_WRITE)
        request = ExpenseCreate.model_validate(data)
        with UnitOfWork(self.factory) as uow:
            session = uow.session
            command = begin_command(
                session,
                context,
                scope="expense.recorded",
                key=key,
                payload={"order_id": str(order_id), **request.model_dump()},
            )
            repository = ExpenseRepository(session)
            order = repository.order(context.organization_id, order_id, lock=True)
            if command.resource_id:
                row = repository.get(context.organization_id, order_id, command.resource_id)
                uow.commit()
                return row
            if order.confirmed_at is None:
                raise ApiProblem(
                    409,
                    "ORDER_NOT_CONFIRMED",
                    "Order not confirmed",
                    "Record order expenses only after confirmation.",
                )
            if request.incurred_on > organization_today(session, context.organization_id):
                raise ApiProblem(
                    422,
                    "EXPENSE_DATE_IN_FUTURE",
                    "Future expense",
                    "Record an already incurred expense date.",
                )
            if request.currency_code == order.currency_code and request.exchange_rate != 1:
                raise ApiProblem(
                    422,
                    "EXPENSE_SAME_CURRENCY_RATE",
                    "Invalid exchange rate",
                    "Same-currency expenses require an exchange rate of one.",
                )
            with localcontext() as precision:
                precision.prec = 50
                converted = quantize_money(request.amount * request.exchange_rate)
            if converted > Decimal("99999999999999.9999"):
                raise ApiProblem(
                    422,
                    "EXPENSE_AMOUNT_OVERFLOW",
                    "Amount too large",
                    "The converted expense exceeds supported precision.",
                )
            row = Expense(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                sales_order_id=order_id,
                expense_number=next_document_number(session, context, "EXPENSE", "EX"),
                kind=ExpenseKind.EXPENSE,
                order_currency_code=order.currency_code,
                order_currency_amount=converted,
                **request.model_dump(),
            )
            session.add(row)
            session.flush()
            session.refresh(row)
            self._record_evidence(session, context, row, "recorded")
            complete_command(command, row.id, "expense")
            uow.commit()
            return row

    def reverse(
        self,
        context: RequestContext,
        order_id: UUID,
        expense_id: UUID,
        data: dict[str, object],
        *,
        key: str,
    ) -> Expense:
        context.require(Permission.EXPENSE_WRITE)
        request = ExpenseReverse.model_validate(data)
        with UnitOfWork(self.factory) as uow:
            session = uow.session
            command = begin_command(
                session,
                context,
                scope="expense.reversed",
                key=key,
                payload={
                    "order_id": str(order_id),
                    "expense_id": str(expense_id),
                    **request.model_dump(),
                },
            )
            repository = ExpenseRepository(session)
            repository.order(context.organization_id, order_id, lock=True)
            if command.resource_id:
                row = repository.get(context.organization_id, order_id, command.resource_id)
                uow.commit()
                return row
            original = repository.get(context.organization_id, order_id, expense_id, lock=True)
            if original.version != request.expected_version:
                raise ApiProblem(
                    409,
                    "VERSION_CONFLICT",
                    "Version conflict",
                    "Refresh and review the expense before reversing.",
                )
            if original.kind != ExpenseKind.EXPENSE or repository.reversals(
                context.organization_id, order_id, {expense_id}
            ):
                raise ApiProblem(
                    409,
                    "EXPENSE_NOT_REVERSIBLE",
                    "Expense not reversible",
                    "Only an unreversed original expense can be reversed.",
                )
            copied = {
                field: getattr(original, field)
                for field in (
                    "category",
                    "cost_treatment",
                    "amount",
                    "currency_code",
                    "exchange_rate",
                    "order_currency_code",
                    "order_currency_amount",
                    "description",
                    "evidence_reference",
                )
            }
            row = Expense(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                sales_order_id=order_id,
                expense_number=next_document_number(session, context, "EXPENSE", "EX"),
                kind=ExpenseKind.REVERSAL,
                reversal_of_expense_id=expense_id,
                incurred_on=organization_today(session, context.organization_id),
                reason=request.reason,
                **copied,
            )
            session.add(row)
            session.flush()
            session.refresh(row)
            self._record_evidence(session, context, row, "reversed")
            complete_command(command, row.id, "expense")
            uow.commit()
            return row

    def _record_evidence(
        self, session: Session, context: RequestContext, row: Expense, action: str
    ) -> None:
        after: dict[str, object] = {
            field: str(getattr(row, field))
            for field in (
                "expense_number",
                "kind",
                "sales_order_id",
                "category",
                "cost_treatment",
                "amount",
                "currency_code",
                "exchange_rate",
                "order_currency_amount",
                "order_currency_code",
                "incurred_on",
                "description",
                "evidence_reference",
                "reversal_of_expense_id",
            )
        }
        record_activity(
            session,
            context,
            subject_type="sales_order",
            subject_id=row.sales_order_id,
            activity_type=f"expense.{action}",
            summary=f"{row.expense_number}: {action}",
            details={"expense_id": str(row.id)},
        )
        self.audit.record(
            session,
            context,
            action=f"expense.{action}",
            target_type="expense",
            target_id=row.id,
            before=None,
            after=after,
            reason=row.reason,
        )
        self.outbox.record(
            session,
            context,
            DomainEvent(
                f"expense.{action}.v1",
                "expense",
                row.id,
                {"expense_id": str(row.id), "sales_order_id": str(row.sales_order_id)},
            ),
        )
