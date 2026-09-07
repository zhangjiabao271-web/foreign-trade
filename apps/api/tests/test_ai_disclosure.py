import copy
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.ai.content import run_digest
from app.ai.disclosure import AiDisclosureService
from app.ai.models import AiDisclosure, AiRun
from app.ai.services import AiQueryService
from app.auth.context import RequestContext
from app.auth.permissions import permissions_for_role
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership, User
from app.platform.models import AuditLog, OutboxEvent
from app.work.models import Activity, Task
from legacy_migration import verify_legacy_guard, verify_legacy_upgrade
from sqlalchemy import event, func, select
from test_ai_copilot import ScriptedProvider, create_run, execute
from test_shipment_documents_vertical_slice import executing_order

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)
SECRET = "内部成本77123利润88123"
SAFE = {"inferences": ["请核对客户需求"], "draft": "请确认交付安排。", "task_title": "核对交付安排"}


def headers(fixture, subject="quotation-sales", organization=None):
    return fixture.headers(subject, organization or fixture.organization_a)


def post(fixture, path, body, *, subject="quotation-sales", key=None):
    return fixture.client.post(
        path,
        json=body,
        headers={**headers(fixture, subject), "Idempotency-Key": key or str(uuid4())},
    )


def prepare(fixture):
    order = executing_order(fixture)
    run_id = create_run(fixture, order["id"], "TASK_DRAFT").json()["id"]
    execute(fixture, run_id, ScriptedProvider(order["id"]))
    with fixture.session_factory.begin() as session:
        row = session.get(AiRun, UUID(run_id))
        row.output = {
            **row.output,
            "artifact": {"inferences": [SECRET], "draft": SECRET, "task_title": SECRET},
        }
        row.estimated_cost_usd = Decimal("12.345")
        row.input_summary = {"private_input": SECRET}
    return fixture.client.get(f"/api/v1/ai/runs/{run_id}", headers=headers(fixture)).json()


def submit(fixture, run, key=None):
    result = post(
        fixture,
        f"/api/v1/ai/runs/{run['id']}/submit-disclosure",
        {"expected_version": run["version"]},
        key=key,
    )
    assert result.status_code == 201, result.text
    return result.json()


def inspect_review(fixture, row):
    response = fixture.client.get(
        f"/api/v1/ai/disclosures/{row['id']}", headers=headers(fixture, "quotation-manager")
    )
    assert response.status_code == 200, response.text
    return response.json()


def decision(fixture, row, release=True, key=None):
    return post(
        fixture,
        f"/api/v1/ai/disclosures/{row['id']}/decide",
        {
            "expected_version": row["version"],
            "content_digest": row["content_digest"],
            "confirmed": True,
            "release": release,
            "reason": "核对整个候选后决定",
        },
        subject="quotation-manager",
        key=key,
    )


def test_private_submission_sanitized_revision_and_independent_execution(quotation_fixture):
    fixture = quotation_fixture
    run = prepare(fixture)
    run_path = f"/api/v1/ai/runs/{run['id']}"
    assert run["content_protected"] and run["output"] is None
    assert run["input_summary"] is None and run["estimated_cost_usd"] is None
    assert SECRET not in str(run)
    assert (
        fixture.client.get(run_path, headers=headers(fixture, "quotation-manager")).status_code
        == 404
    )
    assert (
        fixture.client.get(
            "/api/v1/ai/disclosures", headers=headers(fixture, "quotation-manager")
        ).json()["items"]
        == []
    )
    with fixture.session_factory() as session:
        original = session.get(AiRun, UUID(run["id"]))
        original_output, original_digest = copy.deepcopy(original.output), run_digest(original)
        tasks_before = session.scalar(select(func.count()).select_from(Task))
        context = RequestContext(
            user_id=fixture.sales_user,
            organization_id=fixture.organization_a,
            permissions=permissions_for_role(MembershipRole.SALES),
            request_id=uuid4(),
        )
        projected = AiQueryService(session).get(context, UUID(run["id"]))
        assert projected.output is None and projected.estimated_cost_usd is None
    assert (
        post(
            fixture,
            run_path + "/request-approval",
            {"expected_version": run["version"], "reason": "请求执行建议"},
        ).status_code
        == 409
    )
    key = str(uuid4())
    submitted = submit(fixture, run, key)
    assert submit(fixture, run, key) == submitted
    assert submitted["candidate"] is None and submitted["content_digest"] is None
    reviewed = inspect_review(fixture, submitted)
    assert SECRET in reviewed["candidate"]["draft"]
    revised = post(
        fixture,
        f"/api/v1/ai/disclosures/{reviewed['id']}/revise",
        {
            "expected_version": reviewed["version"],
            "content_digest": reviewed["content_digest"],
            "candidate": SAFE,
        },
        subject="quotation-manager",
    )
    assert revised.status_code == 201, revised.text
    revised = revised.json()
    assert revised["status"] == "PENDING" and revised["revision"] == 2
    assert fixture.client.get(run_path, headers=headers(fixture)).json()["output"] is None
    assert decision(fixture, reviewed).status_code == 409
    approved = decision(fixture, revised)
    assert approved.status_code == 200, approved.text
    visible = fixture.client.get(run_path, headers=headers(fixture)).json()
    assert visible["output"] == {"artifact": SAFE}
    assert visible["input_summary"] is None and visible["references"] == []
    assert visible["estimated_cost_usd"] is None and SECRET not in str(visible)
    assert (
        fixture.client.get(run_path, headers=headers(fixture, "quotation-manager")).status_code
        == 404
    )
    calls = fixture.client.get(run_path + "/tool-calls", headers=headers(fixture)).json()
    assert all(
        call["argument_summary"] is None and call["result_summary"] is None for call in calls
    )
    with fixture.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Task)) == tasks_before
        original = session.get(AiRun, UUID(run["id"]))
        assert original.output == original_output and run_digest(original) == original_digest
        assert session.scalar(select(func.count()).select_from(AiDisclosure)) == 2
    requested = post(
        fixture,
        run_path + "/request-approval",
        {
            "expected_version": run["version"],
            "reason": "请审核已脱敏的任务建议",
            "disclosure_id": approved.json()["id"],
            "disclosure_version": approved.json()["version"],
        },
    )
    assert requested.status_code == 201, requested.text
    assert requested.json()["proposed_action"] is None
    manager_approval = fixture.client.get(
        f"/api/v1/ai/approvals/{requested.json()['id']}",
        headers=headers(fixture, "quotation-manager"),
    ).json()
    assert manager_approval["proposed_action"]["title"] == SAFE["task_title"]
    revoked = decision(fixture, approved.json(), False)
    assert revoked.status_code == 200
    assert fixture.client.get(run_path, headers=headers(fixture)).json()["output"] is None


