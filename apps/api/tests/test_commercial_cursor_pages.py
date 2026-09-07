import json
import math
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import UUID, uuid4

import pytest
from alembic import command
from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.fulfillment.models import Shipment
from app.fulfillment.repositories import ShipmentRepository
from app.fulfillment.services import ShipmentQueryService
from app.identity.enums import MembershipRole, MembershipStatus
from app.identity.models import OrganizationMembership, User
from app.inquiries.models import Inquiry
from app.inquiries.repositories import InquiryRepository
from app.inquiries.services import InquiryQueryService
from app.procurement.models import PurchaseOrder
from app.procurement.repositories import PurchaseOrderRepository
from app.procurement.services import PurchaseOrderQueryService
from app.sales.models import Quotation
from app.sales.repositories import QuotationRepository
from app.sales.services import QuotationQueryService
from legacy_migration import assert_snapshot, legacy_snapshot
from sqlalchemy import event, select
from test_order_list_queries import create_orders
from test_quotation_vertical_slice import post_ok, table_counts

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration


def test_commercial_pages_reach_all_ties_and_preserve_tenant_and_text_rules(quotation_fixture):
    f = quotation_fixture
    orders, _ = create_orders(f, 105)
    source = next(iter(orders.values()))
    post_ok(f, f"/api/v1/sales-orders/{source['id']}/confirm", "quotation-manager")
    post_ok(
        f,
        f"/api/v1/companies/{source['company_id']}/roles",
        "quotation-manager",
        {"role": "SUPPLIER"},
        201,
    )
    purchases = [
        post_ok(
            f,
            "/api/v1/purchase-orders",
            "quotation-manager",
            {
                "sales_order_id": source["id"],
                "supplier_company_id": source["company_id"],
                "currency_code": "EUR",
                "exchange_rate": "1.00000000",
                "items": [
                    {
                        "sales_order_item_id": source["items"][0]["id"],
                        "quantity": "0.0001",
                        "unit_cost": "100.0000",
                    }
                ],
            },
            201,
        )
        for _ in range(105)
    ]
    with f.session_factory.begin() as session:
        session.add_all(
            [
                Shipment(organization_id=f.organization_a, shipment_number=f"PAGE-{index}")
                for index in range(105)
            ]
        )
    headers = f.headers("quotation-operations", f.organization_a)
    foreign = f.headers("quotation-other", f.organization_b)
    with f.session_factory.begin() as session:
        for role in MembershipRole:
            user = User(external_subject=f"cursor-{role}", display_name=f"Cursor {role}")
            session.add(user)
            session.flush()
            session.add(
                OrganizationMembership(
                    organization_id=f.organization_a,
                    user_id=user.id,
                    role=role,
                    status=MembershipStatus.ACTIVE,
                )
            )
    measurements = {}
    for path, model, timestamp_column, params in (
        ("/api/v1/quotations", Quotation, "created_at", {"status": "ACCEPTED"}),
        ("/api/v1/inquiries", Inquiry, "received_at", {"status": "QUOTING"}),
        ("/api/v1/shipments", Shipment, "created_at", {}),
        ("/api/v1/purchase-orders", PurchaseOrder, "created_at", {"sales_order_id": source["id"]}),
    ):
        with f.session_factory.begin() as session:
            rows = session.scalars(
                select(model).where(model.organization_id == f.organization_a)
            ).all()
            expected_ids = sorted((str(row.id) for row in rows), reverse=True)
            timestamp = datetime.now(UTC)
            for row in rows:
                setattr(row, timestamp_column, timestamp)
        before = table_counts(f)
        found = []
        query = {**params, "limit": 50}
        for expected_count in (50, 50, 5):
            response = f.client.get(path, headers=headers, params=query)
            assert response.status_code == 200, response.text
            page = response.json()
            assert page["count"] == len(page["items"]) == expected_count
            assert page["has_more"] is (expected_count == 50)
            found.extend(page["items"])
            query["cursor"] = page["next_cursor"]
        assert query["cursor"] is None
        assert [row["id"] for row in found] == expected_ids
        if model is Quotation:
            assert all(row["gross_profit"] is row["gross_margin"] is None for row in found)
        elif model is Inquiry:
            assert all(row["description"] is None for row in found)
        elif model is PurchaseOrder:
            assert all(row["total"] is row["currency_code"] is None for row in found)
            assert all(
                item["unit_cost"] is item["description_snapshot"] is None
                for row in found
                for item in row["items"]
            )
        else:
            assert all(
                row["missing_required_documents"] == ["COMMERCIAL_INVOICE", "PACKING_LIST"]
                for row in found
            )
        assert table_counts(f) == before
        for role in MembershipRole:
            response = f.client.get(
                path,
                headers=f.headers(f"cursor-{role}", f.organization_a),
                params={**params, "limit": 50, "cursor": expected_ids[49]},
            )
            assert response.status_code == 200, response.text
            page_items = response.json()["items"]
            assert len(page_items) == 50
            visible = role in {MembershipRole.ADMIN, MembershipRole.MANAGER, MembershipRole.FINANCE}
            if model is Quotation:
                assert all((row["gross_profit"] is not None) is visible for row in page_items)
            elif model is Inquiry:
                assert all((row["description"] is not None) is visible for row in page_items)
            elif model is PurchaseOrder:
                assert all((row["total"] is not None) is visible for row in page_items)
                assert all(
                    (item["unit_cost"] is not None) is visible
                    for row in page_items
                    for item in row["items"]
                )
        measurements[path] = measure_page(f, path, params, expected_ids[49])
        empty = f.client.get(path, headers=foreign).json()
        assert empty == {"items": [], "count": 0, "has_more": False, "next_cursor": None}
        for cursor, request_headers, status in (
            (expected_ids[0], foreign, 404),
            (str(uuid4()), headers, 404),
            ("invalid", headers, 422),
        ):
            assert (
                f.client.get(
                    path, headers=request_headers, params={**params, "cursor": cursor}
                ).status_code
                == status
            )
        with f.session_factory.begin() as session:
            session.get(model, UUID(expected_ids[0])).deleted_at = datetime.now(UTC)
        assert (
            f.client.get(
                path, headers=headers, params={**params, "cursor": expected_ids[0]}
            ).status_code
            == 404
        )
    # The same organization cannot use another order's purchase cursor under this filter.
    other_order_id = next(value for value in orders if value != source["id"])
    assert (
        f.client.get(
            "/api/v1/purchase-orders",
            headers=headers,
            params={"sales_order_id": other_order_id, "cursor": purchases[-1]["id"]},
        ).status_code
        == 404
    )
    with legacy_snapshot(f.engine, "20260907_0032") as (config, target, metadata, expected):
        command.downgrade(config, "20260907_0031")
        assert_snapshot(target, metadata, expected)
        command.upgrade(config, "head")
        command.check(config)
        assert_snapshot(target, metadata, expected)
    artifact = (
        Path(__file__).resolve().parents[3] / "test-results" / "commercial-cursor-performance.json"
    )
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(
        json.dumps(
            {
                "measured_at": datetime.now(UTC).isoformat(),
                "scope": "ASGI HTTP + PostgreSQL; single request; excludes network/browser",
                "rows_per_entity": 105,
                "page_size": 50,
                "measurements": measurements,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def measure_page(f, path, filters, cursor):
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    statements = []

    def capture(_connection, _cursor, statement, parameters, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append((statement, parameters))

    event.listen(f.engine, "before_cursor_execute", capture)
    try:
        with f.session_factory() as session:
            options = {"limit": 51, "cursor": UUID(cursor)}
            if path.endswith("shipments"):
                ShipmentQueryService(ShipmentRepository(session)).list(context, **options)
                expected_queries = 4
            elif path.endswith("purchase-orders"):
                PurchaseOrderQueryService(PurchaseOrderRepository(session)).list(
                    context, **options, sales_order_id=UUID(filters["sales_order_id"])
                )
                expected_queries = 3
            elif path.endswith("quotations"):
                QuotationQueryService(QuotationRepository(session)).list(
                    context, **options, status=filters["status"]
                )
                expected_queries = 2
            else:
                InquiryQueryService(InquiryRepository(session)).list(
                    context, **options, status=filters["status"]
                )
                expected_queries = 2
    finally:
        event.remove(f.engine, "before_cursor_execute", capture)
    assert len(statements) == expected_queries
    with f.engine.connect() as connection:
        statement, parameters = statements[1]
        plan = connection.exec_driver_sql(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters
        ).scalar_one()
    samples = []
    for index in range(33):
        started = perf_counter()
        response = f.client.get(
            path,
            headers=f.headers("quotation-operations", f.organization_a),
            params={**filters, "limit": 50, "cursor": cursor},
        )
        elapsed = (perf_counter() - started) * 1000
        assert response.status_code == 200
        if index >= 3:
            samples.append(elapsed)
    p95 = sorted(samples)[math.ceil(len(samples) * 0.95) - 1]
    assert p95 < 500
    return {
        "p95_ms": round(p95, 3),
        "samples": 30,
        "warmups": 3,
        "business_selects": expected_queries,
        "page_query_explain": plan,
    }
