import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.ai.models import AiRun, AiToolCall, ApprovalRequest
from app.ai.provider import OpenAIResponsesProvider, ProviderError, ProviderTurn
from app.ai.runner import AiRunner, RunBusy, RunRetry
from app.core.config import Settings
from app.identity.models import OrganizationMembership
from app.platform.models import AsyncJob, AuditLog, OutboxEvent
from app.sales.models import SalesOrder
from app.work.models import Activity, Task
from sqlalchemy import event, func, select
from test_quotation_vertical_slice import QuotationFixture
from test_shipment_documents_vertical_slice import executing_order

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


class ScriptedProvider:
    def __init__(self, order_id, *, tool="read_order", arguments=None, before_return=None):
        self.order_id = order_id
        self.tool = tool
        self.arguments = arguments or {"order_id": order_id}
        self.before_return = before_return
        self.calls = 0

    def next_turn(self, *, model, inputs, tools):
        self.calls += 1
        if self.before_return:
            self.before_return()
        if self.calls == 1:
            return ProviderTurn(
                [
                    {
                        "type": "function_call",
                        "call_id": "fixture-call",
                        "name": self.tool,
                        "arguments": json.dumps(self.arguments),
                    }
                ],
                100,
                20,
            )
        assert inputs[-1]["type"] == "function_call_output"
        return ProviderTurn(
            [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                {
                                    "inferences": ["建议核对执行进度"],
                                    "draft": "请内部核对订单资料。",
                                    "task_title": "核对订单执行进度",
                                }
                            ),
                        }
                    ],
                }
            ],
            120,
            30,
        )


def create_run(fixture, order_id, intent="TIMELINE", subject="quotation-sales", key=None):
    return fixture.client.post(
        "/api/v1/ai/runs",
        headers={
            **fixture.headers(subject, fixture.organization_a),
            "Idempotency-Key": key or str(uuid4()),
        },
        json={"intent": intent, "subject_id": order_id},
    )


def execute(fixture, run_id, provider):
    AiRunner(fixture.session_factory, provider, Settings()).execute(
        organization_id=fixture.organization_a, run_id=UUID(run_id), request_id=uuid4()
    )


def test_read_run_is_audited_private_idempotent_and_cannot_change_order(
    quotation_fixture: QuotationFixture,
):
    fixture = quotation_fixture
    order = executing_order(fixture)
    key = str(uuid4())
    created = create_run(fixture, order["id"], key=key)
    assert created.status_code == 202, created.text
    run_id = created.json()["id"]
    assert create_run(fixture, order["id"], key=key).json()["id"] == run_id
    provider = ScriptedProvider(order["id"], tool="order_timeline")
    execute(fixture, run_id, provider)
    execute(fixture, run_id, provider)
    assert provider.calls == 2
    headers = fixture.headers("quotation-sales", fixture.organization_a)
    run = fixture.client.get(f"/api/v1/ai/runs/{run_id}", headers=headers)
    assert run.status_code == 200, run.text
    assert run.json()["status"] == "SUCCEEDED"
    assert run.json()["input_tokens"] == 220
    assert run.json()["output"] is None and run.json()["content_protected"]
    assert run.json()["references"] == []
    with fixture.session_factory() as session:
        original = session.get(AiRun, UUID(run_id))
        assert original.output["executed_actions"] == []
        assert original.references[0]["id"] == order["id"]
    calls = fixture.client.get(f"/api/v1/ai/runs/{run_id}/tool-calls", headers=headers).json()
    assert len(calls) == 1 and calls[0]["status"] == "SUCCEEDED"
    assert (
        fixture.client.get(f"/api/v1/sales-orders/{order['id']}", headers=headers).json()["status"]
        == order["status"]
    )
    for subject, organization in (
        ("quotation-other", fixture.organization_b),
        ("quotation-manager", fixture.organization_a),
    ):
        assert (
            fixture.client.get(
                f"/api/v1/ai/runs/{run_id}", headers=fixture.headers(subject, organization)
            ).status_code
            == 404
        )
        assert (
            fixture.client.get(
                "/api/v1/ai/runs", headers=fixture.headers(subject, organization)
            ).json()["items"]
            == []
        )
    with fixture.session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.organization_id == fixture.organization_a,
                    AuditLog.target_id == UUID(run_id),
                )
            )
            == 3
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(
                    OutboxEvent.organization_id == fixture.organization_a,
                    OutboxEvent.aggregate_id == UUID(run_id),
                )
            )
            == 3
        )


