from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from uuid import uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import permissions_for_role
from app.documents.models import Document, DocumentLink, DocumentVersion
from app.documents.repositories import DocumentRepository
from app.documents.review import DocumentReviewRequest, DocumentReviewService, is_released
from app.documents.services import DocumentCommandService, DocumentQueryService
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership, User
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.work.models import Activity
from sqlalchemy import func, select
from test_shipment_documents_vertical_slice import FakeObjectStorage, executing_order

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def seed_document(f):
    order = executing_order(f)
    with f.session_factory.begin() as session:
        from uuid import UUID

        document = Document(
            organization_id=f.organization_a,
            title="Internal cost 350 CNY",
            document_type="OTHER",
            latest_version_number=1,
        )
        session.add(document)
        session.flush()
        version = DocumentVersion(
            organization_id=f.organization_a,
            document_id=document.id,
            version_number=1,
            status="AVAILABLE",
            object_key=f"{f.organization_a}/{uuid4()}",
            storage_version_id="immutable-v1",
            file_name="supplier-cost.txt",
            mime_type="text/plain",
            expected_size_bytes=10,
            actual_size_bytes=10,
            expected_sha256="a" * 64,
            actual_sha256="a" * 64,
        )
        session.add_all(
            [
                version,
                DocumentLink(
                    organization_id=f.organization_a,
                    document_id=document.id,
                    target_type="SALES_ORDER",
                    target_id=UUID(order["id"]),
                ),
            ]
        )
        session.flush()
        assert not is_released(document, version)
        return document.id, version.id


def reviewer(f, role=MembershipRole.MANAGER):
    subject = f"review-{role}"
    with f.session_factory.begin() as session:
        user = User(external_subject=subject, display_name="Review fixture")
        session.add(user)
        session.flush()
        session.add(
            OrganizationMembership(
                organization_id=f.organization_a,
                user_id=user.id,
                role=role,
                status="ACTIVE",
            )
        )
    return subject, RequestContext(
        user_id=user.id,
        organization_id=f.organization_a,
        permissions=permissions_for_role(role),
        request_id=uuid4(),
    )


def counts(f):
    with f.session_factory() as session:
        return [
            session.scalar(select(func.count()).select_from(model))
            for model in (Activity, AuditLog, OutboxEvent, IdempotencyKey)
        ]


def decision(preview, release=True):
    return DocumentReviewRequest(
        expected_version=preview.version,
        content_digest=preview.content_digest,
        release=release,
        reason="Reviewed exact content and filename",
        confirmed=True,
    )


@pytest.mark.parametrize("role", list(MembershipRole))
def test_review_authority_http_and_service(quotation_fixture, role):
    f = quotation_fixture
    document_id, version_id = seed_document(f)
    subject, context = reviewer(f, role)
    service = DocumentReviewService(f.session_factory)
    path = f"/api/v1/documents/{document_id}/versions/{version_id}/review"
    headers = f.headers(subject, f.organization_a) | {"Idempotency-Key": "role-review"}
    before = counts(f)
    privileged = role in {MembershipRole.ADMIN, MembershipRole.MANAGER, MembershipRole.FINANCE}
    document_path = f"/api/v1/documents/{document_id}"
    response = f.client.get(document_path, headers=headers)
    assert response.status_code == 200
    assert response.json()["title"] == ("Internal cost 350 CNY" if privileged else None)
    assert response.json()["versions"][0]["file_name"] == (
        "supplier-cost.txt" if privileged else None
    )
    assert response.json()["versions"][0]["content_visible"] is privileged
    with f.session_factory() as session:
        result, _, _ = DocumentQueryService(DocumentRepository(session)).get(context, document_id)
        assert result.model_dump(mode="json") == response.json()
        assert session.get(Document, document_id).title == "Internal cost 350 CNY"
        assert not session.dirty
    if role in {MembershipRole.SALES, MembershipRole.OPERATIONS, MembershipRole.VIEWER}:
        assert f.client.get(path, headers=headers).status_code == 403
        assert (
            f.client.post(
                path,
                headers=headers,
                json={
                    "expected_version": 1,
                    "content_digest": "a" * 64,
                    "release": True,
                    "reason": "Unauthorized review",
                    "confirmed": True,
                },
            ).status_code
            == 403
        )
        with pytest.raises(ApiProblem) as error:
            service.inspect(context, document_id, version_id)
        assert error.value.status == 403
        assert counts(f) == before
        return
    preview = service.inspect(context, document_id, version_id)
    assert not preview.released
    request = decision(preview)
    result = f.client.post(path, headers=headers, json=request.model_dump())
    assert result.status_code == 200, result.text
    assert result.json()["released"]
    assert counts(f) == [number + 1 for number in before]
    assert f.client.post(path, headers=headers, json=request.model_dump()).json() == result.json()
    assert counts(f) == [number + 1 for number in before]
    with pytest.raises(ApiProblem) as error:
        service.inspect(replace(context, organization_id=f.organization_b), document_id, version_id)
    assert error.value.status == 404


