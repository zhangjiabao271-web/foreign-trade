from collections.abc import Sequence
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select, tuple_
from sqlalchemy.orm import Session

from app.auth.errors import ApiProblem
from app.finance.supplier_models import Payable, SupplierPayment, SupplierPaymentAllocation


def missing(kind: str) -> ApiProblem:
    return ApiProblem(
        404,
        f"{kind}_NOT_FOUND",
        "Record not found",
        "The financial record was not found in this organization and filter scope.",
    )


class SupplierFinanceRepository:
    def __init__(self, session: Session):
        self.session = session

    def payable(self, organization_id: UUID, payable_id: UUID, *, lock: bool = False) -> Payable:
        query = select(Payable).where(
            Payable.organization_id == organization_id,
            Payable.id == payable_id,
            Payable.deleted_at.is_(None),
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self.session.scalar(query)
        if row is None:
            raise missing("PAYABLE")
        return row

    def payment(
        self, organization_id: UUID, payment_id: UUID, *, lock: bool = False
    ) -> SupplierPayment:
        query = select(SupplierPayment).where(
            SupplierPayment.organization_id == organization_id,
            SupplierPayment.id == payment_id,
            SupplierPayment.deleted_at.is_(None),
        )
        if lock:
            query = query.with_for_update().execution_options(populate_existing=True)
        row = self.session.scalar(query)
        if row is None:
            raise missing("SUPPLIER_PAYMENT")
        return row

    def payables(
        self,
        organization_id: UUID,
        *,
        purchase_id: UUID | None,
        supplier_id: UUID | None,
        currency: str | None,
        cursor: UUID | None,
        limit: int,
    ) -> Sequence[Payable]:
        query = select(Payable).where(
            Payable.organization_id == organization_id, Payable.deleted_at.is_(None)
        )
        if purchase_id:
            query = query.where(Payable.purchase_order_id == purchase_id)
        if supplier_id:
            query = query.where(Payable.supplier_company_id == supplier_id)
        if currency:
            query = query.where(Payable.currency_code == currency)
        if cursor:
            anchor = self.session.scalar(query.where(Payable.id == cursor))
            if anchor is None:
                raise missing("PAYABLE_CURSOR")
            query = query.where(
                tuple_(Payable.created_at, Payable.id) < (anchor.created_at, anchor.id)
            )
        return self.session.scalars(
            query.order_by(Payable.created_at.desc(), Payable.id.desc()).limit(limit + 1)
        ).all()

    def payments(
        self,
        organization_id: UUID,
        *,
        supplier_id: UUID | None,
        currency: str | None,
        cursor: UUID | None,
        limit: int,
    ) -> Sequence[SupplierPayment]:
        query = select(SupplierPayment).where(
            SupplierPayment.organization_id == organization_id, SupplierPayment.deleted_at.is_(None)
        )
        if supplier_id:
            query = query.where(SupplierPayment.supplier_company_id == supplier_id)
        if currency:
            query = query.where(SupplierPayment.currency_code == currency)
        if cursor:
            anchor = self.session.scalar(query.where(SupplierPayment.id == cursor))
            if anchor is None:
                raise missing("SUPPLIER_PAYMENT_CURSOR")
            query = query.where(
                tuple_(SupplierPayment.created_at, SupplierPayment.id)
                < (anchor.created_at, anchor.id)
            )
        return self.session.scalars(
            query.order_by(SupplierPayment.created_at.desc(), SupplierPayment.id.desc()).limit(
                limit + 1
            )
        ).all()

    def allocations(
        self, organization_id: UUID, payment_ids: set[UUID]
    ) -> Sequence[SupplierPaymentAllocation]:
        return self.session.scalars(
            select(SupplierPaymentAllocation)
            .where(
                SupplierPaymentAllocation.organization_id == organization_id,
                SupplierPaymentAllocation.payment_id.in_(payment_ids),
                SupplierPaymentAllocation.deleted_at.is_(None),
            )
            .order_by(SupplierPaymentAllocation.created_at, SupplierPaymentAllocation.id)
        ).all()

    def paid_totals(self, organization_id: UUID, payable_ids: set[UUID]) -> dict[UUID, Decimal]:
        row = SupplierPaymentAllocation
        effect = case((row.kind == "REVERSAL", -row.amount), else_=row.amount)
        rows = self.session.execute(
            select(row.payable_id, func.sum(effect))
            .where(
                row.organization_id == organization_id,
                row.payable_id.in_(payable_ids),
                row.deleted_at.is_(None),
            )
            .group_by(row.payable_id)
        ).all()
        return {payable_id: amount for payable_id, amount in rows}

    def reversals(self, organization_id: UUID, payment_ids: set[UUID]) -> dict[UUID, UUID]:
        row = SupplierPayment
        rows = self.session.execute(
            select(row.reversal_of_payment_id, row.id).where(
                row.organization_id == organization_id,
                row.reversal_of_payment_id.in_(payment_ids),
                row.deleted_at.is_(None),
            )
        ).all()
        return {
            original_id: reverse_id for original_id, reverse_id in rows if original_id is not None
        }