@pytest.mark.parametrize(
    "tool,arguments,code",
    [
        ("execute_sql", {"sql": "UPDATE sales_orders SET status = 'COMPLETED'"}, "AI_TOOL_DENIED"),
        ("read_order", {"order_id": str(uuid4())}, "SALES_ORDER_NOT_FOUND"),
        (
            "read_order",
            {"order_id": "replace", "organization_id": str(uuid4())},
            "AI_TOOL_ARGUMENTS_INVALID",
        ),
        ("order_profit", {"order_id": "replace"}, "AI_TOOL_DENIED"),
    ],
)
def test_model_tool_authority_is_bounded(quotation_fixture, tool, arguments, code):
    fixture = quotation_fixture
    order = executing_order(fixture)
    arguments = {
        key: order["id"] if value == "replace" else value for key, value in arguments.items()
    }
    run_id = create_run(fixture, order["id"]).json()["id"]
    execute(fixture, run_id, ScriptedProvider(order["id"], tool=tool, arguments=arguments))
    with fixture.session_factory() as session:
        run = session.scalar(
            select(AiRun).where(
                AiRun.organization_id == fixture.organization_a, AiRun.id == UUID(run_id)
            )
        )
        assert run.status == "FAILED" and run.error_code == code and run.output is None
        call = session.scalar(
            select(AiToolCall).where(
                AiToolCall.organization_id == fixture.organization_a, AiToolCall.run_id == run.id
            )
        )
        assert call.status == "DENIED" and call.error_code == code


def test_privilege_revocation_before_tool_blocks_access(quotation_fixture):
    fixture = quotation_fixture
    order = executing_order(fixture)
    run_id = create_run(fixture, order["id"]).json()["id"]

    def revoke():
        with fixture.session_factory.begin() as session:
            membership = session.scalar(
                select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == fixture.organization_a,
                    OrganizationMembership.user_id == fixture.sales_user,
                )
            )
            membership.role = "VIEWER"

    execute(fixture, run_id, ScriptedProvider(order["id"], before_return=revoke))
    with fixture.session_factory() as session:
        run = session.scalar(
            select(AiRun).where(
                AiRun.organization_id == fixture.organization_a, AiRun.id == UUID(run_id)
            )
        )
        assert run.status == "FAILED" and run.output is None
    assert (
        fixture.client.get(
            f"/api/v1/ai/runs/{run_id}",
            headers=fixture.headers("quotation-sales", fixture.organization_a),
        ).status_code
        == 403
    )


def test_profit_and_cross_organization_run_creation_are_rejected(quotation_fixture):
    fixture = quotation_fixture
    order = executing_order(fixture)
    assert create_run(fixture, order["id"], "PROFIT").status_code == 403
    denied = fixture.client.post(
        "/api/v1/ai/runs",
        headers={
            **fixture.headers("quotation-other", fixture.organization_b),
            "Idempotency-Key": str(uuid4()),
        },
        json={"intent": "TIMELINE", "subject_id": order["id"]},
    )
    assert denied.status_code == 404


def test_saved_profit_run_is_inaccessible_after_cost_permission_revocation(quotation_fixture):
    fixture = quotation_fixture
    order = executing_order(fixture)
    key = str(uuid4())
    response = create_run(fixture, order["id"], "PROFIT", "quotation-manager", key)
    assert response.status_code == 202
    run_id = response.json()["id"]
    execute(fixture, run_id, ScriptedProvider(order["id"], tool="order_profit"))
    headers = fixture.headers("quotation-manager", fixture.organization_a)
    path = f"/api/v1/ai/runs/{run_id}"
    full = fixture.client.get(path, headers=headers)
    assert full.status_code == 200
    assert full.json()["status"] == "SUCCEEDED"
    assert "estimated_cost" in json.dumps(full.json()["output"])
    with fixture.session_factory.begin() as session:
        run = session.get(AiRun, UUID(run_id))
        member = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == fixture.organization_a,
                OrganizationMembership.user_id == run.created_by,
            )
        )
        member.role = "SALES"
    assert fixture.client.get(path, headers=headers).status_code == 403
    assert fixture.client.get(path + "/tool-calls", headers=headers).status_code == 403
    page = fixture.client.get("/api/v1/ai/runs", headers=headers)
    assert page.status_code == 200
    assert all(row["id"] != run_id for row in page.json()["items"])
    assert create_run(fixture, order["id"], "PROFIT", "quotation-manager", key).status_code == 403


