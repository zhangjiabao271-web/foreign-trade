from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlparse
from uuid import UUID, uuid4

import pytest
from app.documents.models import Document
from app.documents.routers import get_object_storage
from app.documents.services import mark_document_available
from app.documents.storage import StoredObject
from app.main import app
from app.platform.models import OutboxEvent
from app.platform.outbox import IdempotentEventConsumer, outbox_message
from app.sales.models import SalesOrder
from sqlalchemy import func, select
from test_order_procurement_vertical_slice import create_accepted_quotation
from test_quotation_vertical_slice import QuotationFixture, post_ok, shipment_decision

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


class FakeObjectStorage:
    def __init__(self) -> None:
        self.objects: dict[str, StoredObject] = {}
        self.fail_presign = False

    def ensure_bucket(self) -> None:
        return None

    def presign_upload(self, object_key: str, *, expires: timedelta) -> str:
        _ = expires
        if self.fail_presign:
            raise RuntimeError("signing unavailable")
        return f"https://storage.example.test/upload/{object_key}"

    def presign_download(
        self, object_key: str, *, expires: timedelta, version_id: str, file_name: str
    ) -> str:
        _ = expires
        return f"https://storage.example.test/download/{object_key}"

    def inspect(self, object_key: str, *, version_id: str | None = None) -> StoredObject:
        return self.objects[object_key]


@pytest.fixture
def fake_storage() -> Iterator[FakeObjectStorage]:
    storage = FakeObjectStorage()
    app.dependency_overrides[get_object_storage] = lambda: storage
    try:
        yield storage
    finally:
        app.dependency_overrides.pop(get_object_storage, None)


def executing_order(fixture: QuotationFixture) -> dict[str, object]:
    quotation, _, _ = create_accepted_quotation(fixture)
    order = post_ok(
        fixture,
        "/api/v1/sales-orders",
        "quotation-sales",
        {"quotation_id": quotation["id"], "deposit_rate": "0.0000"},
        201,
    )
    return post_ok(
        fixture,
        f"/api/v1/sales-orders/{order['id']}/confirm",
        "quotation-manager",
    )


def upload_required_document(
    fixture: QuotationFixture,
    storage: FakeObjectStorage,
    *,
    shipment_id: str,
    document_type: str,
    target_type: str = "SHIPMENT",
) -> dict[str, object]:
    content = f"{document_type} evidence".encode()
    import hashlib

    digest = hashlib.sha256(content).hexdigest()
    session = post_ok(
        fixture,
        "/api/v1/documents/upload-sessions",
        "quotation-operations",
        {
            "title": document_type.replace("_", " ").title(),
            "document_type": document_type,
            "file_name": f"{document_type.lower()}.txt",
            "mime_type": "text/plain",
            "size_bytes": len(content),
            "sha256": digest,
            "target_type": target_type,
            "target_id": shipment_id,
        },
        201,
    )
    key = urlparse(str(session["upload_url"])).path.removeprefix("/upload/")
    storage.objects[key] = StoredObject(
        size=len(content), content_type="text/plain", sha256=digest, version_id="test-version-1"
    )
    document = session["document"]
    assert isinstance(document, dict)
    completed = post_ok(
        fixture,
        f"/api/v1/documents/{document['id']}/versions/{session['version_id']}/complete",
        "quotation-operations",
    )
    with fixture.session_factory() as database:
        event = database.scalar(
            select(OutboxEvent)
            .where(
                OutboxEvent.organization_id == fixture.organization_a,
                OutboxEvent.event_type == "document.uploaded.v1",
                OutboxEvent.aggregate_id == UUID(str(document["id"])),
            )
            .order_by(OutboxEvent.created_at.desc())
        )
        assert event is not None
        message = outbox_message(event)
    assert IdempotentEventConsumer(fixture.session_factory).consume(
        consumer_name="test.document-scan",
        message=message,
        handler=mark_document_available,
    )
    assert not IdempotentEventConsumer(fixture.session_factory).consume(
        consumer_name="test.document-scan",
        message=message,
        handler=mark_document_available,
    )
    return completed


def create_shipment(fixture: QuotationFixture, items: list[dict[str, object]]) -> dict[str, object]:
    return post_ok(
        fixture,
        "/api/v1/shipments",
        "quotation-operations",
        {"items": items},
        201,
    )


