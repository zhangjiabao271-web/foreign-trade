from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from app.ai.models import AiRun, ApprovalRequest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.observability import RequestMetrics
from app.documents.models import Document, DocumentVersion
from app.platform.models import AsyncJob, OutboxEvent, ProcessedEvent
from app.platform.operations_queries import OperationsQuery
from app.work.models import Task
from sqlalchemy import event, select, text

pytestmark = pytest.mark.integration
pytest_plugins = ("test_identity_administration",)


def seed(f, organization_id, multiplier):
    with f.session_factory.begin() as session:
        events = [
            OutboxEvent(
                organization_id=organization_id,
                event_type="fixture.observed.v1",
                aggregate_type="fixture",
                aggregate_id=uuid4(),
                correlation_id=uuid4(),
                status=status,
                created_at=datetime.now(UTC) - timedelta(minutes=10),
            )
            for status in ["PENDING", "PUBLISHED", "PUBLISHED", "DEAD"]
        ]
        session.add_all(events)
        session.flush()
        session.add(
            ProcessedEvent(
                organization_id=organization_id,
                event_id=events[1].id,
                consumer_name="worker.fixture.observed.v1",
            )
        )
        for index in range(multiplier):
            job = AsyncJob(
                organization_id=organization_id,
                job_type="fixture",
                status="FAILED",
                correlation_id=uuid4(),
            )
            session.add(job)
            session.flush()
            run = AiRun(
                organization_id=organization_id,
                job_id=job.id,
                intent="TASK_DRAFT",
                model="fixture",
                prompt_version="1",
                status="FAILED",
                input_tokens=10,
                output_tokens=5,
                estimated_cost_usd=Decimal("0.25") if index == 0 else None,
            )
            session.add(run)
            session.flush()
            task = Task(
                organization_id=organization_id,
                task_type="fixture",
                subject_type="fixture",
                subject_id=uuid4(),
                title="Fixture",
                status="OPEN",
                priority="NORMAL",
            )
            session.add(task)
            session.flush()
            session.add(
                ApprovalRequest(
                    organization_id=organization_id,
                    run_id=run.id,
                    proposed_action={},
                    status="APPROVED" if index == 0 else "REJECTED",
                    task_id=task.id if index == 0 else None,
                )
            )


def test_operational_totals_are_tenant_scoped_and_unknown_cost_is_explicit(admin):
    f, context, _ = admin
    seed(f, f.organization_a, 2)
    seed(f, f.organization_b, 3)
    with f.session_factory() as session:
        response = OperationsQuery(session, RequestMetrics()).read(context)
        assert response.outbox_states == {"PENDING": 1, "PUBLISHED": 2, "DEAD": 1}
        assert response.awaiting_consumer_count == 2
        assert response.oldest_awaiting_seconds >= 599
        assert response.ai_input_tokens == 20 and response.ai_output_tokens == 10
        assert response.known_estimated_cost_usd == Decimal("0.25")
        assert response.unknown_cost_runs == 1
        assert response.approval_rate == Decimal("0.5")
        assert response.job_states == {"FAILED": 2}
        assert response.request_metrics is None
        denied = RequestContext(context.user_id, context.organization_id, frozenset(), uuid4())
        with pytest.raises(ApiProblem) as error:
            OperationsQuery(session).read(denied)
        assert error.value.status == 403


def test_empty_metrics_are_not_fabricated_zero_cost_acceptance(admin):
    f, context, _ = admin
    with f.session_factory() as session:
        response = OperationsQuery(session, RequestMetrics()).read(context)
        assert response.approval_rate is None
        assert response.oldest_awaiting_seconds is None
        assert response.request_metrics is None
    headers = f.headers("identity-admin", f.organization_a)
    response = f.client.get("/api/v1/operations", headers=headers)
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store"
    for subject in (
        "quotation-sales",
        "quotation-manager",
        "quotation-finance",
        "quotation-operations",
    ):
        assert (
            f.client.get(
                "/api/v1/operations", headers=f.headers(subject, f.organization_a)
            ).status_code
            == 403
        )
    assert f.client.get("/api/v1/operations").status_code == 401
    assert Permission.OPERATIONS_MONITOR in context.permissions


