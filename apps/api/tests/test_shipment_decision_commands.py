from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from threading import Barrier
from uuid import UUID

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.documents.models import DocumentVersion
from app.fulfillment.models import Shipment
from app.fulfillment.schemas import ShipmentBook, ShipmentDecision
from app.fulfillment.services import ShipmentCommandService
from app.identity.enums import MembershipRole
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.sales.models import SalesOrder, SalesOrderItem
from app.work.models import Activity
from sqlalchemy import event, func, select
from test_document_review import reviewer
from test_quotation_vertical_slice import post_ok, shipment_decision
from test_shipment_documents_vertical_slice import (
    create_shipment,
    executing_order,
    upload_required_document,
)
from test_shipment_lock_order import ACTIONS

pytest_plugins = ("test_shipment_documents_vertical_slice",)
pytestmark = pytest.mark.integration


def setup(f, storage, action):
    order = executing_order(f)
    shipment = create_shipment(
        f,
        [
            {"sales_order_item_id": item["id"], "quantity": item["quantity"]}
            for item in order["items"]
        ],
    )
    record_id = UUID(shipment["id"])
    for kind in ("COMMERCIAL_INVOICE", "PACKING_LIST"):
        upload_required_document(f, storage, shipment_id=str(record_id), document_type=kind)
    for previous, _ in ACTIONS:
        if previous == action:
            break
        shipment = post_ok(
            f,
            f"/api/v1/shipments/{record_id}/{previous}",
            "quotation-operations",
            {"booking_reference": "ORIGINAL-BOOKING"} if previous == "book" else None,
        )
    body = shipment_decision(f, record_id)
    if action == "book":
        body["booking_reference"] = "ORIGINAL-BOOKING"
    return record_id, body, order, shipment


def counts(f):
    with f.session_factory() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (Activity, AuditLog, OutboxEvent, IdempotencyKey)
        )


def invoke(f, action, record_id, body, key="decision", subject="quotation-operations"):
    headers = f.headers(subject, f.organization_a)
    if key is not None:
        headers["Idempotency-Key"] = key
    return f.client.post(f"/api/v1/shipments/{record_id}/{action}", json=body, headers=headers)


def call(f, context, action, record_id, body, key="decision"):
    request_type = ShipmentBook if action == "book" else ShipmentDecision
    return getattr(ShipmentCommandService(f.session_factory), action.replace("-", "_"))(
        context,
        record_id,
        request_type.model_validate(body),
        idempotency_key=key,
    )


@pytest.mark.parametrize("action,target", ACTIONS)
def test_required_stale_exact_conflicting_and_noop_guards(
    quotation_fixture, fake_storage, action, target
):
    f = quotation_fixture
    record_id, body, _, _ = setup(f, fake_storage, action)
    before = counts(f)
    for invalid in (None, {}, {**body, "expected_version": 0}, {**body, "status": target}):
        assert invoke(f, action, record_id, invalid).status_code == 422
    for key in (None, "", "  ", "x" * 256):
        assert invoke(f, action, record_id, body, key).status_code == 422
    assert counts(f) == before
    first = invoke(f, action, record_id, body)
    assert first.status_code == 200, first.text
    assert first.json()["status"] == target
    assert first.json()["version"] == body["expected_version"] + 1
    after = counts(f)
    effects = 2 if action in {"ready", "depart"} else 1
    assert after == (*[value + effects for value in before[:-1]], before[-1] + 1)
    assert invoke(f, action, record_id, body).json() == first.json()
    changed = invoke(f, action, record_id, {**body, "expected_version": first.json()["version"]})
    assert changed.status_code == 409 and changed.json()["code"] == "IDEMPOTENCY_CONFLICT"
    stale = invoke(f, action, record_id, body, "new-stale")
    assert stale.status_code == 409 and stale.json()["code"] == "VERSION_CONFLICT"
    assert counts(f) == after
    current = {**body, **shipment_decision(f, record_id)}
    assert invoke(f, action, record_id, current, "noop").json() == first.json()
    assert counts(f) == (*after[:-1], after[-1] + 1)
    if action == "book":
        before = counts(f)
        conflict = invoke(
            f, action, record_id, {**current, "booking_reference": "CHANGED"}, "changed"
        )
        assert (
            conflict.status_code == 409 and conflict.json()["code"] == "BOOKING_REFERENCE_CONFLICT"
        )
        assert counts(f) == before


@pytest.mark.parametrize("action,target", ACTIONS)
def test_each_role_is_checked_before_http_and_service_replay(
    quotation_fixture, fake_storage, action, target
):
    f = quotation_fixture
    record_id, body, _, _ = setup(f, fake_storage, action)
    assert invoke(f, action, record_id, body).status_code == 200
    for role in MembershipRole:
        subject, context = reviewer(f, role)
        before = counts(f)
        response = invoke(f, action, record_id, body, subject=subject)
        if Permission.SHIPMENT_TRANSITION in context.permissions:
            assert response.status_code == 200
            assert call(f, context, action, record_id, body)[0].status == target
        else:
            assert response.status_code == 403
            with pytest.raises(ApiProblem) as denied:
                call(f, context, action, record_id, body)
            assert denied.value.status == 403
        assert counts(f) == before