@pytest.mark.parametrize("malformed", [False, True])
def test_rejected_provider_calls_each_have_a_receipt(quotation_fixture, malformed):
    fixture = quotation_fixture
    order = executing_order(fixture)
    run_id = create_run(fixture, order["id"]).json()["id"]
    call = {
        "type": "function_call",
        "call_id": "duplicate-id",
        "name": "read_order",
        "arguments": {"order_id": order["id"]}
        if malformed
        else json.dumps({"order_id": order["id"]}),
    }

    class RejectedProvider:
        def next_turn(self, **kwargs):
            return ProviderTurn([call] if malformed else [call, call], 10, 10)

    execute(fixture, run_id, RejectedProvider())
    with fixture.session_factory() as session:
        receipts = list(
            session.scalars(
                select(AiToolCall).where(
                    AiToolCall.organization_id == fixture.organization_a,
                    AiToolCall.run_id == UUID(run_id),
                )
            )
        )
        assert len(receipts) == (1 if malformed else 2)
        expected = "AI_TOOL_CALL_INVALID" if malformed else "AI_TOOL_LIMIT_EXCEEDED"
        assert all(row.status == "DENIED" and row.error_code == expected for row in receipts)
        assert all(set(row.argument_summary) == {"sha256"} for row in receipts)
        assert all(row.result_summary == {"references": []} for row in receipts)


def test_repeated_provider_call_ids_do_not_erase_receipts(quotation_fixture):
    fixture = quotation_fixture
    order = executing_order(fixture)
    run_id = create_run(fixture, order["id"]).json()["id"]

    class RepeatedProvider:
        calls = 0

        def next_turn(self, **kwargs):
            self.calls += 1
            scripted = ScriptedProvider(order["id"], tool="order_timeline")
            if self.calls > 2:
                scripted.calls = 1
            return scripted.next_turn(**kwargs)

    execute(fixture, run_id, RepeatedProvider())
    headers = fixture.headers("quotation-sales", fixture.organization_a)
    result = fixture.client.get(f"/api/v1/ai/runs/{run_id}", headers=headers).json()
    assert result["status"] == "SUCCEEDED"
    calls = fixture.client.get(f"/api/v1/ai/runs/{run_id}/tool-calls", headers=headers).json()
    assert len(calls) == 2 and all(row["status"] == "SUCCEEDED" for row in calls)


@pytest.mark.parametrize(
    "intent,tool,subject",
    [
        ("TIMELINE", "order_timeline", "quotation-sales"),
        ("EMAIL_DRAFT", "read_order", "quotation-sales"),
        ("PROFIT", "order_profit", "quotation-manager"),
    ],
)
def test_read_intents_use_evidence_and_do_not_propose_tasks(
    quotation_fixture, intent, tool, subject
):
    fixture = quotation_fixture
    order = executing_order(fixture)
    run_id = create_run(fixture, order["id"], intent, subject=subject).json()["id"]
    execute(fixture, run_id, ScriptedProvider(order["id"], tool=tool))
    result = fixture.client.get(
        f"/api/v1/ai/runs/{run_id}",
        headers=fixture.headers(subject, fixture.organization_a),
    ).json()
    assert result["status"] == "SUCCEEDED"
    if subject == "quotation-sales":
        assert result["output"] is None and result["content_protected"]
    with fixture.session_factory() as session:
        original = session.get(AiRun, UUID(run_id))
        assert original.output["facts"][0]["tool"] == tool
        assert original.output["artifact"]["task_title"] is None


def test_timeline_cannot_succeed_using_only_order_header(quotation_fixture):
    fixture = quotation_fixture
    order = executing_order(fixture)
    run_id = create_run(fixture, order["id"]).json()["id"]
    execute(fixture, run_id, ScriptedProvider(order["id"]))
    result = fixture.client.get(
        f"/api/v1/ai/runs/{run_id}",
        headers=fixture.headers("quotation-sales", fixture.organization_a),
    ).json()
    assert result["status"] == "FAILED" and result["error_code"] == "AI_MISSING_EVIDENCE"
    assert result["output"] is None


