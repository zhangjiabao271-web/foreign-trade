from datetime import date
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Date, Select, case, func, literal, select
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, require_permissions
from app.auth.permissions import Permission
from app.crm.models import Lead
from app.documents.checklists import missing_document_types
from app.documents.enums import DocumentLinkTargetType
from app.export.models import CustomsDeclaration, TaxRefundCase
from app.finance.models import PaymentAllocation, Receivable
from app.finance.services import organization_today
from app.fulfillment.models import Shipment
from app.sales.models import Quotation, QuotationVersion, SalesOrder


class QueueKind(StrEnum):
    LEADS = "leads"
    QUOTATIONS = "quotations"
    DEPOSITS = "deposits"
    PREPARATION = "preparation"
    SHIPMENTS = "shipments"
    RECEIVABLES = "receivables"
    CUSTOMS = "customs"
    REFUNDS = "refunds"


QUEUE_ACCESS = {
    QueueKind.LEADS: (Permission.LEAD_READ, "/leads", "跟进客户"),
    QueueKind.QUOTATIONS: (Permission.QUOTATION_READ, "/quotations", "确认客户回复"),
    QueueKind.DEPOSITS: (Permission.ORDER_READ, "/orders", "核对定金到账与核销"),
    QueueKind.PREPARATION: (Permission.ORDER_READ, "/orders", "推进采购与备货"),
    QueueKind.SHIPMENTS: (Permission.SHIPMENT_READ, "/shipments", "检查文件与出运节点"),
    QueueKind.RECEIVABLES: (Permission.RECEIVABLE_READ, "/orders", "跟进到期款项"),
    QueueKind.CUSTOMS: (Permission.EXPORT_READ, "/export/customs", "跟进人工报关"),
    QueueKind.REFUNDS: (Permission.EXPORT_READ, "/export/refunds", "跟进人工退税"),
}


class ActionItem(BaseModel):
    id: UUID
    title: str
    status: str
    due_date: date | None
    overdue: bool
    href: str
    next_action: str
    missing_document_types: list[str]


class ActionPage(BaseModel):
    queue: QueueKind
    business_date: date
    items: list[ActionItem]
    has_more: bool
    next_offset: int | None


class OverviewQueryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def page(
        self, context: RequestContext, queue: QueueKind, *, offset: int, limit: int
    ) -> ActionPage:
        context.require(Permission.OVERVIEW_READ)
        permission, path, action = QUEUE_ACCESS[queue]
        context.require(permission)
        today = organization_today(self.session, context.organization_id)
        query = self._query(context.organization_id, queue, today)
        rows = self.session.execute(query.offset(offset).limit(limit + 1)).all()
        page = rows[:limit]
        requirements: dict[UUID, list[str]] = {}
        target: DocumentLinkTargetType | None = None
        if queue == QueueKind.SHIPMENTS:
            target = DocumentLinkTargetType.SHIPMENT
            requirements = {row.id: ["COMMERCIAL_INVOICE", "PACKING_LIST"] for row in page}
        elif queue in {QueueKind.CUSTOMS, QueueKind.REFUNDS}:
            target = (
                DocumentLinkTargetType.CUSTOMS_DECLARATION
                if queue == QueueKind.CUSTOMS
                else DocumentLinkTargetType.TAX_REFUND_CASE
            )
            requirements = {row.id: row.required_document_types for row in page}
        missing = (
            missing_document_types(
                self.session,
                organization_id=context.organization_id,
                target_type=target,
                requirements=requirements,
            )
            if target is not None
            else {}
        )
        return ActionPage(
            queue=queue,
            business_date=today,
            items=[
                ActionItem(
                    id=row.id,
                    title=row.title,
                    status=row.status,
                    due_date=row.due_date,
                    overdue=row.due_date is not None and row.due_date < today,
                    href=f"{path}/{row.target_id}",
                    next_action=action,
                    missing_document_types=missing.get(row.id, []),
                )
                for row in page
            ],
            has_more=len(rows) > limit,
            next_offset=offset + limit if len(rows) > limit else None,
        )

    @staticmethod
    def _query(
        organization_id: UUID, queue: QueueKind, today: date
    ) -> (
        Select[tuple[UUID, str, str, date, UUID]]
        | Select[tuple[UUID, str, str, date | None, UUID]]
        | Select[tuple[UUID, str, str, date | None, UUID, list[str]]]
    ):
        # Each branch selects a bounded projection, never loading per-row relationships.
        if queue == QueueKind.LEADS:
            return (
                select(
                    Lead.id,
                    Lead.company_name.label("title"),
                    Lead.status,
                    literal(None, Date).label("due_date"),
                    Lead.id.label("target_id"),
                )
                .where(
                    Lead.organization_id == organization_id,
                    Lead.deleted_at.is_(None),
                    Lead.status.not_in(["CONVERTED", "DISQUALIFIED"]),
                )
                .order_by(Lead.updated_at, Lead.id)
            )
        if queue == QueueKind.QUOTATIONS:
            return (
                select(
                    QuotationVersion.id,
                    Quotation.quotation_number.label("title"),
                    QuotationVersion.status,
                    QuotationVersion.valid_until.label("due_date"),
                    Quotation.id.label("target_id"),
                )
                .join(
                    Quotation,
                    (Quotation.id == QuotationVersion.quotation_id)
                    & (Quotation.organization_id == QuotationVersion.organization_id),
                )
                .where(
                    QuotationVersion.organization_id == organization_id,
                    QuotationVersion.deleted_at.is_(None),
                    Quotation.deleted_at.is_(None),
                    QuotationVersion.is_current.is_(True),
                    QuotationVersion.status.in_(["SENT", "CUSTOMER_REVIEW"]),
                )
                .order_by(QuotationVersion.valid_until, QuotationVersion.id)
            )
        if queue in {QueueKind.DEPOSITS, QueueKind.PREPARATION}:
            states = (
                ["DEPOSIT_PENDING"]
                if queue == QueueKind.DEPOSITS
                else ["EXECUTING", "READY_TO_SHIP"]
            )
            due = (
                SalesOrder.deposit_due_date if queue == QueueKind.DEPOSITS else literal(None, Date)
            )
            return (
                select(
                    SalesOrder.id,
                    SalesOrder.order_number.label("title"),
                    SalesOrder.status,
                    due.label("due_date"),
                    SalesOrder.id.label("target_id"),
                )
                .where(
                    SalesOrder.organization_id == organization_id,
                    SalesOrder.deleted_at.is_(None),
                    SalesOrder.status.in_(states),
                )
                .order_by(due.asc().nulls_last(), SalesOrder.created_at, SalesOrder.id)
            )
        if queue == QueueKind.SHIPMENTS:
            return (
                select(
                    Shipment.id,
                    Shipment.shipment_number.label("title"),
                    Shipment.status,
                    Shipment.planned_departure_date.label("due_date"),
                    Shipment.id.label("target_id"),
                )
                .where(
                    Shipment.organization_id == organization_id,
                    Shipment.deleted_at.is_(None),
                    Shipment.status.in_(["PLANNING", "BOOKED", "READY", "CUSTOMS"]),
                )
                .order_by(Shipment.planned_departure_date.asc().nulls_last(), Shipment.id)
            )
        if queue == QueueKind.RECEIVABLES:
            net = func.coalesce(
                func.sum(
                    case(
                        (PaymentAllocation.kind == "ALLOCATION", PaymentAllocation.amount),
                        else_=-PaymentAllocation.amount,
                    )
                ),
                0,
            )
            return (
                select(
                    Receivable.id,
                    Receivable.receivable_number.label("title"),
                    case((Receivable.due_date < today, "OVERDUE"), else_="DUE").label("status"),
                    Receivable.due_date,
                    Receivable.sales_order_id.label("target_id"),
                )
                .outerjoin(
                    PaymentAllocation,
                    (PaymentAllocation.organization_id == Receivable.organization_id)
                    & (PaymentAllocation.receivable_id == Receivable.id)
                    & PaymentAllocation.deleted_at.is_(None),
                )
                .where(
                    Receivable.organization_id == organization_id,
                    Receivable.deleted_at.is_(None),
                    Receivable.due_date <= today,
                )
                .group_by(Receivable.id)
                .having(net < Receivable.amount)
                .order_by(Receivable.due_date, Receivable.id)
            )
        model = CustomsDeclaration if queue == QueueKind.CUSTOMS else TaxRefundCase
        title = (
            CustomsDeclaration.declaration_number
            if queue == QueueKind.CUSTOMS
            else TaxRefundCase.case_number
        )
        return (
            select(
                model.id,
                title.label("title"),
                model.status,
                model.follow_up_date.label("due_date"),
                model.id.label("target_id"),
                model.required_document_types,
            )
            .where(
                model.organization_id == organization_id,
                model.deleted_at.is_(None),
                model.status.not_in(["CLEARED", "REFUNDED", "REJECTED"]),
            )
            .order_by(model.follow_up_date.asc().nulls_last(), model.created_at, model.id)
        )


router = APIRouter(prefix="/api/v1/overview", tags=["overview"])


@router.get("/{queue}", response_model=ActionPage)
def read_action_queue(
    queue: QueueKind,
    context: Annotated[RequestContext, Depends(require_permissions(Permission.OVERVIEW_READ))],
    session: Annotated[Session, Depends(get_database_session)],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ActionPage:
    return OverviewQueryService(session).page(context, queue, offset=offset, limit=limit)
