from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.crm.models import Opportunity
from app.identity.enums import MembershipRole
from app.inquiries.models import Inquiry
from app.inquiries.services import InquiryCommandService
from app.inquiries.text_review import InquiryTextReviewRequest, InquiryTextReviewService
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.work.models import Activity
from sqlalchemy import event, func, select
from test_document_review import reviewer
from test_quotation_vertical_slice import create_opportunity, post_ok

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration


def setup(f):
    company, opportunity = create_opportunity(f)
    return {
        "company_id": company,
        "opportunity_id": opportunity,
        "customer_reference": "RFQ-ID",
        "description": "Confidential original inquiry",
        "received_at": datetime.now(UTC).isoformat(),
    }


def request(f, body, key, subject="quotation-sales", organization=None):
    headers = f.headers(subject, organization or f.organization_a)
    if key is not None:
        headers["Idempotency-Key"] = key
    return f.client.post("/api/v1/inquiries", json=body, headers=headers)


def counts(f):
    with f.session_factory() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (Inquiry, Activity, AuditLog, OutboxEvent, IdempotencyKey)
        )


def test_retry_recovers_quoted_inquiry_without_resetting_crm_or_description(quotation_fixture):
    f = quotation_fixture
    body = setup(f)
    original = deepcopy(body)
    _, sales = reviewer(f, MembershipRole.SALES)
    created = InquiryCommandService(f.session_factory).create(sales, body, key="once")
    assert body == original and created.description is None
    product = post_ok(
        f,
        "/api/v1/products",
        "quotation-manager",
        {
            "sku": "INQUIRY-RETRY",
            "name": "Business product",
            "unit": "set",
            "standard_cost": "5",
            "cost_currency": "CNY",
        },
        201,
    )
    post_ok(
        f,
        "/api/v1/quotations",
        "quotation-sales",
        {
            "inquiry_id": str(created.id),
            "currency_code": "CNY",
            "base_currency_code": "USD",
            "exchange_rate": "0.14",
            "valid_until": (datetime.now(UTC) + timedelta(days=30)).date().isoformat(),
            "items": [{"product_id": product["id"], "quantity": "1", "unit_price": "10"}],
        },
        201,
    )
    before = counts(f)
    replay = request(f, body, "once")
    assert replay.status_code == 201
    assert replay.json()["id"] == str(created.id) and replay.json()["status"] == "QUOTING"
    assert replay.json()["description"] is None and replay.json()["customer_reference"] == "RFQ-ID"
    assert counts(f) == before
    conflict = request(f, {**body, "description": "Changed"}, "once")
    assert conflict.status_code == 409 and conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"
    assert request(f, body, "fresh").status_code == 409
    with f.session_factory() as session:
        stored = session.get(Inquiry, created.id)
        assert stored.description == original["description"]
        assert stored.received_at == datetime.fromisoformat(body["received_at"])
        assert session.get(Opportunity, UUID(body["opportunity_id"])).status == "QUOTING"
    assert counts(f) == before


@pytest.mark.parametrize("role", list(MembershipRole))
def test_live_role_and_service_permission_apply_to_creation_replay(quotation_fixture, role):
    f = quotation_fixture
    body = setup(f)
    assert request(f, body, "shared").status_code == 201
    subject, context = reviewer(f, role)
    before = counts(f)
    replay = request(f, body, "shared", subject)
    service = InquiryCommandService(f.session_factory)
    if Permission.INQUIRY_WRITE in context.permissions:
        assert replay.status_code == 201
        result = service.create(context, body, key="shared")
        expected = body["description"] if Permission.PROFIT_READ in context.permissions else None
        assert result.description == replay.json()["description"] == expected
    else:
        assert replay.status_code == 403
        with pytest.raises(ApiProblem) as denied:
            service.create(context, body, key="shared")
        assert denied.value.status == 403
    assert counts(f) == before


def test_keys_tenant_scope_and_unkeyed_new_registration_semantics(quotation_fixture):
    f = quotation_fixture
    body = setup(f)
    first = request(f, body, "scoped")
    assert first.status_code == 201
    before = counts(f)
    for key in ("", "   ", "x" * 256):
        assert request(f, body, key).status_code == 422
    assert request(f, body, "scoped", "quotation-other", f.organization_b).status_code == 404
    assert counts(f) == before
    one, two = request(f, body, None), request(f, body, None)
    assert one.status_code == two.status_code == 201
    assert len({one.json()["id"], two.json()["id"], first.json()["id"]}) == 3


def test_review_and_deleted_resource_are_rechecked_on_replay(quotation_fixture):
    f = quotation_fixture
    body = setup(f)
    created = request(f, body, "reviewed").json()
    record_id = UUID(created["id"])
    _, high = reviewer(f, MembershipRole.MANAGER)
    service = InquiryTextReviewService(f.session_factory)
    for release in (True, False):
        snapshot = service.inspect(high, record_id)
        service.decide(
            high,
            record_id,
            InquiryTextReviewRequest(
                expected_version=snapshot.version,
                content_digest=snapshot.content_digest,
                release=release,
                confirmed=True,
                reason="Reviewed exact source",
            ),
            key=str(uuid4()),
        )
        before = counts(f)
        replay = request(f, body, "reviewed")
        assert replay.status_code == 201
        assert replay.json()["description"] == (body["description"] if release else None)
        assert counts(f) == before
    with f.session_factory.begin() as session:
        session.get(Inquiry, record_id).deleted_at = datetime.now(UTC)
    assert request(f, body, "reviewed").status_code == 404
    assert counts(f) == before


@pytest.mark.parametrize("table", ("activities", "audit_logs", "outbox_events"))
def test_creation_evidence_failure_rolls_back_inquiry_progress_and_key(quotation_fixture, table):
    f = quotation_fixture
    body = setup(f)
    _, context = reviewer(f, MembershipRole.SALES)
    before = counts(f)

    def fail(_connection, _cursor, statement, *_args):
        if statement.lower().startswith(f"insert into {table} "):
            raise RuntimeError("injected inquiry evidence failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected inquiry evidence failure"):
            InquiryCommandService(f.session_factory).create(context, body, key="recover")
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert counts(f) == before
    with f.session_factory() as session:
        assert session.get(Opportunity, UUID(body["opportunity_id"])).status == "OPEN"
    assert request(f, body, "recover").status_code == 201
    before = counts(f)
    assert request(f, body, "recover").status_code == 201
    assert counts(f) == before


@pytest.mark.parametrize("mode", ("same", "changed", "new"))
def test_concurrent_registration_distinguishes_retry_from_new_inquiry(quotation_fixture, mode):
    f = quotation_fixture
    body = setup(f)
    _, context = reviewer(f, MembershipRole.SALES)
    before = counts(f)

    def run(index):
        data = {**body, "description": "Different inquiry"} if mode == "changed" and index else body
        try:
            return str(
                InquiryCommandService(f.session_factory)
                .create(context, data, key=f"new-{index}" if mode == "new" else "parallel")
                .id
            )
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, (0, 1)))
    after = counts(f)
    expected = 2 if mode == "new" else 1
    assert after[0] == before[0] + expected and after[-1] == before[-1] + expected
    if mode == "same":
        assert results[0] == results[1]
    elif mode == "changed":
        assert results.count("IDEMPOTENCY_CONFLICT") == 1
    else:
        assert len(set(results)) == 2
