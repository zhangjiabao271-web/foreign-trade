from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.sales.models import QuotationItem, QuotationVersion
from app.sales.services import QuotationCommandService
from app.work.models import Activity
from sqlalchemy import event, func, select
from test_quotation_vertical_slice import create_commercial_inputs, post_ok

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration


def setup(f):
    payload, _, _ = create_commercial_inputs(f)
    quote = post_ok(f, "/api/v1/quotations", "quotation-manager", payload, 201)
    return quote, {
        "expected_version_id": quote["current_version"]["id"],
        "exchange_rate": "1.12345678",
    }


def context(f):
    return RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset({Permission.QUOTATION_WRITE}),
        request_id=uuid4(),
    )


def counts(f):
    with f.session_factory() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (
                QuotationVersion,
                QuotationItem,
                Activity,
                AuditLog,
                OutboxEvent,
                IdempotencyKey,
            )
        )


def request(f, quote, body, key, subject="quotation-sales", organization=None):
    headers = f.headers(subject, organization or f.organization_a)
    if key is not None:
        headers["Idempotency-Key"] = key
    return f.client.post(f"/api/v1/quotations/{quote['id']}/revisions", headers=headers, json=body)


def test_revision_replay_conflict_and_later_revision_keep_original_id(quotation_fixture):
    f = quotation_fixture
    quote, body = setup(f)
    first = request(f, quote, body, "revision-once")
    assert first.status_code == 201, first.text
    baseline = counts(f)
    assert request(f, quote, body, "revision-once").json() == first.json()
    conflict = request(f, quote, {**body, "exchange_rate": "1.2"}, "revision-once")
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    stale = request(f, quote, body, "another-editor")
    assert stale.status_code == 409
    assert stale.json()["code"] == "VERSION_CONFLICT"
    assert counts(f) == baseline
    later = request(f, quote, {"expected_version_id": first.json()["id"]}, "later")
    assert later.status_code == 201
    baseline = counts(f)
    replay = request(f, quote, body, "revision-once").json()
    assert replay["id"] == first.json()["id"]
    assert replay["status"] == "SUPERSEDED"
    assert replay["items"] == first.json()["items"]
    assert counts(f) == baseline
    with f.session_factory() as session:
        audit = session.scalar(
            select(AuditLog).where(AuditLog.target_id == UUID(first.json()["id"]))
        )
        assert audit.before_data["status"] == "DRAFT"
        key = session.scalar(
            select(IdempotencyKey).where(IdempotencyKey.idempotency_key == "revision-once")
        )
        assert key.status == "COMPLETED"
        assert key.resource_id == UUID(first.json()["id"])


def test_permissions_foreign_quote_invalid_keys_and_legacy_boundary(quotation_fixture):
    f = quotation_fixture
    quote, body = setup(f)
    baseline = counts(f)
    for key in ("", " ", "x" * 256):
        assert request(f, quote, body, key).status_code == 422
    assert request(f, quote, body, "denied", "quotation-finance").status_code == 403
    assert (
        request(f, quote, body, "foreign", "quotation-other", f.organization_b).status_code == 404
    )
    with pytest.raises(ApiProblem) as denied:
        QuotationCommandService(f.session_factory).revise(
            replace(context(f), permissions=frozenset()), UUID(quote["id"]), body, key="denied"
        )
    assert denied.value.status == 403
    assert counts(f) == baseline
    # Existing clients without either optional guard still issue distinct current-version commands.
    one = request(f, quote, {}, None)
    two = request(f, quote, {}, None)
    assert one.status_code == two.status_code == 201
    assert one.json()["id"] != two.json()["id"]


@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
def test_revision_evidence_failure_rolls_back_version_and_key(quotation_fixture, table):
    f = quotation_fixture
    quote, body = setup(f)
    baseline = counts(f)
    original = deepcopy(body)

    def fail(_connection, _cursor, statement, *_args):
        if statement.lower().startswith(f"insert into {table} "):
            raise RuntimeError("injected evidence failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected evidence failure"):
            QuotationCommandService(f.session_factory).revise(
                context(f), UUID(quote["id"]), body, key="retry"
            )
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert body == original
    assert counts(f) == baseline
    with f.session_factory() as session:
        old = session.get(QuotationVersion, UUID(body["expected_version_id"]))
        assert old.is_current and old.status == "DRAFT"
    assert request(f, quote, body, "retry").status_code == 201


@pytest.mark.parametrize("mode", ["same", "changed", "different-keys"])
def test_concurrent_revision_guards(quotation_fixture, mode):
    f = quotation_fixture
    quote, body = setup(f)
    baseline = counts(f)

    def revise(index):
        data = {**body, "exchange_rate": "1.2"} if mode == "changed" and index else body
        try:
            version = QuotationCommandService(f.session_factory).revise(
                context(f),
                UUID(quote["id"]),
                data,
                key=f"key-{index}" if mode == "different-keys" else "same",
            )
            return str(version.id)
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(revise, (0, 1)))
    after = counts(f)
    assert after == tuple(value + (2 if index == 1 else 1) for index, value in enumerate(baseline))
    if mode == "same":
        assert results[0] == results[1]
    else:
        assert (
            results.count("IDEMPOTENCY_CONFLICT" if mode == "changed" else "VERSION_CONFLICT") == 1
        )
