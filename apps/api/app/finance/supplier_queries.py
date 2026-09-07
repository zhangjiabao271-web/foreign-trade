from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.finance.services import organization_today
from app.finance.supplier_models import Payable, SupplierPayment, SupplierPaymentAllocation
from app.finance.supplier_repositories import SupplierFinanceRepository
from app.finance.supplier_schemas import (
    PayableListResponse,
    PayableResponse,
    SupplierPaymentListResponse,
    SupplierPaymentResponse,
)
from app.sales.services import quantize_money


def payable_response(row: Payable, paid: Decimal, today: date) -> PayableResponse:
    status = "PENDING"
    if row.voided_at:
        status = "VOIDED"
    elif paid >= row.amount:
        status = "PAID"
    elif paid > 0:
        status = "PARTIALLY_PAID"
    elif row.due_date < today:
        status = "OVERDUE"
    elif row.due_date == today:
        status = "DUE"
    fields = {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
        if column.name in PayableResponse.model_fields
    }
    return PayableResponse.model_validate(
        {
            **fields,
            "paid_amount": quantize_money(paid),
            "balance": quantize_money(Decimal(0) if row.voided_at else row.amount - paid),
            "status": status,
        }
    )


def payment_response(
    row: SupplierPayment, allocations: list[SupplierPaymentAllocation], reversal: UUID | None
) -> SupplierPaymentResponse:
    allocated = sum((a.amount for a in allocations), Decimal(0))
    fields = {
        column.name: getattr(row, column.name)
        for column in row.__table__.columns
        if column.name in SupplierPaymentResponse.model_fields
    }
    return SupplierPaymentResponse.model_validate(
        {
            **fields,
            "reversed_by_payment_id": reversal,
            "allocated_amount": quantize_money(allocated),
            "available_amount": quantize_money(
                row.amount - allocated if row.kind == "PAYMENT" and not reversal else Decimal(0)
            ),
            "allocations": allocations,
        }
    )


class SupplierFinanceQuery:
    def __init__(self, session: Session):
        self.session = session
        self.repository = SupplierFinanceRepository(session)

    def payable(self, context: RequestContext, payable_id: UUID) -> PayableResponse:
        context.require(Permission.PAYABLE_READ)
        row = self.repository.payable(context.organization_id, payable_id)
        paid = self.repository.paid_totals(context.organization_id, {row.id})
        return payable_response(
            row,
            paid.get(row.id, Decimal(0)),
            organization_today(self.session, context.organization_id),
        )

    def payment(self, context: RequestContext, payment_id: UUID) -> SupplierPaymentResponse:
        context.require(Permission.SUPPLIER_PAYMENT_READ)
        row = self.repository.payment(context.organization_id, payment_id)
        allocations = self.repository.allocations(context.organization_id, {row.id})
        reverse = self.repository.reversals(context.organization_id, {row.id})
        return payment_response(row, list(allocations), reverse.get(row.id))

    def payables(
        self,
        context: RequestContext,
        *,
        purchase_id: UUID | None,
        supplier_id: UUID | None,
        currency: str | None,
        cursor: UUID | None,
        limit: int,
    ) -> PayableListResponse:
        context.require(Permission.PAYABLE_READ)
        rows = self.repository.payables(
            context.organization_id,
            purchase_id=purchase_id,
            supplier_id=supplier_id,
            currency=currency,
            cursor=cursor,
            limit=limit,
        )
        page = rows[:limit]
        totals = self.repository.paid_totals(context.organization_id, {r.id for r in page})
        today = organization_today(self.session, context.organization_id)
        return PayableListResponse(
            items=[payable_response(r, totals.get(r.id, Decimal(0)), today) for r in page],
            has_more=len(rows) > limit,
            next_cursor=page[-1].id if len(rows) > limit else None,
        )

    def payments(
        self,
        context: RequestContext,
        *,
        supplier_id: UUID | None,
        currency: str | None,
        cursor: UUID | None,
        limit: int,
    ) -> SupplierPaymentListResponse:
        context.require(Permission.SUPPLIER_PAYMENT_READ)
        rows = self.repository.payments(
            context.organization_id,
            supplier_id=supplier_id,
            currency=currency,
            cursor=cursor,
            limit=limit,
        )
        page = rows[:limit]
        ids = {r.id for r in page}
        groups: dict[UUID, list[SupplierPaymentAllocation]] = defaultdict(list)
        for allocation in self.repository.allocations(context.organization_id, ids):
            groups[allocation.payment_id].append(allocation)
        reversals = self.repository.reversals(context.organization_id, ids)
        return SupplierPaymentListResponse(
            items=[payment_response(r, groups[r.id], reversals.get(r.id)) for r in page],
            has_more=len(rows) > limit,
            next_cursor=page[-1].id if len(rows) > limit else None,
        )
