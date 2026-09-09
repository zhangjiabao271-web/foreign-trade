from dataclasses import replace

import pytest
from app.auth.errors import ApiProblem
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.sales.models import SalesOrder, SalesOrderItem
from app.work.models import Activity, Task
from app.work.review import WorkReviewService
from app.work.schemas import TaskComplete
from app.work.services import TaskCommandService, WorkQueryService
from sqlalchemy import event, select
from test_document_review import reviewer
from test_work_review import decision, seed

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def snapshot(f):
    with f.session_factory() as session:
        return {
            model.__tablename__: list(session.execute(select(model.__table__).order_by(model.id)))
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


def test_stale_task_completion_preserves_original_facts(quotation_fixture):
    f = quotation_fixture
    order_id, task_id = seed(f, "task")
    subject, context = reviewer(f)
    with f.session_factory.begin() as session:
        row = session.get(Task, task_id)
        version = row.version
        row.title = "Revised task after the page opened"
        session.flush()
        assert row.version == version + 1
    request = TaskComplete(expected_version=version, resolution="Stale completion")
    before = snapshot(f)
    response = f.client.post(
        f"/api/v1/sales-orders/{order_id}/tasks/{task_id}/complete",
        headers=f.headers(subject, f.organization_a),
        json=request.model_dump(),
    )
    assert response.status_code == 409
    assert response.json()["code"] == "VERSION_CONFLICT"
    with pytest.raises(ApiProblem) as stale:
        TaskCommandService(f.session_factory).complete_order_task(
            context, order_id, task_id, request
        )
    assert stale.value.code == "VERSION_CONFLICT"
    assert snapshot(f) == before


@pytest.mark.parametrize("role", list(MembershipRole))
@pytest.mark.parametrize("state", ["OPEN", "IN_PROGRESS", "DONE", "CANCELLED"])
def test_task_completion_role_state_and_service_replay(quotation_fixture, role, state):
    f = quotation_fixture
    order_id, task_id = seed(f, "task")
    subject, context = reviewer(f, role)
    with f.session_factory.begin() as session:
        row = session.get(Task, task_id)
        # Isolate every accepted stored state; normal OPEN -> DONE has a vertical test.
        row.status = state
        session.flush()
        request = TaskComplete(expected_version=row.version, resolution="Synthetic completion")
    path = f"/api/v1/sales-orders/{order_id}/tasks/{task_id}/complete"
    headers = f.headers(subject, f.organization_a)
    service = TaskCommandService(f.session_factory)
    before = snapshot(f)
    response = f.client.post(path, headers=headers, json=request.model_dump())
    error = None
    if role == MembershipRole.VIEWER:
        error = "PERMISSION_DENIED"
    elif state == "CANCELLED":
        error = "INVALID_STATE_TRANSITION"
    if error:
        assert response.status_code == (403 if role == MembershipRole.VIEWER else 409)
        assert response.json()["code"] == error
        with pytest.raises(ApiProblem) as denied:
            service.complete_order_task(context, order_id, task_id, request)
        assert denied.value.code == error
        assert snapshot(f) == before
        return
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "DONE"
    after = snapshot(f)
    if state == "DONE":
        assert after == before
    else:
        for table in ("activities", "audit_logs", "outbox_events"):
            assert len(after[table]) == len(before[table]) + 1
        with f.session_factory() as session:
            row = session.get(Task, task_id)
            assert row.details["resolution"] == request.resolution
            assert row.updated_by == context.user_id
        assert after["sales_orders"] == before["sales_orders"]
        assert after["sales_order_items"] == before["sales_order_items"]
    assert f.client.post(path, headers=headers, json=request.model_dump()).json() == response.json()
    assert service.complete_order_task(context, order_id, task_id, request).id == task_id
    assert snapshot(f) == after


@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
def test_task_completion_rolls_back_after_each_evidence_insert(quotation_fixture, table):
    f = quotation_fixture
    order_id, task_id = seed(f, "task")
    _, context = reviewer(f)
    with f.session_factory() as session:
        request = TaskComplete(
            expected_version=session.get(Task, task_id).version, resolution="Atomic completion"
        )
    service = TaskCommandService(f.session_factory)
    before = snapshot(f)
    inserted = []

    def fail_after_insert(_connection, _cursor, statement, *_args):
        if statement.lstrip().lower().startswith(f"insert into {table} "):
            inserted.append(table)
            raise RuntimeError("injected completion evidence failure")

    event.listen(f.engine, "after_cursor_execute", fail_after_insert)
    try:
        with pytest.raises(RuntimeError, match="injected completion evidence failure"):
            service.complete_order_task(context, order_id, task_id, request)
    finally:
        event.remove(f.engine, "after_cursor_execute", fail_after_insert)
    assert inserted == [table]
    assert snapshot(f) == before
    result = service.complete_order_task(context, order_id, task_id, request)
    assert result.status == "DONE"
    after = snapshot(f)
    assert service.complete_order_task(context, order_id, task_id, request) == result
    assert snapshot(f) == after


@pytest.mark.parametrize("kind", ["task", "activity"])
def test_work_order_paths_foreign_manager_rejected_without_writes(quotation_fixture, kind):
    f = quotation_fixture
    order_id, record_id = seed(f, kind)
    subject, context = reviewer(f)
    with f.session_factory.begin() as session:
        session.add(
            OrganizationMembership(
                organization_id=f.organization_b,
                user_id=context.user_id,
                role="MANAGER",
                status="ACTIVE",
            )
        )
    foreign = replace(context, organization_id=f.organization_b)
    headers = f.headers(subject, f.organization_b)
    assert f.client.get("/api/v1/me/context", headers=headers).status_code == 200
    service = WorkReviewService(f.session_factory)
    request = decision(service.inspect(context, order_id, kind, record_id))
    parent = f"/api/v1/sales-orders/{order_id}"
    review_path = parent + f"/work/{kind}/{record_id}/review"
    before = snapshot(f)
    for path in (
        parent + "/tasks",
        parent + "/activities",
        parent + "/activity-history",
        review_path,
    ):
        assert f.client.get(path, headers=headers).status_code == 404
        assert snapshot(f) == before
    response = f.client.post(
        review_path, headers=headers | {"Idempotency-Key": "foreign"}, json=request.model_dump()
    )
    assert response.status_code == 404
    with pytest.raises(ApiProblem) as missing:
        service.decide(foreign, order_id, kind, record_id, request, key="foreign")
    assert missing.value.status == 404
    if kind == "task":
        complete = TaskComplete(
            expected_version=request.expected_version, resolution="Foreign completion"
        )
        assert (
            f.client.post(
                parent + f"/tasks/{record_id}/complete", headers=headers, json=complete.model_dump()
            ).status_code
            == 404
        )
        with pytest.raises(ApiProblem) as missing:
            TaskCommandService(f.session_factory).complete_order_task(
                foreign, order_id, record_id, complete
            )
        assert missing.value.status == 404
    with f.session_factory() as session:
        query = WorkQueryService(session)
        for read in (
            lambda: query.order_tasks(foreign, order_id),
            lambda: query.order_activities(foreign, order_id, 20),
            lambda: query.commercial_activities(
                foreign, "sales_order", order_id, cursor=None, limit=20
            ),
        ):
            with pytest.raises(ApiProblem) as missing:
                read()
            assert missing.value.status == 404
    assert snapshot(f) == before