def test_review_revoke_stale_and_changed_content(quotation_fixture):
    f = quotation_fixture
    document_id, version_id = seed_document(f)
    _, context = reviewer(f)
    service = DocumentReviewService(f.session_factory)
    low = replace(context, permissions=permissions_for_role(MembershipRole.OPERATIONS))
    downloader = DocumentCommandService(f.session_factory, FakeObjectStorage())
    with pytest.raises(ApiProblem) as confidential:
        downloader.download(low, document_id, version_id=version_id)
    assert confidential.value.code == "DOCUMENT_REVIEW_REQUIRED"
    original = service.inspect(context, document_id, version_id)
    opened = service.decide(context, document_id, version_id, decision(original), key="open")
    assert opened.released
    assert downloader.download(low, document_id, version_id=version_id)[0].startswith("https://")
    with pytest.raises(ApiProblem) as stale:
        service.decide(context, document_id, version_id, decision(original, False), key="stale")
    assert stale.value.code == "VERSION_CONFLICT"
    closed = service.decide(context, document_id, version_id, decision(opened, False), key="close")
    assert not closed.released
    with pytest.raises(ApiProblem) as confidential:
        downloader.download(low, document_id, version_id=version_id)
    assert confidential.value.code == "DOCUMENT_REVIEW_REQUIRED"
    # Old release replay returns current restriction, never reopens it.
    assert not service.decide(
        context, document_id, version_id, decision(original), key="open"
    ).released
    reopened = service.decide(context, document_id, version_id, decision(closed), key="reopen")
    assert reopened.released
    with f.session_factory.begin() as session:
        document = session.get(Document, document_id)
        document.title = "Changed internal note"
    assert not service.inspect(context, document_id, version_id).released
    with pytest.raises(ApiProblem) as changed:
        service.decide(context, document_id, version_id, decision(reopened), key="changed")
    assert changed.value.code == "VERSION_CONFLICT"


@pytest.mark.parametrize("stage", ["activity", "audit", "outbox"])
def test_review_evidence_failure_rolls_back(quotation_fixture, stage):
    f = quotation_fixture
    document_id, version_id = seed_document(f)
    _, context = reviewer(f)
    service = DocumentReviewService(f.session_factory)
    preview = service.inspect(context, document_id, version_id)
    before = counts(f)
    from sqlalchemy import event

    def fail(*args, **kwargs):
        raise RuntimeError("injected review evidence failure")

    target = {"activity": Activity, "audit": AuditLog, "outbox": OutboxEvent}[stage]
    event.listen(target, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="injected review"):
            service.decide(context, document_id, version_id, decision(preview), key="failed")
    finally:
        event.remove(target, "before_insert", fail)
    assert counts(f) == before
    assert service.inspect(context, document_id, version_id) == preview


def test_unverified_file_cannot_be_released_and_confirmation_is_required(quotation_fixture):
    f = quotation_fixture
    document_id, version_id = seed_document(f)
    _, context = reviewer(f)
    service = DocumentReviewService(f.session_factory)
    with f.session_factory.begin() as session:
        version = session.get(DocumentVersion, version_id)
        version.storage_version_id = None
    preview = service.inspect(context, document_id, version_id)
    before = counts(f)
    with pytest.raises(ApiProblem) as error:
        service.decide(context, document_id, version_id, decision(preview), key="unverified")
    assert error.value.code == "DOCUMENT_NOT_AVAILABLE"
    request = decision(preview).model_copy(update={"confirmed": False})
    with pytest.raises(ApiProblem) as error:
        service.decide(context, document_id, version_id, request, key="unconfirmed")
    assert error.value.code == "CONFIRMATION_REQUIRED"
    assert counts(f) == before


