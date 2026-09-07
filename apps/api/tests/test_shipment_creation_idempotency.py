from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from threading import Event
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.fulfillment.models import Shipment, ShipmentItem
from app.fulfillment.services import ShipmentCommandService
from app.identity.models import OrganizationMembership
from app.platform.models import AuditLog, DocumentSequence, IdempotencyKey, OutboxEvent
from app.sales.models import SalesOrder, SalesOrderItem
from app.work.models import Activity
from sqlalchemy import event, func, select
from test_quotation_vertical_slice import post_ok
from test_shipment_documents_vertical_slice import executing_order

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration


def setup(f):
    order = executing_order(f)
    return order, {
        "items": [
            {"sales_order_item_id": item["id"], "quantity": "0.2500"} for item in order["items"]
        ]
    }


def context(f):
    return RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset({Permission.SHIPMENT_WRITE}),
        request_id=uuid4(),
    )


def counts(f):
    with f.session_factory() as session:
        return (
            *[
                session.scalar(select(func.count()).select_from(model))
                for model in (
                    Shipment,
                    ShipmentItem,
                    Activity,
                    AuditLog,
                    OutboxEvent,
                    IdempotencyKey,
                )
            ],
            session.scalar(select(func.sum(DocumentSequence.next_value))),
        )


def request(f, body, key, subject="quotation-operations"):
    headers = f.headers(subject, f.organization_a)
    if key is not None:
        headers["Idempotency-Key"] = key
    return f.client.post("/api/v1/shipments", headers=headers, json=body)


def test_replay_conflict_and_booking_preserve_original_resource(quotation_fixture):
    f = quotation_fixture
    _, body = setup(f)
    first = request(f, body, "once")
    assert first.status_code == 201, first.text
    before = counts(f)
    assert request(f, body, "once").json() == first.json()
    assert counts(f) == before
    changed = request(f, {**body, "planned_departure_date": "2026-11-11"}, "once")
    assert changed.status_code == 409
    assert changed.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert counts(f) == before
    booked = post_ok(
        f,
        f"/api/v1/shipments/{first.json()['id']}/book",
        "quotation-operations",
        {"booking_reference": "BK-1"},
    )
    before = counts(f)
    assert request(f, body, "once").json() == booked
    assert counts(f) == before
    with f.session_factory() as session:
        key = session.scalar(
            select(IdempotencyKey).where(IdempotencyKey.scope == "shipment.create")
        )
        assert key.status == "COMPLETED"
        assert key.resource_id == UUID(booked["id"])
        assert key.resource_type == "shipment"


def test_invalid_keys_permissions_and_unkeyed_compatibility(quotation_fixture):
    f = quotation_fixture
    _, body = setup(f)
    before = counts(f)
    for key in ("", "   ", "x" * 256):
        assert request(f, body, key).status_code == 422
    assert request(f, body, "denied", "quotation-sales").status_code == 403
    assert counts(f) == before
    with pytest.raises(ApiProblem) as denied:
        ShipmentCommandService(f.session_factory).create(
            replace(context(f), permissions=frozenset()), body, idempotency_key="denied"
        )
    assert denied.value.status == 403
    with f.session_factory() as session:
        other_user = session.scalar(
            select(OrganizationMembership.user_id).where(
                OrganizationMembership.organization_id == f.organization_b
            )
        )
    with pytest.raises(ApiProblem) as foreign:
        ShipmentCommandService(f.session_factory).create(
            replace(context(f), organization_id=f.organization_b, user_id=other_user),
            body,
            idempotency_key="foreign",
        )
    assert foreign.value.status == 404
    assert counts(f) == before
    one, two = request(f, body, None), request(f, body, None)
    assert one.status_code == two.status_code == 201
    assert one.json()["id"] != two.json()["id"]


@pytest.mark.parametrize("combined", [False, True])
def test_concurrent_first_numbers_for_disjoint_or_combined_orders(
    quotation_fixture, monkeypatch, combined
):
    import test_quotation_vertical_slice as fixtures

    original_post = fixtures.post_ok

    def unique_products(fixture, path, subject, body=None, expected_status=200):
        if path == "/api/v1/products":
            body = {**body, "sku": f"{body['sku']}-{uuid4().hex[:8]}"}
        return original_post(fixture, path, subject, body, expected_status)

    monkeypatch.setattr(fixtures, "post_ok", unique_products)
    f = quotation_fixture
    bodies = [setup(f)[1], setup(f)[1]]
    if combined:
        items = bodies[0]["items"] + bodies[1]["items"]
        bodies = [{"items": items}, {"items": list(reversed(items))}]

    def create(index):
        shipment, _, _ = ShipmentCommandService(f.session_factory).create(
            context(f), bodies[index], idempotency_key=f"disjoint-{index}"
        )
        return shipment.shipment_number

    with ThreadPoolExecutor(max_workers=2) as pool:
        numbers = list(pool.map(create, (0, 1)))
    assert len(set(numbers)) == 2
    assert sorted(number.rsplit("-", 1)[1] for number in numbers) == ["000001", "000002"]


