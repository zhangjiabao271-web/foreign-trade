from datetime import UTC, datetime

import pytest
from app.auth.errors import ApiProblem
from app.documents.models import Document, DocumentLink, DocumentVersion
from app.documents.services import DocumentCommandService
from app.documents.storage import StoredObject
from app.platform.models import AsyncJob
from sqlalchemy import select
from test_shipment_parent_atomicity import snapshot
from test_upload_recovery import prepare

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice", "test_shipment_documents_vertical_slice")


def facts(f):
    with f.session_factory() as session:
        return snapshot(f) | {
            model.__tablename__: [
                dict(row)
                for row in session.execute(select(model.__table__).order_by(model.id)).mappings()
            ]
            for model in (Document, DocumentVersion, DocumentLink, AsyncJob)
        }


@pytest.mark.parametrize("condition", ["deleted_document", "deleted_link"])
def test_completion_rejects_inaccessible_document_before_storage(
    quotation_fixture, fake_storage, monkeypatch, condition
):
    f = quotation_fixture
    context, body = prepare(f)
    service = DocumentCommandService(f.session_factory, fake_storage)
    document, versions, _, _, _ = service.create_upload(context, body)
    version_id = versions[0].id
    with f.session_factory.begin() as session:
        model = Document if condition == "deleted_document" else DocumentLink
        record = session.scalar(select(model))
        record.deleted_at = datetime.now(UTC)
    before = facts(f)
    inspections = []

    def inspect(object_key, *, version_id=None):
        inspections.append(object_key)
        return StoredObject(
            size=5, content_type="text/plain", sha256=body["sha256"], version_id="pinned"
        )

    monkeypatch.setattr(fake_storage, "inspect", inspect)
    with pytest.raises(ApiProblem) as denied:
        service.complete(context, document.id, version_id)
    assert denied.value.status == 404
    response = f.client.post(
        f"/api/v1/documents/{document.id}/versions/{version_id}/complete",
        headers=f.headers("quotation-operations", f.organization_a),
    )
    assert response.status_code == 404
    assert inspections == []
    assert facts(f) == before


def test_completion_rechecks_links_after_storage_and_allows_valid_recovery(
    quotation_fixture, fake_storage, monkeypatch
):
    f = quotation_fixture
    context, body = prepare(f)
    service = DocumentCommandService(f.session_factory, fake_storage)
    document, versions, _, _, _ = service.create_upload(context, body)
    version_id = versions[0].id
    after_unlink = []

    def inspect(object_key, *, version_id=None):
        with f.session_factory.begin() as session:
            session.scalar(select(DocumentLink)).deleted_at = datetime.now(UTC)
        after_unlink.append(facts(f))
        return StoredObject(
            size=5, content_type="text/plain", sha256=body["sha256"], version_id="pinned"
        )

    monkeypatch.setattr(fake_storage, "inspect", inspect)
    with pytest.raises(ApiProblem) as denied:
        service.complete(context, document.id, version_id)
    assert denied.value.status == 404
    assert facts(f) == after_unlink[0]
    with f.session_factory.begin() as session:
        session.scalar(select(DocumentLink)).deleted_at = None
    monkeypatch.setattr(
        fake_storage,
        "inspect",
        lambda *args, **kwargs: StoredObject(
            size=5, content_type="text/plain", sha256=body["sha256"], version_id="pinned"
        ),
    )
    completed = service.complete(context, document.id, version_id)
    assert completed[1][0].status == "UPLOADED"
    before_replay = facts(f)
    service.complete(context, document.id, version_id)
    assert facts(f) == before_replay
