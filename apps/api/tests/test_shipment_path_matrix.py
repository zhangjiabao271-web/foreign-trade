from dataclasses import replace
from uuid import UUID

import pytest
from app.auth.errors import ApiProblem
from app.fulfillment.enums import ShipmentStatus
from app.fulfillment.models import Shipment
from app.fulfillment.order_queries import milestone_quantities
from app.fulfillment.repositories import ShipmentRepository
from app.fulfillment.services import (
    ShipmentCommandService,
    ShipmentQueryService,
    missing_documents_for_shipments,
)
from app.identity.enums import MembershipRole
from sqlalchemy import event
from test_document_review import reviewer
from test_quotation_vertical_slice import shipment_decision
from test_sales_foreign_commands import foreign_manager
from test_shipment_creation_idempotency import setup as creation_setup
from test_shipment_decision_commands import call, counts, invoke, setup
from test_shipment_parent_atomicity import snapshot

pytestmark = pytest.mark.integration
pytest_plugins = ("test_shipment_documents_vertical_slice",)

TRANSITIONS = (
    ("book", "PLANNING", "BOOKED", "booked_at"),
    ("ready", "BOOKED", "READY", "ready_at"),
    ("enter-customs", "READY", "CUSTOMS", "customs_at"),
    ("depart", "CUSTOMS", "DEPARTED", "departed_at"),
    ("start-transit", "DEPARTED", "IN_TRANSIT", "in_transit_at"),
    ("arrive", "IN_TRANSIT", "ARRIVED", "arrived_at"),
    ("deliver", "ARRIVED", "DELIVERED", "delivered_at"),
)


@pytest.mark.parametrize("action,source,target,timestamp", TRANSITIONS)
@pytest.mark.parametrize("state", list(ShipmentStatus))
def test_all_shipment_states_reject_invalid_commands_without_partial_writes(
    quotation_fixture, fake_storage, action, source, target, timestamp, state
):
    f = quotation_fixture
    record_id, body, _, _ = setup(f, fake_storage, action)
    if state == target:
        assert invoke(f, action, record_id, body, key="prepare-noop").status_code == 200
    else:
        # State guard isolation only; legal journey tests prove natural reachability.
        with f.session_factory.begin() as session:
            session.get(Shipment, record_id).status = state
    body = {**body, **shipment_decision(f, record_id)}
    before, before_counts = snapshot(f), counts(f)
    response = invoke(f, action, record_id, body, key="matrix")
    if state not in {source, target}:
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "INVALID_STATE_TRANSITION"
        assert snapshot(f) == before
        return
    assert response.status_code == 200, response.text
    assert response.json()["status"] == target
    assert response.json()[timestamp] is not None
    no_op = state == target
    if no_op:
        effects = 0
    elif action in {"ready", "depart"}:
        effects = 2
    else:
        effects = 1
    assert counts(f) == (*(value + effects for value in before_counts[:-1]), before_counts[-1] + 1)
    after = snapshot(f)
    if no_op:
        for table in before:
            if table != "idempotency_keys":
                assert after[table] == before[table]
    assert after["shipment_items"] == before["shipment_items"]
    assert after["sales_order_items"] == before["sales_order_items"]
    assert invoke(f, action, record_id, body, key="matrix").json() == response.json()
    assert snapshot(f) == after


@pytest.mark.parametrize("action,source,target,timestamp", TRANSITIONS)
def test_foreign_manager_cannot_run_any_shipment_milestone(
    quotation_fixture, fake_storage, action, source, target, timestamp
):
    f = quotation_fixture
    record_id, body, _, _ = setup(f, fake_storage, action)
    foreign = foreign_manager(f)
    before = snapshot(f)
    response = f.client.post(
        f"/api/v1/shipments/{record_id}/{action}",
        headers=f.headers("quotation-other", f.organization_b) | {"Idempotency-Key": "foreign"},
        json=body,
    )
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "SHIPMENT_NOT_FOUND"
    with pytest.raises(ApiProblem) as denied:
        call(f, foreign, action, record_id, body, key="foreign-service")
    assert (denied.value.status, denied.value.code) == (404, "SHIPMENT_NOT_FOUND")
    assert snapshot(f) == before


