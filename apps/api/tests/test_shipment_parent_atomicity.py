from datetime import UTC, datetime
from uuid import UUID

import pytest
from app.fulfillment.models import Shipment, ShipmentItem
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.sales.models import SalesOrder, SalesOrderItem
from app.work.models import Activity
from sqlalchemy import event, select
from test_quotation_vertical_slice import (
    create_commercial_inputs,
    create_opportunity,
    post_ok,
    shipment_decision,
)
from test_shipment_documents_vertical_slice import (
    create_shipment,
    upload_required_document,
)

pytestmark = pytest.mark.integration
pytest_plugins = ("test_shipment_documents_vertical_slice",)


def snapshot(f):
    with f.session_factory() as session:
        return {
            model.__tablename__: [
                dict(row)
                for row in session.execute(select(model.__table__).order_by(model.id)).mappings()
            ]
            for model in (
                SalesOrder,
                SalesOrderItem,
                Shipment,
                ShipmentItem,
                Activity,
                AuditLog,
                OutboxEvent,
                IdempotencyKey,
            )
        }


@pytest.mark.parametrize("action", ["ready", "depart"])
@pytest.mark.parametrize("parent_count", [1, 2])
@pytest.mark.parametrize(
    "evidence_model,owner_field,id_field",
    [
        (Activity, "subject_type", "subject_id"),
        (AuditLog, "target_type", "target_id"),
        (OutboxEvent, "aggregate_type", "aggregate_id"),
    ],
)
def test_order_side_insert_failure_rolls_back_complete_shipment_transaction(
    quotation_fixture, fake_storage, action, parent_count, evidence_model, owner_field, id_field
):
    f = quotation_fixture
    quote_body, _, _ = create_commercial_inputs(f)
    orders = []
    for index in range(parent_count):
        if index:
            company_id, opportunity_id = create_opportunity(f)
            inquiry = post_ok(
                f,
                "/api/v1/inquiries",
                "quotation-sales",
                {
                    "company_id": company_id,
                    "opportunity_id": opportunity_id,
                    "customer_reference": f"PARENT-ROLLBACK-{index}",
                    "description": "Synthetic combined shipment source",
                    "received_at": datetime.now(UTC).isoformat(),
                },
                201,
            )
            quote_body = {**quote_body, "inquiry_id": inquiry["id"]}
        quote = post_ok(f, "/api/v1/quotations", "quotation-manager", quote_body, 201)
        for step in ("submit", "approve", "send", "accept"):
            post_ok(f, f"/api/v1/quotations/{quote['id']}/{step}", "quotation-manager")
        order = post_ok(
            f,
            "/api/v1/sales-orders",
            "quotation-manager",
            {"quotation_id": quote["id"], "deposit_rate": "0"},
            201,
        )
        orders.append(
            post_ok(f, f"/api/v1/sales-orders/{order['id']}/confirm", "quotation-manager")
        )
    parent_ids = {UUID(order["id"]) for order in orders}
    last_parent_id = max(parent_ids)
    shipment = create_shipment(
        f,
        [
            {"sales_order_item_id": item["id"], "quantity": item["quantity"]}
            for order in orders
            for item in order["items"]
        ],
    )
    for kind in ("COMMERCIAL_INVOICE", "PACKING_LIST"):
        upload_required_document(f, fake_storage, shipment_id=shipment["id"], document_type=kind)
    post_ok(
        f,
        f"/api/v1/shipments/{shipment['id']}/book",
        "quotation-operations",
        {"booking_reference": "SYNTHETIC-PARENT-ROLLBACK"},
    )
    if action == "depart":
        for preceding in ("ready", "enter-customs"):
            post_ok(f, f"/api/v1/shipments/{shipment['id']}/{preceding}", "quotation-operations")
    body = shipment_decision(f, shipment["id"])
    headers = f.headers("quotation-operations", f.organization_a)
    headers["Idempotency-Key"] = "parent-evidence-recovery"
    url = f"/api/v1/shipments/{shipment['id']}/{action}"
    before = snapshot(f)
    failed_ids = []

    def fail_after_order_insert(mapper, connection, target):
        if (
            getattr(target, owner_field) == "sales_order"
            and getattr(target, id_field) == last_parent_id
        ):
            failed_ids.append(getattr(target, id_field))
            raise RuntimeError("Injected persisted parent evidence failure")

    # Fail after SQL INSERT, specifically at the last UUID-ordered parent, not
    # at the shipment's earlier evidence. All records still belong to one UoW.
    event.listen(evidence_model, "after_insert", fail_after_order_insert)
    try:
        with pytest.raises(RuntimeError, match="Injected persisted parent evidence failure"):
            f.client.post(url, json=body, headers=headers)
    finally:
        event.remove(evidence_model, "after_insert", fail_after_order_insert)
    assert failed_ids == [last_parent_id]
    assert snapshot(f) == before

    response = f.client.post(url, json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == ("READY" if action == "ready" else "DEPARTED")
    after = snapshot(f)
    for table in ("activities", "audit_logs", "outbox_events"):
        assert len(after[table]) == len(before[table]) + parent_count + 1
    assert len(after["idempotency_keys"]) == len(before["idempotency_keys"]) + 1
    assert after["sales_order_items"] == before["sales_order_items"]
    assert after["shipment_items"] == before["shipment_items"]
    original_orders = {row["id"]: row for row in before["sales_orders"]}
    for row in after["sales_orders"]:
        original = original_orders[row["id"]]
        assert row["id"] in parent_ids
        assert row["status"] == ("READY_TO_SHIP" if action == "ready" else "SHIPPED")
        assert row["version"] == original["version"] + 1
        for field, value in original.items():
            if field not in {"status", "version", "updated_at", "updated_by"}:
                assert row[field] == value
    replay = f.client.post(url, json=body, headers=headers)
    assert replay.status_code == 200
    assert replay.json() == response.json()
    assert snapshot(f) == after