@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
def test_evidence_failure_rolls_back_creation_and_retry_key(quotation_fixture, table):
    f = quotation_fixture
    _, body = setup(f)
    before = counts(f)

    def fail(_connection, _cursor, statement, *_args):
        if statement.lower().startswith(f"insert into {table} "):
            raise RuntimeError("injected evidence failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected evidence failure"):
            ShipmentCommandService(f.session_factory).create(
                context(f), body, idempotency_key="retry"
            )
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert counts(f) == before
    first = request(f, body, "retry")
    assert first.status_code == 201
    assert request(f, body, "retry").json() == first.json()


@pytest.mark.parametrize("mode", ["same", "conflict", "capacity"])
def test_concurrent_creation_replay_conflict_and_capacity(quotation_fixture, mode):
    f = quotation_fixture
    order, body = setup(f)
    if mode == "capacity":
        body = {
            "items": [
                {"sales_order_item_id": item["id"], "quantity": item["quantity"]}
                for item in order["items"]
            ]
        }
    before = counts(f)

    def create(index):
        data = (
            {**body, "planned_departure_date": "2026-11-11"}
            if mode == "conflict" and index
            else body
        )
        try:
            shipment, _, _ = ShipmentCommandService(f.session_factory).create(
                context(f), data, idempotency_key=f"key-{index}" if mode == "capacity" else "same"
            )
            return str(shipment.id)
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, (0, 1)))
    after = counts(f)
    assert after[0] == before[0] + 1
    assert after[1] == before[1] + len(body["items"])
    assert after[2:6] == tuple(value + 1 for value in before[2:6])
    if mode == "same":
        assert results[0] == results[1]
    else:
        assert (
            results.count(
                "IDEMPOTENCY_CONFLICT" if mode == "conflict" else "SHIPMENT_QUANTITY_EXCEEDED"
            )
            == 1
        )


@pytest.mark.parametrize("change", ["finalize", "delete_order", "delete_line"])
def test_creation_waits_for_parent_then_revalidates_sources(quotation_fixture, change):
    f = quotation_fixture
    order, body = setup(f)
    before = counts(f)
    waiting = Event()
    locks = []

    def observe(_connection, _cursor, statement, *_args):
        sql = statement.lower()
        if "for update" not in sql:
            return
        if "from sales_orders" in sql or "from sales_order_items" in sql:
            locks.append(sql)
        if "from sales_orders" in sql:
            waiting.set()

    def run():
        try:
            ShipmentCommandService(f.session_factory).create(
                context(f), body, idempotency_key="parent-race"
            )
        except ApiProblem as error:
            return error.code
        return "unexpected success"

    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            with f.session_factory.begin() as session:
                parent = session.scalar(
                    select(SalesOrder)
                    .where(
                        SalesOrder.organization_id == f.organization_a,
                        SalesOrder.id == UUID(order["id"]),
                    )
                    .with_for_update()
                )
                event.listen(f.engine, "before_cursor_execute", observe)
                future = pool.submit(run)
                assert waiting.wait(timeout=10)
                assert not future.done()
                # The competing parent owner can still lock its lines. With the
                # old line-first planner this would deadlock (bounded by timeout).
                session.connection().exec_driver_sql("SET LOCAL lock_timeout = '2s'")
                line = session.scalar(
                    select(SalesOrderItem)
                    .where(
                        SalesOrderItem.organization_id == f.organization_a,
                        SalesOrderItem.id == UUID(order["items"][0]["id"]),
                    )
                    .with_for_update()
                )
                if change == "finalize":
                    parent.status = "COMPLETED"
                elif change == "delete_order":
                    parent.deleted_at = datetime.now(UTC)
                else:
                    line.deleted_at = datetime.now(UTC)
            assert (
                future.result(timeout=10)
                == {
                    "finalize": "ORDER_NOT_EXECUTING",
                    "delete_order": "SALES_ORDER_NOT_FOUND",
                    "delete_line": "SALES_ORDER_ITEM_NOT_FOUND",
                }[change]
            )
        finally:
            event.remove(f.engine, "before_cursor_execute", observe)
    assert "from sales_orders" in locks[0]
    assert "order by sales_orders.id" in locks[0]
    assert counts(f) == before


def test_creation_locks_lines_in_id_order_and_preserves_selected_lines(quotation_fixture):
    f = quotation_fixture
    _, body = setup(f)
    body["items"].sort(key=lambda item: item["sales_order_item_id"], reverse=True)
    locks = []

    def observe(_connection, _cursor, statement, *_args):
        sql = statement.lower()
        if "for update" in sql and ("from sales_orders" in sql or "from sales_order_items" in sql):
            locks.append(sql)

    event.listen(f.engine, "before_cursor_execute", observe)
    try:
        response = request(f, body, "ordered")
    finally:
        event.remove(f.engine, "before_cursor_execute", observe)
    assert response.status_code == 201, response.text
    assert len(locks) == 2
    assert "order by sales_orders.id" in locks[0]
    assert "order by sales_order_items.id" in locks[1]
    assert {item["sales_order_item_id"] for item in response.json()["items"]} == {
        item["sales_order_item_id"] for item in body["items"]
    }
