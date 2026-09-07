"""Safe Celery lifecycle diagnostics without task arguments, results or exceptions."""

from collections import OrderedDict
from threading import Lock
from time import perf_counter
from typing import Literal
from uuid import UUID

from app.core.observability import Observation, configure_safe_logging, observe
from celery.signals import setup_logging, task_postrun, task_prerun

TASK_NAMES = frozenset(
    {
        "health.ping",
        "platform.tenant-context-probe",
        "platform.relay-outbox",
        "platform.recover-outbox",
        "platform.consume-outbox-event",
        "ai.execute-run",
    }
)
_starts: OrderedDict[str, float] = OrderedDict()
_lock = Lock()


def setup_worker_logging(**kwargs: object) -> None:
    configure_safe_logging()
    observe(Observation(event="service.started", service="worker"))


def task_started(task_id: str | None = None, **kwargs: object) -> None:
    if task_id is None:
        return
    with _lock:
        _starts[task_id] = perf_counter()
        while len(_starts) > 4096:
            _starts.popitem(last=False)


def task_finished(
    task_id: str | None = None,
    task: object = None,
    kwargs: object = None,
    state: object = None,
    **extra: object,
) -> None:
    with _lock:
        started = _starts.pop(task_id, None) if task_id is not None else None
    elapsed = (perf_counter() - started) * 1000 if started is not None else None
    name = getattr(task, "name", None)
    if name not in TASK_NAMES:
        name = "unregistered-task"
    request_id = None
    organization_id = None
    context = kwargs.get("context") if isinstance(kwargs, dict) else None
    if isinstance(context, dict):
        try:
            request_id = UUID(str(context.get("request_id")))
            organization_id = UUID(str(context.get("organization_id")))
        except ValueError:
            request_id = None
            organization_id = None
    outcome: Literal["succeeded", "failed", "retry"] = "failed"
    if state == "SUCCESS":
        outcome = "succeeded"
    elif state == "RETRY":
        outcome = "retry"
    observation = Observation(
        event="worker.task",
        service="worker",
        request_id=request_id,
        organization_id=organization_id,
        task_name=name,
        duration_ms=elapsed,
        outcome=outcome,
    )
    observe(observation)


def connect_worker_observers() -> None:
    configure_safe_logging()
    setup_logging.connect(setup_worker_logging, weak=False)
    task_prerun.connect(task_started, weak=False)
    task_postrun.connect(task_finished, weak=False)