def test_transient_failure_retries_are_bounded_and_persisted(quotation_fixture):
    fixture = quotation_fixture
    order = executing_order(fixture)
    run_id = create_run(fixture, order["id"]).json()["id"]

    class UnavailableProvider:
        calls = 0

        def next_turn(self, **kwargs):
            self.calls += 1
            raise ProviderError("AI_PROVIDER_UNAVAILABLE")

    provider = UnavailableProvider()
    for attempt in (1, 2):
        with pytest.raises(RunRetry):
            execute(fixture, run_id, provider)
        with fixture.session_factory() as session:
            run = session.scalar(
                select(AiRun).where(
                    AiRun.organization_id == fixture.organization_a,
                    AiRun.id == UUID(run_id),
                )
            )
            job = session.scalar(
                select(AsyncJob).where(
                    AsyncJob.organization_id == fixture.organization_a,
                    AsyncJob.id == run.job_id,
                )
            )
            assert run.status == job.status == "PENDING"
            assert run.attempt_count == job.attempt_count == attempt
            assert run.lease_id is None and run.completed_at is None
    execute(fixture, run_id, provider)
    execute(fixture, run_id, provider)
    assert provider.calls == 3
    result = fixture.client.get(
        f"/api/v1/ai/runs/{run_id}",
        headers=fixture.headers("quotation-sales", fixture.organization_a),
    ).json()
    assert result["status"] == "FAILED" and result["error_code"] == "AI_PROVIDER_UNAVAILABLE"


def test_active_lease_blocks_duplicate_and_stale_lease_recovers(quotation_fixture):
    fixture = quotation_fixture
    order = executing_order(fixture)
    run_id = create_run(fixture, order["id"]).json()["id"]
    with fixture.session_factory.begin() as session:
        run = session.scalar(
            select(AiRun).where(
                AiRun.organization_id == fixture.organization_a,
                AiRun.id == UUID(run_id),
            )
        )
        run.status = "RUNNING"
        run.started_at = datetime.now(UTC)
        run.lease_id = uuid4()
        run.attempt_count = 1
    provider = ScriptedProvider(order["id"], tool="order_timeline")
    with pytest.raises(RunBusy):
        execute(fixture, run_id, provider)
    assert provider.calls == 0
    with fixture.session_factory.begin() as session:
        run = session.scalar(
            select(AiRun).where(
                AiRun.organization_id == fixture.organization_a,
                AiRun.id == UUID(run_id),
            )
        )
        run.started_at = datetime.now(UTC) - timedelta(minutes=5)
    execute(fixture, run_id, provider)
    assert provider.calls == 2


def test_provider_runs_without_checked_out_database_connection(quotation_fixture):
    fixture = quotation_fixture
    order = executing_order(fixture)
    run_id = create_run(fixture, order["id"]).json()["id"]

    def assert_no_connection():
        assert fixture.session_factory.kw["bind"].pool.checkedout() == 0

    provider = ScriptedProvider(
        order["id"], tool="order_timeline", before_return=assert_no_connection
    )
    execute(fixture, run_id, provider)
    result = fixture.client.get(
        f"/api/v1/ai/runs/{run_id}",
        headers=fixture.headers("quotation-sales", fixture.organization_a),
    ).json()
    assert result["status"] == "SUCCEEDED"


