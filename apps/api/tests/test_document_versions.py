from hashlib import sha256
from uuid import UUID, uuid4

import httpx
import pytest
from app.core.config import Settings
from app.documents.models import DocumentVersion
from app.documents.routers import get_object_storage
from app.documents.services import mark_document_available
from app.documents.storage import MinioObjectStorage
from app.fulfillment.models import Shipment
from app.identity.models import OrganizationMembership
from app.main import app
from app.platform.models import OutboxEvent
from app.platform.outbox import IdempotentEventConsumer, outbox_message
from sqlalchemy import select
from test_quotation_vertical_slice import QuotationFixture
from test_shipment_documents_vertical_slice import create_shipment, executing_order

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def test_real_storage_replacement_preserves_pinned_evidence(quotation_fixture: QuotationFixture):
    fixture = quotation_fixture
    storage = MinioObjectStorage(Settings(minio_bucket=f"test-versions-{uuid4().hex}"))
    app.dependency_overrides[get_object_storage] = lambda: storage
    headers = fixture.headers("quotation-operations", fixture.organization_a)
    order = executing_order(fixture)
    item = order["items"][0]
    shipment = create_shipment(
        fixture, [{"sales_order_item_id": item["id"], "quantity": item["quantity"]}]
    )
    original = b"Original evidence"
    with fixture.session_factory() as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == fixture.organization_b
            )
        )
        membership.role = "OPERATIONS"
        session.commit()

    def metadata(content):
        return {
            "file_name": "invoice.txt",
            "mime_type": "text/plain",
            "size_bytes": len(content),
            "sha256": sha256(content).hexdigest(),
        }

    def complete_and_scan(upload):
        document_id = upload["document"]["id"]
        response = fixture.client.post(
            f"/api/v1/documents/{document_id}/versions/{upload['version_id']}/complete",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        with fixture.session_factory() as session:
            event = session.scalar(
                select(OutboxEvent).where(
                    OutboxEvent.organization_id == fixture.organization_a,
                    OutboxEvent.event_type == "document.uploaded.v1",
                    OutboxEvent.payload["version_id"].astext == upload["version_id"],
                )
            )
            assert event is not None
            message = outbox_message(event)
        IdempotentEventConsumer(fixture.session_factory).consume(
            consumer_name="test.pinned-evidence", message=message, handler=mark_document_available
        )
        review_path = f"/api/v1/documents/{document_id}/versions/{upload['version_id']}/review"
        reviewer_headers = fixture.headers("quotation-manager", fixture.organization_a)
        preview = fixture.client.get(review_path, headers=reviewer_headers)
        assert preview.status_code == 200, preview.text
        if not preview.json()["released"]:
            approved = fixture.client.post(
                review_path,
                headers={
                    **reviewer_headers,
                    "Idempotency-Key": f"storage-review-{upload['version_id']}",
                },
                json={
                    "expected_version": preview.json()["version"],
                    "content_digest": preview.json()["content_digest"],
                    "release": True,
                    "confirmed": True,
                    "reason": "Synthetic storage evidence reviewed without internal costs",
                },
            )
            assert approved.status_code == 200, approved.text

    try:
        created = fixture.client.post(
            "/api/v1/documents/upload-sessions",
            headers=headers,
            json={
                **metadata(original),
                "title": "Invoice",
                "document_type": "COMMERCIAL_INVOICE",
                "target_type": "SHIPMENT",
                "target_id": shipment["id"],
            },
        )
        assert created.status_code == 201, created.text
        upload = created.json()
        document_id = upload["document"]["id"]
        with httpx.Client(trust_env=False) as client:
            assert client.put(
                upload["upload_url"], content=original, headers={"Content-Type": "text/plain"}
            ).is_success
            complete_and_scan(upload)
            assert client.put(
                upload["upload_url"],
                content=b"Tampered content",
                headers={"Content-Type": "text/plain"},
            ).is_success
            download = fixture.client.post(
                f"/api/v1/documents/{document_id}/download-session", headers=headers
            )
            assert download.status_code == 200, download.text
            assert client.get(download.json()["download_url"]).content == original
            # Retrying completion must inspect the pinned version, not the tampered latest object.
            complete_and_scan(upload)
            document = fixture.client.get(
                f"/api/v1/documents/{document_id}", headers=headers
            ).json()
            replacement_body = {**metadata(b"Replacement"), "expected_version": document["version"]}
            endpoint = f"/api/v1/documents/{document_id}/version-upload-sessions"
            for subject, organization, expected in (
                ("quotation-other", fixture.organization_b, 404),
                ("quotation-sales", fixture.organization_a, 403),
            ):
                denied = fixture.client.post(
                    endpoint, headers=fixture.headers(subject, organization), json=replacement_body
                )
                assert denied.status_code == expected
            replacement = fixture.client.post(endpoint, headers=headers, json=replacement_body)
            assert replacement.status_code == 201, replacement.text
            assert (
                fixture.client.post(endpoint, headers=headers, json=replacement_body).status_code
                == 409
            )
            pending = fixture.client.get(
                f"/api/v1/shipments/{shipment['id']}", headers=headers
            ).json()
            assert "COMMERCIAL_INVOICE" in pending["missing_required_documents"]
            replacement_upload = replacement.json()
            assert replacement_upload["version_id"] != upload["version_id"]
            pending_download = fixture.client.post(
                f"/api/v1/documents/{document_id}/versions/{replacement_upload['version_id']}/download-session",
                headers=headers,
            )
            assert pending_download.status_code == 409
            assert client.put(
                replacement_upload["upload_url"],
                content=b"Replacement",
                headers={"Content-Type": "text/plain"},
            ).is_success
            complete_and_scan(replacement_upload)
            ready = fixture.client.get(
                f"/api/v1/shipments/{shipment['id']}", headers=headers
            ).json()
            assert "COMMERCIAL_INVOICE" not in ready["missing_required_documents"]
            with fixture.session_factory() as session:
                versions = list(
                    session.scalars(
                        select(DocumentVersion)
                        .where(
                            DocumentVersion.organization_id == fixture.organization_a,
                            DocumentVersion.document_id == UUID(document_id),
                        )
                        .order_by(DocumentVersion.version_number)
                    )
                )
                assert len(versions) == 2
                assert versions[0].object_key != versions[1].object_key
                assert versions[0].actual_sha256 == sha256(original).hexdigest()
                assert all(version.storage_version_id for version in versions)
            # The original authorized download remains tied to original evidence after replacement.
            assert client.get(download.json()["download_url"]).content == original
            historical_endpoint = (
                f"/api/v1/documents/{document_id}/versions/{upload['version_id']}/download-session"
            )
            historical = fixture.client.post(historical_endpoint, headers=headers)
            assert historical.status_code == 200
            assert client.get(historical.json()["download_url"]).content == original
            latest = fixture.client.post(
                f"/api/v1/documents/{document_id}/download-session",
                headers=headers,
            )
            assert client.get(latest.json()["download_url"]).content == b"Replacement"
            assert (
                fixture.client.post(
                    historical_endpoint,
                    headers=fixture.headers("quotation-other", fixture.organization_b),
                ).status_code
                == 404
            )
            assert (
                fixture.client.post(
                    f"/api/v1/documents/{document_id}/versions/{uuid4()}/download-session",
                    headers=headers,
                ).status_code
                == 404
            )
            current = fixture.client.get(f"/api/v1/documents/{document_id}", headers=headers).json()
            pending_upload = fixture.client.post(
                endpoint,
                headers=headers,
                json={
                    **metadata(b"Pending evidence"),
                    "expected_version": current["version"],
                },
            ).json()
            assert client.put(
                pending_upload["upload_url"],
                content=b"Pending evidence",
                headers={"Content-Type": "text/plain"},
            ).is_success
            # Simulate finalization between upload initiation and completion.
            with fixture.session_factory() as session:
                target = session.scalar(
                    select(Shipment).where(
                        Shipment.organization_id == fixture.organization_a,
                        Shipment.id == UUID(shipment["id"]),
                    )
                )
                target.status = "DELIVERED"
                session.commit()
            blocked = fixture.client.post(
                f"/api/v1/documents/{document_id}/versions/{pending_upload['version_id']}/complete",
                headers=headers,
            )
            assert blocked.status_code == 409
            assert blocked.json()["code"] == "DOCUMENT_TARGET_FINALIZED"
            historical = fixture.client.post(historical_endpoint, headers=headers)
            assert historical.status_code == 200
            assert client.get(historical.json()["download_url"]).content == original
            blocked = fixture.client.post(
                endpoint,
                headers=headers,
                json={
                    **metadata(b"Blocked"),
                    "expected_version": pending_upload["document"]["version"],
                },
            )
            assert blocked.status_code == 409
            assert blocked.json()["code"] == "DOCUMENT_TARGET_FINALIZED"
    finally:
        app.dependency_overrides.pop(get_object_storage, None)
        # Delete only this test's randomly named bucket and its exact enumerated versions.
        if storage._client.bucket_exists(storage._bucket):
            for obj in storage._client.list_objects(
                storage._bucket, recursive=True, include_version=True
            ):
                storage._client.remove_object(
                    storage._bucket, obj.object_name, version_id=obj.version_id
                )
            storage._client.remove_bucket(storage._bucket)
