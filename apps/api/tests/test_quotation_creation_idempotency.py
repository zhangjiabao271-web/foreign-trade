from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.crm.models import Opportunity
from app.inquiries.models import Inquiry
from app.platform.models import AuditLog, DocumentSequence, IdempotencyKey, OutboxEvent
from app.sales.models import Quotation, QuotationItem, QuotationVersion
from app.sales.services import QuotationCommandService
from app.work.models import Activity
from sqlalchemy import event, func, select
from test_quotation_vertical_slice import create_commercial_inputs, post_ok

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration


def setup(f):
    body, _, _ = create_commercial_inputs(f)
    # Sales can inherit a same-currency product cost without receiving or submitting it.
    body["currency_code"] = "CNY"
    body["items"] = [
        {
            "product_id": body["items"][0]["product_id"],
            "quantity": "3.3333",
            "unit_price": "19.9955",
        }
    ]
    return body


def context(f):
    return RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset({Permission.QUOTATION_WRITE}),
        request_id=uuid4(),
    )


def counts(f):
    with f.session_factory() as session:
        return (
            *[
                session.scalar(select(func.count()).select_from(model))
                for model in (
                    Quotation,
                    QuotationVersion,
                    QuotationItem,
                    Activity,
                    AuditLog,
                    OutboxEvent,
                    IdempotencyKey,
                )
            ],
            session.scalar(select(func.sum(DocumentSequence.next_value))),
        )


def request(f, body, key, subject="quotation-sales", organization=None):
    headers = f.headers(subject, organization or f.organization_a)
    if key is not None:
        headers["Idempotency-Key"] = key
    return f.client.post("/api/v1/quotations", json=body, headers=headers)


def test_creation_recovers_current_quote_after_revision_without_new_facts(quotation_fixture):
    f = quotation_fixture
    body = setup(f)
    first = request(f, body, "create-once")
    assert first.status_code == 201, first.text
    baseline = counts(f)
    assert request(f, body, "create-once").json() == first.json()
    assert counts(f) == baseline
    conflict = request(f, {**body, "exchange_rate": "1.2"}, "create-once")
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    quote_id = first.json()["id"]
    revision = post_ok(f, f"/api/v1/quotations/{quote_id}/revisions", "quotation-sales", {}, 201)
    baseline = counts(f)
    replay = request(f, body, "create-once")
    assert replay.status_code == 201
    assert replay.json()["id"] == quote_id
    assert replay.json()["current_version"]["id"] == revision["id"]
    assert len(replay.json()["versions"]) == 2
    for version in replay.json()["versions"]:
        assert version["total_cost"] is None
        assert version["payment_terms"] is None
        assert version["items"][0]["unit_cost"] is None
    assert counts(f) == baseline
    with f.session_factory() as session:
        stored = session.scalar(
            select(IdempotencyKey).where(IdempotencyKey.scope == "quotation.create")
        )
        assert stored.status == "COMPLETED"
        assert stored.resource_id == UUID(quote_id)
        assert stored.resource_type == "quotation"


def test_creation_authority_tenant_keys_and_legacy_rule(quotation_fixture):
    f = quotation_fixture
    body = setup(f)
    assert request(f, body, "scoped").status_code == 201
    baseline = counts(f)
    for key in ("", "   ", "x" * 256):
        assert request(f, body, key).status_code == 422
    assert request(f, body, "scoped", "quotation-finance").status_code == 403
    assert request(f, body, "scoped", "quotation-other", f.organization_b).status_code == 404
    with pytest.raises(ApiProblem) as denied:
        QuotationCommandService(f.session_factory).create(
            replace(context(f), permissions=frozenset()), body, key="scoped"
        )
    assert denied.value.status == 403
    for key in (None, "new-command"):
        duplicate = request(f, body, key)
        assert duplicate.status_code == 409
        assert duplicate.json()["code"] == "INQUIRY_ALREADY_QUOTED"
    assert counts(f) == baseline


def test_creation_replay_rechecks_cost_authority_and_live_resource(quotation_fixture):
    f = quotation_fixture
    body = setup(f)
    priced = deepcopy(body)
    priced["items"][0]["unit_cost"] = "8.0000"
    created = request(f, priced, "priced", "quotation-manager")
    assert created.status_code == 201
    baseline = counts(f)
    assert request(f, priced, "priced").status_code == 403
    assert counts(f) == baseline
    with f.session_factory.begin() as session:
        session.get(Quotation, UUID(created.json()["id"])).deleted_at = datetime.now(UTC)
    assert request(f, priced, "priced", "quotation-manager").status_code == 404
    assert counts(f) == baseline


@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
def test_creation_failure_rolls_back_key_number_and_crm_facts(quotation_fixture, table):
    f = quotation_fixture
    body = setup(f)
    original = deepcopy(body)
    baseline = counts(f)
    with f.session_factory() as session:
        inquiry = session.get(Inquiry, UUID(body["inquiry_id"]))
        opportunity_id = inquiry.opportunity_id
        states = (inquiry.status, session.get(Opportunity, opportunity_id).status)

    def fail(_connection, _cursor, statement, *_args):
        if statement.lower().startswith(f"insert into {table} "):
            raise RuntimeError("injected creation evidence failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected creation evidence failure"):
            QuotationCommandService(f.session_factory).create(context(f), body, key="recover")
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert body == original
    assert counts(f) == baseline
    with f.session_factory() as session:
        assert (
            session.get(Inquiry, UUID(body["inquiry_id"])).status,
            session.get(Opportunity, opportunity_id).status,
        ) == states
    assert request(f, body, "recover").status_code == 201
    baseline = counts(f)
    assert request(f, body, "recover").status_code == 201
    assert counts(f) == baseline


@pytest.mark.parametrize("mode", ["same", "changed", "different-keys"])
def test_concurrent_creation_keeps_one_quote_and_receipt(quotation_fixture, mode):
    f = quotation_fixture
    body = setup(f)
    baseline = counts(f)

    def create(index):
        data = {**body, "exchange_rate": "1.2"} if mode == "changed" and index else body
        try:
            quote = QuotationCommandService(f.session_factory).create(
                context(f), data, key=f"key-{index}" if mode == "different-keys" else "same"
            )
            return str(quote.id)
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, (0, 1)))
    after = counts(f)
    assert after[:3] == tuple(value + 1 for value in baseline[:3])
    assert after[6] == baseline[6] + 1
    with f.session_factory() as session:
        for model, field in ((Activity, Activity.activity_type), (AuditLog, AuditLog.action)):
            assert (
                session.scalar(
                    select(func.count()).select_from(model).where(field == "quotation.created")
                )
                == 1
            )
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "quotation.created.v1")
            )
            == 1
        )
    if mode == "same":
        assert results[0] == results[1]
    else:
        assert (
            results.count("IDEMPOTENCY_CONFLICT" if mode == "changed" else "INQUIRY_ALREADY_QUOTED")
            == 1
        )
