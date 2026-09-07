from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.documents.models import Document, DocumentVersion
from app.documents.services import DocumentCommandService
from app.documents.storage import StoredObject
from app.fulfillment.models import Shipment
from app.platform.models import IdempotencyKey
from sqlalchemy import event, func, select
from test_quotation_vertical_slice import table_counts
from test_shipment_documents_vertical_slice import create_shipment, executing_order

pytest_plugins = ("test_quotation_vertical_slice", "test_shipment_documents_vertical_slice")
pytestmark = pytest.mark.integration


def prepare(f):
    order = executing_order(f)
    shipment = create_shipment(
        f, [{"sales_order_item_id": order["items"][0]["id"], "quantity": "0.1"}]
    )
    body = dict(
        title="Evidence",
        document_type="PACKING_LIST",
        file_name="proof.txt",
        mime_type="text/plain",
        size_bytes=5,
        sha256=sha256(b"proof").hexdigest(),
        target_type="SHIPMENT",
        target_id=shipment["id"],
    )
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    return context, body


def stored_version(f, version_id):
    with f.session_factory() as session:
        return session.get(DocumentVersion, version_id)


def counts(f):
    with f.session_factory() as session:
        return table_counts(f), tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (Document, DocumentVersion, IdempotencyKey)
        )


def test_explicit_resume_matches_file_without_allocating(quotation_fixture, fake_storage):
    f = quotation_fixture
    context, body = prepare(f)
    service = DocumentCommandService(f.session_factory, fake_storage)
    first = service.create_upload(context, body)
    version = first[1][0]
    metadata = {field: body[field] for field in ("file_name", "mime_type", "size_bytes", "sha256")}
    path = f"/api/v1/documents/{first[0].id}/versions/{version.id}/upload-session"
    headers = f.headers("quotation-operations", f.organization_a)
    before = counts(f)
    resumed = f.client.post(path, headers=headers, json=metadata)
    assert resumed.status_code == 200
    assert resumed.json()["version_id"] == str(version.id)
    assert resumed.json()["upload_url"] == first[3]
    fake_storage.fail_presign = True
    for field, value in (
        ("file_name", "different.txt"),
        ("mime_type", "application/octet-stream"),
        ("size_bytes", 6),
        ("sha256", "0" * 64),
    ):
        mismatch = f.client.post(path, headers=headers, json={**metadata, field: value})
        assert mismatch.status_code == 409
        assert mismatch.json()["code"] == "UPLOAD_FILE_MISMATCH"
    for denied_context, document_id, status in (
        (replace(context, organization_id=f.organization_b), first[0].id, 404),
        (context, uuid4(), 404),
        (replace(context, permissions=frozenset()), first[0].id, 403),
        (replace(context, permissions=frozenset({Permission.DOCUMENT_WRITE})), first[0].id, 403),
    ):
        with pytest.raises(ApiProblem) as denied:
            service.resume_upload(denied_context, document_id, version.id, metadata)
        assert denied.value.status == status
    assert counts(f) == before
    fake_storage.objects[stored_version(f, version.id).object_key] = StoredObject(
        size=5, content_type="text/plain", sha256=body["sha256"], version_id="resume-pinned"
    )
    service.complete(context, first[0].id, version.id)
    with f.session_factory.begin() as session:
        session.get(Shipment, UUID(body["target_id"])).status = "DELIVERED"
    before = counts(f)
    accepted = f.client.post(path, headers=headers, json=metadata)
    assert accepted.status_code == 200
    assert accepted.json()["upload_url"] is None
    assert counts(f) == before


@pytest.mark.parametrize("condition", ["superseded", "rejected", "deleted", "finalized"])
def test_explicit_resume_rejects_unusable_versions(quotation_fixture, fake_storage, condition):
    f = quotation_fixture
    context, body = prepare(f)
    service = DocumentCommandService(f.session_factory, fake_storage)
    first = service.create_upload(context, body)
    version = first[1][0]
    metadata = {field: body[field] for field in ("file_name", "mime_type", "size_bytes", "sha256")}
    if condition == "superseded":
        service.create_version(
            context, first[0].id, {**metadata, "expected_version": first[0].version}
        )
    else:
        with f.session_factory.begin() as session:
            if condition == "rejected":
                session.get(DocumentVersion, version.id).status = "REJECTED"
            elif condition == "deleted":
                session.get(Document, first[0].id).deleted_at = first[0].created_at
            else:
                session.get(Shipment, UUID(body["target_id"])).status = "DELIVERED"
    before = counts(f)
    fake_storage.fail_presign = True
    with pytest.raises(ApiProblem) as rejected:
        service.resume_upload(context, first[0].id, version.id, metadata)
    assert (
        rejected.value.code
        == {
            "superseded": "UPLOAD_VERSION_SUPERSEDED",
            "rejected": "INVALID_DOCUMENT_STATE",
            "deleted": "DOCUMENT_NOT_FOUND",
            "finalized": "DOCUMENT_TARGET_FINALIZED",
        }[condition]
    )
    assert counts(f) == before


