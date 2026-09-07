from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import permissions_for_role
from app.identity.enums import MembershipRole
from app.platform.models import AuditLog, OutboxEvent
from app.work.models import Activity, Task
from app.work.review import WorkReviewRequest, WorkReviewService
from app.work.schemas import TaskComplete
from app.work.services import TaskCommandService, WorkQueryService
from sqlalchemy import event
from test_document_review import counts, reviewer
from test_shipment_documents_vertical_slice import executing_order

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def seed(f, kind):
    order_id = UUID(executing_order(f)["id"])
    with f.session_factory.begin() as session:
        common = dict(
            organization_id=f.organization_a,
            subject_type="sales_order",
            subject_id=order_id,
            details={"nested": {"note": "cost 350"}},
        )
        if kind == "task":
            row = Task(**common, task_type="REVIEW_FIXTURE", title="Internal cost 350")
        else:
            row = Activity(
                **common,
                activity_type="fixture.noted",
                summary="Internal cost 350",
                correlation_id=uuid4(),
            )
        session.add(row)
        session.flush()
        return order_id, row.id


def decision(snapshot, release=True):
    return WorkReviewRequest(
        expected_version=snapshot.version,
        content_digest=snapshot.content_digest,
        release=release,
        confirmed=True,
        reason="Exact text reviewed",
    )


@pytest.mark.parametrize("kind", ["task", "activity"])
@pytest.mark.parametrize("role", list(MembershipRole))
def test_work_text_role_service_http_and_release(quotation_fixture, kind, role):
    f = quotation_fixture
    order_id, record_id = seed(f, kind)
    subject, context = reviewer(f, role)
    privileged = role in {MembershipRole.ADMIN, MembershipRole.MANAGER, MembershipRole.FINANCE}
    collection = "tasks" if kind == "task" else "activities"
    field = "title" if kind == "task" else "summary"
    path = f"/api/v1/sales-orders/{order_id}"
    headers = f.headers(subject, f.organization_a)
    response = f.client.get(f"{path}/{collection}", headers=headers)
    assert response.status_code == 200, response.text
    item = next(row for row in response.json()["items"] if row["id"] == str(record_id))
    assert item[field] == ("Internal cost 350" if privileged else None)
    assert item["details"] == ({"nested": {"note": "cost 350"}} if privileged else {})
    assert item["content_visible"] is privileged
    with f.session_factory() as session:
        query = WorkQueryService(session)
        rows = (
            query.order_tasks(context, order_id)
            if kind == "task"
            else query.order_activities(context, order_id, 100)
        )
        assert next(row for row in rows if row.id == record_id).model_dump(mode="json") == item
        assert not session.dirty
    review_path = f"{path}/work/{kind}/{record_id}/review"
    before = counts(f)
    service = WorkReviewService(f.session_factory)
    if not privileged:
        assert f.client.get(review_path, headers=headers).status_code == 403
        denied_request = WorkReviewRequest(
            expected_version=1,
            content_digest="a" * 64,
            release=True,
            confirmed=True,
            reason="Unauthorized release",
        )
        assert (
            f.client.post(
                review_path,
                headers=headers | {"Idempotency-Key": "denied"},
                json=denied_request.model_dump(),
            ).status_code
            == 403
        )
        with pytest.raises(ApiProblem) as denied:
            service.inspect(context, order_id, kind, record_id)
        assert denied.value.status == 403
        with pytest.raises(ApiProblem) as denied:
            service.decide(context, order_id, kind, record_id, denied_request, key="denied")
        assert denied.value.status == 403
        assert counts(f) == before
        return
    opened = service.inspect(context, order_id, kind, record_id)
    assert opened.text == "Internal cost 350"
    request = decision(opened)
    headers |= {"Idempotency-Key": "review"}
    result = f.client.post(review_path, headers=headers, json=request.model_dump())
    assert result.status_code == 200, result.text
    assert result.json()["released"]
    assert result.json()["version"] == opened.version + 1
    assert counts(f) == [number + 1 for number in before]
    assert (
        f.client.post(review_path, headers=headers, json=request.model_dump()).json()
        == result.json()
    )
    assert counts(f) == [number + 1 for number in before]
    low = replace(context, permissions=permissions_for_role(MembershipRole.SALES))
    with f.session_factory() as session:
        query = WorkQueryService(session)
        rows = (
            query.order_tasks(low, order_id)
            if kind == "task"
            else query.order_activities(low, order_id, 100)
        )
        assert next(row for row in rows if row.id == record_id).content_visible
    with pytest.raises(ApiProblem) as foreign:
        service.inspect(
            replace(context, organization_id=f.organization_b), order_id, kind, record_id
        )
    assert foreign.value.status == 404


