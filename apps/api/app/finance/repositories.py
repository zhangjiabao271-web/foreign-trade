from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, or_, select, tuple_
from sqlalchemy.orm import Session

from app.auth.errors import ApiProblem
from app.core.repositories import TenantRepository
from app.finance.enums import AllocationKind
from app.finance.models import Payment, PaymentAllocation, Receivable


class ReceivableRepository(TenantRepository[Receivable]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Receivable)

    def list_with_allocated(
        self, *, organization_id: UUID, sales_order_id: UUID | None, limit: int
    ) -> Sequence[tuple[Receivable, Decimal]]:
        effect = case(
            (PaymentAllocation.kind == AllocationKind.ALLOCATION, PaymentAllocation.amount),
            else_=-PaymentAllocation.amount,
        )
        statement = (
            select(Receivable, func.coalesce(func.sum(effect), 0))
            .outerjoin(
                PaymentAllocation,
                (PaymentAllocation.organization_id == Receivable.organization_id)
                & (PaymentAllocation.receivable_id == Receivable.id)
                & (PaymentAllocation.deleted_at.is_(None)),
            )
            .where(
                Receivable.organization_id == organization_id,
                Receivable.deleted_at.is_(None),
            )
            .group_by(Receivable.id)
            .order_by(Receivable.due_date, Receivable.created_at)
            .limit(limit)
        )
        if sales_order_id is not None:
            statement = statement.where(Receivable.sales_order_id == sales_order_id)
        return [
            (receivable, Decimal(str(allocated)))
            for receivable, allocated in self.session.execute(statement).all()
        ]

    def locked(self, *, organization_id: UUID, ids: set[UUID]) -> Sequence[Receivable]:
        return self.session.scalars(
            self._select_for_organization(organization_id)
            .where(Receivable.id.in_(ids))
            .order_by(Receivable.id)
            .with_for_update()
        ).all()

    def locked_for_order(
        self, *, organization_id: UUID, sales_order_id: UUID
    ) -> Sequence[Receivable]:
        rows = self.session.scalars(
            self._select_for_organization(organization_id)
            .where(Receivable.sales_order_id == sales_order_id)
            .order_by(Receivable.id)
            .with_for_update()
        ).all()
        # Lock consistently with allocation/refresh, then preserve the installment display order.
        return sorted(rows, key=lambda row: row.receivable_number)

    def allocated_totals(
        self, *, organization_id: UUID, receivable_ids: set[UUID]
    ) -> dict[UUID, Decimal]:
        if not receivable_ids:
            return {}
        effect = case(
            (PaymentAllocation.kind == AllocationKind.ALLOCATION, PaymentAllocation.amount),
            else_=-PaymentAllocation.amount,
        )
        rows = self.session.execute(
            select(PaymentAllocation.receivable_id, func.coalesce(func.sum(effect), 0))
            .where(
                PaymentAllocation.organization_id == organization_id,
                PaymentAllocation.receivable_id.in_(receivable_ids),
                PaymentAllocation.deleted_at.is_(None),
            )
            .group_by(PaymentAllocation.receivable_id)
        ).all()
        return {receivable_id: Decimal(str(value)) for receivable_id, value in rows}


class PaymentRepository(TenantRepository[Payment]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Payment)

    def list_recent(
        self,
        *,
        organization_id: UUID,
        limit: int,
        company_id: UUID | None = None,
        currency_code: str | None = None,
        query: str | None = None,
        cursor: UUID | None = None,
    ) -> Sequence[Payment]:
        statement = self._select_for_organization(organization_id)
        if company_id is not None:
            statement = statement.where(Payment.company_id == company_id)
        if currency_code is not None:
            statement = statement.where(Payment.currency_code == currency_code)
        if query and query.strip():
            needle = query.strip().lower()
            statement = statement.where(
                or_(
                    func.lower(Payment.payment_number).contains(needle, autoescape=True),
                    func.lower(Payment.reference).contains(needle, autoescape=True),
                )
            )
        if cursor is not None:
            anchor = self.session.scalar(statement.where(Payment.id == cursor))
            if anchor is None:
                raise ApiProblem(
                    404,
                    "PAYMENT_NOT_FOUND",
                    "Payment not found",
                    "The payment cursor was not found in this search.",
                )
            statement = statement.where(
                tuple_(Payment.received_at, Payment.created_at, Payment.id)
                < (anchor.received_at, anchor.created_at, anchor.id)
            )
        return self.session.scalars(
            statement.order_by(
                Payment.received_at.desc(), Payment.created_at.desc(), Payment.id.desc()
            ).limit(limit)
        ).all()

    def get_for_update(self, *, organization_id: UUID, payment_id: UUID) -> Payment | None:
        return self.session.scalar(
            self._select_for_organization(organization_id)
            .where(Payment.id == payment_id)
            .with_for_update()
        )

    def reversal_for(self, *, organization_id: UUID, payment_id: UUID) -> Payment | None:
        return self.session.scalar(
            self._select_for_organization(organization_id).where(
                Payment.reversal_of_payment_id == payment_id
            )
        )

    def allocations(
        self, *, organization_id: UUID, payment_id: UUID
    ) -> Sequence[PaymentAllocation]:
        return self.allocations_for_payments(
            organization_id=organization_id, payment_ids={payment_id}
        )

    def allocations_for_payments(
        self, *, organization_id: UUID, payment_ids: set[UUID]
    ) -> Sequence[PaymentAllocation]:
        return self.session.scalars(
            select(PaymentAllocation)
            .where(
                PaymentAllocation.organization_id == organization_id,
                PaymentAllocation.payment_id.in_(payment_ids),
                PaymentAllocation.deleted_at.is_(None),
            )
            .order_by(PaymentAllocation.allocated_at, PaymentAllocation.id)
        ).all()

    def allocated_amount(self, *, organization_id: UUID, payment_id: UUID) -> Decimal:
        value = self.session.scalar(
            select(func.coalesce(func.sum(PaymentAllocation.amount), 0)).where(
                PaymentAllocation.organization_id == organization_id,
                PaymentAllocation.payment_id == payment_id,
                PaymentAllocation.deleted_at.is_(None),
            )
        )
        return Decimal(str(value))
