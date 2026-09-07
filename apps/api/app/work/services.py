from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.unit_of_work import UnitOfWork
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.sales.order_repositories import SalesOrderRepository
from app.work.content import activity_response, task_response
from app.work.models import Activity, Task
from app.work.schemas import ActivityResponse, TaskComplete, TaskResponse


def require_order(
    session: Session, context: RequestContext, order_id: UUID, *, lock: bool = False
) -> None:
    context.require(Permission.ORDER_READ)
    repository = SalesOrderRepository(session)
    if lock:
        order = repository.get_for_update(
            organization_id=context.organization_id, sales_order_id=order_id
        )
    else:
        order = repository.get(organization_id=context.organization_id, record_id=order_id)
    if order is None:
        raise ApiProblem(404, "SALES_ORDER_NOT_FOUND", "Order not found", "Order not found.")


class WorkQueryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def order_tasks(self, context: RequestContext, order_id: UUID) -> Sequence[TaskResponse]:
        context.require(Permission.TASK_READ)
        require_order(self.session, context, order_id)
        rows = self.session.scalars(
            select(Task)
            .where(
                Task.organization_id == context.organization_id,
                Task.subject_type == "sales_order",
                Task.subject_id == order_id,
                Task.deleted_at.is_(None),
            )
            .order_by(Task.created_at, Task.id)
        ).all()
        return [task_response(context, row) for row in rows]

    def order_activities(
        self, context: RequestContext, order_id: UUID, limit: int
    ) -> Sequence[ActivityResponse]:
        require_order(self.session, context, order_id)
        rows = self.session.scalars(
            select(Activity)
            .where(
                Activity.organization_id == context.organization_id,
                Activity.subject_type == "sales_order",
                Activity.subject_id == order_id,
                Activity.deleted_at.is_(None),
            )
            .order_by(Activity.occurred_at.desc(), Activity.id)
            .limit(limit)
        ).all()
        return [activity_response(context, row) for row in rows]


class TaskCommandService:
    def __init__(
        self,
        factory: sessionmaker[Session],
        *,
        audit: AuditRecorder | None = None,
        outbox: OutboxRecorder | None = None,
    ) -> None:
        self.factory = factory
        self.audit = audit or AuditRecorder()
        self.outbox = outbox or OutboxRecorder()

    def complete_order_task(
        self, context: RequestContext, order_id: UUID, task_id: UUID, request: TaskComplete
    ) -> TaskResponse:
        context.require(Permission.TASK_WRITE)
        with UnitOfWork(self.factory) as unit:
            session = unit.session
            require_order(session, context, order_id, lock=True)
            task = session.scalar(
                select(Task)
                .where(
                    Task.organization_id == context.organization_id,
                    Task.id == task_id,
                    Task.subject_type == "sales_order",
                    Task.subject_id == order_id,
                    Task.deleted_at.is_(None),
                )
                .with_for_update()
            )
            if task is None:
                raise ApiProblem(404, "TASK_NOT_FOUND", "Task not found", "Task not found.")
            if task.status == "DONE":
                unit.commit()
                return task_response(context, task)
            if task.version != request.expected_version:
                raise ApiProblem(409, "VERSION_CONFLICT", "Version conflict", "Reload the task.")
            if task.status not in {"OPEN", "IN_PROGRESS"}:
                raise ApiProblem(
                    409, "INVALID_STATE_TRANSITION", "Invalid state", "Task is not open."
                )
            previous = task.status
            task.status = "DONE"
            task.updated_by = context.user_id
            task.details = {**task.details, "resolution": request.resolution}
            session.add(
                Activity(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    subject_type="sales_order",
                    subject_id=order_id,
                    activity_type="task.completed",
                    summary=f"Completed: {task.title}",
                    details={"task_id": str(task.id), "resolution": request.resolution},
                    correlation_id=context.request_id,
                )
            )
            self.audit.record(
                session,
                context,
                action="task.completed",
                target_type="task",
                target_id=task.id,
                before={"status": previous},
                after={"status": task.status},
                reason=request.resolution,
            )
            self.outbox.record(
                session,
                context,
                DomainEvent(
                    "task.completed.v1",
                    "task",
                    task.id,
                    {"task_id": str(task.id), "sales_order_id": str(order_id)},
                ),
            )
            session.flush()
            unit.commit()
            return task_response(context, task)