@pytest.mark.parametrize("corrects", [True, False])
def test_parallel_requests_are_denied_before_bounded_model_correction(quotation_fixture, corrects):
    fixture = quotation_fixture
    order = executing_order(fixture)
    run_id = create_run(fixture, order["id"], "TASK_DRAFT").json()["id"]
    serial = ScriptedProvider(order["id"])

    class ParallelProvider:
        calls = 0

        def next_turn(self, **kwargs):
            self.calls += 1
            if corrects and self.calls > 1:
                if self.calls == 2:
                    errors = kwargs["inputs"][-2:]
                    assert all(item["type"] == "function_call_output" for item in errors)
                    assert all(
                        json.loads(item["output"])["error"] == "AI_TOOL_LIMIT_EXCEEDED"
                        for item in errors
                    )
                return serial.next_turn(**kwargs)
            return ProviderTurn(
                [
                    {
                        "type": "function_call",
                        "call_id": f"parallel-{index}",
                        "name": "read_order",
                        "arguments": json.dumps({"order_id": order["id"]}),
                    }
                    for index in range(2)
                ],
                10,
                5,
            )

    provider = ParallelProvider()
    execute(fixture, run_id, provider)
    with fixture.session_factory() as session:
        run = session.scalar(
            select(AiRun).where(
                AiRun.organization_id == fixture.organization_a, AiRun.id == UUID(run_id)
            )
        )
        calls = list(
            session.scalars(
                select(AiToolCall).where(
                    AiToolCall.organization_id == fixture.organization_a,
                    AiToolCall.run_id == run.id,
                )
            )
        )
        denied = [call for call in calls if call.status == "DENIED"]
        assert all(call.error_code == "AI_TOOL_LIMIT_EXCEEDED" for call in denied)
        assert all(call.result_summary == {"references": []} for call in denied)
        if corrects:
            assert provider.calls == 3 and len(denied) == 2 and len(calls) == 3
            assert run.status == "SUCCEEDED" and run.output["executed_actions"] == []
        else:
            assert provider.calls == 4 and len(denied) == len(calls) == 8
            assert run.status == "FAILED" and run.error_code == "AI_TURN_LIMIT_EXCEEDED"
            assert run.output is None


@pytest.mark.parametrize("call_ids", [("same", "same"), (None, "valid"), ("", "valid")])
def test_invalid_parallel_ids_cannot_enter_correction_loop(quotation_fixture, call_ids):
    fixture = quotation_fixture
    order = executing_order(fixture)
    run_id = create_run(fixture, order["id"], "TASK_DRAFT").json()["id"]

    class InvalidProvider:
        calls = 0

        def next_turn(self, **kwargs):
            self.calls += 1
            return ProviderTurn(
                [
                    {
                        "type": "function_call",
                        "call_id": call_id,
                        "name": "read_order",
                        "arguments": json.dumps({"order_id": order["id"]}),
                    }
                    for call_id in call_ids
                ],
                1,
                1,
            )

    provider = InvalidProvider()
    execute(fixture, run_id, provider)
    assert provider.calls == 1
    with fixture.session_factory() as session:
        run = session.scalar(
            select(AiRun).where(
                AiRun.organization_id == fixture.organization_a, AiRun.id == UUID(run_id)
            )
        )
        assert run.status == "FAILED" and run.error_code == "AI_TOOL_LIMIT_EXCEEDED"
        assert run.output is None
        calls = list(
            session.scalars(
                select(AiToolCall).where(
                    AiToolCall.organization_id == fixture.organization_a,
                    AiToolCall.run_id == run.id,
                )
            )
        )
        assert len(calls) == 2 and all(call.status == "DENIED" for call in calls)


def test_unconfigured_provider_persists_failed_job_without_retry(quotation_fixture):
    fixture = quotation_fixture
    order = executing_order(fixture)
    run_id = create_run(fixture, order["id"]).json()["id"]
    settings = Settings(openai_api_key=None, openai_model=None)
    execute(fixture, run_id, OpenAIResponsesProvider(settings))
    with fixture.session_factory() as session:
        run = session.scalar(
            select(AiRun).where(
                AiRun.organization_id == fixture.organization_a,
                AiRun.id == UUID(run_id),
            )
        )
        job = session.scalar(
            select(AsyncJob).where(
                AsyncJob.organization_id == fixture.organization_a,
                AsyncJob.id == run.job_id,
            )
        )
        assert run.status == job.status == "FAILED"
        assert run.error_code == job.error_code == "AI_PROVIDER_NOT_CONFIGURED"
        assert run.attempt_count == 1 and run.output is None