@pytest.mark.parametrize("role", list(MembershipRole))
def test_shipment_creation_role_boundary_and_service_replay(quotation_fixture, role):
    f = quotation_fixture
    _, body = creation_setup(f)
    subject, context = reviewer(f, role)
    before = snapshot(f)
    service = ShipmentCommandService(f.session_factory)
    response = f.client.post(
        "/api/v1/shipments",
        json=body,
        headers=f.headers(subject, f.organization_a) | {"Idempotency-Key": "role"},
    )
    if role not in {MembershipRole.ADMIN, MembershipRole.MANAGER, MembershipRole.OPERATIONS}:
        assert response.status_code == 403
        with pytest.raises(ApiProblem) as denied:
            service.create(context, body, idempotency_key="role")
        assert denied.value.status == 403
        assert snapshot(f) == before
        return
    assert response.status_code == 201, response.text
    after = snapshot(f)
    assert len(after["shipments"]) == len(before["shipments"]) + 1
    for table in ("activities", "audit_logs", "outbox_events", "idempotency_keys"):
        assert len(after[table]) == len(before[table]) + 1
    assert str(service.create(context, body, idempotency_key="role")[0].id) == response.json()["id"]
    assert snapshot(f) == after


def test_shipment_repository_query_and_creation_foreign_paths(quotation_fixture, fake_storage):
    f = quotation_fixture
    record_id, _, order, shipment = setup(f, fake_storage, "deliver")
    foreign = foreign_manager(f)
    item_ids = {UUID(item["id"]) for item in shipment["items"]}
    source_ids = [UUID(item["id"]) for item in order["items"]]
    before = snapshot(f)
    with f.session_factory() as session:
        repository = ShipmentRepository(session)
        assert repository.get(organization_id=f.organization_b, record_id=record_id) is None
        assert (
            repository.get_for_update(organization_id=f.organization_b, shipment_id=record_id)
            is None
        )
        assert repository.list(organization_id=f.organization_b) == []
        assert repository.count(organization_id=f.organization_b) == 0
        assert repository.list_recent(organization_id=f.organization_b, limit=10) == []
        assert repository.items(organization_id=f.organization_b, shipment_id=record_id) == []
        assert repository.items_for_shipments(
            organization_id=f.organization_b, shipment_ids=[record_id]
        ) == {record_id: []}
        assert (
            repository.locked_items(
                organization_id=f.organization_b, shipment_id=record_id, item_ids=item_ids
            )
            == []
        )
        for departed in (False, True):
            assert (
                milestone_quantities(
                    session,
                    organization_id=f.organization_b,
                    sales_order_item_ids=source_ids,
                    departed=departed,
                )
                == {}
            )
            assert milestone_quantities(
                session,
                organization_id=f.organization_a,
                sales_order_item_ids=source_ids,
                departed=departed,
            )
        assert missing_documents_for_shipments(
            session, organization_id=f.organization_b, shipment_ids=[record_id]
        ) == {record_id: ["COMMERCIAL_INVOICE", "PACKING_LIST"]}
        assert missing_documents_for_shipments(
            session, organization_id=f.organization_a, shipment_ids=[record_id]
        ) == {record_id: []}
        queries = ShipmentQueryService(repository)
        assert queries.list(foreign, limit=10) == []
        for query in (
            lambda context: queries.get(context, record_id),
            lambda context: queries.list(context, limit=10, cursor=record_id),
            lambda context: queries.source_lines(context, record_id),
        ):
            with pytest.raises(ApiProblem) as denied:
                query(foreign)
            assert denied.value.status == 404

        def prohibit_sql(*_args):
            pytest.fail("Unauthorized shipment query reached SQL")

        event.listen(f.engine, "before_cursor_execute", prohibit_sql)
        try:
            unauthorized = replace(foreign, permissions=frozenset())
            for query in (
                lambda: queries.get(unauthorized, record_id),
                lambda: queries.list(unauthorized, limit=10),
                lambda: queries.source_lines(unauthorized, record_id),
            ):
                with pytest.raises(ApiProblem) as denied:
                    query()
                assert denied.value.status == 403
        finally:
            event.remove(f.engine, "before_cursor_execute", prohibit_sql)
    headers = f.headers("quotation-other", f.organization_b)
    for suffix in ("", "/activities", "/source-lines"):
        assert (
            f.client.get(f"/api/v1/shipments/{record_id}{suffix}", headers=headers).status_code
            == 404
        )
    assert f.client.get("/api/v1/shipments", headers=headers).json()["items"] == []
    assert (
        f.client.get(
            "/api/v1/shipments", headers=headers, params={"cursor": str(record_id)}
        ).status_code
        == 404
    )
    body = {"items": [{"sales_order_item_id": str(source_ids[0]), "quantity": "0.1"}]}
    response = f.client.post(
        "/api/v1/shipments", json=body, headers=headers | {"Idempotency-Key": "foreign-create"}
    )
    assert response.status_code == 404
    with pytest.raises(ApiProblem) as denied:
        ShipmentCommandService(f.session_factory).create(foreign, body, idempotency_key="foreign")
    assert denied.value.status == 404
    assert snapshot(f) == before
