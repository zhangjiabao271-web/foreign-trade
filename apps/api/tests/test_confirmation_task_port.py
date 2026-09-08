from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.sales.confirmation_facts import procurement_preparation_source
from app.sales.models import SalesOrder, SalesOrderItem
from app.sales.order_enums import SalesOrderStatus
from app.sales.order_services import SalesOrderCommandService
from app.work.confirmation_tasks import stage_procurement_preparation
from app.work.models import Activity, Task
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from test_document_review import reviewer
from test_order_confirmation_commands import setup

pytest_plugins = ("test_quotation_vertical_slice",)


def snapshots(f):
    with f.session_factory() as session:
        return {
            model.__tablename__: list(
                session.execute(select(*model.__table__.columns).order_by(model.id))
            )
            for model in (
                SalesOrder,
                SalesOrderItem,
                Task,
                Activity,
                AuditLog,
                OutboxEvent,
                IdempotencyKey,
            )
        }


@pytest.mark.parametrize("source_only", [False, True])
def test_each_port_requires_confirmation_permission_before_database_access(source_only):
    context = RequestContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        request_id=uuid4(),
        permissions=frozenset(Permission) - {Permission.ORDER_CONFIRM},
    )
    with Session() as session:
        with pytest.raises(ApiProblem) as error:
            if source_only:
                procurement_preparation_source(session, context, uuid4())
            else:
                stage_procurement_preparation(session, context, order_id=uuid4())
        assert error.value.code == "PERMISSION_DENIED"
        assert not session.new and not session.dirty and not session.in_transaction()


@pytest.mark.integration
@pytest.mark.parametrize("deposit", ["0", "0.3"])
def test_confirmation_task_retains_exact_fields_and_evidence(quotation_fixture, deposit):
    f = quotation_fixture
    order_id, request = setup(f, deposit)
    _, original = reviewer(f)
    context = replace(original, permissions=frozenset({Permission.ORDER_CONFIRM}))
    before = snapshots(f)
    service = SalesOrderCommandService(f.session_factory)
    result = service.confirm(context, order_id, request, key="owner-task")
    with f.session_factory() as session:
        task = session.scalar(
            select(Task).where(
                Task.organization_id == f.organization_a,
                Task.subject_id == order_id,
            )
        )
        assert task.task_type == "PROCUREMENT_PREPARATION"
        assert task.subject_type == "sales_order"
        assert task.title == f"Prepare procurement for {result.order_number}"
        assert task.status == "OPEN" and task.priority == "HIGH"
        assert task.due_at == result.confirmed_at + timedelta(days=2)
        assert task.details == {
            "order_number": result.order_number,
            "deposit_pending": deposit != "0",
        }
        assert task.created_by == task.updated_by == context.user_id
        assert task.assigned_to is None and task.reviewed_by is None
    after = snapshots(f)
    assert after["sales_order_items"] == before["sales_order_items"]
    for table in ("tasks", "activities", "audit_logs", "outbox_events", "idempotency_keys"):
        assert len(after[table]) == len(before[table]) + 1
    assert service.confirm(context, order_id, request, key="owner-task") == result
    assert snapshots(f) == after


@pytest.mark.integration
def test_port_rejects_foreign_missing_and_deleted_orders_without_staging(quotation_fixture):
    f = quotation_fixture
    order_id, _ = setup(f)
    _, context = reviewer(f)
    before = snapshots(f)
    for ctx, target in (
        (replace(context, organization_id=f.organization_b), order_id),
        (context, uuid4()),
    ):
        with f.session_factory() as session:
            with pytest.raises(ApiProblem) as error:
                stage_procurement_preparation(session, ctx, order_id=target)
            assert error.value.status == 404
            assert not session.new and not session.dirty
        assert snapshots(f) == before
    with f.session_factory.begin() as session:
        session.get(SalesOrder, order_id).deleted_at = datetime.now(UTC)
    before = snapshots(f)
    with f.session_factory() as session:
        with pytest.raises(ApiProblem) as error:
            stage_procurement_preparation(session, context, order_id=order_id)
        assert error.value.status == 404
        assert not session.new and not session.dirty
    assert snapshots(f) == before


@pytest.mark.integration
def test_port_requires_both_confirmation_timestamp_and_allowed_state(quotation_fixture):
    f = quotation_fixture
    order_id, _ = setup(f)
    _, context = reviewer(f)
    before = snapshots(f)
    for state in SalesOrderStatus:
        for confirmed_at in (None, datetime.now(UTC)):
            allowed = confirmed_at is not None and state in {"DEPOSIT_PENDING", "EXECUTING"}
            if allowed:
                continue
            with f.session_factory() as session:
                order = session.get(SalesOrder, order_id)
                order.status, order.confirmed_at = state, confirmed_at
                with pytest.raises(ApiProblem) as error:
                    stage_procurement_preparation(session, context, order_id=order_id)
                assert error.value.code == "INVALID_STATE_TRANSITION"
                assert not session.new
            assert snapshots(f) == before


@pytest.mark.integration
@pytest.mark.parametrize("flush", [False, True])
def test_caller_failure_after_work_port_rolls_back_entire_confirmation(
    quotation_fixture, monkeypatch, flush
):
    f = quotation_fixture
    order_id, request = setup(f)
    _, context = reviewer(f)
    before = snapshots(f)
    calls = []

    def fail_after_stage(session, ctx, *, order_id):
        statements = []

        def capture(_conn, _cursor, statement, *_args):
            statements.append(statement.strip().lower())

        event.listen(f.engine, "before_cursor_execute", capture)
        try:
            stage_procurement_preparation(session, ctx, order_id=order_id)
        finally:
            event.remove(f.engine, "before_cursor_execute", capture)
        # Source lookup may re-lock the caller's order, but must not flush its pending mutation.
        assert statements and all(statement.startswith("select") for statement in statements)
        assert len([item for item in session.new if isinstance(item, Task)]) == 1
        calls.append(order_id)
        if flush:
            session.flush()
            assert session.scalar(select(Task.id).where(Task.subject_id == order_id)) is not None
        raise RuntimeError("caller failed after Work staged task")

    monkeypatch.setattr("app.sales.order_services.stage_procurement_preparation", fail_after_stage)
    with pytest.raises(RuntimeError, match="caller failed after Work"):
        SalesOrderCommandService(f.session_factory).confirm(
            context, order_id, request, key="rollback-owner-task"
        )
    assert calls == [order_id]
    assert snapshots(f) == before
