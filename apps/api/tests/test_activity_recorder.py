import ast
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from app.auth.context import RequestContext
from app.crm.models import Lead
from app.platform.models import AuditLog, OutboxEvent
from app.work.models import Activity
from app.work.records import record_activity, record_system_activity
from sqlalchemy import func, select
from sqlalchemy.orm import Session

pytest_plugins = ("test_crm_vertical_slice",)


@pytest.mark.parametrize("system", [False, True])
def test_recorder_stages_exactly_one_row_without_query_flush_commit_or_release(system):
    organization_id, actor_id, correlation_id, subject_id = (uuid4() for _ in range(4))
    details = {"synthetic_cost": "123.4500", "nested": {"text": "原始证据"}}
    fields = dict(
        subject_type="synthetic",
        subject_id=subject_id,
        activity_type="synthetic.recorded",
        summary="未经审核的原始正文",
        details=details,
    )
    with Session() as session:
        if system:
            result = record_system_activity(
                session, organization_id=organization_id, correlation_id=correlation_id, **fields
            )
        else:
            # The internal evidence recorder must still work for a denied/revoked actor event.
            result = record_activity(
                session,
                RequestContext(actor_id, organization_id, frozenset(), correlation_id),
                **fields,
            )
        assert result is None and len(session.new) == 1 and not session.dirty
        row = next(iter(session.new))
        assert isinstance(row, Activity)
        assert row.id is None and row.occurred_at is None
        assert row.organization_id == organization_id and row.correlation_id == correlation_id
        assert row.created_by == row.updated_by == (None if system else actor_id)
        assert row.subject_type == "synthetic" and row.subject_id == subject_id
        assert row.activity_type == "synthetic.recorded" and row.summary == fields["summary"]
        assert row.details is details
        assert row.released_digest is row.reviewed_by is row.reviewed_at is None


@pytest.mark.integration
@pytest.mark.parametrize("system", [False, True])
def test_persisted_origin_timestamp_and_confidential_defaults(crm_fixture, system):
    f = crm_fixture
    correlation_id, subject_id = uuid4(), uuid4()
    before = datetime.now(UTC)
    with f.session_factory.begin() as session:
        fields = dict(
            subject_type="synthetic",
            subject_id=subject_id,
            activity_type="synthetic.recorded",
            summary="保留正文",
            details={"amount": "1.2500"},
        )
        if system:
            record_system_activity(
                session, organization_id=f.organization_a, correlation_id=correlation_id, **fields
            )
        else:
            record_activity(
                session,
                RequestContext(f.user_a, f.organization_a, frozenset(), correlation_id),
                **fields,
            )
    after = datetime.now(UTC)
    with f.session_factory() as session:
        row = session.scalar(select(Activity).where(Activity.organization_id == f.organization_a))
        assert before <= row.occurred_at <= after
        assert row.created_by == row.updated_by == (None if system else f.user_a)
        assert row.correlation_id == correlation_id and row.subject_id == subject_id
        assert row.summary == "保留正文" and row.details == {"amount": "1.2500"}
        assert row.released_digest is row.reviewed_by is row.reviewed_at is None
        assert (
            session.scalar(select(Activity.id).where(Activity.organization_id == f.organization_b))
            is None
        )
        assert session.scalar(select(func.count()).select_from(AuditLog)) == 0
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 0


@pytest.mark.integration
@pytest.mark.parametrize("system", [False, True])
def test_caller_failure_after_flush_rolls_back_business_and_activity(crm_fixture, system):
    f = crm_fixture
    correlation_id = uuid4()
    with pytest.raises(RuntimeError, match="caller failed"), f.session_factory.begin() as session:
        lead = Lead(organization_id=f.organization_a, company_name="Recorder rollback")
        session.add(lead)
        session.flush()
        fields = dict(
            subject_type="lead",
            subject_id=lead.id,
            activity_type="lead.created",
            summary="Rollback evidence",
            details={},
        )
        if system:
            record_system_activity(
                session, organization_id=f.organization_a, correlation_id=correlation_id, **fields
            )
        else:
            record_activity(
                session,
                RequestContext(f.user_a, f.organization_a, frozenset(), correlation_id),
                **fields,
            )
        session.flush()
        assert session.scalar(select(func.count()).select_from(Activity)) == 1
        raise RuntimeError("caller failed after evidence flush")
    with f.session_factory() as session:
        for model in (Lead, Activity, AuditLog, OutboxEvent):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_activity_construction_stays_in_work_recorder():
    root = Path(__file__).resolve().parents[1] / "app"
    violations = []
    for path in root.rglob("*.py"):
        if path == root / "work" / "records.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        names = {"Activity"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "app.work.models":
                names.update(
                    alias.asname or alias.name for alias in node.names if alias.name == "Activity"
                )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            direct = isinstance(node.func, ast.Name) and node.func.id in names
            qualified = isinstance(node.func, ast.Attribute) and node.func.attr == "Activity"
            if direct or qualified:
                violations.append(f"{path.relative_to(root)}:{node.lineno}")
    assert violations == []