@pytest.mark.parametrize("kind", ["task", "activity"])
def test_work_release_revocation_and_content_version_invalidation(quotation_fixture, kind):
    f = quotation_fixture
    order_id, record_id = seed(f, kind)
    _, context = reviewer(f)
    service = WorkReviewService(f.session_factory)
    original = service.inspect(context, order_id, kind, record_id)
    opened = service.decide(context, order_id, kind, record_id, decision(original), key="open")
    with pytest.raises(ApiProblem) as stale:
        service.decide(context, order_id, kind, record_id, decision(original, False), key="stale")
    assert stale.value.code == "VERSION_CONFLICT"
    closed = service.decide(
        context, order_id, kind, record_id, decision(opened, False), key="close"
    )
    assert not closed.released
    assert not service.decide(
        context, order_id, kind, record_id, decision(original), key="open"
    ).released
    service.decide(context, order_id, kind, record_id, decision(closed), key="reopen")
    model = Task if kind == "task" else Activity
    with f.session_factory.begin() as session:
        row = session.get(model, record_id)
        row.details = {"changed": "new content"}
    with f.session_factory.begin() as session:
        row = session.get(model, record_id)
        row.details = {"nested": {"note": "cost 350"}}
    assert not service.inspect(context, order_id, kind, record_id).released


@pytest.mark.parametrize("kind", ["task", "activity"])
@pytest.mark.parametrize("stage", [Activity, AuditLog, OutboxEvent])
def test_work_review_rolls_back_every_evidence_boundary(quotation_fixture, kind, stage):
    f = quotation_fixture
    order_id, record_id = seed(f, kind)
    _, context = reviewer(f)
    service = WorkReviewService(f.session_factory)
    original = service.inspect(context, order_id, kind, record_id)
    before = counts(f)

    def fail(*args, **kwargs):
        raise RuntimeError("injected evidence failure")

    event.listen(stage, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="injected evidence"):
            service.decide(context, order_id, kind, record_id, decision(original), key="failed")
    finally:
        event.remove(stage, "before_insert", fail)
    assert counts(f) == before
    assert service.inspect(context, order_id, kind, record_id) == original


def test_task_completion_and_done_replay_hide_resolution_and_invalidate_review(quotation_fixture):
    f = quotation_fixture
    order_id, task_id = seed(f, "task")
    _, context = reviewer(f)
    review = WorkReviewService(f.session_factory)
    original = review.inspect(context, order_id, "task", task_id)
    opened = review.decide(context, order_id, "task", task_id, decision(original), key="open")
    low = replace(context, permissions=permissions_for_role(MembershipRole.OPERATIONS))
    service = TaskCommandService(f.session_factory)
    request = TaskComplete(expected_version=opened.version, resolution="supplier cost 500")
    result = service.complete_order_task(low, order_id, task_id, request)
    assert result.status == "DONE"
    assert result.title is None and result.details == {} and not result.released
    before = counts(f)
    assert service.complete_order_task(low, order_id, task_id, request) == result
    assert counts(f) == before
    with f.session_factory() as session:
        task = session.get(Task, task_id)
        assert task.title == "Internal cost 350"
        assert task.details["resolution"] == "supplier cost 500"
        rows = WorkQueryService(session).order_activities(low, order_id, 100)
        completed = next(row for row in rows if row.activity_type == "task.completed")
        assert completed.summary is None and completed.details == {}


@pytest.mark.parametrize("kind", ["task", "activity"])
def test_work_review_concurrency_confirmation_and_wrong_subject(quotation_fixture, kind):
    f = quotation_fixture
    order_id, record_id = seed(f, kind)
    _, context = reviewer(f)
    service = WorkReviewService(f.session_factory)
    original = service.inspect(context, order_id, kind, record_id)
    before = counts(f)
    with pytest.raises(ApiProblem) as unconfirmed:
        service.decide(
            context,
            order_id,
            kind,
            record_id,
            decision(original).model_copy(update={"confirmed": False}),
            key="unconfirmed",
        )
    assert unconfirmed.value.code == "CONFIRMATION_REQUIRED"
    with pytest.raises(ApiProblem) as wrong:
        service.inspect(context, uuid4(), kind, record_id)
    assert wrong.value.status == 404
    assert counts(f) == before
    barrier = Barrier(2)

    def decide_together(release):
        barrier.wait(timeout=10)
        try:
            return service.decide(
                context,
                order_id,
                kind,
                record_id,
                decision(original, release),
                key=f"competing-{release}",
            )
        except ApiProblem as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(decide_together, (True, False)))
    failed = [result for result in outcomes if isinstance(result, ApiProblem)]
    passed = [result for result in outcomes if not isinstance(result, ApiProblem)]
    assert len(failed) == len(passed) == 1
    assert failed[0].code == "VERSION_CONFLICT"
    assert service.inspect(context, order_id, kind, record_id) == passed[0]
    assert counts(f) == [number + 1 for number in before]
