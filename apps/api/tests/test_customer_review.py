from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.platform.records import AuditRecorder, OutboxRecorder
from app.sales.models import QuotationVersion
from app.sales.services import QuotationCommandService
from app.work.models import Activity
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_quotation_vertical_slice import create_commercial_inputs, post_ok, table_counts

pytest_plugins = ("test_quotation_vertical_slice",)


def prepare(f, sent=True):
    request, _, _ = create_commercial_inputs(f)
    quote = post_ok(f, "/api/v1/quotations", "quotation-manager", request, 201)
    if sent:
        for action, subject in (
            ("submit", "quotation-sales"),
            ("approve", "quotation-manager"),
            ("send", "quotation-sales"),
        ):
            post_ok(f, f"/api/v1/quotations/{quote['id']}/{action}", subject)
    return quote, {
        "expected_version_id": quote["current_version"]["id"],
        "reason": "Customer confirmed review by email REF-24",
    }


def record(f, quote, body, key="review", subject="quotation-sales", organization=None):
    return f.client.post(
        f"/api/v1/quotations/{quote['id']}/mark-customer-review",
        headers=f.headers(subject, organization or f.organization_a) | {"Idempotency-Key": key},
        json=body,
    )


def test_review_is_atomic_idempotent_and_preserves_snapshots(quotation_fixture):
    f = quotation_fixture
    quote, body = prepare(f)
    before = table_counts(f)
    response = record(f, quote, body)
    assert response.status_code == 200, response.text
    assert response.json() == {"id": body["expected_version_id"]}
    assert table_counts(f) == tuple(value + 1 for value in before)
    saved = table_counts(f)
    assert record(f, quote, body).json() == response.json()
    assert table_counts(f) == saved
    assert record(f, quote, body | {"reason": "Different"}).json()["code"] == "IDEMPOTENCY_CONFLICT"
    with f.session_factory() as session:
        version = session.get(QuotationVersion, UUID(body["expected_version_id"]))
        assert version.status == "CUSTOMER_REVIEW"
        assert str(version.total) == quote["current_version"]["total"]
        audit = session.scalar(
            select(AuditLog).where(AuditLog.action == "quotation.customer_review_started")
        )
        assert audit.reason == body["reason"]
        assert audit.before_data["status"] == "SENT"
        event = session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "quotation.customer_review_started.v1"
            )
        )
        assert event.organization_id == f.organization_a
        assert "reason" not in event.payload
    post_ok(f, f"/api/v1/quotations/{quote['id']}/accept", "quotation-sales")
    saved = table_counts(f)
    assert record(f, quote, body).json() == response.json()
    assert table_counts(f) == saved
    assert record(f, quote, body, "new-key").status_code == 409


def test_review_rejects_wrong_state_version_tenant_and_role(quotation_fixture):
    f = quotation_fixture
    quote, body = prepare(f, sent=False)
    before = table_counts(f)
    assert record(f, quote, body).json()["code"] == "INVALID_STATE_TRANSITION"
    assert (
        record(f, quote, body | {"expected_version_id": str(uuid4())}).json()["code"]
        == "VERSION_CONFLICT"
    )
    assert record(f, quote, body, subject="quotation-finance").status_code == 403
    assert (
        record(f, quote, body, subject="quotation-other", organization=f.organization_b).status_code
        == 404
    )
    for invalid in (
        {"reason": " "},
        {"reason": "a" * 501},
        {"expected_version_id": "bad"},
        {"status": "CUSTOMER_REVIEW"},
    ):
        assert record(f, quote, body | invalid).status_code == 422
    assert table_counts(f) == before
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(),
        request_id=uuid4(),
    )
    with pytest.raises(ApiProblem) as denied:
        QuotationCommandService(f.session_factory).mark_customer_review(
            context, UUID(quote["id"]), body, key="denied"
        )
    assert denied.value.status == 403


@pytest.mark.parametrize("recorder", [Activity, AuditRecorder, OutboxRecorder])
def test_review_evidence_failure_rolls_back_state_and_key(quotation_fixture, monkeypatch, recorder):
    f = quotation_fixture
    quote, body = prepare(f)
    before = table_counts(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )

    def fail(*args, **kwargs):
        raise RuntimeError("review evidence failed")

    if recorder is Activity:
        original = Session.add

        def add(session, value, *args, **kwargs):
            if isinstance(value, Activity):
                fail()
            return original(session, value, *args, **kwargs)

        monkeypatch.setattr(Session, "add", add)
    else:
        monkeypatch.setattr(recorder, "record", fail)
    with pytest.raises(RuntimeError, match="review evidence failed"):
        QuotationCommandService(f.session_factory).mark_customer_review(
            context, UUID(quote["id"]), body, key="rollback"
        )
    assert table_counts(f) == before
    with f.session_factory() as session:
        assert session.get(QuotationVersion, UUID(body["expected_version_id"])).status == "SENT"
        assert (
            session.scalar(
                select(IdempotencyKey).where(
                    IdempotencyKey.scope == "quotation.customer_review_started"
                )
            )
            is None
        )


def test_competing_review_commands_have_one_fact_and_stale_revision_is_rejected(quotation_fixture):
    f = quotation_fixture
    quote, body = prepare(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    before = table_counts(f)

    def run(index):
        try:
            QuotationCommandService(f.session_factory).mark_customer_review(
                context, UUID(quote["id"]), body, key=f"concurrent-{index}"
            )
            return "ok"
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, range(2))) == ["INVALID_STATE_TRANSITION", "ok"]
    assert table_counts(f) == tuple(value + 1 for value in before)
    post_ok(f, f"/api/v1/quotations/{quote['id']}/revisions", "quotation-sales", {}, 201)
    for action, subject in (
        ("submit", "quotation-sales"),
        ("approve", "quotation-manager"),
        ("send", "quotation-sales"),
    ):
        post_ok(f, f"/api/v1/quotations/{quote['id']}/{action}", subject)
    assert record(f, quote, body, "stale").json()["code"] == "VERSION_CONFLICT"
