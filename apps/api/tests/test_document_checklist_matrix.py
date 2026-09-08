"""Metadata projection matrix, not object-storage or malware-scanner acceptance."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from app.documents.checklists import missing_document_types
from app.documents.enums import DocumentLinkTargetType, DocumentVersionStatus
from app.documents.models import Document, DocumentLink, DocumentVersion
from sqlalchemy import event, text

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


@pytest.mark.parametrize("target_type", list(DocumentLinkTargetType))
def test_checklists_require_live_current_pinned_version_in_exact_scope(
    quotation_fixture, target_type
):
    f = quotation_fixture
    target_id, other_target = uuid4(), uuid4()
    with f.session_factory.begin() as session:
        document = Document(
            organization_id=f.organization_a,
            title="Synthetic checklist evidence",
            document_type="COMMERCIAL_INVOICE",
        )
        session.add(document)
        session.flush()
        version = DocumentVersion(
            organization_id=f.organization_a,
            document_id=document.id,
            version_number=1,
            status="AVAILABLE",
            storage_version_id="immutable-v1",
            object_key=f"{f.organization_a}/{uuid4()}",
            file_name="synthetic.txt",
            mime_type="text/plain",
            expected_size_bytes=1,
            expected_sha256="a" * 64,
        )
        link = DocumentLink(
            organization_id=f.organization_a,
            document_id=document.id,
            target_type=target_type,
            target_id=target_id,
        )
        session.add_all([version, link])
        session.flush()
        document_id, version_id, link_id = document.id, version.id, link.id

    statements = []

    def capture(_connection, _cursor, statement, *_args):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    def read(*, organization=None, kind=target_type, requirements=None):
        with f.session_factory.begin() as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            statements.clear()
            result = missing_document_types(
                session,
                organization_id=organization or f.organization_a,
                target_type=kind,
                requirements=(
                    {target_id: ["PACKING_LIST", "COMMERCIAL_INVOICE", "PACKING_LIST"]}
                    if requirements is None
                    else requirements
                ),
            )
            assert len(statements) == (0 if requirements == {} else 1)
            return result

    missing = {target_id: ["COMMERCIAL_INVOICE", "PACKING_LIST"]}
    event.listen(f.engine, "before_cursor_execute", capture)
    try:
        for state in DocumentVersionStatus:
            with f.session_factory.begin() as session:
                session.get(DocumentVersion, version_id).status = state.value
            assert read() == (
                {target_id: ["PACKING_LIST"]}
                if state == DocumentVersionStatus.AVAILABLE
                else missing
            )
        with f.session_factory.begin() as session:
            session.get(DocumentVersion, version_id).status = "AVAILABLE"
        for pointer in (None, "", "null"):
            with f.session_factory.begin() as session:
                session.get(DocumentVersion, version_id).storage_version_id = pointer
            assert read() == missing
        with f.session_factory.begin() as session:
            session.get(DocumentVersion, version_id).storage_version_id = "immutable-v1"
        assert read() == {target_id: ["PACKING_LIST"]}
        assert read(organization=f.organization_b) == missing
        for kind in DocumentLinkTargetType:
            if kind != target_type:
                assert read(kind=kind) == missing
        assert read(requirements={other_target: ["COMMERCIAL_INVOICE"]}) == {
            other_target: ["COMMERCIAL_INVOICE"]
        }
        assert read(requirements={}) == {}

        for model, record_id in (
            (Document, document_id),
            (DocumentVersion, version_id),
            (DocumentLink, link_id),
        ):
            with f.session_factory.begin() as session:
                session.get(model, record_id).deleted_at = datetime.now(UTC)
            assert read() == missing
            with f.session_factory.begin() as session:
                session.get(model, record_id).deleted_at = None

        with f.session_factory.begin() as session:
            session.get(Document, document_id).latest_version_number = 2
            replacement = DocumentVersion(
                organization_id=f.organization_a,
                document_id=document_id,
                version_number=2,
                status="PENDING_UPLOAD",
                object_key=f"{f.organization_a}/{uuid4()}",
                file_name="replacement.txt",
                mime_type="text/plain",
                expected_size_bytes=2,
                expected_sha256="b" * 64,
            )
            session.add(replacement)
            session.flush()
            replacement_id = replacement.id
        assert read() == missing  # Retained AVAILABLE v1 must not fill the current gap.
        with f.session_factory.begin() as session:
            row = session.get(DocumentVersion, replacement_id)
            row.status = "AVAILABLE"
            row.storage_version_id = "immutable-v2"
        assert read() == {target_id: ["PACKING_LIST"]}
        with f.session_factory() as session:
            historical = session.get(DocumentVersion, version_id)
            assert historical.status == "AVAILABLE"
            assert historical.storage_version_id == "immutable-v1"
            assert historical.expected_sha256 == "a" * 64
    finally:
        event.remove(f.engine, "before_cursor_execute", capture)
