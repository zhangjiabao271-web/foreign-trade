from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.sales.models import Quotation, QuotationVersion
from app.sales.services import QuotationCommandService
from app.work.models import Activity
from sqlalchemy import event, func, select
from test_quotation_vertical_slice import create_commercial_inputs, post_ok, state_request

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration
ACTIONS = ("submit", "approve", "send", "accept", "reject", "expire")


def advance(f, quote_id, action):
    prerequisites = {
        "submit": (),
        "approve": ("submit",),
        "send": ("submit", "approve"),
        "accept": ("submit", "approve", "send"),
        "reject": ("submit", "approve", "send"),
        "expire": (),
    }
    for step in prerequisites[action]:
        post_ok(f, f"/api/v1/quotations/{quote_id}/{step}", "quotation-manager")


def setup(f, action):
    data, _, _ = create_commercial_inputs(f)
    quote_id = post_ok(f, "/api/v1/quotations", "quotation-manager", data, 201)["id"]
    advance(f, quote_id, action)
    return quote_id, state_request(f, quote_id)


def counts(f):
    with f.session_factory() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (Activity, AuditLog, OutboxEvent, IdempotencyKey)
        )


def invoke(
    f, quote_id, action, body, key="decision", subject="quotation-manager", organization=None
):
    headers = f.headers(subject, organization or f.organization_a)
    if key is not None:
        headers["Idempotency-Key"] = key
    return f.client.post(f"/api/v1/quotations/{quote_id}/{action}", json=body, headers=headers)


def context(f, permissions=frozenset(Permission)):
    return RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=permissions,
        request_id=uuid4(),
    )


@pytest.mark.parametrize("action", ACTIONS)
def test_required_guards_success_replay_conflict_and_permissions(quotation_fixture, action):
    f = quotation_fixture
    quote_id, request = setup(f, action)
    body = request.model_dump(mode="json")
    before = counts(f)
    for invalid in (
        None,
        {},
        {"expected_version_id": body["expected_version_id"]},
        {**body, "expected_version": 0},
        {**body, "status": "ACCEPTED"},
    ):
        assert invoke(f, quote_id, action, invalid).status_code == 422
    for key in (None, "", "  ", "x" * 256):
        assert invoke(f, quote_id, action, body, key).status_code == 422
    assert counts(f) == before
    first = invoke(f, quote_id, action, body)
    assert first.status_code == 200, first.text
    after = counts(f)
    assert invoke(f, quote_id, action, body).json() == first.json()
    assert counts(f) == after
    conflict = invoke(
        f, quote_id, action, {**body, "expected_version": request.expected_version + 1}
    )
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert invoke(f, quote_id, action, body, subject="quotation-finance").status_code == 403
    assert invoke(
        f, quote_id, action, body, subject="quotation-other", organization=f.organization_b
    ).status_code == (403 if action == "approve" else 404)
    with pytest.raises(ApiProblem) as denied:
        getattr(QuotationCommandService(f.session_factory), action)(
            context(f, frozenset()), UUID(quote_id), request, key="decision"
        )
    assert denied.value.status == 403
    assert counts(f) == after
    # Replay uses current permissions, not a stored privileged response.
    projected = getattr(QuotationCommandService(f.session_factory), action)(
        context(f, frozenset(Permission) - {Permission.PROFIT_READ}),
        UUID(quote_id),
        request,
        key="decision",
    )
    assert projected.total_cost is None and projected.payment_terms is None
    assert projected.items[0].unit_cost is None
    assert counts(f) == after


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("change", ("revision", "row_version"))
def test_stale_view_cannot_act_on_another_actionable_version(quotation_fixture, action, change):
    f = quotation_fixture
    quote_id, request = setup(f, action)
    if change == "revision":
        post_ok(f, f"/api/v1/quotations/{quote_id}/revisions", "quotation-manager", {}, 201)
        advance(f, quote_id, action)
    else:
        with f.session_factory.begin() as session:
            session.get(QuotationVersion, request.expected_version_id).version += 1
    before = counts(f)
    result = invoke(f, quote_id, action, request.model_dump(mode="json"))
    assert result.status_code == 409
    assert result.json()["code"] == "VERSION_CONFLICT"
    assert counts(f) == before
    fresh = state_request(f, quote_id)
    assert invoke(f, quote_id, action, fresh.model_dump(mode="json")).status_code == 200


@pytest.mark.parametrize("action", ACTIONS)
def test_replay_keeps_original_version_and_rejects_deleted_quote(quotation_fixture, action):
    f = quotation_fixture
    quote_id, request = setup(f, action)
    body = request.model_dump(mode="json")
    first = invoke(f, quote_id, action, body)
    assert first.status_code == 200
    if action != "accept":
        post_ok(f, f"/api/v1/quotations/{quote_id}/revisions", "quotation-manager", {}, 201)
    before = counts(f)
    replay = invoke(f, quote_id, action, body)
    assert replay.status_code == 200
    assert replay.json()["id"] == first.json()["id"]
    assert replay.json()["status"] == ("ACCEPTED" if action == "accept" else "SUPERSEDED")
    assert counts(f) == before
    with f.session_factory.begin() as session:
        session.get(Quotation, UUID(quote_id)).deleted_at = datetime.now(UTC)
    assert invoke(f, quote_id, action, body).status_code == 404
    assert counts(f) == before


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("table", ("activities", "audit_logs", "outbox_events"))
def test_decision_evidence_failure_rolls_back_receipt_and_state(quotation_fixture, action, table):
    f = quotation_fixture
    quote_id, request = setup(f, action)
    before = counts(f)
    with f.session_factory() as session:
        old = session.get(QuotationVersion, request.expected_version_id)
        old_status, old_approved_at = old.status, old.approved_at

    def fail(_connection, _cursor, statement, *_args):
        if statement.lower().startswith(f"insert into {table} "):
            raise RuntimeError("injected state evidence failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected state evidence failure"):
            getattr(QuotationCommandService(f.session_factory), action)(
                context(f), UUID(quote_id), request, key="recover"
            )
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert counts(f) == before
    with f.session_factory() as session:
        row = session.get(QuotationVersion, request.expected_version_id)
        assert (row.status, row.version, row.approved_at) == (
            old_status,
            request.expected_version,
            old_approved_at,
        )
    assert (
        invoke(f, quote_id, action, request.model_dump(mode="json"), "recover").status_code == 200
    )


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("same_key", (True, False))
def test_concurrent_commands_replay_or_reject_stale_decision(quotation_fixture, action, same_key):
    f = quotation_fixture
    quote_id, request = setup(f, action)
    before = counts(f)

    def run(index):
        try:
            result = getattr(QuotationCommandService(f.session_factory), action)(
                context(f), UUID(quote_id), request, key="race" if same_key else f"race-{index}"
            )
            return str(result.id)
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, (0, 1)))
    after = counts(f)
    assert after[-1] == before[-1] + 1
    assert after[:-1] == tuple(value + (2 if action == "accept" else 1) for value in before[:-1])
    if same_key:
        assert results[0] == results[1]
    else:
        assert results.count("VERSION_CONFLICT") == 1
