from datetime import date, timedelta
from uuid import UUID

import pytest
from app.finance.models import Receivable
from app.platform.models import AuditLog, OutboxEvent
from app.work.models import Activity
from sqlalchemy import event, select
from test_customer_finance_tenant_paths import facts
from test_finance_vertical_slice import allocation, finance_post, payment, receivables
from test_order_procurement_vertical_slice import create_confirmed_order
from test_quotation_vertical_slice import post_ok
from test_shipment_documents_vertical_slice import create_shipment, prepare_and_depart

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice", "test_shipment_documents_vertical_slice")


def prepare_command(f, storage, operation):
    order, _, _ = create_confirmed_order(f)
    if operation == "generate":
        return lambda: receivables(f, order)
    rows = receivables(f, order)
    if operation == "refresh":
        with f.session_factory.begin() as session:
            for row in session.scalars(select(Receivable)):
                row.status = "PENDING"
                row.due_date = date.today() - timedelta(days=2)
        return lambda: finance_post(f, "/api/v1/receivables/refresh-statuses", None)
    if operation == "reverse":
        receipt = payment(f, order, order["total"])
        for row in rows:
            allocation(f, receipt, row)
        return lambda: finance_post(
            f, f"/api/v1/payments/{receipt['id']}/reverse", {"reason": "Synthetic atomic reversal"}
        )
    for row in rows:
        allocation(f, payment(f, order, row["amount"]), row)
    shipment = create_shipment(
        f,
        [
            {"sales_order_item_id": item["id"], "quantity": item["quantity"]}
            for item in order["items"]
        ],
    )
    prepare_and_depart(f, storage, shipment)
    for step in ("start-transit", "arrive", "deliver"):
        post_ok(f, f"/api/v1/shipments/{shipment['id']}/{step}", "quotation-operations")
    headers = f.headers("quotation-manager", f.organization_a)
    tasks = f.client.get(f"/api/v1/sales-orders/{order['id']}/tasks", headers=headers).json()[
        "items"
    ]
    for task in tasks:
        post_ok(
            f,
            f"/api/v1/sales-orders/{order['id']}/tasks/{task['id']}/complete",
            "quotation-operations",
            {"expected_version": task["version"], "resolution": "Checked"},
        )
    current = f.client.get(f"/api/v1/sales-orders/{order['id']}", headers=headers).json()
    return lambda: post_ok(
        f,
        f"/api/v1/sales-orders/{order['id']}/complete",
        "quotation-manager",
        {"expected_version": current["version"]},
    )


@pytest.mark.parametrize("operation", ["generate", "refresh", "reverse", "complete"])
@pytest.mark.parametrize("model", [Activity, AuditLog, OutboxEvent])
def test_customer_finance_remaining_commands_roll_back_persisted_evidence_failure(
    quotation_fixture, fake_storage, operation, model
):
    f = quotation_fixture
    command = prepare_command(f, fake_storage, operation)
    before = facts(f)
    inserted = []

    def fail_after_insert(mapper, connection, row):
        inserted.append(row.id)
        raise RuntimeError("Synthetic persisted financial evidence failure")

    event.listen(model, "after_insert", fail_after_insert)
    try:
        with pytest.raises(RuntimeError, match="Synthetic persisted financial evidence failure"):
            command()
    finally:
        event.remove(model, "after_insert", fail_after_insert)
    assert len(inserted) == 1
    assert isinstance(inserted[0], UUID)
    assert facts(f) == before
    command()
    after = facts(f)
    assert after != before
    command()
    assert facts(f) == after
