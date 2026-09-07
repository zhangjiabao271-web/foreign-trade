from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from threading import Barrier

import pytest
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission, permissions_for_role
from app.finance.models import Payment
from app.finance.payment_text_review import PaymentTextReviewRequest, PaymentTextReviewService
from app.finance.repositories import PaymentRepository
from app.finance.services import PaymentQueryService
from app.identity.enums import MembershipRole
from app.platform.models import AuditLog, OutboxEvent
from app.work.models import Activity
from legacy_migration import verify_legacy_guard, verify_legacy_upgrade
from sqlalchemy import event
from test_document_review import counts, reviewer
from test_finance_vertical_slice import payment
from test_order_procurement_vertical_slice import create_confirmed_order

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def seed(f):
    from uuid import UUID

    order, _, _ = create_confirmed_order(f)
    record_id = UUID(payment(f, order, "100")["id"])
    with f.session_factory.begin() as session:
        row = session.get(Payment, record_id)
        row.notes = "Internal cost 350"
        row.reference = "RECEIPT-2026-001"
    return record_id


def decision(snapshot, release=True):
    return PaymentTextReviewRequest(
        expected_version=snapshot.version,
        content_digest=snapshot.content_digest,
        release=release,
        reason="Reviewed all original case text",
        confirmed=True,
    )


def projection(f, context, record_id):
    with f.session_factory() as session:
        query = PaymentQueryService(PaymentRepository(session))
        result = query.get(context, record_id)[0]
        page = [item[0] for item in query.list(context, limit=50)]
        assert next(row for row in page if row.id == record_id).notes == result.notes
        assert not session.dirty
        return result


@pytest.mark.parametrize("role", list(MembershipRole))
def test_payment_source_role_service_http_and_review_replay(quotation_fixture, role):
    f = quotation_fixture
    record_id = seed(f)
    subject, context = reviewer(f, role)
    headers = f.headers(subject, f.organization_a)
    privileged = Permission.PROFIT_READ in context.permissions
    readable = Permission.PAYMENT_READ in context.permissions
    response = f.client.get(f"/api/v1/payments/{record_id}", headers=headers)
    if not readable:
        assert response.status_code == 403
        return
    assert response.status_code == 200, response.text
    result = projection(f, context, record_id)
    assert result.notes == response.json()["notes"] == ("Internal cost 350" if privileged else None)
    assert str(result.amount) == "100.0000"
    assert result.reference == "RECEIPT-2026-001"
    assert result.content_visible is privileged
    service = PaymentTextReviewService(f.session_factory)
    path = f"/api/v1/payments/{record_id}/text-review"
    before = counts(f)
    if not privileged:
        request = PaymentTextReviewRequest(
            expected_version=1,
            content_digest="a" * 64,
            release=True,
            confirmed=True,
            reason="Unauthorized",
        )
        assert f.client.get(path, headers=headers).status_code == 403
        assert (
            f.client.post(
                path, headers=headers | {"Idempotency-Key": "denied"}, json=request.model_dump()
            ).status_code
            == 403
        )
        with pytest.raises(ApiProblem):
            service.decide(context, record_id, request, key="denied")
        assert counts(f) == before
        return
    original = service.inspect(context, record_id)
    request = decision(original)
    response = f.client.post(
        path, headers=headers | {"Idempotency-Key": "open"}, json=request.model_dump()
    )
    assert response.status_code == 200, response.text
    opened = service.inspect(context, record_id)
    assert opened.released and opened.version == original.version + 1
    low = replace(context, permissions=permissions_for_role(MembershipRole.OPERATIONS))
    visible = projection(f, low, record_id)
    assert visible.notes == "Internal cost 350"
    service.decide(context, record_id, decision(opened, False), key="close")
    assert not service.decide(context, record_id, request, key="open").released
    assert projection(f, low, record_id).notes is None
    assert counts(f) == [value + 2 for value in before]
    with pytest.raises(ApiProblem) as foreign:
        service.inspect(replace(context, organization_id=f.organization_b), record_id)
    assert foreign.value.status == 404
    with pytest.raises(ApiProblem) as missing_read:
        service.inspect(
            replace(context, permissions=frozenset({Permission.PROFIT_READ})), record_id
        )
    assert missing_read.value.status == 403


@pytest.mark.parametrize("stage", [Activity, AuditLog, OutboxEvent])
def test_payment_review_failure_rolls_back_every_record(quotation_fixture, stage):
    f = quotation_fixture
    record_id = seed(f)
    _, context = reviewer(f)
    service = PaymentTextReviewService(f.session_factory)
    original = service.inspect(context, record_id)
    before = counts(f)

    def fail(*args, **kwargs):
        raise RuntimeError("injected review failure")

    event.listen(stage, "before_insert", fail)
    try:
        with pytest.raises(RuntimeError, match="injected"):
            service.decide(context, record_id, decision(original), key="failed")
    finally:
        event.remove(stage, "before_insert", fail)
    assert service.inspect(context, record_id) == original
    assert counts(f) == before