@pytest.mark.parametrize("role", list(MembershipRole))
def test_only_three_reviewer_roles_and_no_private_run_grant(quotation_fixture, role):
    fixture = quotation_fixture
    run = prepare(fixture)
    row = submit(fixture, run)
    with fixture.session_factory.begin() as session:
        manager = session.scalar(select(User).where(User.external_subject == "quotation-manager"))
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == fixture.organization_a,
                OrganizationMembership.user_id == manager.id,
            )
        )
        membership.role = role
    reviewer = role in {MembershipRole.ADMIN, MembershipRole.MANAGER, MembershipRole.FINANCE}
    path = f"/api/v1/ai/disclosures/{row['id']}"
    response = fixture.client.get(path, headers=headers(fixture, "quotation-manager"))
    assert response.status_code == (200 if reviewer else 404)
    assert (
        fixture.client.get(
            f"/api/v1/ai/runs/{run['id']}", headers=headers(fixture, "quotation-manager")
        ).status_code
        == 404
    )
    page = fixture.client.get(
        "/api/v1/ai/disclosures", headers=headers(fixture, "quotation-manager")
    )
    assert len(page.json()["items"]) == (1 if reviewer else 0)
    if reviewer:
        assert decision(fixture, response.json(), False).status_code == 200
    assert (
        fixture.client.get(
            path, headers=headers(fixture, "quotation-other", fixture.organization_b)
        ).status_code
        == 404
    )
    foreign = fixture.client.get(
        "/api/v1/ai/disclosures",
        headers=headers(fixture, "quotation-other", fixture.organization_b),
    )
    assert foreign.json()["items"] == []


@pytest.mark.parametrize("changed", ["run", "candidate"])
def test_changed_content_invalidates_release(quotation_fixture, changed):
    fixture = quotation_fixture
    run = prepare(fixture)
    row = inspect_review(fixture, submit(fixture, run))
    # Deliberately approve the synthetic candidate; tests check binding, not human judgment.
    assert decision(fixture, row).status_code == 200
    with fixture.session_factory.begin() as session:
        if changed == "run":
            record = session.get(AiRun, UUID(run["id"]))
            record.output = {**record.output, "changed": True}
        else:
            record = session.get(AiDisclosure, UUID(row["id"]))
            record.candidate = {**SAFE, "draft": "unreviewed changed draft"}
    result = fixture.client.get(f"/api/v1/ai/runs/{run['id']}", headers=headers(fixture)).json()
    assert result["output"] is None and result["content_protected"]
    owner_review = fixture.client.get(
        f"/api/v1/ai/disclosures/{row['id']}", headers=headers(fixture)
    ).json()
    assert owner_review["candidate"] is None and not owner_review["current"]