@pytest.mark.parametrize("model", [Activity, AuditLog, OutboxEvent])
def test_run_creation_record_failure_rolls_back_run_and_job(quotation_fixture, model):
    fixture = quotation_fixture
    order = executing_order(fixture)

    def fail_insert(*args):
        raise RuntimeError("injected run creation failure")

    event.listen(model, "before_insert", fail_insert)
    try:
        with pytest.raises(RuntimeError, match="injected run creation failure"):
            create_run(fixture, order["id"])
    finally:
        event.remove(model, "before_insert", fail_insert)
    with fixture.session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AiRun)
                .where(
                    AiRun.organization_id == fixture.organization_a,
                )
            )
            == 0
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(AsyncJob)
                .where(
                    AsyncJob.organization_id == fixture.organization_a,
                    AsyncJob.job_type == "AI_COPILOT",
                )
            )
            == 0
        )


def release_fixture_draft(fixture, run):
    """Explicit human content review prerequisite; not a provider bypass."""
    response = fixture.client.post(
        f"/api/v1/ai/runs/{run['id']}/submit-disclosure",
        headers={
            **fixture.headers("quotation-sales", fixture.organization_a),
            "Idempotency-Key": str(uuid4()),
        },
        json={"expected_version": run["version"]},
    )
    assert response.status_code == 201, response.text
    path = f"/api/v1/ai/disclosures/{response.json()['id']}"
    headers = fixture.headers("quotation-manager", fixture.organization_a)
    candidate = fixture.client.get(path, headers=headers).json()
    released = fixture.client.post(
        path + "/decide",
        headers={**headers, "Idempotency-Key": str(uuid4())},
        json={
            "expected_version": candidate["version"],
            "content_digest": candidate["content_digest"],
            "release": True,
            "confirmed": True,
            "reason": "已核对测试草稿，无成本利润",
        },
    )
    assert released.status_code == 200, released.text
    return released.json()


def prepare_approval(fixture):
    order = executing_order(fixture)
    run_id = create_run(fixture, order["id"], "TASK_DRAFT").json()["id"]
    execute(fixture, run_id, ScriptedProvider(order["id"]))
    headers = fixture.headers("quotation-sales", fixture.organization_a)
    run = fixture.client.get(f"/api/v1/ai/runs/{run_id}", headers=headers).json()
    release = release_fixture_draft(fixture, run)
    requested = fixture.client.post(
        f"/api/v1/ai/runs/{run_id}/request-approval",
        headers=headers,
        json={
            "expected_version": run["version"],
            "reason": "请经理审核该内部跟进建议",
            "disclosure_id": release["id"],
            "disclosure_version": release["version"],
        },
    )
    assert requested.status_code == 201, requested.text
    return order, requested.json()


def test_human_approval_creates_exactly_one_task(quotation_fixture):
    fixture = quotation_fixture
    order, approval = prepare_approval(fixture)
    path = f"/api/v1/ai/approvals/{approval['id']}/approve"
    body = {"expected_version": approval["version"], "reason": "已核实建议，仅创建内部任务"}
    assert (
        fixture.client.post(
            path, headers=fixture.headers("quotation-sales", fixture.organization_a), json=body
        ).status_code
        == 403
    )
    assert (
        fixture.client.post(
            path, headers=fixture.headers("quotation-other", fixture.organization_b), json=body
        ).status_code
        == 403
    )
    manager = fixture.headers("quotation-manager", fixture.organization_a)
    approved = fixture.client.post(path, headers=manager, json=body)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert (
        fixture.client.post(path, headers=manager, json=body).json()["task_id"]
        == approved.json()["task_id"]
    )
    assert (
        fixture.client.post(
            path.removesuffix("approve") + "reject", headers=manager, json=body
        ).status_code
        == 409
    )
    with fixture.session_factory() as session:
        tasks = list(
            session.scalars(
                select(Task).where(
                    Task.organization_id == fixture.organization_a,
                    Task.task_type == f"AI_FOLLOW_UP:{approval['id']}",
                )
            )
        )
        assert len(tasks) == 1 and tasks[0].subject_id == UUID(order["id"])


def test_concurrent_approval_creates_one_task(quotation_fixture):
    fixture = quotation_fixture
    _, approval = prepare_approval(fixture)

    def approve():
        return fixture.client.post(
            f"/api/v1/ai/approvals/{approval['id']}/approve",
            headers=fixture.headers("quotation-manager", fixture.organization_a),
            json={"expected_version": approval["version"], "reason": "并发审批检查"},
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: approve(), range(2)))
    assert all(result.status_code == 200 for result in results)
    assert results[0].json()["task_id"] == results[1].json()["task_id"]


