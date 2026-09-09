from dataclasses import replace
from uuid import UUID

import pytest
from app.auth.errors import ApiProblem
from app.documents.repositories import DocumentRepository
from app.documents.review import DocumentReviewRequest, DocumentReviewService
from app.documents.services import DocumentCommandService, DocumentQueryService
from test_document_completion_access import facts
from test_sales_foreign_commands import foreign_manager
from test_upload_recovery import prepare

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice", "test_shipment_documents_vertical_slice")


def test_document_repository_and_all_http_paths_are_tenant_scoped(
    quotation_fixture, fake_storage, monkeypatch
):
    f = quotation_fixture
    owner, body = prepare(f)
    command = DocumentCommandService(f.session_factory, fake_storage)
    document, versions, _, _, _ = command.create_upload(owner, body)
    version_id = versions[0].id
    foreign = foreign_manager(f)
    before = facts(f)
    target_id = UUID(body["target_id"])
    with f.session_factory() as session:
        repository = DocumentRepository(session)
        for organization_id, visible in ((f.organization_a, True), (f.organization_b, False)):
            assert (
                bool(repository.get(organization_id=organization_id, record_id=document.id))
                == visible
            )
            assert bool(repository.list(organization_id=organization_id)) == visible
            assert repository.count(organization_id=organization_id) == int(visible)
            assert (
                bool(
                    repository.get_for_update(
                        organization_id=organization_id, document_id=document.id
                    )
                )
                == visible
            )
            assert (
                bool(repository.versions(organization_id=organization_id, document_id=document.id))
                == visible
            )
            assert (
                bool(repository.links(organization_id=organization_id, document_id=document.id))
                == visible
            )
            assert (
                bool(
                    repository.versions_for_documents(
                        organization_id=organization_id, document_ids={document.id}
                    )
                )
                == visible
            )
            assert (
                bool(
                    repository.links_for_documents(
                        organization_id=organization_id, document_ids={document.id}
                    )
                )
                == visible
            )
            assert (
                bool(
                    repository.linked(
                        organization_id=organization_id, target_type="SHIPMENT", target_id=target_id
                    )
                )
                == visible
            )
            assert (
                bool(
                    repository.version_for_update(
                        organization_id=organization_id, version_id=version_id
                    )
                )
                == visible
            )
        assert (
            repository.versions_for_documents(organization_id=f.organization_a, document_ids=set())
            == []
        )
        assert (
            repository.links_for_documents(organization_id=f.organization_a, document_ids=set())
            == []
        )
        query = DocumentQueryService(repository)
        assert query.get(owner, document.id)[0].id == document.id
        assert (
            query.linked(owner, target_type="SHIPMENT", target_id=target_id)[0][0].id == document.id
        )
        for context, status in ((foreign, 404), (replace(owner, permissions=frozenset()), 403)):
            with pytest.raises(ApiProblem) as denied:
                query.get(context, document.id)
            assert denied.value.status == status
            with pytest.raises(ApiProblem) as denied:
                query.linked(context, target_type="SHIPMENT", target_id=target_id)
            assert denied.value.status == status

    def forbidden_storage(*args, **kwargs):
        raise AssertionError("Foreign access must fail before any storage call")

    for method in ("ensure_bucket", "presign_upload", "presign_download", "inspect"):
        monkeypatch.setattr(fake_storage, method, forbidden_storage)
    metadata = {key: body[key] for key in ("file_name", "mime_type", "size_bytes", "sha256")}
    replacement = {**metadata, "expected_version": document.version}
    review = DocumentReviewRequest(
        expected_version=1,
        content_digest="0" * 64,
        release=False,
        confirmed=True,
        reason="Synthetic foreign review denied",
    )
    base = f"/api/v1/documents/{document.id}"
    version_base = f"{base}/versions/{version_id}"
    routes = (
        ("GET", f"{version_base}/review", None),
        ("POST", f"{version_base}/review", review.model_dump(mode="json")),
        ("GET", f"/api/v1/documents?target_type=SHIPMENT&target_id={target_id}", None),
        ("POST", "/api/v1/documents/upload-sessions", body),
        ("POST", f"{version_base}/complete", None),
        ("POST", f"{base}/version-upload-sessions", replacement),
        ("POST", f"{version_base}/upload-session", metadata),
        ("GET", base, None),
        ("POST", f"{base}/download-session", None),
        ("POST", f"{version_base}/download-session", None),
    )
    headers = {**f.headers("quotation-other", f.organization_b), "Idempotency-Key": "foreign-doc"}
    for method, path, payload in routes:
        response = f.client.request(method, path, headers=headers, json=payload)
        assert response.status_code == 404, (path, response.text)
        assert facts(f) == before
    reviewer = DocumentReviewService(f.session_factory)
    for operation in (
        lambda: command.create_upload(foreign, body),
        lambda: command.create_version(foreign, document.id, replacement),
        lambda: command.complete(foreign, document.id, version_id),
        lambda: command.resume_upload(foreign, document.id, version_id, metadata),
        lambda: command.download(foreign, document.id),
        lambda: command.download(foreign, document.id, version_id=version_id),
        lambda: reviewer.inspect(foreign, document.id, version_id),
        lambda: reviewer.decide(foreign, document.id, version_id, review, key="foreign-doc"),
    ):
        with pytest.raises(ApiProblem) as denied:
            operation()
        assert denied.value.status == 404
        assert facts(f) == before
