from collections.abc import Callable
from typing import Any, Literal, TypedDict, TypeVar, cast
from uuid import UUID

from app.ai.provider import configured_provider
from app.ai.runner import AiRunner
from app.core.config import get_settings
from app.documents.services import mark_document_available
from app.platform.outbox import (
    IdempotentEventConsumer,
    OutboxMessage,
    OutboxRelay,
    mark_async_job_event_consumed,
)
from sqlalchemy.orm import Session

from worker.app import app
from worker.outbox import CeleryEventDispatcher, worker_session_factory
from worker.tenant_context import TenantTaskContext, validate_tenant_task_context


class PingPayload(TypedDict):
    service: Literal["worker"]
    status: Literal["ready"]


def ping_payload() -> PingPayload:
    return {"service": "worker", "status": "ready"}


TaskCallable = TypeVar("TaskCallable", bound=Callable[..., Any])


def celery_task(*args: object, **kwargs: object) -> Callable[[TaskCallable], TaskCallable]:
    """Contain Celery's untyped decorator at the integration boundary."""

    return cast(Callable[[TaskCallable], TaskCallable], app.task(*args, **kwargs))


@celery_task(name="health.ping")
def health_ping() -> PingPayload:
    return ping_payload()


@celery_task(name="platform.tenant-context-probe")
def tenant_context_probe(context: TenantTaskContext) -> TenantTaskContext:
    """Example business-task boundary: tenant context is a required argument."""

    return validate_tenant_task_context(context)


@celery_task(name="platform.relay-outbox")
def relay_outbox() -> dict[str, int]:
    relay = OutboxRelay(
        worker_session_factory(),
        CeleryEventDispatcher(),
        worker_id="celery-relay",
    )
    relay.recover_stale()
    result = relay.run_once()
    return {
        "claimed": result.claimed,
        "published": result.published,
        "failed": result.failed,
    }


@celery_task(name="platform.recover-outbox", soft_time_limit=30, time_limit=45)
def recover_outbox() -> dict[str, int]:
    relay = OutboxRelay(
        worker_session_factory(),
        CeleryEventDispatcher(),
        worker_id="celery-recovery",
    )
    return {"recovered": relay.recover_unconsumed(consumer_name_prefix="worker.")}


@celery_task(
    name="platform.consume-outbox-event",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    soft_time_limit=120,
    time_limit=150,
    acks_late=True,
    reject_on_worker_lost=True,
)
def consume_outbox_event(
    context: TenantTaskContext,
    message: OutboxMessage,
) -> bool:
    validated_context = validate_tenant_task_context(context)
    if validated_context["organization_id"] != message["organization_id"]:
        raise ValueError("Task and outbox organization contexts do not match")
    handlers = {
        "async_job.created.v1": mark_async_job_event_consumed,
        "document.uploaded.v1": mark_document_available,
    }
    handler = handlers.get(message["event_type"], acknowledge_domain_event)
    return IdempotentEventConsumer(worker_session_factory()).consume(
        consumer_name=f"worker.{message['event_type']}",
        message=message,
        handler=handler,
    )


def acknowledge_domain_event(session: Session, message: OutboxMessage) -> None:
    """Persist the processed-event receipt when no side effect is registered yet."""

    _ = session, message


@celery_task(
    name="ai.execute-run",
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_jitter=True,
    max_retries=8,
    soft_time_limit=150,
    time_limit=180,
    acks_late=True,
    reject_on_worker_lost=True,
)
def execute_ai_run(context: TenantTaskContext, message: OutboxMessage) -> bool:
    validated = validate_tenant_task_context(context)
    if (
        validated["organization_id"] != message["organization_id"]
        or message["event_type"] != "ai.run_requested.v1"
    ):
        raise ValueError("Invalid AI run event context")
    settings = get_settings()
    factory = worker_session_factory()
    AiRunner(factory, configured_provider(settings), settings).execute(
        organization_id=UUID(message["organization_id"]),
        run_id=UUID(message["aggregate_id"]),
        request_id=UUID(message["correlation_id"]),
    )
    return IdempotentEventConsumer(factory).consume(
        consumer_name="worker.ai.run_requested.v1",
        message=message,
        handler=acknowledge_domain_event,
    )
