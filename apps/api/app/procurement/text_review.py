from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.content_review import ContentReviewRequest, ContentReviewSnapshot
from app.core.unit_of_work import UnitOfWork
from app.platform.idempotency import begin_command, complete_command
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.procurement.content import content_digest, is_released, text_fields
from app.procurement.models import PurchaseOrder, PurchaseOrderItem
from app.procurement.repositories import PurchaseOrderRepository
from app.sales.models import SalesOrder
from app.work.models import Activity


class PurchaseTextReviewRequest(ContentReviewRequest):
    pass


class PurchaseTextReviewResponse(ContentReviewSnapshot):
    pass


def require_content(
    session: Session, context: RequestContext, record_id: UUID, *, lock: bool = False
) -> tuple[PurchaseOrder, Sequence[PurchaseOrderItem]]:
    context.require(Permission.PROFIT_READ, Permission.PROCUREMENT_READ)
    query = select(PurchaseOrder).where(
        PurchaseOrder.organization_id == context.organization_id,
        PurchaseOrder.id == record_id,
        PurchaseOrder.deleted_at.is_(None),
    )
    row = session.scalar(query)
    if row is None:
        raise ApiProblem(404, "PURCHASE_TEXT_NOT_FOUND", "Not found", "Purchase not found.")
    parent_query = select(SalesOrder).where(
        SalesOrder.organization_id == context.organization_id,
        SalesOrder.id == row.sales_order_id,
        SalesOrder.deleted_at.is_(None),
    )
    if lock:
        parent_query = parent_query.with_for_update()
    if session.scalar(parent_query) is None:
        raise ApiProblem(404, "PURCHASE_TEXT_NOT_FOUND", "Not found", "Purchase owner not found.")
    if lock:
        # Match amendment's parent-before-purchase lock order and refresh the candidate read.
        row = session.scalar(query.with_for_update().execution_options(populate_existing=True))
        if row is None:
            raise ApiProblem(404, "PURCHASE_TEXT_NOT_FOUND", "Not found", "Purchase not found.")
    items = PurchaseOrderRepository(session).items(
        organization_id=context.organization_id, purchase_order_id=row.id
    )
    return row, items


def snapshot(row: PurchaseOrder, items: Sequence[PurchaseOrderItem]) -> PurchaseTextReviewResponse:
    return PurchaseTextReviewResponse(
        record_id=row.id,
        version=row.version,
        content_digest=content_digest(row, items),
        text="采购行说明、取消原因及凭据说明",
        details=text_fields(row, items),
        released=is_released(row, items),
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
    )


class PurchaseTextReviewService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def inspect(self, context: RequestContext, record_id: UUID) -> PurchaseTextReviewResponse:
        with self.factory() as session:
            return snapshot(*require_content(session, context, record_id))

    def decide(
        self,
        context: RequestContext,
        record_id: UUID,
        request: PurchaseTextReviewRequest,
        *,
        key: str,
    ) -> PurchaseTextReviewResponse:
        context.require(Permission.PROFIT_READ, Permission.PROCUREMENT_READ)
        if not request.confirmed:
            raise ApiProblem(
                422, "CONFIRMATION_REQUIRED", "Confirm review", "Confirm the decision."
            )
        with UnitOfWork(self.factory) as unit:
            session = unit.session
            command = begin_command(
                session,
                context,
                scope="purchase.text_review",
                key=key,
                payload={"record_id": record_id, **request.model_dump()},
            )
            row, items = require_content(session, context, record_id, lock=True)
            if command.resource_id is not None:
                result = snapshot(row, items)
                unit.commit()
                return result
            if (
                row.version != request.expected_version
                or content_digest(row, items) != request.content_digest
            ):
                raise ApiProblem(
                    409, "VERSION_CONFLICT", "Changed content", "Reload and review again."
                )
            previous = is_released(row, items)
            row.released_digest = (
                content_digest(row, items, version=row.version + 1) if request.release else None
            )
            row.reviewed_by = context.user_id
            row.reviewed_at = datetime.now(UTC)
            row.updated_by = context.user_id
            details = {"record_id": str(row.id), "released": request.release}
            action = "purchase_order.text_reviewed"
            session.add(
                Activity(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    subject_type="purchase_order",
                    subject_id=row.id,
                    activity_type=action,
                    summary="Purchase source text visibility reviewed",
                    details=details,
                    correlation_id=context.request_id,
                )
            )
            AuditRecorder().record(
                session,
                context,
                action=action,
                target_type="purchase_order",
                target_id=row.id,
                before={"released": previous},
                after={**details, "reviewed_content_digest": request.content_digest},
                reason=request.reason,
            )
            OutboxRecorder().record(
                session, context, DomainEvent(f"{action}.v1", "purchase_order", row.id, details)
            )
            complete_command(command, row.id, "purchase_order")
            session.flush()
            result = snapshot(row, items)
            unit.commit()
            return result
