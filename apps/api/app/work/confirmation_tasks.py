from datetime import timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.sales.confirmation_facts import procurement_preparation_source
from app.work.models import Task


def stage_procurement_preparation(
    session: Session, context: RequestContext, *, order_id: UUID
) -> None:
    """Caller owns confirmation replay, transaction and its original evidence stream."""
    context.require(Permission.ORDER_CONFIRM)
    source = procurement_preparation_source(session, context, order_id)
    session.add(
        Task(
            organization_id=context.organization_id,
            created_by=context.user_id,
            updated_by=context.user_id,
            task_type="PROCUREMENT_PREPARATION",
            subject_type="sales_order",
            subject_id=source.order_id,
            title=f"Prepare procurement for {source.order_number}",
            priority="HIGH",
            due_at=source.confirmed_at + timedelta(days=2),
            details={
                "order_number": source.order_number,
                "deposit_pending": source.deposit_pending,
            },
        )
    )
