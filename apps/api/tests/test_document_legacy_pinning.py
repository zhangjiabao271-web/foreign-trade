from dataclasses import replace

import pytest
from app.auth.errors import ApiProblem
from app.documents.models import DocumentVersion
from app.documents.services import DocumentCommandService
from app.documents.storage import StoredObject
from app.platform.models import AuditLog, OutboxEvent
from app.work.models import Activity
from sqlalchemy import event, select
from test_document_review import counts, reviewer, seed_document
from test_shipment_documents_vertical_slice import FakeObjectStorage

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def prepare_legacy(f, state="AVAILABLE"):
    document_id, version_id = seed_document(f)
    _, context = reviewer(f)
    with f.session_factory.begin() as session:
        version = session.get(DocumentVersion, version_id)
        version.storage_version_id = None
        version.status = state
        object_key = version.object_key

    class InspectingStorage(FakeObjectStorage):
        def inspect(self, object_key, *, version_id=None):
            assert f.engine.pool.checkedout() == 0
            if version_id is not None:
                assert version_id == "legacy-verified-v1"
            return super().inspect(object_key, version_id=version_id)

    storage = InspectingStorage()
    storage.objects[object_key] = StoredObject(10, "text/plain", "a" * 64, "legacy-verified-v1")
    return document_id, version_id, context, storage, object_key


def version_snapshot(f, version_id):
    with f.session_factory() as session:
        return dict(
            session.execute(
                select(DocumentVersion.__table__).where(DocumentVersion.id == version_id)
            )
            .mappings()
            .one()
        )


@pytest.mark.parametrize("state", ["UPLOADED", "SCANNING", "AVAILABLE"])
def test_legacy_revalidation_pins_once_and_preserves_original_metadata(quotation_fixture, state):
    f = quotation_fixture
    document_id, version_id, context, storage, _ = prepare_legacy(f, state)
    service = DocumentCommandService(f.session_factory, storage)
    before = version_snapshot(f, version_id)
    before_counts = counts(f)
    if state == "AVAILABLE":
        with pytest.raises(ApiProblem) as unpinned:
            service.download(context, document_id, version_id=version_id)
        assert unpinned.value.code == "DOCUMENT_VERSION_UNPINNED"
    service.complete(context, document_id, version_id)
    after = version_snapshot(f, version_id)
    assert after["storage_version_id"] == "legacy-verified-v1"
    for column in before:
        if column not in {"storage_version_id", "version", "updated_at"}:
            assert after[column] == before[column], column
    assert counts(f) == [*(value + 1 for value in before_counts[:3]), before_counts[3]]
    service.complete(context, document_id, version_id)
    assert version_snapshot(f, version_id) == after
    assert counts(f) == [*(value + 1 for value in before_counts[:3]), before_counts[3]]
    if state == "AVAILABLE":
        url, _ = service.download(context, document_id, version_id=version_id)
        assert url.startswith("https://storage.example.test/download/")


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"size": 11}, "UPLOAD_SIZE_MISMATCH"),
        ({"sha256": "b" * 64}, "UPLOAD_CHECKSUM_MISMATCH"),
        ({"content_type": "application/pdf"}, "UPLOAD_MIME_MISMATCH"),
        ({"version_id": None}, "STORAGE_VERSION_REQUIRED"),
        ({"version_id": "null"}, "STORAGE_VERSION_REQUIRED"),
    ],
)
def test_legacy_invalid_evidence_never_pins(quotation_fixture, changes, code):
    f = quotation_fixture
    document_id, version_id, context, storage, key = prepare_legacy(f)
    storage.objects[key] = replace(storage.objects[key], **changes)
    before = version_snapshot(f, version_id), counts(f)
    with pytest.raises(ApiProblem) as error:
        DocumentCommandService(f.session_factory, storage).complete(
            context, document_id, version_id
        )
    assert error.value.code == code
    assert (version_snapshot(f, version_id), counts(f)) == before


@pytest.mark.parametrize("model", [Activity, AuditLog, OutboxEvent])
def test_legacy_pinning_evidence_failure_rolls_back(quotation_fixture, model):
    f = quotation_fixture
    document_id, version_id, context, storage, _ = prepare_legacy(f)
    before = version_snapshot(f, version_id), counts(f)

    def fail(*args, **kwargs):
        raise RuntimeError("Injected legacy pin evidence failure")

    event.listen(model, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="Injected legacy pin evidence failure"):
            DocumentCommandService(f.session_factory, storage).complete(
                context, document_id, version_id
            )
    finally:
        event.remove(model, "before_insert", fail)
    assert (version_snapshot(f, version_id), counts(f)) == before