@pytest.mark.parametrize("action,target", ACTIONS)
def test_later_replay_reports_current_documents_tenants_and_deletion(
    quotation_fixture, fake_storage, action, target
):
    f = quotation_fixture
    record_id, body, order, _ = setup(f, fake_storage, action)
    first = invoke(f, action, record_id, body).json()
    # Reach later milestones using real commands, preserving all independent times.
    for following, _ in ACTIONS[list(dict(ACTIONS)).index(action) + 1 :]:
        post_ok(f, f"/api/v1/shipments/{record_id}/{following}", "quotation-operations")
    _, context = reviewer(f)
    with f.session_factory.begin() as session:
        session.get(SalesOrder, UUID(order["id"])).status = "COMPLETED"
        for version in session.scalars(
            select(DocumentVersion).where(DocumentVersion.organization_id == f.organization_a)
        ):
            version.status = "REJECTED"
    before = counts(f)
    replay = invoke(f, action, record_id, body)
    assert replay.status_code == 200
    assert replay.json()["status"] == "DELIVERED"
    assert replay.json()["missing_required_documents"] == ["COMMERCIAL_INVOICE", "PACKING_LIST"]
    for field, value in first.items():
        if field.endswith("_at") and value is not None:
            assert replay.json()[field] == value
    with pytest.raises(ApiProblem) as foreign:
        call(f, replace(context, organization_id=f.organization_b), action, record_id, body)
    assert foreign.value.status == 404
    with f.session_factory.begin() as session:
        session.get(Shipment, record_id).deleted_at = datetime.now(UTC)
    assert invoke(f, action, record_id, body).status_code == 404
    assert counts(f) == before


@pytest.mark.parametrize("action,target", ACTIONS)
def test_fresh_decisions_reject_finalized_pending_deleted_and_overcapacity_sources(
    quotation_fixture, fake_storage, action, target
):
    f = quotation_fixture
    record_id, body, order, _ = setup(f, fake_storage, action)
    order_id = UUID(order["id"])
    before = counts(f)
    for status, code in (
        ("COMPLETED", "ORDER_FINALIZED"),
        ("CANCELLED", "ORDER_FINALIZED"),
        ("DEPOSIT_PENDING", "ORDER_NOT_EXECUTING"),
    ):
        with f.session_factory.begin() as session:
            session.get(SalesOrder, order_id).status = status
        response = invoke(f, action, record_id, body)
        assert response.status_code == 409 and response.json()["code"] == code
        assert counts(f) == before
    with f.session_factory.begin() as session:
        parent = session.get(SalesOrder, order_id)
        parent.status = "EXECUTING"
        parent.deleted_at = datetime.now(UTC)
    assert invoke(f, action, record_id, body).status_code == 404
    with f.session_factory.begin() as session:
        session.get(SalesOrder, order_id).deleted_at = None
        source = session.get(SalesOrderItem, UUID(order["items"][0]["id"]))
        source.quantity /= 2
    response = invoke(f, action, record_id, body)
    assert response.status_code == 409 and response.json()["code"] == "SHIPMENT_QUANTITY_EXCEEDED"
    assert counts(f) == before


@pytest.mark.parametrize("action,target", ACTIONS)
@pytest.mark.parametrize("table", ("activities", "audit_logs", "outbox_events"))
def test_evidence_failure_rolls_back_state_times_and_key(
    quotation_fixture, fake_storage, action, target, table
):
    f = quotation_fixture
    record_id, body, _, shipment = setup(f, fake_storage, action)
    _, context = reviewer(f)
    before = counts(f)

    def fail(_connection, _cursor, statement, *_args):
        if statement.lower().startswith(f"insert into {table} "):
            raise RuntimeError("injected shipment decision failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected shipment decision failure"):
            call(f, context, action, record_id, body)
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert counts(f) == before
    current = f.client.get(
        f"/api/v1/shipments/{record_id}",
        headers=f.headers("quotation-operations", f.organization_a),
    ).json()
    assert current["version"] == shipment["version"]
    assert current["status"] == shipment["status"]
    for field, value in shipment.items():
        if field.endswith("_at"):
            assert current[field] == value
    assert invoke(f, action, record_id, body).status_code == 200


@pytest.mark.parametrize("action,target", ACTIONS)
@pytest.mark.parametrize("mode", ("same", "different", "changed"))
def test_concurrent_keys_and_versions_preserve_one_effect(
    quotation_fixture, fake_storage, action, target, mode
):
    f = quotation_fixture
    record_id, body, _, _ = setup(f, fake_storage, action)
    _, context = reviewer(f)
    before = counts(f)
    barrier = Barrier(2)

    def run(index):
        request = (
            {**body, "expected_version": body["expected_version"] + 1}
            if mode == "changed" and index
            else body
        )
        barrier.wait(timeout=10)
        try:
            return str(
                call(
                    f,
                    context,
                    action,
                    record_id,
                    request,
                    f"race-{index}" if mode == "different" else "race",
                )[0].id
            )
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, (0, 1)))
    effects = 2 if action in {"ready", "depart"} else 1
    assert counts(f) == (*[value + effects for value in before[:-1]], before[-1] + 1)
    if mode == "same":
        assert results == [str(record_id), str(record_id)]
    else:
        assert results.count(str(record_id)) == 1
        assert any(value in {"VERSION_CONFLICT", "IDEMPOTENCY_CONFLICT"} for value in results)
