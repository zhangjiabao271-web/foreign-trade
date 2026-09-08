from datetime import UTC, datetime, timedelta
from hashlib import sha256
from urllib.parse import urlparse
from uuid import UUID

import pytest
from app.ai.models import AiRun, AiToolCall
from app.documents.models import Document, DocumentVersion
from app.documents.services import mark_document_available
from app.documents.storage import StoredObject
from app.identity.models import OrganizationMembership
from app.platform.domain_jobs import complete_document_scan_job, finish_ai_attempt, start_ai_attempt
from app.platform.models import AsyncJob, AuditLog, OutboxEvent, ProcessedEvent
from app.platform.outbox import IdempotentEventConsumer, outbox_message
from app.work.models import Activity
from sqlalchemy import select
from test_ai_copilot import ScriptedProvider, create_run, execute
from test_quotation_vertical_slice import post_ok
from test_shipment_documents_vertical_slice import create_shipment, executing_order

pytest_plugins = ("test_quotation_vertical_slice", "test_shipment_documents_vertical_slice")
pytestmark = pytest.mark.integration


def snapshot(f):
    with f.session_factory() as session:
        return {
            model.__tablename__: list(
                session.execute(select(*model.__table__.columns).order_by(model.id))
            )
            for model in (
                AiRun,
                AiToolCall,
                AsyncJob,
                Document,
                DocumentVersion,
                Activity,
                AuditLog,
                OutboxEvent,
            )
        }


@pytest.mark.parametrize("phase", ["start", "finish"])
def test_ai_owner_flush_failure_preserves_correct_transaction_boundary(
    quotation_fixture, monkeypatch, phase
):
    f = quotation_fixture
    order = executing_order(f)
    response = create_run(f, order["id"])
    assert response.status_code == 202
    run_id = response.json()["id"]
    before = snapshot(f)
    provider = ScriptedProvider(order["id"], tool="order_timeline")
    calls = []
    original = start_ai_attempt if phase == "start" else finish_ai_attempt

    def fail_after_owner(session, **kwargs):
        calls.append(original(session, **kwargs))
        session.flush()
        raise RuntimeError("injected failure after Platform job flush")

    with monkeypatch.context() as patch:
        patch.setattr(f"app.ai.runner.{phase}_ai_attempt", fail_after_owner)
        with pytest.raises(RuntimeError, match="after Platform job flush"):
            execute(f, run_id, provider)
    assert len(calls) == 1
    if phase == "start":
        assert provider.calls == 0
        assert snapshot(f) == before
    else:
        assert provider.calls == 2
        with f.session_factory() as session:
            run = session.get(AiRun, UUID(run_id))
            job = session.get(AsyncJob, run.job_id)
            assert run.status == job.status == "RUNNING"
            assert run.attempt_count == job.attempt_count == 1
            assert run.lease_id is not None and run.completed_at is None
            assert run.input_tokens == run.output_tokens == 0 and run.output is None
            assert job.progress == 0 and job.error_code is None
            assert not list(
                session.scalars(
                    select(Activity).where(
                        Activity.subject_id == run.id, Activity.activity_type == "ai.run_finished"
                    )
                )
            )
        # The separately committed start/tool receipt remains; simulate only lease expiry.
        with f.session_factory.begin() as session:
            session.get(AiRun, UUID(run_id)).started_at = datetime.now(UTC) - timedelta(minutes=5)
    execute(f, run_id, ScriptedProvider(order["id"], tool="order_timeline"))
    with f.session_factory() as session:
        run = session.get(AiRun, UUID(run_id))
        job = session.get(AsyncJob, run.job_id)
        assert run.status == job.status == "SUCCEEDED"
        assert run.lease_id is None and job.progress == 100


