from uuid import UUID, uuid4

import pytest
from app.ai.models import AiRun, AiToolCall
from app.core.config import Settings
from app.documents.models import Document, DocumentVersion
from app.platform.models import AsyncJob, AuditLog, OutboxEvent, ProcessedEvent
from app.platform.outbox import outbox_message
from app.sales.models import SalesOrder, SalesOrderItem
from app.work.models import Activity
from sqlalchemy import select
from test_ai_copilot import ScriptedProvider, create_run
from test_shipment_documents_vertical_slice import executing_order
from worker import tasks

pytest_plugins = ("test_quotation_vertical_slice",)


def snapshot(f):
    with f.session_factory() as session:
        return {
            model.__tablename__: list(
                session.execute(
                    select(*model.__table__.columns).order_by(*model.__table__.primary_key)
                )
            )
            for model in (
                AiRun,
                AiToolCall,
                AsyncJob,
                SalesOrder,
                SalesOrderItem,
                Document,
                DocumentVersion,
                Activity,
                AuditLog,
                OutboxEvent,
                ProcessedEvent,
            )
        }


def message(organization_id, run_id):
    return {
        "id": str(uuid4()),
        "organization_id": str(organization_id),
        "event_type": "ai.run_requested.v1",
        "aggregate_type": "ai_run",
        "aggregate_id": str(run_id),
        "payload": {},
        "correlation_id": str(uuid4()),
    }


@pytest.mark.parametrize("invalid", ["organization", "event_type", "context_uuid"])
def test_ai_worker_rejects_invalid_context_before_dependencies(monkeypatch, invalid):
    event = message(uuid4(), uuid4())
    context = {
        "organization_id": event["organization_id"],
        "request_id": event["correlation_id"],
    }
    if invalid == "organization":
        context["organization_id"] = str(uuid4())
    elif invalid == "event_type":
        event["event_type"] = "document.uploaded.v1"
    else:
        context["organization_id"] = "invalid-uuid"

    def forbidden(*args, **kwargs):
        pytest.fail("Rejected task must not initialize settings, database or provider")

    monkeypatch.setattr(tasks, "get_settings", forbidden)
    monkeypatch.setattr(tasks, "worker_session_factory", forbidden)
    monkeypatch.setattr(tasks, "configured_provider", forbidden)
    with pytest.raises(ValueError):
        tasks.execute_ai_run(context, event)


@pytest.mark.integration
def test_matching_foreign_event_cannot_execute_existing_ai_run(quotation_fixture, monkeypatch):
    f = quotation_fixture
    order = executing_order(f)
    created = create_run(f, order["id"])
    assert created.status_code == 202
    run_id = UUID(created.json()["id"])
    provider = ScriptedProvider(order["id"], tool="order_timeline")
    monkeypatch.setattr(tasks, "get_settings", Settings)
    monkeypatch.setattr(tasks, "worker_session_factory", lambda: f.session_factory)
    monkeypatch.setattr(tasks, "configured_provider", lambda settings: provider)

    before = snapshot(f)
    event = message(f.organization_b, run_id)
    context = {
        "organization_id": event["organization_id"],
        "request_id": event["correlation_id"],
    }
    with pytest.raises(ValueError, match="AI run not found in the event organization"):
        tasks.execute_ai_run(context, event)
    assert provider.calls == 0
    assert snapshot(f) == before


@pytest.mark.integration
@pytest.mark.parametrize("target", ["async_job", "scan_version", "scan_job"])
def test_event_handlers_reject_foreign_aggregate_without_receipt(
    quotation_fixture, monkeypatch, target
):
    """Synthetic worker-ready rows isolate each actual handler's tenant boundary."""
    f = quotation_fixture
    jobs, documents, versions = {}, {}, {}
    with f.session_factory.begin() as session:
        for organization in (f.organization_a, f.organization_b):
            job = AsyncJob(
                organization_id=organization, job_type="DOCUMENT_SCAN", correlation_id=uuid4()
            )
            document = Document(
                organization_id=organization,
                title="Synthetic worker evidence",
                document_type="OTHER",
            )
            session.add_all([job, document])
            session.flush()
            version = DocumentVersion(
                organization_id=organization,
                document_id=document.id,
                version_number=1,
                status="UPLOADED",
                object_key=f"{organization}/{uuid4()}",
                storage_version_id="synthetic-v1",
                file_name="worker.txt",
                mime_type="text/plain",
                expected_size_bytes=1,
                expected_sha256="a" * 64,
            )
            session.add(version)
            session.flush()
            jobs[organization], versions[organization] = job.id, version.id
            documents[organization] = document.id
        event = OutboxEvent(
            organization_id=f.organization_b,
            event_type="async_job.created.v1" if target == "async_job" else "document.uploaded.v1",
            aggregate_type="async_job" if target == "async_job" else "document",
            aggregate_id=(
                jobs[f.organization_a] if target == "async_job" else documents[f.organization_b]
            ),
            correlation_id=uuid4(),
            payload={
                "version_id": str(
                    versions[f.organization_a if target == "scan_version" else f.organization_b]
                ),
                "job_id": str(jobs[f.organization_a if target == "scan_job" else f.organization_b]),
            },
        )
        session.add(event)
        session.flush()
        event_message = outbox_message(event)

    monkeypatch.setattr(tasks, "worker_session_factory", lambda: f.session_factory)
    before = snapshot(f)
    with pytest.raises(ValueError, match="(event organization|expected organization and type)"):
        tasks.consume_outbox_event(
            {
                "organization_id": str(f.organization_b),
                "request_id": event_message["correlation_id"],
            },
            event_message,
        )
    assert snapshot(f) == before
