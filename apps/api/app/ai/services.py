from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session, sessionmaker

from app.ai.content import call_response, run_response, run_responses
from app.ai.models import AiRun, AiToolCall
from app.ai.provider import PROMPT_VERSION
from app.ai.schemas import AiIntent, AiRunCreate, AiRunResponse, AiToolCallResponse
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.config import Settings
from app.core.unit_of_work import UnitOfWork
from app.platform.domain_jobs import bind_ai_run, create_ai_job
from app.platform.idempotency import begin_command, complete_command
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.sales.assistant_queries import OrderAssistantQueries
from app.work.records import record_activity


def required_permissions(intent: AiIntent) -> frozenset[Permission]:
    required = {Permission.AI_READ, Permission.AI_RUN}
    required.add(Permission.COMPANY_READ if intent == AiIntent.SEARCH else Permission.ORDER_READ)
    if intent == AiIntent.PROFIT:
        required.add(Permission.PROFIT_READ)
    return frozenset(required)


def require_run_permissions(context: RequestContext, run: AiRun) -> None:
    context.require(Permission.AI_READ, *(Permission(value) for value in run.required_permissions))


def get_run(
    session: Session,
    context: RequestContext,
    run_id: UUID,
    *,
    lock: bool = False,
    private: bool = True,
) -> AiRun:
    query = select(AiRun).where(
        AiRun.organization_id == context.organization_id,
        AiRun.id == run_id,
        AiRun.deleted_at.is_(None),
    )
    if private:
        query = query.where(AiRun.created_by == context.user_id)
    if lock:
        query = query.with_for_update()
    run = session.scalar(query)
    if run is None:
        raise ApiProblem(404, "AI_RUN_NOT_FOUND", "Run not found", "Run not found.")
    require_run_permissions(context, run)
    return run


def record_ai_event(
    session: Session,
    context: RequestContext,
    *,
    target_id: UUID,
    action: str,
    details: dict[str, object],
    reason: str | None = None,
) -> None:
    record_activity(
        session,
        context,
        subject_type="ai_run",
        subject_id=target_id,
        activity_type=action,
        summary=action,
        details=details,
    )
    AuditRecorder().record(
        session,
        context,
        action=action,
        target_type="ai_run",
        target_id=target_id,
        after=details,
        reason=reason,
    )
    OutboxRecorder().record(
        session,
        context,
        DomainEvent(f"{action}.v1", "ai_run", target_id, {"run_id": str(target_id)}),
    )


class AiCommandService:
    def __init__(self, factory: sessionmaker[Session], settings: Settings) -> None:
        self.factory = factory
        self.settings = settings

    def create(self, context: RequestContext, request: AiRunCreate, *, key: str) -> AiRunResponse:
        required = required_permissions(request.intent)
        context.require(*required)
        with UnitOfWork(self.factory) as unit:
            session = unit.session
            command = begin_command(
                session,
                context,
                scope=f"ai.run.{context.user_id}",
                key=key,
                payload=request.model_dump(mode="json"),
            )
            if command.resource_id is not None:
                run = get_run(session, context, command.resource_id)
                result = run_response(session, context, run)
                unit.commit()
                return result
            if request.subject_id is not None:
                OrderAssistantQueries(session).snapshot(
                    context, request.subject_id, profit=request.intent == AiIntent.PROFIT
                )
            job_id = create_ai_job(session, context)
            run = AiRun(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                job_id=job_id,
                intent=request.intent,
                subject_id=request.subject_id,
                input_summary=request.model_dump(mode="json"),
                required_permissions=sorted(permission.value for permission in required),
                model=self.settings.ai_model_identity,
                prompt_version=PROMPT_VERSION,
            )
            session.add(run)
            session.flush()
            bind_ai_run(session, context, job_id=job_id, run_id=run.id)
            complete_command(command, run.id, "ai_run")
            record_ai_event(
                session,
                context,
                target_id=run.id,
                action="ai.run_requested",
                details={"intent": run.intent, "job_id": str(job_id)},
            )
            result = run_response(session, context, run)
            unit.commit()
            return result


class AiQueryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, context: RequestContext, run_id: UUID) -> AiRunResponse:
        return run_response(self.session, context, get_run(self.session, context, run_id))

    def page(
        self, context: RequestContext, *, cursor: UUID | None, limit: int
    ) -> list[AiRunResponse]:
        context.require(Permission.AI_READ)
        query = select(AiRun).where(
            AiRun.organization_id == context.organization_id,
            AiRun.created_by == context.user_id,
            AiRun.deleted_at.is_(None),
            AiRun.required_permissions.contained_by(
                [permission.value for permission in context.permissions]
            ),
        )
        if cursor:
            anchor = get_run(self.session, context, cursor)
            query = query.where(tuple_(AiRun.created_at, AiRun.id) < (anchor.created_at, anchor.id))
        rows = list(
            self.session.scalars(
                query.order_by(AiRun.created_at.desc(), AiRun.id.desc()).limit(limit + 1)
            )
        )

        return run_responses(self.session, context, rows)

    def calls(self, context: RequestContext, run_id: UUID) -> list[AiToolCallResponse]:
        get_run(self.session, context, run_id)
        rows = list(
            self.session.scalars(
                select(AiToolCall)
                .where(
                    AiToolCall.organization_id == context.organization_id,
                    AiToolCall.run_id == run_id,
                )
                .order_by(AiToolCall.created_at, AiToolCall.id)
                .limit(30)
            )
        )
        return [call_response(context, row) for row in rows]
