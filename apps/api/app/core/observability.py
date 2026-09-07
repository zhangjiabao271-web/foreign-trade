"""Bounded operational telemetry. Never a business fact source or an audit replacement."""

import json
import logging
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Literal
from uuid import UUID

from sqlalchemy import Engine
from sqlalchemy.pool import QueuePool

EventName = Literal["api.request", "worker.task", "database.pool", "service.started"]


@dataclass(frozen=True, slots=True)
class Observation:
    event: EventName
    service: Literal["api", "worker"]
    request_id: UUID | None = None
    organization_id: UUID | None = None
    route: str | None = None
    method: str | None = None
    status: int | None = None
    duration_ms: float | None = None
    task_name: str | None = None
    outcome: Literal["succeeded", "failed", "retry", "started"] | None = None
    pool_size: int | None = None
    pool_checked_out: int | None = None
    pool_overflow: int | None = None


class SafeJsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
        }
        observation = getattr(record, "observation", None)
        if isinstance(observation, Observation):
            payload.update(
                {key: value for key, value in asdict(observation).items() if value is not None}
            )
        else:
            # Library arguments and exceptions may contain credentials; never format them.
            payload["event"] = "external.log"
        return json.dumps(payload, ensure_ascii=False, default=str, separators=(",", ":"))


def configure_safe_logging() -> None:
    logging.captureWarnings(True)
    handler = logging.StreamHandler()
    handler.setFormatter(SafeJsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    for name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "celery",
        "celery.task",
        "celery.redirected",
    ):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True


def observe(observation: Observation) -> None:
    try:
        logging.getLogger("trade.observations").info(
            "observation", extra={"observation": observation}
        )
    except Exception:
        # Telemetry must never turn an already committed business command into an apparent failure.
        return


def observe_pool(engine: Engine, service: Literal["api", "worker"]) -> None:
    pool = engine.pool
    if isinstance(pool, QueuePool):
        observe(
            Observation(
                event="database.pool",
                service=service,
                pool_size=pool.size(),
                pool_checked_out=pool.checkedout(),
                pool_overflow=pool.overflow(),
            )
        )


@dataclass(slots=True)
class RequestBucket:
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    requests: int = 0
    errors: int = 0
    server_errors: int = 0
    upload_errors: int = 0
    duration_sum_ms: float = 0
    duration_max_ms: float = 0
    histogram: list[int] = field(default_factory=lambda: [0] * 8)


LATENCY_BOUNDS_MS = (10, 50, 100, 250, 500, 800, 1000)


class RequestMetrics:
    """Per-organization, per-process snapshots. LRU eviction discards telemetry, never facts."""

    def __init__(self, capacity: int = 256) -> None:
        if capacity < 1:
            raise ValueError("Metrics capacity must be positive")
        self.capacity = capacity
        self._buckets: OrderedDict[UUID, RequestBucket] = OrderedDict()
        self._lock = Lock()

    def record(
        self, organization_id: UUID, *, status: int, duration_ms: float, upload: bool
    ) -> None:
        elapsed = max(0.0, duration_ms)
        with self._lock:
            bucket = self._buckets.setdefault(organization_id, RequestBucket())
            self._buckets.move_to_end(organization_id)
            while len(self._buckets) > self.capacity:
                self._buckets.popitem(last=False)
            bucket.requests += 1
            bucket.errors += int(status >= 400)
            bucket.server_errors += int(status >= 500)
            bucket.upload_errors += int(upload and status >= 400)
            bucket.duration_sum_ms += elapsed
            bucket.duration_max_ms = max(bucket.duration_max_ms, elapsed)
            index = next((i for i, bound in enumerate(LATENCY_BOUNDS_MS) if elapsed <= bound), 7)
            bucket.histogram[index] += 1

    def snapshot(self, organization_id: UUID) -> dict[str, object] | None:
        with self._lock:
            bucket = self._buckets.get(organization_id)
            return asdict(bucket) if bucket is not None else None


request_metrics = RequestMetrics()
