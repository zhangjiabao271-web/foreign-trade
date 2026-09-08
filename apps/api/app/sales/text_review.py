from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.content_review import ContentReviewRequest, ContentReviewSnapshot
from app.core.database import TenantRecordMixin
from app.core.unit_of_work import UnitOfWork
from app.platform.idempotency import begin_command, complete_command
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.sales.contract_models import SalesContract
from app.sales.models import Quotation, QuotationVersion, SalesOrder
from app.sales.order_repositories import SalesOrderRepository
from app.sales.repositories import QuotationRepository
from app.sales.text_content import (
    CommercialItems,
    CommercialRecord,
    content_digest,
    is_released,
    text_fields,
)
from app.work.records import record_activity

CommercialTextKind = Literal["quotation_version", "sales_order", "sales_contract"]
READ_PERMISSION = {
    "quotation_version": Permission.QUOTATION_READ,
    "sales_order": Permission.ORDER_READ,
    "sales_contract": Permission.CONTRACT_READ,
}


class CommercialTextReviewRequest(ContentReviewRequest):
    pass


class CommercialTextReviewResponse(ContentReviewSnapshot):
    kind: CommercialTextKind


def require_row[Record: TenantRecordMixin](
    session: Session, context: RequestContext, model: type[Record], record_id: UUID, *, lock: bool
) -> Record:
    query = select(model).where(
        model.organization_id == context.organization_id,
        model.id == record_id,
        model.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = session.scalar(query)
    if row is None:
        raise ApiProblem(
            404, "COMMERCIAL_TEXT_NOT_FOUND", "Not found", "Commercial record not found."
        )
    return row


def require_content(
    session: Session,
    context: RequestContext,
    kind: CommercialTextKind,
    record_id: UUID,
    *,
    lock: bool = False,
) -> tuple[CommercialRecord, CommercialItems, str, UUID]:
    context.require(Permission.PROFIT_READ)
    if kind not in READ_PERMISSION:
        raise ApiProblem(
            404, "COMMERCIAL_TEXT_NOT_FOUND", "Not found", "Unsupported commercial record."
        )
    context.require(READ_PERMISSION[kind])
    # Preserve each commercial domain's parent-before-record command lock order.
    if kind == "quotation_version":
        candidate = require_row(session, context, QuotationVersion, record_id, lock=False)
        parent = require_row(session, context, Quotation, candidate.quotation_id, lock=lock)
        version = require_row(session, context, QuotationVersion, record_id, lock=lock)
        items = QuotationRepository(session).items(
            organization_id=context.organization_id, version_id=version.id
        )
        return version, items, "quotation", parent.id
    if kind == "sales_contract":
        contract = require_row(session, context, SalesContract, record_id, lock=False)
        order = require_row(session, context, SalesOrder, contract.sales_order_id, lock=lock)
        contract = require_row(session, context, SalesContract, record_id, lock=lock)
        return contract, (), "sales_order", order.id
    order = require_row(session, context, SalesOrder, record_id, lock=lock)
    order_items = SalesOrderRepository(session).items(
        organization_id=context.organization_id, sales_order_id=order.id
    )
    return order, order_items, "sales_order", order.id


def snapshot(
    kind: CommercialTextKind, row: CommercialRecord, items: CommercialItems
) -> CommercialTextReviewResponse:
    return CommercialTextReviewResponse(
        record_id=row.id,
        kind=kind,
        version=row.version,
        content_digest=content_digest(row, items),
        text="商业快照说明、条款及备注",
        details=text_fields(row, items),
        released=is_released(row, items),
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
    )


class CommercialTextReviewService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def inspect(
        self, context: RequestContext, kind: CommercialTextKind, record_id: UUID
    ) -> CommercialTextReviewResponse:
        with self.factory() as session:
            row, items, _, _ = require_content(session, context, kind, record_id)
            return snapshot(kind, row, items)

    def decide(
        self,
        context: RequestContext,
        kind: CommercialTextKind,
        record_id: UUID,
        request: CommercialTextReviewRequest,
        *,
        key: str,
    ) -> CommercialTextReviewResponse:
        context.require(Permission.PROFIT_READ)
        if not request.confirmed:
            raise ApiProblem(
                422, "CONFIRMATION_REQUIRED", "Confirm review", "Confirm the decision."
            )
        with UnitOfWork(self.factory) as unit:
            session = unit.session
            command = begin_command(
                session,
                context,
                scope="commercial.text_review",
                key=key,
                payload={"kind": kind, "record_id": record_id, **request.model_dump()},
            )
            row, items, subject_type, subject_id = require_content(
                session, context, kind, record_id, lock=True
            )
            if command.resource_id is not None:
                result = snapshot(kind, row, items)
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
            details = {"record_id": str(row.id), "kind": kind, "released": request.release}
            action = "commercial.text_reviewed"
            record_activity(
                session,
                context,
                subject_type=subject_type,
                subject_id=subject_id,
                activity_type=action,
                summary="Commercial source text visibility reviewed",
                details=details,
            )
            AuditRecorder().record(
                session,
                context,
                action=action,
                target_type=kind,
                target_id=row.id,
                before={"released": previous},
                after={**details, "reviewed_content_digest": request.content_digest},
                reason=request.reason,
            )
            OutboxRecorder().record(
                session, context, DomainEvent(f"{action}.v1", kind, row.id, details)
            )
            complete_command(command, row.id, kind)
            session.flush()
            result = snapshot(kind, row, items)
            unit.commit()
            return result
