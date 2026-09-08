from dataclasses import replace
from decimal import Decimal
from uuid import uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.platform.domain_jobs import (
    bind_ai_run,
    complete_document_scan_job,
    create_ai_job,
    create_document_scan_job,
    finish_ai_attempt,
    lock_document_scan_job,
    start_ai_attempt,
)
from app.platform.models import AsyncJob, AuditLog, OutboxEvent
from app.work.models import Activity
from sqlalchemy import select
from sqlalchemy.orm import Session

pytest_plugins = ("test_crm_vertical_slice",)


def context(f):
    return RequestContext(f.user_a, f.organization_a, frozenset(Permission), uuid4())


def snapshot(f):
    with f.session_factory() as session:
        return {
            model.__tablename__: list(
                session.execute(select(*model.__table__.columns).order_by(model.id))
            )
            for model in (AsyncJob, Activity, AuditLog, OutboxEvent)
        }


@pytest.mark.parametrize("operation", ["create_ai", "create_scan", "bind_ai"])
def test_request_job_ports_require_originating_authority_before_database_access(operation):
    permission = Permission.DOCUMENT_WRITE if operation == "create_scan" else Permission.AI_RUN
    ctx = RequestContext(uuid4(), uuid4(), frozenset(Permission) - {permission}, uuid4())
    with Session() as session:
        with pytest.raises(ApiProblem) as error:
            if operation == "create_ai":
                create_ai_job(session, ctx)
            elif operation == "create_scan":
                create_document_scan_job(session, ctx)
            else:
                bind_ai_run(session, ctx, job_id=uuid4(), run_id=uuid4())
        assert error.value.code == "PERMISSION_DENIED"
        assert not session.new and not session.dirty and not session.in_transaction()


@pytest.mark.integration
@pytest.mark.parametrize("kind", ["AI_COPILOT", "DOCUMENT_SCAN"])
def test_creation_preserves_defaults_and_joins_caller_transaction(crm_fixture, kind):
    f = crm_fixture
    ctx = context(f)
    creator = create_ai_job if kind == "AI_COPILOT" else create_document_scan_job
    required = Permission.AI_RUN if kind == "AI_COPILOT" else Permission.DOCUMENT_WRITE
    before = snapshot(f)
    with pytest.raises(RuntimeError, match="caller failed"), f.session_factory.begin() as session:
        job_id = creator(session, replace(ctx, permissions=frozenset({required})))
        job = session.get(AsyncJob, job_id)
        assert job.job_type == kind and job.organization_id == f.organization_a
        assert job.status == "PENDING" and job.progress == 0
        assert job.attempt_count == 0 and job.max_attempts == 3
        assert job.created_by == job.updated_by == ctx.user_id
        assert job.correlation_id == ctx.request_id
        assert job.result_reference is job.error_code is None
        raise RuntimeError("caller failed after job flush")
    assert snapshot(f) == before