@pytest.mark.parametrize("model", [Activity, AuditLog, OutboxEvent])
def test_submission_record_failure_rolls_back_everything(quotation_fixture, model):
    fixture = quotation_fixture
    run = prepare(fixture)

    def fail(*args):
        raise RuntimeError("injected disclosure failure")

    event.listen(model, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="injected disclosure failure"):
            submit(fixture, run)
    finally:
        event.remove(model, "before_insert", fail)
    with fixture.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AiDisclosure)) == 0
    assert (
        fixture.client.get(f"/api/v1/ai/runs/{run['id']}", headers=headers(fixture)).json()[
            "output"
        ]
        is None
    )


def test_concurrent_decisions_and_replays_preserve_one_decision(quotation_fixture):
    fixture = quotation_fixture
    run = prepare(fixture)
    row = inspect_review(fixture, submit(fixture, run))
    key = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: decision(fixture, row, False, key), range(2)))
    assert all(result.status_code == 200 for result in results)
    with fixture.session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "ai.disclosure_decided")
            )
            == 1
        )
    assert decision(fixture, row, True).status_code == 409


def test_previous_schema_upgrade_preserves_original_ai_and_review_downgrade_is_guarded(
    quotation_fixture,
):
    fixture = quotation_fixture
    run = prepare(fixture)
    verify_legacy_upgrade(fixture.engine, "20260907_0032")
    submit(fixture, run)
    verify_legacy_guard(
        fixture.engine, "20260907_0033", "20260907_0032", "Preserve AI disclosure evidence"
    )


@pytest.mark.parametrize("model", [Activity, AuditLog, OutboxEvent])
def test_decision_failure_never_releases_content(quotation_fixture, model):
    fixture = quotation_fixture
    run = prepare(fixture)
    row = inspect_review(fixture, submit(fixture, run))

    def fail(*args):
        raise RuntimeError("injected decision failure")

    event.listen(model, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="injected decision failure"):
            decision(fixture, row)
    finally:
        event.remove(model, "before_insert", fail)
    with fixture.session_factory() as session:
        persisted = session.get(AiDisclosure, UUID(row["id"]))
        assert persisted.status == "PENDING" and persisted.released_digest is None


def test_cursor_pages_never_reopen_old_release_and_use_constant_queries(quotation_fixture):
    fixture = quotation_fixture
    run = prepare(fixture)
    row = inspect_review(fixture, submit(fixture, run))
    assert decision(fixture, row).status_code == 200
    with fixture.session_factory.begin() as session:
        original = session.get(AiDisclosure, UUID(row["id"]))
        for revision in range(2, 26):
            session.add(
                AiDisclosure(
                    organization_id=fixture.organization_a,
                    created_by=fixture.sales_user,
                    updated_by=fixture.sales_user,
                    run_id=original.run_id,
                    parent_id=original.id,
                    revision=revision,
                    run_version=original.run_version,
                    run_digest=original.run_digest,
                    candidate=SAFE,
                )
            )
    context = RequestContext(
        user_id=fixture.sales_user,
        organization_id=fixture.organization_a,
        permissions=permissions_for_role(MembershipRole.SALES),
        request_id=uuid4(),
    )
    service = AiDisclosureService(fixture.session_factory)
    statements = []

    def capture(connection, cursor, statement, parameters, execution, many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append((statement, parameters))

    event.listen(fixture.engine, "before_cursor_execute", capture)
    try:
        assert len(service.page(context, cursor=None, limit=1)) == 2
        assert len(statements) == 1
        statements.clear()
        page = service.page(context, cursor=None, limit=20)
        assert len(page) == 21 and len(statements) == 1
        assert all(item.candidate is None for item in page)
        next_page = service.page(context, cursor=page[19].id, limit=20)
        assert all(item.candidate is None for item in next_page)
        assert any(item.revision == 1 and not item.current for item in next_page)
    finally:
        event.remove(fixture.engine, "before_cursor_execute", capture)
    with fixture.engine.connect() as connection:
        plans = [
            connection.exec_driver_sql("EXPLAIN " + sql, params).scalars().all()
            for sql, params in statements
        ]
        assert plans and all(plan for plan in plans)


def test_task_request_rejects_wrong_review_version_and_reviewer_downgrade(quotation_fixture):
    fixture = quotation_fixture
    run = prepare(fixture)
    row = inspect_review(fixture, submit(fixture, run))
    approved = decision(fixture, row).json()
    response = post(
        fixture,
        f"/api/v1/ai/runs/{run['id']}/request-approval",
        {
            "expected_version": run["version"],
            "reason": "不得执行错误候选",
            "disclosure_id": approved["id"],
            "disclosure_version": approved["version"] - 1,
        },
    )
    assert response.status_code == 409
    with fixture.session_factory.begin() as session:
        manager = session.scalar(select(User).where(User.external_subject == "quotation-manager"))
        member = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == fixture.organization_a,
                OrganizationMembership.user_id == manager.id,
            )
        )
        member.role = "SALES"
    assert (
        fixture.client.get(
            f"/api/v1/ai/disclosures/{row['id']}", headers=headers(fixture, "quotation-manager")
        ).status_code
        == 404
    )
    assert decision(fixture, approved, False).status_code == 403
