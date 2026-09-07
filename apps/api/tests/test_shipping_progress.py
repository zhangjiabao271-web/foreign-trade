from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.fulfillment.models import Shipment
from app.platform.models import AuditLog, OutboxEvent
from app.platform.records import AuditRecorder, OutboxRecorder
from app.sales.models import SalesOrder
from app.sales.shipping_progress import refresh_shipping_progress
from app.work.models import Activity
from sqlalchemy import event, select
from test_quotation_vertical_slice import post_ok, shipment_decision
from test_shipment_documents_vertical_slice import (
    create_shipment,
    executing_order,
    upload_required_document,
)

pytestmark = pytest.mark.integration
pytest_plugins = ("test_shipment_documents_vertical_slice",)


def booked_with_evidence(fixture, storage):
    order = executing_order(fixture)
    shipment = create_shipment(
        fixture,
        [
            {"sales_order_item_id": item["id"], "quantity": item["quantity"]}
            for item in order["items"]
        ],
    )
    post_ok(
        fixture,
        f"/api/v1/shipments/{shipment['id']}/book",
        "quotation-operations",
        {"booking_reference": "PROGRESS-TEST"},
    )
    for kind in ("COMMERCIAL_INVOICE", "PACKING_LIST"):
        upload_required_document(fixture, storage, shipment_id=shipment["id"], document_type=kind)
    return order, shipment


@pytest.mark.parametrize("model", [Activity, AuditLog, OutboxEvent])
def test_order_progress_failure_rolls_back_shipment_and_order(
    quotation_fixture, fake_storage, model
):
    fixture = quotation_fixture
    order, shipment = booked_with_evidence(fixture, fake_storage)

    def fail_order_record(mapper, connection, target):
        subject = getattr(target, "subject_type", None)
        subject = subject or getattr(target, "target_type", None)
        subject = subject or getattr(target, "aggregate_type", None)
        if subject == "sales_order":
            raise RuntimeError("injected order progress record failure")

    event.listen(model, "before_insert", fail_order_record)
    try:
        with pytest.raises(RuntimeError, match="injected order progress record failure"):
            fixture.client.post(
                f"/api/v1/shipments/{shipment['id']}/ready",
                headers=fixture.headers("quotation-operations", fixture.organization_a)
                | {"Idempotency-Key": str(uuid4())},
                json=shipment_decision(fixture, shipment["id"]),
                # This request intentionally reaches the evidence failure, not validation.
            )
    finally:
        event.remove(model, "before_insert", fail_order_record)
    with fixture.session_factory() as session:
        order_row = session.scalar(
            select(SalesOrder).where(
                SalesOrder.organization_id == fixture.organization_a,
                SalesOrder.id == UUID(order["id"]),
            )
        )
        shipment_row = session.scalar(
            select(Shipment).where(
                Shipment.organization_id == fixture.organization_a,
                Shipment.id == UUID(shipment["id"]),
            )
        )
        assert order_row.status == "EXECUTING"
        assert shipment_row.status == "BOOKED" and shipment_row.ready_at is None


def test_shipping_port_is_permission_checked_tenant_scoped_and_batched(
    quotation_fixture, fake_storage
):
    fixture = quotation_fixture
    order, shipment = booked_with_evidence(fixture, fake_storage)
    post_ok(fixture, f"/api/v1/shipments/{shipment['id']}/ready", "quotation-operations")
    item_ids = [UUID(item["id"]) for item in order["items"]]

    def refresh(session, organization, permissions):
        refresh_shipping_progress(
            session,
            RequestContext(fixture.sales_user, organization, permissions, uuid4()),
            source_item_ids=item_ids,
            departed=False,
            audit_recorder=AuditRecorder(),
            outbox_recorder=OutboxRecorder(),
        )

    with fixture.session_factory.begin() as session:
        with pytest.raises(ApiProblem) as denied:
            refresh(session, fixture.organization_a, frozenset())
        assert denied.value.status == 403
    permissions = frozenset({Permission.SHIPMENT_TRANSITION})
    with fixture.session_factory.begin() as session:
        refresh(session, fixture.organization_b, permissions)
        assert not session.new and not session.dirty
    statements = []

    def capture(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    engine = fixture.session_factory.kw["bind"]
    event.listen(engine, "before_cursor_execute", capture)
    try:
        with fixture.session_factory.begin() as session:
            refresh(session, fixture.organization_a, permissions)
            assert not session.new and not session.dirty
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert len(statements) == 3


@pytest.mark.parametrize("status", ["DEPOSIT_PENDING", "COMPLETED", "CANCELLED"])
def test_shipping_port_does_not_advance_ineligible_order(quotation_fixture, fake_storage, status):
    fixture = quotation_fixture
    order, shipment = booked_with_evidence(fixture, fake_storage)
    post_ok(fixture, f"/api/v1/shipments/{shipment['id']}/ready", "quotation-operations")
    with fixture.session_factory.begin() as session:
        row = session.scalar(
            select(SalesOrder).where(
                SalesOrder.organization_id == fixture.organization_a,
                SalesOrder.id == UUID(order["id"]),
            )
        )
        row.status = status
    with fixture.session_factory.begin() as session:
        refresh_shipping_progress(
            session,
            RequestContext(
                fixture.sales_user,
                fixture.organization_a,
                frozenset({Permission.SHIPMENT_TRANSITION}),
                uuid4(),
            ),
            source_item_ids=[UUID(item["id"]) for item in order["items"]],
            departed=False,
            audit_recorder=AuditRecorder(),
            outbox_recorder=OutboxRecorder(),
        )
        assert not session.new and not session.dirty
        row = session.scalar(
            select(SalesOrder).where(
                SalesOrder.organization_id == fixture.organization_a,
                SalesOrder.id == UUID(order["id"]),
            )
        )
        assert row.status == status
