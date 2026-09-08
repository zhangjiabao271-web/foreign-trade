"""Nonempty eight-queue query bounds; synthetic states are not lifecycle evidence."""

import json
import math
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.crm.models import Lead
from app.export.models import CustomsDeclaration, TaxRefundCase
from app.finance.models import Receivable
from app.fulfillment.models import Shipment
from app.sales.models import QuotationVersion, SalesOrder
from app.work.overview import OverviewQueryService, QueueKind
from sqlalchemy import event, select, text
from test_finance_vertical_slice import receivables
from test_order_list_queries import create_orders
from test_quotation_vertical_slice import post_ok

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def test_all_populated_queues_have_constant_queries_and_read_only_pages(quotation_fixture):
    f = quotation_fixture
    orders, _ = create_orders(f, 21)
    for order_id in orders:
        post_ok(f, f"/api/v1/sales-orders/{order_id}/confirm", "quotation-manager")
        assert len(receivables(f, orders[order_id])) == 2

    # Construct query fixtures only inside the disposable PostgreSQL database.
    with f.session_factory.begin() as session:
        for model, field, value in (
            (Lead, "status", "NEW"),
            (QuotationVersion, "status", "SENT"),
            (SalesOrder, "status", "DEPOSIT_PENDING"),
            (Receivable, "due_date", date(2000, 1, 1)),
        ):
            for row in session.scalars(
                select(model).where(model.organization_id == f.organization_a)
            ):
                setattr(row, field, value)
        for index in range(21):
            shipment = Shipment(
                organization_id=f.organization_a, shipment_number=f"SCALE-SHIP-{index}"
            )
            session.add(shipment)
            session.flush()
            customs = CustomsDeclaration(
                organization_id=f.organization_a,
                shipment_id=shipment.id,
                declaration_number=f"SCALE-CUSTOMS-{index}",
                declared_amount=Decimal("1"),
                currency_code="EUR",
                required_document_types=["COMMERCIAL_INVOICE"],
            )
            session.add(customs)
            session.flush()
            session.add(
                TaxRefundCase(
                    organization_id=f.organization_a,
                    customs_declaration_id=customs.id,
                    case_number=f"SCALE-REFUND-{index}",
                    expected_amount=Decimal("1"),
                    currency_code="EUR",
                    required_document_types=["COMMERCIAL_INVOICE"],
                )
            )

    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    statements = []

    def capture(_connection, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    checklist_queues = {QueueKind.SHIPMENTS, QueueKind.CUSTOMS, QueueKind.REFUNDS}
    observed = {}
    latency = {}
    event.listen(f.engine, "before_cursor_execute", capture)
    try:
        for queue in QueueKind:
            if queue == QueueKind.PREPARATION:
                with f.session_factory.begin() as session:
                    for row in session.scalars(
                        select(SalesOrder).where(SalesOrder.organization_id == f.organization_a)
                    ):
                        row.status = "EXECUTING"
            total = 42 if queue == QueueKind.RECEIVABLES else 21
            expected_queries = 3 if queue in checklist_queues else 2
            pages = {}
            observed[queue.value] = {}
            for limit in (1, 20, 100):
                with f.session_factory.begin() as session:
                    session.execute(text("SET TRANSACTION READ ONLY"))
                    statements.clear()
                    page = OverviewQueryService(session).page(context, queue, offset=0, limit=limit)
                    assert len(statements) == expected_queries, (queue, limit, statements)
                    observed[queue.value][limit] = len(statements)
                    assert len(page.items) == min(limit, total)
                    assert page.has_more is (limit < total)
                    assert page.next_offset == (limit if limit < total else None)
                    assert len({item.id for item in page.items}) == len(page.items)
                    if queue in checklist_queues:
                        missing = ["COMMERCIAL_INVOICE"]
                        if queue == QueueKind.SHIPMENTS:
                            missing.append("PACKING_LIST")
                        assert all(item.missing_document_types == missing for item in page.items)
                    pages[limit] = page.items
            assert pages[1] == pages[100][:1]
            assert pages[20] == pages[100][:20]
            with f.session_factory.begin() as session:
                session.execute(text("SET TRANSACTION READ ONLY"))
                service = OverviewQueryService(session)
                rest = service.page(context, queue, offset=20, limit=100)
                assert rest.items == pages[100][20:]
                assert rest.has_more is False and rest.next_offset is None
                foreign = service.page(
                    replace(context, organization_id=f.organization_b), queue, offset=0, limit=100
                )
                assert foreign.items == []
            timings = []
            expected_ids = [str(item.id) for item in pages[20]]
            for iteration in range(33):
                started = perf_counter()
                response = f.client.get(
                    f"/api/v1/overview/{queue.value}",
                    params={"limit": 20},
                    headers=f.headers("quotation-manager", f.organization_a),
                )
                elapsed = (perf_counter() - started) * 1000
                assert response.status_code == 200, response.text
                assert [item["id"] for item in response.json()["items"]] == expected_ids
                if iteration >= 3:
                    timings.append(elapsed)
            latency[queue.value] = {
                "count": len(timings),
                "p95_ms": round(sorted(timings)[math.ceil(len(timings) * 0.95) - 1], 3),
                "max_ms": round(max(timings), 3),
            }
    finally:
        event.remove(f.engine, "before_cursor_execute", capture)
    assert set(observed) == {queue.value for queue in QueueKind}
    print({"page_sizes": [1, 20, 100], "business_select_counts": observed})
    report = {
        "measured_at": datetime.now(UTC).isoformat(),
        "scope": "In-process ASGI + local PostgreSQL, single request concurrency",
        "dataset": "21 matching records per queue; 42 receivables; synthetic query states",
        "warmup": 3,
        "page_size": 20,
        "exclusions": ["network/TLS", "Logto/JWKS network", "browser rendering"],
        "metrics": latency,
        "business_select_counts": observed,
    }
    artifact = Path(__file__).resolve().parents[3] / "test-results/overview-performance.json"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    assert all(metric["p95_ms"] < 500 for metric in latency.values()), latency
