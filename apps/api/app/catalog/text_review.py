from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.catalog.content import content_digest, is_released
from app.catalog.models import Product
from app.core.content_review import ContentReviewRequest, ContentReviewSnapshot
from app.core.unit_of_work import UnitOfWork
from app.platform.idempotency import begin_command, complete_command
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.work.models import Activity


class ProductTextReviewRequest(ContentReviewRequest):
    pass


class ProductTextReviewResponse(ContentReviewSnapshot):
    pass


def require_record(
    session: Session,
    context: RequestContext,
    record_id: UUID,
    *,
    lock: bool = False,
) -> Product:
    context.require(Permission.PROFIT_READ)
    context.require(Permission.PRODUCT_READ)
    query = select(Product).where(
        Product.organization_id == context.organization_id,
        Product.id == record_id,
        Product.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update()
    row = session.scalar(query)
    if not isinstance(row, Product):
        raise ApiProblem(404, "PRODUCT_TEXT_NOT_FOUND", "Not found", "Product record not found.")
    return row


def snapshot(row: Product) -> ProductTextReviewResponse:
    return ProductTextReviewResponse(
        record_id=row.id,
        version=row.version,
        content_digest=content_digest(row),
        text="产品说明",
        details={"description": row.description},
        released=is_released(row),
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
    )


class ProductTextReviewService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def inspect(self, context: RequestContext, record_id: UUID) -> ProductTextReviewResponse:
        with self.factory() as session:
            return snapshot(require_record(session, context, record_id))

    def decide(
        self,
        context: RequestContext,
        record_id: UUID,
        request: ProductTextReviewRequest,
        *,
        key: str,
    ) -> ProductTextReviewResponse:
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
                scope="product.text_review",
                key=key,
                payload={"record_id": record_id, **request.model_dump()},
            )
            row = require_record(session, context, record_id, lock=True)
            if command.resource_id is not None:
                result = snapshot(row)
                unit.commit()
                return result
            if (
                row.version != request.expected_version
                or content_digest(row) != request.content_digest
            ):
                raise ApiProblem(
                    409, "VERSION_CONFLICT", "Changed content", "Reload and review again."
                )
            previous = is_released(row)
            row.released_digest = (
                content_digest(row, version=row.version + 1) if request.release else None
            )
            row.reviewed_by = context.user_id
            row.reviewed_at = datetime.now(UTC)
            row.updated_by = context.user_id
            details = {"record_id": str(row.id), "released": request.release}
            action = "product.text_reviewed"
            subject = "product"
            session.add(
                Activity(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    subject_type=subject,
                    subject_id=row.id,
                    activity_type=action,
                    summary="Product text visibility reviewed",
                    details=details,
                    correlation_id=context.request_id,
                )
            )
            AuditRecorder().record(
                session,
                context,
                action=action,
                target_type=subject,
                target_id=row.id,
                before={"released": previous},
                after={**details, "reviewed_content_digest": request.content_digest},
                reason=request.reason,
            )
            OutboxRecorder().record(
                session, context, DomainEvent(f"{action}.v1", subject, row.id, details)
            )
            complete_command(command, row.id, subject)
            session.flush()
            result = snapshot(row)
            unit.commit()
            return result
