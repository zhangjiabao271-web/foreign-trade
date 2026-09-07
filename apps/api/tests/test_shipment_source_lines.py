import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from uuid import UUID, uuid4

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.catalog.models import Product
from app.fulfillment.models import Shipment, ShipmentItem
from app.fulfillment.repositories import ShipmentRepository
from app.fulfillment.services import ShipmentQueryService
from app.identity.enums import MembershipRole
from app.sales.models import SalesOrder, SalesOrderItem
from app.sales.order_repositories import SalesOrderRepository
from app.sales.order_services import SalesOrderQueryService
from app.sales.text_review import CommercialTextReviewRequest, CommercialTextReviewService
from sqlalchemy import event, select
from test_commercial_text_review import request
from test_document_review import counts, reviewer
from test_shipment_documents_vertical_slice import create_shipment, executing_order

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration


def test_shipment_sources_are_direct_bounded_protected_and_read_only(quotation_fixture):
    f = quotation_fixture
    order = executing_order(f)
    source_id = UUID(order["items"][0]["id"])
    shipment = create_shipment(f, [{"sales_order_item_id": str(source_id), "quantity": "0.1"}])
    shipment_id = UUID(shipment["id"])
    order_id = UUID(order["id"])
    endpoint = f"/api/v1/shipments/{shipment_id}/source-lines"
    with f.session_factory.begin() as session:
        session.get(SalesOrder, order_id).created_at = datetime(2000, 1, 1, tzinfo=UTC)
    contexts = {}
    for role in MembershipRole:
        subject, context = reviewer(f, role)
        contexts[role] = context
        before = counts(f)
        response = f.client.get(endpoint, headers=f.headers(subject, f.organization_a))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["count"] == 1
        line = body["items"][0]
        assert line["id"] == str(source_id)
        assert line["sales_order_id"] == str(order_id)
        assert line["order_number"] == order["order_number"]
        assert line["sku_snapshot"] == order["items"][0]["sku_snapshot"]
        assert set(line) == {
            "id",
            "sales_order_id",
            "order_number",
            "order_status",
            "sku_snapshot",
            "description_snapshot",
            "unit_snapshot",
        }
        assert (line["description_snapshot"] is not None) == (
            Permission.PROFIT_READ in context.permissions
        )
        assert counts(f) == before
    low = contexts[MembershipRole.OPERATIONS]
    high = contexts[MembershipRole.MANAGER]

    def read(context=low):
        with f.session_factory() as session:
            return ShipmentQueryService(ShipmentRepository(session)).source_lines(
                context, shipment_id
            )

    statements = []

    def capture(_connection, _cursor, statement, parameters, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append((statement, parameters))

    event.listen(f.engine, "before_cursor_execute", capture)
    try:
        assert read().count == 1
        assert len(statements) == 4
    finally:
        event.remove(f.engine, "before_cursor_execute", capture)
    plans = []
    with f.engine.connect() as connection:
        for statement, parameters in statements:
            plans.append(
                connection.exec_driver_sql(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + statement, parameters
                ).scalar_one()
            )
    samples = []
    headers = f.headers("quotation-operations", f.organization_a)
    for index in range(33):
        start = perf_counter()
        response = f.client.get(endpoint, headers=headers)
        elapsed = (perf_counter() - start) * 1000
        assert response.status_code == 200
        if index >= 3:
            samples.append(elapsed)
    p95 = sorted(samples)[28]
    assert p95 < 500
    output = Path(__file__).resolve().parents[3] / "test-results/shipment-source-performance.json"
    output.write_text(
        json.dumps(
            {
                "measured_at": datetime.now(UTC).isoformat(),
                "scope": (
                    "ASGI HTTP + real PostgreSQL, single concurrency; "
                    "one shipment/source order, two order lines, one shipped line"
                ),
                "samples": 30,
                "warmups": 3,
                "p95_ms": round(p95, 3),
                "business_selects": len(statements),
                "plans": plans,
            },
            indent=2,
        ),
        encoding="utf8",
    )
    for permissions in ({Permission.ORDER_READ}, {Permission.SHIPMENT_READ}, set()):
        with pytest.raises(ApiProblem) as denied:
            read(replace(low, permissions=frozenset(permissions)))
        assert denied.value.status == 403
    with pytest.raises(ApiProblem) as foreign:
        read(replace(low, organization_id=f.organization_b))
    assert foreign.value.status == 404
    assert (
        f.client.get(
            f"/api/v1/shipments/{uuid4()}/source-lines",
            headers=f.headers("quotation-operations", f.organization_a),
        ).status_code
        == 404
    )

    reviews = CommercialTextReviewService(f.session_factory)
    preview = reviews.inspect(high, "sales_order", order_id)
    reviews.decide(
        high,
        "sales_order",
        order_id,
        request(CommercialTextReviewRequest, preview),
        key="release-source",
    )
    assert read().items[0].description_snapshot == order["items"][0]["description_snapshot"]
    # An unshipped line is still part of the source's exact disclosure binding.
    other_id = UUID(order["items"][1]["id"])
    with f.session_factory.begin() as session:
        session.get(SalesOrderItem, other_id).description_snapshot = "Changed confidential source"
    assert read().items[0].description_snapshot is None
    with f.session_factory() as session:
        service = SalesOrderQueryService(SalesOrderRepository(session))
        with pytest.raises(ApiProblem) as invalid:
            service.source_lines(low, [source_id] * 201)
        assert invalid.value.status == 422
        with pytest.raises(ApiProblem) as missing:
            service.source_lines(low, [source_id, uuid4()])
        assert missing.value.status == 404
    for model, record_id in (
        (SalesOrderItem, source_id),
        (SalesOrder, order_id),
        (Shipment, shipment_id),
    ):
        with f.session_factory.begin() as session:
            session.get(model, record_id).deleted_at = datetime.now(UTC)
        with pytest.raises(ApiProblem) as deleted:
            read()
        assert deleted.value.status == 404
        with f.session_factory.begin() as session:
            session.get(model, record_id).deleted_at = None
    with f.session_factory.begin() as session:
        session.get(ShipmentItem, UUID(shipment["items"][0]["id"])).deleted_at = datetime.now(UTC)
    before = counts(f)
    assert read().items == []
    assert counts(f) == before


def test_combined_shipment_sources_keep_parent_mapping_and_batch_queries(quotation_fixture):
    f = quotation_fixture
    first = executing_order(f)
    with f.session_factory.begin() as session:
        for product in session.scalars(select(Product)):
            product.sku += "-FIRST"
    second = executing_order(f)
    source_ids = [UUID(item["id"]) for order in (first, second) for item in order["items"]]
    shipment = create_shipment(
        f,
        [
            {"sales_order_item_id": str(item_id), "quantity": "0.1"}
            for item_id in reversed(source_ids)
        ],
    )
    _, context = reviewer(f)
    statements = []

    def capture(_connection, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    before = counts(f)
    event.listen(f.engine, "before_cursor_execute", capture)
    try:
        with f.session_factory() as session:
            result = ShipmentQueryService(ShipmentRepository(session)).source_lines(
                context, UUID(shipment["id"])
            )
        assert result.count == 4
        assert len(statements) == 4
    finally:
        event.remove(f.engine, "before_cursor_execute", capture)
    expected = {UUID(item["id"]): order for order in (first, second) for item in order["items"]}
    for source in result.items:
        assert source.sales_order_id == UUID(expected[source.id]["id"])
        assert source.order_number == expected[source.id]["order_number"]
    assert counts(f) == before