def test_all_document_states_are_nonempty_tenant_scoped_and_read_only(admin):
    f, context, _ = admin
    states = ("PENDING_UPLOAD", "UPLOADED", "SCANNING", "AVAILABLE", "REJECTED")
    with f.session_factory.begin() as session:
        for organization, copies in ((f.organization_a, 1), (f.organization_b, 3)):
            document = Document(
                organization_id=organization, title="Synthetic monitoring", document_type="OTHER"
            )
            session.add(document)
            session.flush()
            for number, status in enumerate(states * copies, start=1):
                session.add(
                    DocumentVersion(
                        organization_id=organization,
                        document_id=document.id,
                        version_number=number,
                        status=status,
                        object_key=f"synthetic/{uuid4()}",
                        file_name="synthetic.txt",
                        mime_type="text/plain",
                        expected_size_bytes=1,
                        expected_sha256="a" * 64,
                    )
                )
            session.add(
                DocumentVersion(
                    organization_id=organization,
                    document_id=document.id,
                    version_number=len(states) * copies + 1,
                    status="REJECTED",
                    object_key=f"synthetic/{uuid4()}",
                    file_name="deleted.txt",
                    mime_type="text/plain",
                    expected_size_bytes=1,
                    expected_sha256="b" * 64,
                    deleted_at=datetime.now(UTC),
                )
            )

    # PostgreSQL itself rejects accidental writes, including audit/outbox writes.
    with f.session_factory.begin() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        response = OperationsQuery(session, RequestMetrics()).read(context)
        assert response.document_states == dict.fromkeys(states, 1)
        foreign = RequestContext(context.user_id, f.organization_b, context.permissions, uuid4())
        assert OperationsQuery(session, RequestMetrics()).read(
            foreign
        ).document_states == dict.fromkeys(states, 3)


def test_soft_deleted_jobs_runs_and_approvals_do_not_contribute(admin):
    f, context, _ = admin
    seed(f, f.organization_a, 2)
    seed(f, f.organization_b, 3)
    with f.session_factory.begin() as session:
        run = session.scalar(
            select(AiRun).where(
                AiRun.organization_id == f.organization_a,
                AiRun.estimated_cost_usd.is_not(None),
            )
        )
        job = session.scalar(
            select(AsyncJob).where(
                AsyncJob.organization_id == f.organization_a,
                AsyncJob.id == run.job_id,
            )
        )
        approval = session.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.organization_id == f.organization_a,
                ApprovalRequest.run_id == run.id,
            )
        )
        for row in (run, job, approval):
            row.deleted_at = datetime.now(UTC)
    with f.session_factory.begin() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        response = OperationsQuery(session, RequestMetrics()).read(context)
        assert response.job_states == {"FAILED": 1}
        assert response.ai_run_states == {"FAILED": 1}
        assert response.approval_states == {"REJECTED": 1}
        assert response.approval_rate == Decimal("0")
        assert response.known_estimated_cost_usd == Decimal("0")
        assert response.unknown_cost_runs == 1
        assert response.ai_input_tokens == 10 and response.ai_output_tokens == 5


def test_only_intended_receipts_remove_pending_work_and_age_is_nonnegative(admin):
    f, context, _ = admin
    seed(f, f.organization_a, 2)
    with f.session_factory.begin() as session:
        events = list(
            session.scalars(
                select(OutboxEvent).where(
                    OutboxEvent.organization_id == f.organization_a,
                )
            )
        )
        pending = next(row for row in events if row.status == "PENDING")
        pending.status = "PROCESSING"
        pending.created_at = datetime.now(UTC) + timedelta(minutes=10)
        session.add(
            ProcessedEvent(
                organization_id=f.organization_a,
                event_id=pending.id,
                consumer_name="unrelated.consumer",
            )
        )
        for row in events:
            if row.status == "PUBLISHED":
                row.deleted_at = datetime.now(UTC)
    with f.session_factory.begin() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        response = OperationsQuery(session, RequestMetrics()).read(context)
        assert response.outbox_states == {"PROCESSING": 1, "DEAD": 1}
        assert response.awaiting_consumer_count == 1
        assert response.oldest_awaiting_seconds == 0
    with f.session_factory.begin() as session:
        session.add(
            ProcessedEvent(
                organization_id=f.organization_a,
                event_id=pending.id,
                consumer_name="worker.fixture.observed.v1",
            )
        )
    with f.session_factory.begin() as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        response = OperationsQuery(session, RequestMetrics()).read(context)
        assert response.awaiting_consumer_count == 0
        assert response.oldest_awaiting_seconds is None
        assert response.outbox_states == {"PROCESSING": 1, "DEAD": 1}