def prepare_and_depart(
    fixture: QuotationFixture,
    storage: FakeObjectStorage,
    shipment: dict[str, object],
) -> dict[str, object]:
    shipment_id = str(shipment["id"])
    post_ok(
        fixture,
        f"/api/v1/shipments/{shipment_id}/book",
        "quotation-operations",
        {"booking_reference": f"BOOK-{shipment_id[-6:]}"},
    )
    blocked = fixture.client.post(
        f"/api/v1/shipments/{shipment_id}/ready",
        headers=fixture.headers("quotation-operations", fixture.organization_a)
        | {"Idempotency-Key": str(uuid4())},
        json=shipment_decision(fixture, shipment_id),
    )
    assert blocked.status_code == 409
    assert blocked.json()["code"] == "SHIPMENT_DOCUMENTS_INCOMPLETE"
    for document_type in ("COMMERCIAL_INVOICE", "PACKING_LIST"):
        upload_required_document(
            fixture,
            storage,
            shipment_id=shipment_id,
            document_type=document_type,
        )
    ready = post_ok(
        fixture,
        f"/api/v1/shipments/{shipment_id}/ready",
        "quotation-operations",
    )
    assert ready["missing_required_documents"] == []
    post_ok(
        fixture,
        f"/api/v1/shipments/{shipment_id}/enter-customs",
        "quotation-operations",
    )
    return post_ok(
        fixture,
        f"/api/v1/shipments/{shipment_id}/depart",
        "quotation-operations",
    )


def test_partial_and_combined_shipments_require_available_documents(
    quotation_fixture: QuotationFixture, fake_storage: FakeObjectStorage
) -> None:
    order = executing_order(quotation_fixture)
    order_items = order["items"]
    assert isinstance(order_items, list)
    first, second = order_items
    assert isinstance(first, dict) and isinstance(second, dict)
    first_quantity = Decimal(str(first["quantity"]))
    first_part = (first_quantity / 2).quantize(Decimal("0.0001"))
    shipment_one_items = [
        {"sales_order_item_id": first["id"], "quantity": str(first_part)},
        {"sales_order_item_id": second["id"], "quantity": second["quantity"]},
    ]
    denied = quotation_fixture.client.post(
        "/api/v1/shipments",
        headers=quotation_fixture.headers("quotation-sales", quotation_fixture.organization_a),
        json={"items": shipment_one_items},
    )
    assert denied.status_code == 403
    shipment_one = create_shipment(quotation_fixture, shipment_one_items)
    remaining = first_quantity - first_part
    shipment_two = create_shipment(
        quotation_fixture,
        [{"sales_order_item_id": first["id"], "quantity": str(remaining)}],
    )
    overage = quotation_fixture.client.post(
        "/api/v1/shipments",
        headers=quotation_fixture.headers("quotation-operations", quotation_fixture.organization_a),
        json={"items": [{"sales_order_item_id": first["id"], "quantity": "0.0001"}]},
    )
    assert overage.status_code == 409
    assert overage.json()["code"] == "SHIPMENT_QUANTITY_EXCEEDED"

    departed_one = prepare_and_depart(quotation_fixture, fake_storage, shipment_one)
    assert departed_one["status"] == "DEPARTED"
    with quotation_fixture.session_factory() as session:
        assert session.get(SalesOrder, UUID(str(order["id"]))).status == "EXECUTING"

    departed_two = prepare_and_depart(quotation_fixture, fake_storage, shipment_two)
    assert departed_two["status"] == "DEPARTED"
    with quotation_fixture.session_factory() as session:
        assert session.get(SalesOrder, UUID(str(order["id"]))).status == "SHIPPED"

    shipment_id = str(shipment_two["id"])
    for command in ("start-transit", "arrive", "deliver"):
        final = post_ok(
            quotation_fixture,
            f"/api/v1/shipments/{shipment_id}/{command}",
            "quotation-operations",
        )
    assert final["status"] == "DELIVERED"

    other_headers = quotation_fixture.headers("quotation-other", quotation_fixture.organization_b)
    assert (
        quotation_fixture.client.get(
            f"/api/v1/shipments/{shipment_one['id']}", headers=other_headers
        ).status_code
        == 404
    )
    documents = quotation_fixture.client.get(
        "/api/v1/documents",
        params={"target_type": "SHIPMENT", "target_id": shipment_one["id"]},
        headers=other_headers,
    )
    assert documents.status_code == 404
    assert documents.json()["code"] == "DOCUMENT_TARGET_NOT_FOUND"


def test_upload_session_rolls_back_if_signing_fails(
    quotation_fixture: QuotationFixture, fake_storage: FakeObjectStorage
) -> None:
    order = executing_order(quotation_fixture)
    order_items = order["items"]
    assert isinstance(order_items, list)
    item = order_items[0]
    assert isinstance(item, dict)
    shipment = create_shipment(
        quotation_fixture,
        [{"sales_order_item_id": item["id"], "quantity": item["quantity"]}],
    )
    fake_storage.fail_presign = True

    with pytest.raises(RuntimeError, match="signing unavailable"):
        quotation_fixture.client.post(
            "/api/v1/documents/upload-sessions",
            headers=quotation_fixture.headers(
                "quotation-operations", quotation_fixture.organization_a
            ),
            json={
                "title": "Commercial invoice",
                "document_type": "COMMERCIAL_INVOICE",
                "file_name": "invoice.txt",
                "mime_type": "text/plain",
                "size_bytes": 8,
                "sha256": "0" * 64,
                "target_type": "SHIPMENT",
                "target_id": shipment["id"],
            },
        )

    with quotation_fixture.session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(Document)
                .where(Document.organization_id == quotation_fixture.organization_a)
            )
            == 0
        )