def test_other_organization_manager_cannot_read_or_decide_approval(quotation_fixture):
    fixture = quotation_fixture
    _, approval = prepare_approval(fixture)
    with fixture.session_factory.begin() as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == fixture.organization_b,
            )
        )
        membership.role = "MANAGER"
    headers = fixture.headers("quotation-other", fixture.organization_b)
    path = f"/api/v1/ai/approvals/{approval['id']}"
    assert fixture.client.get(path, headers=headers).status_code == 404
    for command in ("approve", "reject"):
        response = fixture.client.post(
            path + "/" + command,
            headers=headers,
            json={"expected_version": approval["version"], "reason": "跨组织边界检查"},
        )
        assert response.status_code == 404


def test_search_intent_uses_bounded_application_evidence(quotation_fixture):
    fixture = quotation_fixture
    response = fixture.client.post(
        "/api/v1/ai/runs",
        headers={
            **fixture.headers("quotation-sales", fixture.organization_a),
            "Idempotency-Key": str(uuid4()),
        },
        json={"intent": "SEARCH", "search_term": "fixture"},
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["id"]
    provider = ScriptedProvider(None, tool="search_companies", arguments={"term": "fixture"})
    execute(fixture, run_id, provider)
    result = fixture.client.get(
        f"/api/v1/ai/runs/{run_id}",
        headers=fixture.headers("quotation-sales", fixture.organization_a),
    ).json()
    assert result["status"] == "SUCCEEDED", result
    assert result["output"] is None and result["content_protected"]
    with fixture.session_factory() as session:
        original = session.get(AiRun, UUID(run_id))
        assert original.output["facts"][0]["tool"] == "search_companies"
        assert original.output["artifact"]["task_title"] is None


@pytest.mark.parametrize("status", ["COMPLETED", "CANCELLED"])
def test_finalized_order_rejects_approval_but_allows_rejection(quotation_fixture, status):
    fixture = quotation_fixture
    order, approval = prepare_approval(fixture)
    # Seed the final state directly to isolate the approval boundary, not the
    # independently tested order-completion workflow.
    with fixture.session_factory.begin() as session:
        row = session.scalar(
            select(SalesOrder).where(
                SalesOrder.organization_id == fixture.organization_a,
                SalesOrder.id == UUID(order["id"]),
            )
        )
        row.status = status
    path = f"/api/v1/ai/approvals/{approval['id']}"
    headers = fixture.headers("quotation-manager", fixture.organization_a)
    body = {"expected_version": approval["version"], "reason": "订单已终结，不再创建任务"}
    denied = fixture.client.post(path + "/approve", headers=headers, json=body)
    assert denied.status_code == 409 and denied.json()["code"] == "ORDER_FINALIZED"
    rejected = fixture.client.post(path + "/reject", headers=headers, json=body)
    assert rejected.status_code == 200 and rejected.json()["status"] == "REJECTED"
    assert rejected.json()["task_id"] is None


@pytest.mark.parametrize("model", [Activity, AuditLog, OutboxEvent])
def test_approval_record_failure_rolls_back_task_and_decision(quotation_fixture, model):
    fixture = quotation_fixture
    _, approval = prepare_approval(fixture)

    def fail_insert(*args):
        raise RuntimeError("injected approval failure")

    event.listen(model, "before_insert", fail_insert)
    try:
        with pytest.raises(RuntimeError, match="injected approval failure"):
            fixture.client.post(
                f"/api/v1/ai/approvals/{approval['id']}/approve",
                headers=fixture.headers("quotation-manager", fixture.organization_a),
                json={"expected_version": approval["version"], "reason": "检查事务原子性"},
            )
    finally:
        event.remove(model, "before_insert", fail_insert)
    with fixture.session_factory() as session:
        row = session.scalar(
            select(ApprovalRequest).where(
                ApprovalRequest.organization_id == fixture.organization_a,
                ApprovalRequest.id == UUID(approval["id"]),
            )
        )
        assert row.status == "PENDING" and row.task_id is None
        assert (
            session.scalar(
                select(func.count())
                .select_from(Task)
                .where(
                    Task.organization_id == fixture.organization_a,
                    Task.task_type == f"AI_FOLLOW_UP:{approval['id']}",
                )
            )
            == 0
        )
