from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.documents.models import Document, DocumentLink, DocumentVersion
from app.fulfillment.models import Shipment, ShipmentItem
from app.fulfillment.repositories import ShipmentRepository
from app.fulfillment.routers import shipment_response
from app.fulfillment.services import ShipmentQueryService, missing_documents_for_shipments
from sqlalchemy import event, select
from test_quotation_vertical_slice import table_counts
from test_shipment_documents_vertical_slice import (
    create_shipment,
    executing_order,
    upload_required_document,
)

pytest_plugins = ("test_quotation_vertical_slice", "test_shipment_documents_vertical_slice")
pytestmark = pytest.mark.integration


def test_shipment_list_batches_without_changing_facts(quotation_fixture, fake_storage):
    f = quotation_fixture
    order = executing_order(f)
    shipments = [
        create_shipment(
            f,
            [{"sales_order_item_id": item["id"], "quantity": "0.1000"} for item in order["items"]],
        )
        for _ in range(6)
    ]
    for kind in ("COMMERCIAL_INVOICE", "PACKING_LIST"):
        upload_required_document(
            f, fake_storage, shipment_id=shipments[0]["id"], document_type=kind
        )
    upload_required_document(
        f, fake_storage, shipment_id=shipments[1]["id"], document_type="PACKING_LIST"
    )
    headers = f.headers("quotation-operations", f.organization_a)
    expected = {
        row["id"]: f.client.get(f"/api/v1/shipments/{row['id']}", headers=headers).json()
        for row in shipments
    }
    assert expected[shipments[0]["id"]]["missing_required_documents"] == []
    assert expected[shipments[1]["id"]]["missing_required_documents"] == ["COMMERCIAL_INVOICE"]
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset({Permission.SHIPMENT_READ}),
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
                rows = ShipmentQueryService(ShipmentRepository(session)).list(context, limit=limit)
                actual = [shipment_response(*row).model_dump(mode="json") for row in rows]
                assert len(actual) == min(limit, 6)
                assert actual == [expected[row["id"]] for row in actual]
                assert len(statements) == 3
        with f.session_factory() as session:
            statements.clear()
            assert (
                ShipmentQueryService(ShipmentRepository(session)).list(
                    replace(context, organization_id=f.organization_b), limit=100
                )
                == []
            )
            assert len(statements) == 1
    finally:
        event.remove(f.engine, "before_cursor_execute", capture)
    page = f.client.get("/api/v1/shipments", headers=headers).json()
    assert page["count"] == 6
    assert page["items"] == [expected[row["id"]] for row in page["items"]]
    assert table_counts(f) == before
    with f.session_factory() as session, pytest.raises(ApiProblem) as denied:
        ShipmentQueryService(ShipmentRepository(session)).list(
            replace(context, permissions=frozenset()), limit=100
        )
    assert denied.value.status == 403
    with f.session_factory.begin() as session:
        session.get(ShipmentItem, UUID(shipments[0]["items"][0]["id"])).deleted_at = datetime.now(
            UTC
        )
        session.get(Shipment, UUID(shipments[2]["id"])).deleted_at = datetime.now(UTC)
    page = f.client.get("/api/v1/shipments", headers=headers).json()
    assert page["count"] == 5
    assert shipments[2]["id"] not in {row["id"] for row in page["items"]}
    first = next(row for row in page["items"] if row["id"] == shipments[0]["id"])
    assert first["items"] == shipments[0]["items"][1:]


@pytest.mark.parametrize(
    "invalid",
    [
        "document_deleted",
        "link_deleted",
        "version_deleted",
        "pending",
        "unpinned",
        "empty",
        "null",
        "old",
        "other_target",
    ],
)
def test_batched_checklist_rejects_invalid_evidence(quotation_fixture, fake_storage, invalid):
    f = quotation_fixture
    order = executing_order(f)
    shipment = create_shipment(
        f, [{"sales_order_item_id": order["items"][0]["id"], "quantity": "0.1000"}]
    )
    shipment_id = UUID(shipment["id"])
    uploaded = upload_required_document(
        f, fake_storage, shipment_id=shipment["id"], document_type="PACKING_LIST"
    )
    with f.session_factory() as session:
        assert missing_documents_for_shipments(
            session, organization_id=f.organization_a, shipment_ids=[shipment_id]
        ) == {shipment_id: ["COMMERCIAL_INVOICE"]}
        assert missing_documents_for_shipments(
            session, organization_id=f.organization_b, shipment_ids=[shipment_id]
        ) == {shipment_id: ["COMMERCIAL_INVOICE", "PACKING_LIST"]}
    with f.session_factory.begin() as session:
        document = session.get(Document, UUID(uploaded["id"]))
        version = session.scalar(
            select(DocumentVersion).where(DocumentVersion.document_id == document.id)
        )
        link = session.scalar(select(DocumentLink).where(DocumentLink.document_id == document.id))
        if invalid == "document_deleted":
            document.deleted_at = datetime.now(UTC)
        elif invalid == "link_deleted":
            link.deleted_at = datetime.now(UTC)
        elif invalid == "version_deleted":
            version.deleted_at = datetime.now(UTC)
        elif invalid == "pending":
            version.status = "PENDING_UPLOAD"
        elif invalid in {"unpinned", "empty", "null"}:
            version.storage_version_id = {"unpinned": None, "empty": "", "null": "null"}[invalid]
        elif invalid == "old":
            document.latest_version_number = 2
        else:
            link.target_type = "SALES_ORDER"
    before = table_counts(f)
    with f.session_factory() as session:
        assert missing_documents_for_shipments(
            session, organization_id=f.organization_a, shipment_ids=[shipment_id]
        ) == {shipment_id: ["COMMERCIAL_INVOICE", "PACKING_LIST"]}
        assert missing_documents_for_shipments(
            session, organization_id=f.organization_b, shipment_ids=[shipment_id]
        ) == {shipment_id: ["COMMERCIAL_INVOICE", "PACKING_LIST"]}
        assert ShipmentRepository(session).items_for_shipments(
            organization_id=f.organization_b, shipment_ids=[shipment_id]
        ) == {shipment_id: []}
    assert table_counts(f) == before