def test_monitor_permission_rejection_precedes_database_read(admin):
    f, context, _ = admin
    statements = []

    def record(conn, cursor, statement, parameters, execution_context, executemany):
        statements.append(statement)

    denied = RequestContext(context.user_id, context.organization_id, frozenset(), uuid4())
    event.listen(f.engine, "before_cursor_execute", record)
    try:
        with f.session_factory() as session:
            with pytest.raises(ApiProblem) as error:
                OperationsQuery(session, RequestMetrics()).read(denied)
            assert error.value.code == "PERMISSION_DENIED"
        assert statements == []
    finally:
        event.remove(f.engine, "before_cursor_execute", record)


def test_nonempty_job_ai_and_approval_state_matrix_keeps_pending_out_of_rate(admin):
    f, context, _ = admin
    job_states = ("PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED")
    run_states = ("PENDING", "RUNNING", "SUCCEEDED", "FAILED")
    with f.session_factory.begin() as session:
        for organization, copies in ((f.organization_a, 1), (f.organization_b, 2)):
            for _ in range(copies):
                # Deliberate query fixtures, not evidence of legal lifecycle transitions.
                for index, status in enumerate(job_states):
                    job = AsyncJob(
                        organization_id=organization,
                        job_type="fixture",
                        status=status,
                        correlation_id=uuid4(),
                    )
                    session.add(job)
                    session.flush()
                    if index < len(run_states):
                        session.add(
                            AiRun(
                                organization_id=organization,
                                job_id=job.id,
                                intent="TASK_DRAFT",
                                model="fixture",
                                prompt_version="1",
                                status=run_states[index],
                                input_tokens=10,
                                output_tokens=5,
                                estimated_cost_usd=Decimal("0.12345678"),
                            )
                        )
                for status in ("PENDING", "APPROVED", "REJECTED"):
                    job = AsyncJob(
                        organization_id=organization,
                        job_type="fixture",
                        status="SUCCEEDED",
                        correlation_id=uuid4(),
                    )
                    session.add(job)
                    session.flush()
                    run = AiRun(
                        organization_id=organization,
                        job_id=job.id,
                        intent="TASK_DRAFT",
                        model="fixture",
                        prompt_version="1",
                        status="SUCCEEDED",
                        estimated_cost_usd=None,
                    )
                    session.add(run)
                    session.flush()
                    task_id = None
                    if status == "APPROVED":
                        task = Task(
                            organization_id=organization,
                            task_type="fixture",
                            subject_type="fixture",
                            subject_id=uuid4(),
                            title="Synthetic accepted task",
                            status="OPEN",
                            priority="NORMAL",
                        )
                        session.add(task)
                        session.flush()
                        task_id = task.id
                    session.add(
                        ApprovalRequest(
                            organization_id=organization,
                            run_id=run.id,
                            status=status,
                            proposed_action={},
                            task_id=task_id,
                        )
                    )

    for organization, copies in ((f.organization_a, 1), (f.organization_b, 2)):
        selected = RequestContext(context.user_id, organization, context.permissions, uuid4())
        with f.session_factory.begin() as session:
            session.execute(text("SET TRANSACTION READ ONLY"))
            response = OperationsQuery(session, RequestMetrics()).read(selected)
            expected_jobs = dict.fromkeys(job_states, copies)
            expected_jobs["SUCCEEDED"] = copies * 4
            expected_runs = dict.fromkeys(run_states, copies)
            expected_runs["SUCCEEDED"] = copies * 4
            assert response.job_states == expected_jobs
            assert response.ai_run_states == expected_runs
            assert response.approval_states == dict.fromkeys(
                ("PENDING", "APPROVED", "REJECTED"), copies
            )
            assert response.approval_rate == Decimal("0.5")
            assert response.known_estimated_cost_usd == Decimal("0.49382712") * copies
            assert response.unknown_cost_runs == copies * 3
            assert response.ai_input_tokens == copies * 40
            assert response.ai_output_tokens == copies * 20