def mutate(session, ctx, job_id, operation):
    if operation == "bind_ai":
        bind_ai_run(session, ctx, job_id=job_id, run_id=uuid4())
    elif operation == "start_ai":
        start_ai_attempt(
            session, organization_id=ctx.organization_id, job_id=job_id, attempt_count=1
        )
    elif operation == "finish_ai":
        finish_ai_attempt(
            session,
            organization_id=ctx.organization_id,
            job_id=job_id,
            attempt_count=1,
            error_code="PERMISSION_DENIED",
            retryable=False,
        )
    elif operation == "lock_scan":
        lock_document_scan_job(session, organization_id=ctx.organization_id, job_id=job_id)
    else:
        complete_document_scan_job(
            session, organization_id=ctx.organization_id, job_id=job_id, version_id=uuid4()
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    "operation", ["bind_ai", "start_ai", "finish_ai", "lock_scan", "finish_scan"]
)
def test_lifecycle_guards_tenant_and_type_and_caller_rollback(crm_fixture, operation):
    f = crm_fixture
    ctx = context(f)
    expected_type = "DOCUMENT_SCAN" if "scan" in operation else "AI_COPILOT"
    with f.session_factory.begin() as session:
        ai_id = create_ai_job(session, ctx)
        scan_id = create_document_scan_job(session, ctx)
    valid_id = scan_id if expected_type == "DOCUMENT_SCAN" else ai_id
    other_id = ai_id if expected_type == "DOCUMENT_SCAN" else scan_id
    before = snapshot(f)
    for caller, target in (
        (replace(ctx, organization_id=f.organization_b), valid_id),
        (ctx, other_id),
        (ctx, uuid4()),
    ):
        with f.session_factory() as session:
            with pytest.raises(ValueError, match="expected organization and type"):
                mutate(session, caller, target, operation)
            assert not session.new and not session.dirty
        assert snapshot(f) == before
    with pytest.raises(RuntimeError, match="caller rollback"), f.session_factory.begin() as session:
        mutate(session, ctx, valid_id, operation)
        session.flush()
        raise RuntimeError("caller rollback after owner flush")
    assert snapshot(f) == before


@pytest.mark.integration
def test_ai_retry_limit_success_and_permission_failure_remain_recordable(crm_fixture):
    f = crm_fixture
    ctx = context(f)
    with f.session_factory.begin() as session:
        job_id = create_ai_job(session, ctx)
        run_id = uuid4()
        bind_ai_run(session, ctx, job_id=job_id, run_id=run_id)
    for attempt in (1, 2, 3):
        with f.session_factory.begin() as session:
            maximum = start_ai_attempt(
                session, organization_id=f.organization_a, job_id=job_id, attempt_count=attempt
            )
            assert maximum == 3
            outcome = finish_ai_attempt(
                session,
                organization_id=f.organization_a,
                job_id=job_id,
                attempt_count=attempt,
                error_code="AI_PROVIDER_UNAVAILABLE",
                retryable=True,
            )
            assert outcome.retry is (attempt < 3)
            assert outcome.status == ("PENDING" if attempt < 3 else "FAILED")
        with f.session_factory() as session:
            job = session.get(AsyncJob, job_id)
            assert job.attempt_count == attempt and job.status == outcome.status
            assert job.progress == (0 if outcome.retry else 100)
            assert job.error_code == "AI_PROVIDER_UNAVAILABLE"
            assert job.result_reference == f"ai-run:{run_id}"
    for error in (None, "PERMISSION_DENIED"):
        with f.session_factory.begin() as session:
            target = create_ai_job(session, ctx)
            start_ai_attempt(
                session, organization_id=f.organization_a, job_id=target, attempt_count=1
            )
            outcome = finish_ai_attempt(
                session,
                organization_id=f.organization_a,
                job_id=target,
                attempt_count=1,
                error_code=error,
                retryable=False,
            )
            assert not outcome.retry
            assert outcome.status == ("FAILED" if error else "SUCCEEDED")
            job = session.get(AsyncJob, target)
            assert job.progress == Decimal(100) and job.error_code == error
    after = snapshot(f)
    assert after["activities"] == after["audit_logs"] == after["outbox_events"] == []


@pytest.mark.integration
def test_scan_success_preserves_original_reference_and_attempt_fields(crm_fixture):
    f = crm_fixture
    with f.session_factory.begin() as session:
        job_id = create_document_scan_job(session, context(f))
        version_id = uuid4()
        lock_document_scan_job(session, organization_id=f.organization_a, job_id=job_id)
        complete_document_scan_job(
            session, organization_id=f.organization_a, job_id=job_id, version_id=version_id
        )
    with f.session_factory() as session:
        job = session.get(AsyncJob, job_id)
        assert job.status == "SUCCEEDED" and job.progress == 100
        assert job.result_reference == f"document-version:{version_id}"
        assert job.attempt_count == 0 and job.error_code is None
