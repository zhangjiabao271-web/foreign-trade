"""Local ASGI + real PostgreSQL baseline; excludes browser/network/provider latency."""

import json
import math
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.crm.models import Lead
from app.fulfillment.models import Shipment
from app.work.overview import OverviewQueryService, QueueKind
from sqlalchemy import event
from test_order_procurement_vertical_slice import create_confirmed_order

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def test_local_latency_and_populated_checklist_query_bound(quotation_fixture):
    fixture = quotation_fixture
    order, _, _ = create_confirmed_order(fixture)
    # Disposable test data only: volume construction is outside the measured commands.
    with fixture.session_factory.begin() as session:
        session.add_all(
            [
                Lead(organization_id=organization, company_name=f"Benchmark company {index}")
                for organization in [fixture.organization_a, fixture.organization_b]
                for index in range(1000)
            ]
        )
        session.add_all(
            [
                Shipment(organization_id=fixture.organization_a, shipment_number=f"BENCH-{index}")
                for index in range(30)
            ]
        )

    headers = fixture.headers("quotation-sales", fixture.organization_a)
    samples: dict[str, list[float]] = {}

    def measure(name, callback, expected_status, count=60):
        for _ in range(3):
            assert callback().status_code == expected_status
        times = []
        for _ in range(count):
            started = perf_counter()
            response = callback()
            times.append((perf_counter() - started) * 1000)
            assert response.status_code == expected_status, response.text
        samples[name] = times

    for path in ["/api/v1/leads", "/api/v1/overview/leads", "/api/v1/overview/shipments"]:
        measure(path, lambda path=path: fixture.client.get(path, headers=headers), 200)
    measure(
        "lead_create",
        lambda: fixture.client.post(
            "/api/v1/leads",
            headers=headers,
            json={"company_name": f"Command {uuid4()}"},
        ),
        201,
    )
    measure(
        "async_job_acceptance",
        lambda: fixture.client.post(
            "/api/v1/ai/runs",
            headers=headers | {"Idempotency-Key": str(uuid4())},
            json={"intent": "TIMELINE", "subject_id": order["id"]},
        ),
        202,
    )

    context = RequestContext(
        user_id=fixture.sales_user,
        organization_id=fixture.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    statements = []

    def counted(_connection, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    query_counts = {}
    event.listen(fixture.engine, "before_cursor_execute", counted)
    try:
        for page_size in [1, 20]:
            with fixture.session_factory() as session:
                statements.clear()
                page = OverviewQueryService(session).page(
                    context,
                    QueueKind.SHIPMENTS,
                    offset=0,
                    limit=page_size,
                )
                assert len(page.items) == page_size
                assert all(item.missing_document_types for item in page.items)
                query_counts[str(page_size)] = len(statements)
    finally:
        event.remove(fixture.engine, "before_cursor_execute", counted)
    assert query_counts["1"] == query_counts["20"] <= 3

    metrics = {
        name: {
            "count": len(values),
            "p95_ms": round(sorted(values)[math.ceil(len(values) * 0.95) - 1], 3),
            "max_ms": round(max(values), 3),
        }
        for name, values in samples.items()
    }
    report = {
        "measured_at": datetime.now(UTC).isoformat(),
        "scope": "In-process ASGI HTTP client + real local PostgreSQL; 1 concurrent request",
        "exclusions": ["network/TLS", "Logto/JWKS network", "browser rendering", "model execution"],
        "dataset": {
            "organizations": 2,
            "leads_per_organization": 1000,
            "shipments": 30,
            "confirmed_orders": 1,
        },
        "warmup_per_operation": 3,
        "metrics": metrics,
        "shipment_checklist_select_counts": query_counts,
    }
    artifact = Path(__file__).resolve().parents[3] / "test-results" / "local-api-performance.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report))
    command_limits = {"async_job_acceptance": 1000, "lead_create": 800}
    for name, metric in metrics.items():
        limit = command_limits.get(name, 500)
        assert metric["p95_ms"] < limit, (name, metric, limit)
