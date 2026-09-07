import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.core.observability import Observation, RequestMetrics, SafeJsonFormatter
from starlette.requests import Request
from starlette.responses import Response


def test_external_messages_arguments_and_exception_are_never_formatted():
    secret = "sensitive-token-password-signed-url-body"
    record = logging.LogRecord(secret, logging.ERROR, secret, 1, secret + "%s", (secret,), None)
    record.exc_info = (ValueError, ValueError(secret), None)
    record.stack_info = secret
    result = SafeJsonFormatter().format(record)
    assert secret not in result
    assert json.loads(result)["event"] == "external.log"


def test_safe_observation_has_correlation_without_raw_message():
    request_id, organization_id = uuid4(), uuid4()
    record = logging.LogRecord("trade.observations", logging.INFO, "", 0, "secret", (), None)
    record.observation = Observation(
        event="api.request",
        service="api",
        request_id=request_id,
        organization_id=organization_id,
        route="/api/v1/leads/{lead_id}",
        method="GET",
        status=200,
        duration_ms=2.5,
    )
    result = SafeJsonFormatter().format(record)
    assert "secret" not in result
    payload = json.loads(result)
    assert payload["request_id"] == str(request_id)
    assert payload["organization_id"] == str(organization_id)


def test_metrics_are_bounded_tenant_scoped_and_snapshot_is_detached():
    metrics = RequestMetrics(capacity=2)
    first, second, third = uuid4(), uuid4(), uuid4()
    metrics.record(first, status=200, duration_ms=5, upload=False)
    metrics.record(second, status=422, duration_ms=80, upload=True)
    assert metrics.snapshot(second)["upload_errors"] == 1
    snapshot = metrics.snapshot(second)
    snapshot["histogram"][0] = 999
    assert metrics.snapshot(second)["histogram"][0] == 0
    metrics.record(third, status=500, duration_ms=2000, upload=False)
    assert metrics.snapshot(first) is None
    assert metrics.snapshot(third)["server_errors"] == 1
    assert metrics.snapshot(second)["requests"] == 1


def test_concurrent_metrics_do_not_lose_samples():
    metrics = RequestMetrics()
    organization = uuid4()

    def record(_):
        metrics.record(organization, status=200, duration_ms=1, upload=False)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(record, range(1000)))
    snapshot = metrics.snapshot(organization)
    assert snapshot["requests"] == 1000
    assert sum(snapshot["histogram"]) == 1000


def test_http_observation_omits_headers_query_path_and_exception(monkeypatch):
    import app.main as main

    records = []
    monkeypatch.setattr(main, "observe", records.append)
    secret = "sensitive-token-password-body"
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/" + secret,
            "query_string": f"token={secret}".encode(),
            "headers": [
                (b"authorization", secret.encode()),
                (b"x-organization-id", str(uuid4()).encode()),
            ],
        }
    )

    async def fail(request):
        request.scope["route"] = SimpleNamespace(path="/api/v1/leads/{lead_id}")
        raise RuntimeError(secret)

    with pytest.raises(RuntimeError, match=secret):
        asyncio.run(main.request_id_middleware(request, fail))
    record = logging.LogRecord("trade.observations", logging.INFO, "", 0, "", (), None)
    record.observation = records[0]
    output = SafeJsonFormatter().format(record)
    assert secret not in output
    assert records[0].status == 500
    assert records[0].organization_id is None
    assert records[0].request_id is not None


def test_metrics_failure_does_not_change_successful_response(monkeypatch):
    import app.main as main

    def fail(*args, **kwargs):
        raise RuntimeError("Telemetry failure")

    monkeypatch.setattr(main.request_metrics, "record", fail)
    request = Request({"type": "http", "method": "POST", "path": "/safe", "headers": []})

    async def success(request):
        request.state.verified_organization_id = uuid4()
        return Response(status_code=201)

    response = asyncio.run(main.request_id_middleware(request, success))
    assert response.status_code == 201
