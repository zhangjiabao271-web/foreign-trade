import json
import math
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import UUID, uuid4

import pytest
from alembic import command
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.sales.models import SalesOrder, SalesOrderItem
from app.sales.order_repositories import SalesOrderRepository
from app.sales.order_services import SalesOrderQueryService
from legacy_migration import assert_snapshot, legacy_snapshot
from sqlalchemy import event, inspect
from test_quotation_vertical_slice import (
    create_commercial_inputs,
    create_opportunity,
    post_ok,
    table_counts,
)

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def create_orders(f, count, request=None):
    reuse_products = request is not None
    if request is None:
        request, _, _ = create_commercial_inputs(f)
    expected = {}
    for index in range(count):
        if index or reuse_products:
            company_id, opportunity_id = create_opportunity(f)
            inquiry = post_ok(
                f,
                "/api/v1/inquiries",
                "quotation-sales",
                {
                    "company_id": company_id,
                    "opportunity_id": opportunity_id,
                    "description": "Batch order read fixture",
                    "received_at": datetime.now(UTC).isoformat(),
                },
                201,
            )
            request = {**request, "inquiry_id": inquiry["id"]}
        quote = post_ok(f, "/api/v1/quotations", "quotation-manager", request, 201)
        for action, subject in (
            ("submit", "quotation-sales"),
            ("approve", "quotation-manager"),
            ("send", "quotation-sales"),
            ("accept", "quotation-sales"),
        ):
            post_ok(f, f"/api/v1/quotations/{quote['id']}/{action}", subject)
        order = post_ok(
            f,
            "/api/v1/sales-orders",
            "quotation-sales",
            {"quotation_id": quote["id"], "deposit_rate": "0.3000"},
            201,
        )
        expected[order["id"]] = order
    return expected, request


def test_order_list_batches_lines_and_preserves_scoped_snapshots(quotation_fixture):
    f = quotation_fixture
    expected, _ = create_orders(f, 6)

    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset({Permission.ORDER_READ}),
        request_id=uuid4(),
    )
    statements = []

    def capture(_connection, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    before = table_counts(f)
    event.listen(f.engine, "before_cursor_execute", capture)
    try:
        for limit in (1, 6, 100):
            with f.session_factory() as session:
                statements.clear()
                orders = SalesOrderQueryService(SalesOrderRepository(session)).list(
                    context, limit=limit
                )
                serialized = [order.model_dump(mode="json") for order in orders]
                assert len(serialized) == min(limit, 6)
                assert len(statements) == 2
                assert serialized == [expected[row["id"]] for row in serialized]
    finally:
        event.remove(f.engine, "before_cursor_execute", capture)

    headers = f.headers("quotation-sales", f.organization_a)
    page = f.client.get("/api/v1/sales-orders", headers=headers).json()
    assert page["count"] == 6
    assert page["items"] == [expected[row["id"]] for row in page["items"]]
    assert table_counts(f) == before
    foreign_headers = f.headers("quotation-other", f.organization_b)
    assert f.client.get("/api/v1/sales-orders", headers=foreign_headers).json() == {
        "items": [],
        "count": 0,
        "has_more": False,
        "next_cursor": None,
    }

    ids = [UUID(order_id) for order_id in expected]
    # Equal timestamps require the UUID tie-breaker, not offset-based navigation.
    with f.session_factory.begin() as session:
        timestamp = datetime.now(UTC)
        for order_id in ids:
            session.get(SalesOrder, order_id).created_at = timestamp
    for order_id in ids:
        expected[str(order_id)] = f.client.get(
            f"/api/v1/sales-orders/{order_id}", headers=headers
        ).json()
    cursor = None
    seen = []
    for page_number in range(3):
        params = {"limit": 2}
        if cursor:
            params["cursor"] = cursor
        response = f.client.get("/api/v1/sales-orders", headers=headers, params=params)
        assert response.status_code == 200
        result = response.json()
        assert result["count"] == 2
        assert result["has_more"] is (page_number < 2)
        seen.extend(row["id"] for row in result["items"])
        assert result["items"] == [expected[row["id"]] for row in result["items"]]
        cursor = result["next_cursor"]
        assert cursor == (seen[-1] if page_number < 2 else None)
    assert seen == [str(value) for value in sorted(ids, reverse=True)]
    assert len(set(seen)) == 6
    last_page = f.client.get(
        "/api/v1/sales-orders", headers=headers, params={"cursor": seen[-1]}
    ).json()
    assert last_page == {"items": [], "count": 0, "has_more": False, "next_cursor": None}
    for rejected_headers, rejected_cursor, status in (
        (foreign_headers, seen[0], 404),
        (headers, str(uuid4()), 404),
        (headers, "not-a-uuid", 422),
    ):
        assert (
            f.client.get(
                "/api/v1/sales-orders",
                headers=rejected_headers,
                params={"cursor": rejected_cursor},
            ).status_code
            == status
        )
    assert table_counts(f) == before

    with f.session_factory() as session:
        repository = SalesOrderRepository(session)
        assert repository.items_for_orders(
            organization_id=f.organization_b, sales_order_ids=ids
        ) == {order_id: [] for order_id in ids}
        event.listen(f.engine, "before_cursor_execute", capture)
        try:
            statements.clear()
            assert (
                repository.items_for_orders(organization_id=f.organization_a, sales_order_ids=[])
                == {}
            )
            assert not statements
        finally:
            event.remove(f.engine, "before_cursor_execute", capture)

    first = expected[str(ids[0])]
    with f.session_factory.begin() as session:
        session.get(SalesOrderItem, UUID(first["items"][0]["id"])).deleted_at = datetime.now(UTC)
        session.get(SalesOrder, ids[1]).deleted_at = datetime.now(UTC)
    page = f.client.get("/api/v1/sales-orders", headers=headers).json()
    assert page["count"] == 5
    assert str(ids[1]) not in {row["id"] for row in page["items"]}
    assert (
        f.client.get(
            "/api/v1/sales-orders", headers=headers, params={"cursor": str(ids[1])}
        ).status_code
        == 404
    )
    remaining = next(row for row in page["items"] if row["id"] == first["id"])
    assert remaining["items"] == first["items"][1:]

    denied = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(),
        request_id=uuid4(),
    )
    with f.session_factory() as session, pytest.raises(ApiProblem) as error:
        SalesOrderQueryService(SalesOrderRepository(session)).list(denied, limit=50)
    assert error.value.status == 403