def test_upload_key_recovers_pending_completed_and_finalized(quotation_fixture, fake_storage):
    f = quotation_fixture
    context, body = prepare(f)
    service = DocumentCommandService(f.session_factory, fake_storage)
    first = service.create_upload(context, body, key="recover")
    before = counts(f)
    retry = service.create_upload(context, body, key="recover")
    assert retry[0].id == first[0].id
    assert retry[1][0].id == first[1][0].id
    assert retry[3] == first[3]
    assert counts(f) == before
    with pytest.raises(ApiProblem) as conflict:
        service.create_upload(context, {**body, "title": "Changed"}, key="recover")
    assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
    version = first[1][0]
    fake_storage.objects[stored_version(f, version.id).object_key] = StoredObject(
        size=5, content_type="text/plain", sha256=body["sha256"], version_id="immutable-1"
    )
    service.complete(context, first[0].id, version.id)
    with f.session_factory.begin() as session:
        session.get(Shipment, UUID(body["target_id"])).status = "DELIVERED"
    fake_storage.fail_presign = True
    before = counts(f)
    recovered = service.create_upload(context, body, key="recover")
    assert recovered[3] is None
    assert recovered[1][0].id == version.id
    assert stored_version(f, recovered[1][0].id).storage_version_id == "immutable-1"
    assert counts(f) == before
    with pytest.raises(ApiProblem) as denied:
        service.create_upload(replace(context, permissions=frozenset()), body, key="recover")
    assert denied.value.status == 403


def test_replacement_key_preserves_opening_version(quotation_fixture, fake_storage):
    f = quotation_fixture
    context, body = prepare(f)
    service = DocumentCommandService(f.session_factory, fake_storage)
    original = service.create_upload(context, body, key="original")
    replacement = {
        field: body[field] for field in ("file_name", "mime_type", "size_bytes", "sha256")
    }
    replacement["expected_version"] = original[0].version
    first = service.create_version(context, original[0].id, replacement, key="replace")
    before = counts(f)
    replay = service.create_version(context, original[0].id, replacement, key="replace")
    assert replay[1][0].id == first[1][0].id
    assert replay[1][0].version_number == 2
    assert counts(f) == before
    with pytest.raises(ApiProblem) as superseded:
        service.create_upload(context, body, key="original")
    assert superseded.value.code == "UPLOAD_VERSION_SUPERSEDED"


@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
def test_upload_failure_rolls_back_key_and_all_facts(quotation_fixture, fake_storage, table):
    f = quotation_fixture
    context, body = prepare(f)
    service = DocumentCommandService(f.session_factory, fake_storage)
    before = counts(f)

    def fail(_connection, _cursor, statement, *_args):
        if statement.lower().startswith(f"insert into {table} "):
            raise RuntimeError("injected upload failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected upload failure"):
            service.create_upload(context, body, key="retry")
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert counts(f) == before
    assert service.create_upload(context, body, key="retry")[1][0].version_number == 1


def test_concurrent_upload_key_creates_one_version(quotation_fixture, fake_storage):
    f = quotation_fixture
    context, body = prepare(f)
    service = DocumentCommandService(f.session_factory, fake_storage)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: service.create_upload(context, body, key="parallel"), (0, 1))
        )
    assert results[0][1][0].id == results[1][1][0].id
    with f.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 1
        assert session.scalar(select(func.count()).select_from(DocumentVersion)) == 1


def test_recovery_http_permissions_finality_and_key_validation(quotation_fixture, fake_storage):
    f = quotation_fixture
    context, body = prepare(f)
    headers = f.headers("quotation-operations", f.organization_a)
    path = "/api/v1/documents/upload-sessions"
    for invalid in ("", " ", "x" * 256):
        response = f.client.post(path, headers={**headers, "Idempotency-Key": invalid}, json=body)
        assert response.status_code == 422
    headers["Idempotency-Key"] = "http-retry"
    first = f.client.post(path, headers=headers, json=body)
    assert first.status_code == 201
    assert first.json()["document"]["title"] is None
    assert first.json()["document"]["versions"][0]["file_name"] is None
    assert first.json()["document"]["versions"][0]["mime_type"] is None
    before = counts(f)
    replay = f.client.post(path, headers=headers, json=body)
    assert replay.status_code == 201
    assert replay.json()["version_id"] == first.json()["version_id"]
    assert replay.json()["document"] == first.json()["document"]
    with pytest.raises(ApiProblem) as foreign:
        DocumentCommandService(f.session_factory, fake_storage).create_upload(
            replace(context, organization_id=f.organization_b), body, key="http-retry"
        )
    assert foreign.value.status == 404
    with f.session_factory.begin() as session:
        session.get(Shipment, UUID(body["target_id"])).status = "DELIVERED"
    denied = f.client.post(path, headers=headers, json=body)
    assert denied.status_code == 409
    assert denied.json()["code"] == "DOCUMENT_TARGET_FINALIZED"
    assert counts(f) == before


def test_recovery_rechecks_after_signing(quotation_fixture, fake_storage, monkeypatch):
    f = quotation_fixture
    context, body = prepare(f)
    service = DocumentCommandService(f.session_factory, fake_storage)
    first = service.create_upload(context, body, key="sign-race")
    version = first[1][0]
    fake_storage.objects[stored_version(f, version.id).object_key] = StoredObject(
        size=5, content_type="text/plain", sha256=body["sha256"], version_id="pinned"
    )
    original = fake_storage.presign_upload

    def complete_during_sign(object_key, *, expires):
        service.complete(context, first[0].id, version.id)
        return original(object_key, expires=expires)

    monkeypatch.setattr(fake_storage, "presign_upload", complete_during_sign)
    replay = service.create_upload(context, body, key="sign-race")
    assert replay[3] is None
    assert replay[1][0].status == "UPLOADED"
    assert stored_version(f, replay[1][0].id).storage_version_id == "pinned"
