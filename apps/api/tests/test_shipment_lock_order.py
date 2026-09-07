from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.fulfillment.models import Shipment
from app.fulfillment.schemas import ShipmentBook, ShipmentDecision
from app.fulfillment.services import ShipmentCommandService
from app.sales.models import SalesOrder
from sqlalchemy import event, select
from test_quotation_vertical_slice import post_ok, shipment_decision
from test_shipment_creation_idempotency import counts
from test_shipment_documents_vertical_slice import (
    create_shipment,
    executing_order,
    upload_required_document,
)

pytestmark = pytest.mark.integration
pytest_plugins = ("test_shipment_documents_vertical_slice",)

ACTIONS = (
    ("book", "BOOKED"),
    ("ready", "READY"),
    ("enter-customs", "CUSTOMS"),
    ("depart", "DEPARTED"),
    ("start-transit", "IN_TRANSIT"),
    ("arrive", "ARRIVED"),
    ("deliver", "DELIVERED"),
)


@pytest.mark.parametrize("action,target", ACTIONS)
@pytest.mark.parametrize("finalize_parent", [False, True])
def test_every_milestone_locks_parent_before_shipment(
    quotation_fixture, fake_storage, action, target, finalize_parent
):
    f = quotation_fixture
    order = executing_order(f)
    shipment = create_shipment(
        f,
        [
            {"sales_order_item_id": item["id"], "quantity": item["quantity"]}
            for item in order["items"]
        ],
    )
    shipment_id = UUID(shipment["id"])
    for kind in ("COMMERCIAL_INVOICE", "PACKING_LIST"):
        upload_required_document(f, fake_storage, shipment_id=str(shipment_id), document_type=kind)
    for previous, _ in ACTIONS:
        if previous == action:
            break
        post_ok(
            f,
            f"/api/v1/shipments/{shipment_id}/{previous}",
            "quotation-operations",
            {"booking_reference": "LOCK-ORDER"} if previous == "book" else None,
        )
    waiting = Event()
    locks = []
    request_body = shipment_decision(f, shipment_id)
    before = counts(f)

    def observe(_connection, _cursor, statement, *_args):
        sql = statement.lower()
        if "for update" not in sql:
            return
        if "from sales_orders" in sql or "from shipments" in sql:
            locks.append(sql)
        if "from sales_orders" in sql:
            waiting.set()

    def run():
        context = RequestContext(
            f.sales_user,
            f.organization_a,
            frozenset({Permission.SHIPMENT_TRANSITION}),
            uuid4(),
        )
        handler = getattr(ShipmentCommandService(f.session_factory), action.replace("-", "_"))
        request = (
            ShipmentBook(**request_body, booking_reference="LOCK-ORDER")
            if action == "book"
            else ShipmentDecision(**request_body)
        )
        try:
            return handler(context, shipment_id, request, idempotency_key="lock-order")[0].status
        except ApiProblem as error:
            return error.code

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
                session.connection().exec_driver_sql("SET LOCAL lock_timeout = '2s'")
                # A parent-owning operation must be able to inspect/lock the
                # shipment while the competing milestone waits for that parent.
                session.scalar(
                    select(Shipment)
                    .where(
                        Shipment.organization_id == f.organization_a,
                        Shipment.id == shipment_id,
                    )
                    .with_for_update()
                )
                if finalize_parent:
                    parent.status = "COMPLETED"
            assert future.result(timeout=10) == ("ORDER_FINALIZED" if finalize_parent else target)
        finally:
            event.remove(f.engine, "before_cursor_execute", observe)
    assert "from sales_orders" in locks[0]
    assert "order by sales_orders.id" in locks[0]
    if finalize_parent:
        assert counts(f) == before