def test_order_pages_reach_beyond_one_hundred_without_offset_drift(quotation_fixture):
    f = quotation_fixture
    expected, template = create_orders(f, 105)
    headers = f.headers("quotation-sales", f.organization_a)
    path = "/api/v1/sales-orders"
    before = table_counts(f)
    first = f.client.get(path, headers=headers, params={"limit": 50}).json()
    assert first["count"] == 50 and first["has_more"]
    verify_cursor_performance(f, first["next_cursor"])
    # Newer inserts must not push already-seen records into a subsequent page.
    inserted, _ = create_orders(f, 1, template)
    removed = next(
        order_id for order_id in expected if order_id not in {row["id"] for row in first["items"]}
    )
    with f.session_factory.begin() as session:
        session.get(SalesOrder, UUID(removed)).deleted_at = datetime.now(UTC)
    after_changes = table_counts(f)
    found = list(first["items"])
    cursor = first["next_cursor"]
    for size in (50, 4):
        response = f.client.get(path, headers=headers, params={"limit": 50, "cursor": cursor})
        assert response.status_code == 200
        page = response.json()
        assert page["count"] == size
        assert page["has_more"] is (size == 50)
        found.extend(page["items"])
        cursor = page["next_cursor"]
    assert cursor is None
    assert len(found) == len({row["id"] for row in found}) == 104
    assert {row["id"] for row in found} == set(expected) - {removed}
    assert not set(inserted).intersection(row["id"] for row in found)
    assert found == [expected[row["id"]] for row in found]
    assert table_counts(f) == after_changes
    assert before != after_changes


def test_order_cursor_index_upgrade_preserves_commercial_facts(quotation_fixture):
    f = quotation_fixture
    create_orders(f, 1)
    name = "ix_sales_orders_org_created_id_active"
    with legacy_snapshot(f.engine, "20260907_0031") as (config, target, metadata, expected):
        command.downgrade(config, "20260906_0030")
        assert_snapshot(target, metadata, expected)
        assert name not in {index["name"] for index in inspect(target).get_indexes("sales_orders")}
        command.upgrade(config, "head")
        command.check(config)
        assert_snapshot(target, metadata, expected)
        indexes = {index["name"]: index for index in inspect(target).get_indexes("sales_orders")}
        assert indexes[name]["column_names"] == ["organization_id", "created_at", "id"]


def verify_cursor_performance(f, cursor):
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset({Permission.ORDER_READ}),
        request_id=uuid4(),
    )
    statements = []

    def capture(_connection, _cursor, statement, parameters, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append((statement, parameters))

    event.listen(f.engine, "before_cursor_execute", capture)
    try:
        with f.session_factory() as session:
            rows = SalesOrderQueryService(SalesOrderRepository(session)).list(
                context, limit=51, cursor=UUID(cursor)
            )
            assert len(rows) == 51
            assert len(statements) == 3
    finally:
        event.remove(f.engine, "before_cursor_execute", capture)
    with f.engine.connect() as connection:
        statement, parameters = statements[1]
        plan = connection.exec_driver_sql(
            "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters
        ).scalar_one()
    headers = f.headers("quotation-sales", f.organization_a)
    samples = []
    for index in range(33):
        started = perf_counter()
        response = f.client.get(
            "/api/v1/sales-orders", headers=headers, params={"limit": 50, "cursor": cursor}
        )
        duration = (perf_counter() - started) * 1000
        assert response.status_code == 200
        if index >= 3:
            samples.append(duration)
    p95 = sorted(samples)[math.ceil(len(samples) * 0.95) - 1]
    report = {
        "measured_at": datetime.now(UTC).isoformat(),
        "scope": "ASGI HTTP + real PostgreSQL; one request at a time; no network/browser",
        "orders": 105,
        "lines_per_order": 2,
        "page_size": 50,
        "samples": len(samples),
        "warmups": 3,
        "p95_ms": round(p95, 3),
        "business_selects": len(statements),
        "page_query_explain": plan,
    }
    artifact = (
        Path(__file__).resolve().parents[3] / "test-results" / "order-cursor-performance.json"
    )
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    assert p95 < 500