def test_payment_content_restoration_and_deleted_owner_do_not_restore_release(quotation_fixture):
    f = quotation_fixture
    record_id = seed(f)
    _, context = reviewer(f)
    service = PaymentTextReviewService(f.session_factory)
    original = service.inspect(context, record_id)
    opened = service.decide(context, record_id, decision(original), key="open")
    for text in ("changed", "Internal cost 350"):
        with f.session_factory.begin() as session:
            session.get(Payment, record_id).notes = text
    assert not service.inspect(context, record_id).released
    with pytest.raises(ApiProblem) as stale:
        service.decide(context, record_id, decision(opened), key="stale")
    assert stale.value.code == "VERSION_CONFLICT"
    with f.session_factory.begin() as session:
        session.get(Payment, record_id).deleted_at = datetime.now(UTC)
    with pytest.raises(ApiProblem) as deleted:
        service.decide(context, record_id, decision(original), key="open")
    assert deleted.value.status == 404


def test_payment_legacy_upgrade_preserves_confidential_facts(quotation_fixture):
    from sqlalchemy.orm import Session

    f = quotation_fixture
    record_id = seed(f)

    def check(target):
        with Session(target) as session:
            row = session.get(Payment, record_id)
            assert row.notes == "Internal cost 350"
            assert row.reference == "RECEIPT-2026-001"
            assert row.reviewed_by is row.reviewed_at is row.released_digest is None

    verify_legacy_upgrade(f.engine, "20260906_0027", check=check)
    verify_legacy_guard(f.engine, "20260906_0028", "20260906_0027", "Payment evidence exists")


def test_payment_review_competing_decisions_and_confirmation(quotation_fixture):
    f = quotation_fixture
    record_id = seed(f)
    _, context = reviewer(f)
    service = PaymentTextReviewService(f.session_factory)
    original = service.inspect(context, record_id)
    before = counts(f)
    with pytest.raises(ApiProblem) as unconfirmed:
        service.decide(
            context,
            record_id,
            decision(original).model_copy(update={"confirmed": False}),
            key="unconfirmed",
        )
    assert unconfirmed.value.code == "CONFIRMATION_REQUIRED"
    barrier = Barrier(2)

    def race(release):
        barrier.wait(timeout=10)
        try:
            return service.decide(
                context, record_id, decision(original, release), key=f"race-{release}"
            )
        except ApiProblem as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(race, (True, False)))
    errors = [row for row in results if isinstance(row, ApiProblem)]
    assert len(errors) == 1 and errors[0].code == "VERSION_CONFLICT"
    assert counts(f) == [value + 1 for value in before]


def test_payment_write_replays_and_reversal_never_inherit_text_release(quotation_fixture):
    from decimal import Decimal

    from app.finance.services import PaymentCommandService
    from test_finance_vertical_slice import receivables

    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    installment = receivables(f, order)[0]
    _, high = reviewer(f)
    low = replace(high, permissions=frozenset(Permission) - {Permission.PROFIT_READ})
    commands = PaymentCommandService(f.session_factory)
    reviews = PaymentTextReviewService(f.session_factory)
    request = {
        "company_id": order["company_id"],
        "amount": "100",
        "currency_code": order["currency_code"],
        "method": "BANK_TRANSFER",
        "received_at": datetime.now(UTC),
        "reference": "BANK-001",
        "notes": "Internal cost 350",
    }
    receipt = commands.create(low, request, idempotency_key="create")[0]
    assert receipt.notes is None and receipt.amount == Decimal("100")
    assert commands.create(low, request, idempotency_key="create")[0].notes is None
    original = reviews.inspect(high, receipt.id)
    reviews.decide(high, receipt.id, decision(original), key="release")
    assert commands.create(low, request, idempotency_key="create")[0].notes == request["notes"]
    allocation = {"allocations": [{"receivable_id": installment["id"], "amount": "1"}]}
    result = commands.allocate(low, receipt.id, allocation, idempotency_key="allocate")
    replay = commands.allocate(low, receipt.id, allocation, idempotency_key="allocate")
    assert result[0].notes == replay[0].notes
    assert result[1] == replay[1] == Decimal("1")
    current = reviews.inspect(high, receipt.id)
    reviews.decide(high, receipt.id, decision(current, False), key="restrict")
    assert (
        commands.allocate(low, receipt.id, allocation, idempotency_key="allocate")[0].notes is None
    )
    reversal = commands.reverse(low, receipt.id, reason="Sensitive cost 350")[0]
    assert reversal.notes is None and reversal.reversal_of_payment_id == receipt.id
    assert commands.reverse(low, receipt.id, reason="Sensitive cost 350")[0].notes is None
    assert reviews.inspect(high, reversal.id).details == {"notes": "Reversal: Sensitive cost 350"}
    assert not reviews.inspect(high, reversal.id).released
    assert projection(f, low, receipt.id).notes is None
    with f.session_factory() as session:
        assert session.get(Payment, receipt.id).notes == request["notes"]
        assert session.get(Payment, receipt.id).amount == Decimal("100")