def test_concurrent_review_decisions_do_not_overwrite_each_other(quotation_fixture):
    f = quotation_fixture
    document_id, version_id = seed_document(f)
    _, context = reviewer(f)
    service = DocumentReviewService(f.session_factory)
    preview = service.inspect(context, document_id, version_id)
    before = counts(f)
    barrier = Barrier(2)

    def decide_together(release):
        barrier.wait(timeout=10)
        try:
            return service.decide(
                replace(context, request_id=uuid4()),
                document_id,
                version_id,
                decision(preview, release),
                key=f"concurrent-{release}",
            )
        except ApiProblem as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(decide_together, (True, False)))
    failures = [result for result in outcomes if isinstance(result, ApiProblem)]
    successes = [result for result in outcomes if not isinstance(result, ApiProblem)]
    assert len(failures) == len(successes) == 1
    assert failures[0].code == "VERSION_CONFLICT"
    assert service.inspect(context, document_id, version_id) == successes[0]
    assert counts(f) == [number + 1 for number in before]


def test_review_and_replay_recheck_downgraded_membership(quotation_fixture):
    f = quotation_fixture
    document_id, version_id = seed_document(f)
    subject, context = reviewer(f)
    service = DocumentReviewService(f.session_factory)
    preview = service.inspect(context, document_id, version_id)
    # Keep the content confidential; successful review does not imply release.
    request = decision(preview, False)
    path = f"/api/v1/documents/{document_id}/versions/{version_id}/review"
    headers = f.headers(subject, f.organization_a) | {"Idempotency-Key": "before-downgrade"}
    assert f.client.post(path, headers=headers, json=request.model_dump()).status_code == 200
    before = counts(f)
    with f.session_factory.begin() as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_a,
                OrganizationMembership.user_id == context.user_id,
            )
        )
        membership.role = MembershipRole.SALES
    assert f.client.get(path, headers=headers).status_code == 403
    assert f.client.post(path, headers=headers, json=request.model_dump()).status_code == 403
    assert (
        f.client.post(
            path,
            headers=headers | {"Idempotency-Key": "after-downgrade"},
            json=decision(preview).model_dump(),
        ).status_code
        == 403
    )
    document = f.client.get(f"/api/v1/documents/{document_id}", headers=headers)
    assert document.status_code == 200
    assert document.json()["title"] is None
    assert document.json()["versions"][0]["file_name"] is None
    download = f.client.post(
        f"/api/v1/documents/{document_id}/versions/{version_id}/download-session",
        headers=headers,
    )
    assert download.status_code == 403
    assert counts(f) == before


def test_download_does_not_return_url_if_release_is_revoked_during_signing(quotation_fixture):
    f = quotation_fixture
    document_id, version_id = seed_document(f)
    _, context = reviewer(f)
    service = DocumentReviewService(f.session_factory)
    preview = service.inspect(context, document_id, version_id)
    opened = service.decide(context, document_id, version_id, decision(preview), key="open")
    low = replace(context, permissions=permissions_for_role(MembershipRole.OPERATIONS))

    reviewed_version_id = version_id

    class RevokingStorage(FakeObjectStorage):
        def presign_download(self, object_key, *, expires, version_id):
            assert f.engine.pool.checkedout() == 0
            service.decide(
                context,
                document_id,
                reviewed_version_id,
                decision(opened, False),
                key="revoke-in-flight",
            )
            return super().presign_download(object_key, expires=expires, version_id=version_id)

    with pytest.raises(ApiProblem) as revoked:
        DocumentCommandService(f.session_factory, RevokingStorage()).download(
            low, document_id, version_id=version_id
        )
    assert revoked.value.code == "DOCUMENT_REVIEW_REQUIRED"


@pytest.mark.parametrize("change", ["title", "storage_pointer"])
def test_privileged_download_rechecks_exact_content_after_signing(quotation_fixture, change):
    f = quotation_fixture
    document_id, reviewed_version_id = seed_document(f)
    _, context = reviewer(f)

    class ChangingStorage(FakeObjectStorage):
        def presign_download(self, object_key, *, expires, version_id):
            assert f.engine.pool.checkedout() == 0
            with f.session_factory.begin() as session:
                if change == "title":
                    session.get(Document, document_id).title = "Changed during signing"
                else:
                    session.get(DocumentVersion, reviewed_version_id).storage_version_id = "v2"
            return super().presign_download(object_key, expires=expires, version_id=version_id)

    with pytest.raises(ApiProblem) as changed:
        DocumentCommandService(f.session_factory, ChangingStorage()).download(
            context, document_id, version_id=reviewed_version_id
        )
    assert changed.value.code == "VERSION_CONFLICT"