def test_revoked_actor_records_matching_failed_run_job_and_evidence(quotation_fixture):
    f = quotation_fixture
    order = executing_order(f)
    response = create_run(f, order["id"])
    assert response.status_code == 202
    run_id = response.json()["id"]

    def revoke():
        with f.session_factory.begin() as session:
            member = session.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == f.organization_a,
                    OrganizationMembership.user_id == f.sales_user,
                )
            )
            member.role = "VIEWER"

    execute(f, run_id, ScriptedProvider(order["id"], before_return=revoke))
    with f.session_factory() as session:
        run = session.get(AiRun, UUID(run_id))
        job = session.get(AsyncJob, run.job_id)
        assert run.status == job.status == "FAILED"
        assert run.error_code == job.error_code == "PERMISSION_DENIED"
        assert run.output is None and run.lease_id is None and run.completed_at is not None
        assert job.progress == 100 and run.attempt_count == job.attempt_count == 1
        assert (
            session.scalar(
                select(Activity.id).where(
                    Activity.subject_id == run.id, Activity.activity_type == "ai.run_finished"
                )
            )
            is not None
        )
        assert (
            session.scalar(
                select(OutboxEvent.id).where(
                    OutboxEvent.aggregate_id == run.id,
                    OutboxEvent.event_type == "ai.run_finished.v1",
                )
            )
            is not None
        )


def test_scan_owner_failure_rolls_back_version_job_activity_and_consumer_receipt(
    quotation_fixture, fake_storage, monkeypatch
):
    f = quotation_fixture
    order = executing_order(f)
    item = order["items"][0]
    shipment = create_shipment(
        f, [{"sales_order_item_id": item["id"], "quantity": item["quantity"]}]
    )
    content = b"Synthetic scan atomicity evidence"
    digest = sha256(content).hexdigest()
    upload = post_ok(
        f,
        "/api/v1/documents/upload-sessions",
        "quotation-operations",
        {
            "title": "Scan atomicity",
            "document_type": "COMMERCIAL_INVOICE",
            "file_name": "scan.txt",
            "mime_type": "text/plain",
            "size_bytes": len(content),
            "sha256": digest,
            "target_type": "SHIPMENT",
            "target_id": shipment["id"],
        },
        201,
    )
    key = urlparse(upload["upload_url"]).path.removeprefix("/upload/")
    fake_storage.objects[key] = StoredObject(
        size=len(content), content_type="text/plain", sha256=digest, version_id="scan-test-version"
    )
    post_ok(
        f,
        f"/api/v1/documents/{upload['document']['id']}/versions/{upload['version_id']}/complete",
        "quotation-operations",
    )
    with f.session_factory() as session:
        event = session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.organization_id == f.organization_a,
                OutboxEvent.event_type == "document.uploaded.v1",
                OutboxEvent.payload["version_id"].astext == upload["version_id"],
            )
        )
        message = outbox_message(event)
    consumer = IdempotentEventConsumer(f.session_factory)
    before = snapshot(f)
    calls = []

    def fail_after_owner(session, **kwargs):
        complete_document_scan_job(session, **kwargs)
        session.flush()
        calls.append(kwargs["job_id"])
        raise RuntimeError("scan caller failed after Platform flush")

    with monkeypatch.context() as patch:
        patch.setattr("app.documents.services.complete_document_scan_job", fail_after_owner)
        with pytest.raises(RuntimeError, match="scan caller failed"):
            consumer.consume(
                consumer_name="scan-owner-atomicity",
                message=message,
                handler=mark_document_available,
            )
    assert calls == [UUID(message["payload"]["job_id"])]
    assert snapshot(f) == before
    with f.session_factory() as session:
        assert (
            session.scalar(
                select(ProcessedEvent.event_id).where(
                    ProcessedEvent.event_id == UUID(message["id"]),
                    ProcessedEvent.consumer_name == "scan-owner-atomicity",
                )
            )
            is None
        )
    assert consumer.consume(
        consumer_name="scan-owner-atomicity", message=message, handler=mark_document_available
    )
    after = snapshot(f)
    assert not consumer.consume(
        consumer_name="scan-owner-atomicity", message=message, handler=mark_document_available
    )
    assert snapshot(f) == after
    with f.session_factory() as session:
        version = session.get(DocumentVersion, UUID(upload["version_id"]))
        job = session.get(AsyncJob, UUID(message["payload"]["job_id"]))
        activity = session.scalar(
            select(Activity).where(
                Activity.subject_id == version.document_id,
                Activity.activity_type == "document.available",
            )
        )
        assert version.status == "AVAILABLE" and job.status == "SUCCEEDED"
        assert job.progress == 100 and job.result_reference == f"document-version:{version.id}"
        assert activity.created_by is activity.updated_by is None
        assert activity.correlation_id == UUID(message["correlation_id"])
