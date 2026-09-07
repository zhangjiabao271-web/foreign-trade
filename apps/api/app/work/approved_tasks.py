from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.sales.order_repositories import SalesOrderRepository
from app.work.models import Activity, Task


def lock_open_order(session: Session, context: RequestContext, order_id: UUID) -> None:
    context.require(Permission.ORDER_READ, Permission.TASK_WRITE)
    order = SalesOrderRepository(session).get_for_update(
        organization_id=context.organization_id, sales_order_id=order_id
    )
    if order is None:
        raise ApiProblem(404, "SALES_ORDER_NOT_FOUND", "Order not found", "Order not found.")
    if order.status in {"COMPLETED", "CANCELLED"}:
        raise ApiProblem(
            409, "ORDER_FINALIZED", "Order finalized", "Finalized orders cannot gain new tasks."
        )


def create_approved_follow_up(
    session: Session,
    context: RequestContext,
    *,
    order_id: UUID,
    approval_id: UUID,
    title: str,
    reason: str,
) -> Task:
    """Caller owns the transaction and takes the order lock before the approval lock."""
    lock_open_order(session, context, order_id)
    task = Task(
        id=uuid4(),
        organization_id=context.organization_id,
        created_by=context.user_id,
        updated_by=context.user_id,
        task_type=f"AI_FOLLOW_UP:{approval_id}",
        subject_type="sales_order",
        subject_id=order_id,
        title=title,
        assigned_to=context.user_id,
        details={"approval_id": str(approval_id), "human_approved": True},
    )
    session.add(task)
    session.add(
        Activity(
            organization_id=context.organization_id,
            created_by=context.user_id,
            updated_by=context.user_id,
            subject_type="sales_order",
            subject_id=order_id,
            activity_type="task.created_from_approval",
            summary="Human-approved follow-up task created",
            details={"task_id": str(task.id), "approval_id": str(approval_id)},
            correlation_id=context.request_id,
        )
    )
    AuditRecorder().record(
        session,
        context,
        action="task.created_from_approval",
        target_type="task",
        target_id=task.id,
        after={"approval_id": str(approval_id)},
        reason=reason,
    )
    OutboxRecorder().record(
        session,
        context,
        DomainEvent(
            "task.created_from_approval.v1",
            "task",
            task.id,
            {"task_id": str(task.id), "order_id": str(order_id)},
        ),
    )
    session.flush()
    return task
