from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from app.ai.models import AiRun, ApprovalRequest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.observability import RequestMetrics
from app.platform.models import AsyncJob, OutboxEvent, ProcessedEvent
from app.platform.operations_queries import OperationsQuery
from app.work.models import Task

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
