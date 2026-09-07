from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class RequestMetricsResponse(BaseModel):
    started_at: datetime
    requests: int
    errors: int
    server_errors: int
    upload_errors: int
    duration_sum_ms: float
    duration_max_ms: float
    histogram: list[int]


class OperationsResponse(BaseModel):
    captured_at: datetime
    scope: Literal["current_organization"] = "current_organization"
    outbox_states: dict[str, int]
    awaiting_consumer_count: int
    oldest_awaiting_seconds: float | None
    job_states: dict[str, int]
    document_states: dict[str, int]
    ai_run_states: dict[str, int]
    approval_states: dict[str, int]
    approval_rate: Decimal | None
    ai_input_tokens: int
    ai_output_tokens: int
    known_estimated_cost_usd: Decimal
    unknown_cost_runs: int
    request_metrics: RequestMetricsResponse | None
    latency_upper_bounds_ms: list[int | None]
    telemetry_scope: Literal["current_api_process_since_bucket_creation"] = (
        "current_api_process_since_bucket_creation"
    )
