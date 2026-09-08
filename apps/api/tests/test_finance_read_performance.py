"""Populated finance ASGI/PG baseline, not network or production load acceptance."""

import json
import math
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from time import perf_counter

import pytest
from test_finance_vertical_slice import allocation, payment, receivables
from test_order_procurement_vertical_slice import create_confirmed_order

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def test_populated_finance_reads_and_receipt_creation_latency(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    installments = receivables(f, order)
    deposit = next(row for row in installments if row["installment_type"] == "DEPOSIT")
    receipt = payment(f, order, order["total"])
    paid = (Decimal(deposit["amount"]) / 2).quantize(Decimal("0.0001"))
    allocation(f, receipt, deposit, paid)
    for _ in range(100):
        payment(f, order, "1")
    headers = f.headers("quotation-finance", f.organization_a)
    filters = {"company_id": order["company_id"], "currency_code": order["currency_code"]}
    cases = [
        ("payment_detail", f"/api/v1/payments/{receipt['id']}", {}),
        ("payment_page", "/api/v1/payments", filters | {"limit": 20}),
        ("payment_search", "/api/v1/payments", filters | {"query": receipt["payment_number"]}),
        ("order_receivables", "/api/v1/receivables", {"sales_order_id": order["id"]}),
        ("order_detail", f"/api/v1/sales-orders/{order['id']}", {}),
        ("funding_estimate", f"/api/v1/sales-orders/{order['id']}/funding-estimate", {}),
    ]
    metrics = {}
    baselines = {}
    for name, path, params in cases:
        baseline = f.client.get(path, params=params, headers=headers)
        assert baseline.status_code == 200, baseline.text
        expected = baseline.json()
        baselines[name] = expected
        samples = []
        for index in range(33):
            started = perf_counter()
            response = f.client.get(path, params=params, headers=headers)
            elapsed = (perf_counter() - started) * 1000
            assert response.status_code == 200, response.text
            assert response.json() == expected
            if index >= 3:
                samples.append(elapsed)
        metrics[name] = {
            "count": len(samples),
            "p95_ms": round(sorted(samples)[math.ceil(len(samples) * 0.95) - 1], 3),
            "max_ms": round(max(samples), 3),
        }
    assert len(baselines["payment_detail"]["allocations"]) == 1
    assert Decimal(baselines["payment_detail"]["allocated_amount"]) == paid
    assert len(baselines["payment_page"]["items"]) == 20
    assert baselines["payment_page"]["has_more"] is True
    assert [row["id"] for row in baselines["payment_search"]["items"]] == [receipt["id"]]
    assert len(baselines["order_receivables"]["items"]) == 2
    assert (
        sum(Decimal(row["paid_amount"]) for row in baselines["order_receivables"]["items"]) == paid
    )
    assert baselines["order_detail"]["id"] == order["id"]
    funding = baselines["funding_estimate"]
    assert funding["sales_order_id"] == order["id"]
    assert Decimal(funding["net_allocated_receipts"]) == paid
    assert Decimal(funding["estimated_funding_need"]) == max(
        Decimal(order["total_cost"]) - paid, Decimal(0)
    )

    samples = []
    created_ids = set()
    for index in range(33):
        started = perf_counter()
        created = payment(f, order, "1")
        elapsed = (perf_counter() - started) * 1000
        assert created["id"] not in created_ids
        created_ids.add(created["id"])
        if index >= 3:
            samples.append(elapsed)
    metrics["payment_create"] = {
        "count": len(samples),
        "p95_ms": round(sorted(samples)[math.ceil(len(samples) * 0.95) - 1], 3),
        "max_ms": round(max(samples), 3),
    }
    report = {
        "measured_at": datetime.now(UTC).isoformat(),
        "scope": "Single-concurrency in-process ASGI with real disposable PostgreSQL",
        "exclusions": ["network/TLS", "Logto network", "browser", "provider", "large-scale load"],
        "read_dataset": {"orders": 1, "receivables": 2, "payments": 101, "allocations": 1},
        "command_dataset": "101 initial payments plus33 distinct receipt creations",
        "warmup_per_operation": 3,
        "metrics": metrics,
    }
    artifact = Path(__file__).resolve().parents[3] / "test-results/finance-api-performance.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name, metric in metrics.items():
        assert metric["p95_ms"] < (800 if name == "payment_create" else 500), (name, metric)
