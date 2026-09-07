from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.finance.models import Payment, PaymentAllocation, Receivable
from app.finance.services import PaymentCommandService, ReceivableCommandService
from app.identity.models import User
from app.platform.models import AuditLog, OutboxEvent
from app.platform.records import DomainEvent, OutboxRecorder
from app.sales.completion_services import OrderCompletionService
from app.work.models import Activity
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session
from test_order_procurement_vertical_slice import create_confirmed_order
from test_quotation_vertical_slice import post_ok
from test_shipment_documents_vertical_slice import (
    FakeObjectStorage,
    create_shipment,
    prepare_and_depart,
)

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice", "test_shipment_documents_vertical_slice")


def finance_post(fixture, path, body, *, key=None, status=200):
    response = fixture.client.post(
        path,
        json=body,
        headers={
            **fixture.headers("quotation-finance", fixture.organization_a),
            "Idempotency-Key": key or str(uuid4()),
        },
    )
    assert response.status_code == status, response.text
    return response.json()


def receivables(fixture, order):
    return finance_post(
        fixture,
        f"/api/v1/sales-orders/{order['id']}/generate-receivables",
        {
            "deposit_due_date": (date.today() - timedelta(days=1)).isoformat(),
            "balance_due_date": (date.today() + timedelta(days=30)).isoformat(),
        },
    )["items"]


def payment(fixture, order, amount, *, key=None):
    return finance_post(
        fixture,
        "/api/v1/payments",
        {
            "company_id": order["company_id"],
            "amount": str(amount),
            "currency_code": order["currency_code"],
            "method": "BANK_TRANSFER",
            "received_at": "2026-09-05T00:00:00Z",
        },
        key=key,
        status=201,
    )


def allocation(fixture, receipt, installment, amount=None, *, key=None, status=200):
    return finance_post(
        fixture,
        f"/api/v1/payments/{receipt['id']}/allocate",
        {
            "allocations": [
                {
                    "receivable_id": installment["id"],
                    "amount": str(amount if amount is not None else installment["amount"]),
                }
            ],
        },
        key=key,
        status=status,
    )


def counts(fixture):
    with fixture.session_factory() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (Payment, PaymentAllocation, Receivable, Activity, AuditLog, OutboxEvent)
        )


def test_deposit_balance_idempotency_repeated_allocations_and_reversal(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    rows = receivables(f, order)
    by_type = {row["installment_type"]: row for row in rows}
    deposit, balance = by_type["DEPOSIT"], by_type["BALANCE"]
    assert sum(Decimal(row["amount"]) for row in rows) == Decimal(order["total"])
    assert deposit["status"] == "OVERDUE"
    assert receivables(f, order) == rows
    receipt = payment(f, order, order["total"], key="receipt-once")
    before = counts(f)
    assert payment(f, order, order["total"], key="receipt-once") == receipt
    assert counts(f) == before
    partial = Decimal(deposit["amount"]) / 2
    partial = partial.quantize(Decimal("0.0001"))
    allocation(f, receipt, deposit, partial, key="part-a")
    allocation(f, receipt, deposit, Decimal(deposit["amount"]) - partial, key="part-b")
    before = counts(f)
    allocation(f, receipt, deposit, partial, key="part-a")
    assert counts(f) == before
    current = f.client.get(
        f"/api/v1/sales-orders/{order['id']}",
        headers=f.headers("quotation-finance", f.organization_a),
    ).json()
    assert current["status"] == "EXECUTING"
    allocation(f, receipt, balance)
    reverse = finance_post(
        f, f"/api/v1/payments/{receipt['id']}/reverse", {"reason": "Bank reversed receipt"}
    )
    assert len(reverse["allocations"]) == 3
    assert Decimal(reverse["allocated_amount"]) == Decimal(order["total"])
    before = counts(f)
    assert (
        finance_post(
            f, f"/api/v1/payments/{receipt['id']}/reverse", {"reason": "Bank reversed receipt"}
        )
        == reverse
    )
    assert counts(f) == before
    current_rows = f.client.get(
        "/api/v1/receivables", headers=f.headers("quotation-finance", f.organization_a)
    ).json()["items"]
    assert all(Decimal(row["paid_amount"]) == 0 for row in current_rows)
    with f.session_factory() as session:
        assert all(row.paid_at is None for row in session.scalars(select(Receivable)).all())
    current = f.client.get(
        f"/api/v1/sales-orders/{order['id']}",
        headers=f.headers("quotation-finance", f.organization_a),
    ).json()
    assert current["status"] == "DEPOSIT_PENDING"


def test_overallocation_key_conflict_tenant_and_permission_have_no_partial_writes(
    quotation_fixture,
):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    rows = receivables(f, order)
    receipt = payment(f, order, "1", key="one")
    before = counts(f)
    assert allocation(f, receipt, rows[0], "2", status=409)["code"] == "PAYMENT_ALLOCATION_EXCEEDED"
    assert counts(f) == before
    conflict = finance_post(
        f,
        "/api/v1/payments",
        {
            "company_id": order["company_id"],
            "amount": "2",
            "currency_code": order["currency_code"],
            "method": "BANK_TRANSFER",
            "received_at": "2026-09-05T00:00:00Z",
        },
        key="one",
        status=409,
    )
    assert conflict["code"] == "IDEMPOTENCY_CONFLICT"
    other = f.headers("quotation-other", f.organization_b)
    assert f.client.get(f"/api/v1/payments/{receipt['id']}", headers=other).status_code == 404
    assert f.client.get("/api/v1/payments", headers=other).json()["items"] == []
    assert f.client.get("/api/v1/receivables", headers=other).json()["items"] == []
    assert (
        f.client.post(
            f"/api/v1/payments/{receipt['id']}/reverse",
            headers=f.headers("quotation-sales", f.organization_a),
            json={"reason": "not permitted"},
        ).status_code
        == 403
    )
    assert finance_post(
        f, f"/api/v1/payments/{receipt['id']}/reverse", {"reason": "     "}, status=422
    )
    assert counts(f) == before


def test_concurrent_receivable_allocation_never_exceeds_balance(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    row = receivables(f, order)[0]
    receipts = [payment(f, order, row["amount"]) for _ in range(2)]
    barrier = Barrier(2)

    def run(receipt):
        context = RequestContext(
            user_id=f.sales_user,
            organization_id=f.organization_a,
            permissions=frozenset(Permission),
            request_id=uuid4(),
        )
        barrier.wait(timeout=10)
        try:
            PaymentCommandService(f.session_factory).allocate(
                context,
                UUID(receipt["id"]),
                {
                    "allocations": [{"receivable_id": row["id"], "amount": row["amount"]}],
                },
                idempotency_key=str(uuid4()),
            )
            return "ok"
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, receipts))
    assert sorted(results) == ["RECEIVABLE_ALLOCATION_EXCEEDED", "ok"]
    with f.session_factory() as session:
        assert session.scalar(select(func.sum(PaymentAllocation.amount))) == Decimal(row["amount"])


def test_concurrent_same_payment_allocations_and_same_key_receipt_creation(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    rows = receivables(f, order)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    request = {
        "company_id": order["company_id"],
        "amount": "1",
        "currency_code": order["currency_code"],
        "method": "BANK_TRANSFER",
        "received_at": datetime.now(UTC),
    }
    barrier = Barrier(2)

    def create_once(_):
        barrier.wait(timeout=10)
        return (
            PaymentCommandService(f.session_factory)
            .create(context, request, idempotency_key="concurrent-create")[0]
            .id
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        ids = list(executor.map(create_once, range(2)))
    assert ids[0] == ids[1]
    with f.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Payment)) == 1
    barrier = Barrier(2)

    def allocate_once(row):
        barrier.wait(timeout=10)
        try:
            PaymentCommandService(f.session_factory).allocate(
                context,
                ids[0],
                {
                    "allocations": [{"receivable_id": row["id"], "amount": "1"}],
                },
                idempotency_key=str(uuid4()),
            )
            return "ok"
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(allocate_once, rows))
    assert sorted(results) == ["PAYMENT_ALLOCATION_EXCEEDED", "ok"]
    with f.session_factory() as session:
        assert session.scalar(select(func.sum(PaymentAllocation.amount))) == Decimal("1")


def test_allocation_failure_rolls_back_receivable_order_and_ledger(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    row = receivables(f, order)[0]
    receipt = payment(f, order, row["amount"])
    before = counts(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    with pytest.raises(RuntimeError, match="injected finance failure"):
        PaymentCommandService(f.session_factory, outbox_recorder=FailingFinanceOutbox()).allocate(
            context,
            UUID(receipt["id"]),
            {"allocations": [{"receivable_id": row["id"], "amount": row["amount"]}]},
            idempotency_key="failed-allocation",
        )
    assert counts(f) == before
    current = f.client.get(
        f"/api/v1/sales-orders/{order['id']}",
        headers=f.headers("quotation-finance", f.organization_a),
    ).json()
    assert current["status"] == "DEPOSIT_PENDING"
    allocation(f, receipt, row, key="failed-allocation")


def test_numbering_is_unique_when_first_payments_are_recorded_concurrently(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    barrier = Barrier(4)

    def record(index):
        context = RequestContext(
            user_id=f.sales_user,
            organization_id=f.organization_a,
            permissions=frozenset(Permission),
            request_id=uuid4(),
        )
        barrier.wait(timeout=10)
        result = PaymentCommandService(f.session_factory).create(
            context,
            {
                "company_id": order["company_id"],
                "amount": "1",
                "currency_code": order["currency_code"],
                "method": "BANK_TRANSFER",
                "received_at": datetime.now(UTC),
            },
            idempotency_key=f"number-{index}",
        )
        return result[0].payment_number

    with ThreadPoolExecutor(max_workers=4) as executor:
        numbers = list(executor.map(record, range(4)))
    assert len(set(numbers)) == 4
    assert sorted(number[-6:] for number in numbers) == ["000001", "000002", "000003", "000004"]


def test_completion_requires_delivery_and_valid_version_and_denies_finance_role(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    manager = f.headers("quotation-manager", f.organization_a)
    before = counts(f)
    stale = f.client.post(
        f"/api/v1/sales-orders/{order['id']}/complete",
        headers=manager,
        json={"expected_version": order["version"] + 1},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "VERSION_CONFLICT"
    not_shipped = f.client.post(
        f"/api/v1/sales-orders/{order['id']}/complete",
        headers=manager,
        json={"expected_version": order["version"]},
    )
    assert not_shipped.status_code == 409
    assert not_shipped.json()["code"] == "ORDER_NOT_SHIPPED"
    denied = f.client.post(
        f"/api/v1/sales-orders/{order['id']}/complete",
        headers=f.headers("quotation-finance", f.organization_a),
        json={"expected_version": order["version"]},
    )
    assert denied.status_code == 403
    assert counts(f) == before


class FailingFinanceOutbox(OutboxRecorder):
    def record(self, session: Session, context: RequestContext, event: DomainEvent) -> OutboxEvent:
        raise RuntimeError("injected finance failure")


def test_finance_failure_rolls_back_receipt_and_idempotency(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    before = counts(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    request = {
        "company_id": order["company_id"],
        "amount": "5",
        "currency_code": order["currency_code"],
        "method": "BANK_TRANSFER",
        "received_at": datetime.now(UTC),
    }
    with pytest.raises(RuntimeError, match="injected finance failure"):
        PaymentCommandService(f.session_factory, outbox_recorder=FailingFinanceOutbox()).create(
            context, request, idempotency_key="retry-after-failure"
        )
    assert counts(f) == before
    result = PaymentCommandService(f.session_factory).create(
        context, request, idempotency_key="retry-after-failure"
    )
    assert result[0].payment_number.endswith("000001")


@pytest.mark.parametrize("record_model", [Activity, AuditLog, OutboxEvent])
def test_each_transactional_record_failure_rolls_back_payment(quotation_fixture, record_model):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    before = counts(f)

    def reject_insert(*_):
        raise RuntimeError("injected record insertion failure")

    event.listen(record_model, "before_insert", reject_insert)
    try:
        with pytest.raises(RuntimeError, match="injected record insertion failure"):
            PaymentCommandService(f.session_factory).create(
                context,
                {
                    "company_id": order["company_id"],
                    "amount": "1",
                    "currency_code": order["currency_code"],
                    "method": "BANK_TRANSFER",
                    "received_at": datetime.now(UTC),
                },
                idempotency_key="atomic-records",
            )
    finally:
        event.remove(record_model, "before_insert", reject_insert)
    assert counts(f) == before


def test_finance_cross_tenant_commands_never_reveal_or_mutate_foreign_facts(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    row = receivables(f, order)[0]
    receipt = payment(f, order, row["amount"])
    with f.session_factory() as session:
        other_user = session.scalar(
            select(User.id).where(User.external_subject == "quotation-other")
        )
    assert other_user is not None
    context = RequestContext(
        user_id=other_user,
        organization_id=f.organization_b,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    service = PaymentCommandService(f.session_factory)
    commands = [
        lambda: service.allocate(
            context,
            UUID(receipt["id"]),
            {
                "allocations": [{"receivable_id": row["id"], "amount": "1"}],
            },
            idempotency_key="foreign-payment",
        ),
        lambda: service.reverse(context, UUID(receipt["id"]), reason="Cross organization attempt"),
        lambda: service.create(
            context,
            {
                "company_id": order["company_id"],
                "amount": "1",
                "currency_code": order["currency_code"],
                "method": "BANK_TRANSFER",
                "received_at": datetime.now(UTC),
            },
            idempotency_key="foreign-company",
        ),
        lambda: ReceivableCommandService(f.session_factory).generate_for_order(
            context, UUID(order["id"]), {"balance_due_date": date.today()}
        ),
        lambda: OrderCompletionService(f.session_factory).complete(
            context, UUID(order["id"]), {"expected_version": order["version"]}
        ),
    ]
    before = counts(f)
    for command in commands:
        with pytest.raises(ApiProblem) as raised:
            command()
        assert raised.value.status == 404
        assert counts(f) == before


@pytest.mark.parametrize("waiver", [False, True])
def test_full_delivery_settlement_task_resolution_and_order_completion(
    quotation_fixture, fake_storage: FakeObjectStorage, waiver: bool
):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    rows = receivables(f, order)
    for row in rows:
        if not waiver or row["installment_type"] == "DEPOSIT":
            allocation(f, payment(f, order, row["amount"]), row)
    shipment = create_shipment(
        f,
        [
            {"sales_order_item_id": item["id"], "quantity": item["quantity"]}
            for item in order["items"]
        ],
    )
    prepare_and_depart(f, fake_storage, shipment)
    for command in ("start-transit", "arrive", "deliver"):
        post_ok(f, f"/api/v1/shipments/{shipment['id']}/{command}", "quotation-operations")
    manager_headers = f.headers("quotation-manager", f.organization_a)
    current = f.client.get(f"/api/v1/sales-orders/{order['id']}", headers=manager_headers).json()
    request = {"expected_version": current["version"]}
    blocked = f.client.post(
        f"/api/v1/sales-orders/{order['id']}/complete", headers=manager_headers, json=request
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == (
        "ORDER_RECEIVABLES_UNPAID" if waiver else "ORDER_HAS_BLOCKING_TASKS"
    )
    if waiver:
        request["financial_waiver_reason"] = "Approved documented customer settlement exception"
    tasks = f.client.get(
        f"/api/v1/sales-orders/{order['id']}/tasks", headers=manager_headers
    ).json()["items"]
    for task in tasks:
        post_ok(
            f,
            f"/api/v1/sales-orders/{order['id']}/tasks/{task['id']}/complete",
            "quotation-operations",
            {"expected_version": task["version"], "resolution": "Procurement verified"},
        )
    restricted_context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission) - {Permission.PROFIT_READ},
        request_id=uuid4(),
    )
    projected = OrderCompletionService(f.session_factory).complete(
        restricted_context, UUID(order["id"]), request
    )
    assert projected.status == "COMPLETED"
    assert projected.total_cost is projected.gross_profit is projected.gross_margin is None
    assert all(item.line_cost is item.line_gross_profit is None for item in projected.items)
    before = counts(f)
    assert (
        OrderCompletionService(f.session_factory).complete(
            restricted_context, UUID(order["id"]), request
        )
        == projected
    )
    assert counts(f) == before
    completed = post_ok(
        f, f"/api/v1/sales-orders/{order['id']}/complete", "quotation-manager", request
    )
    assert completed["status"] == "COMPLETED"
    assert completed["total_cost"] == order["total_cost"]
    before = counts(f)
    assert (
        post_ok(f, f"/api/v1/sales-orders/{order['id']}/complete", "quotation-manager", request)
        == completed
    )
    assert counts(f) == before
    if waiver:
        current_rows = f.client.get("/api/v1/receivables", headers=manager_headers).json()["items"]
        assert any(Decimal(row["balance"]) > 0 for row in current_rows)
    activities = f.client.get(
        f"/api/v1/sales-orders/{order['id']}/activities", headers=manager_headers
    ).json()["items"]
    assert {"sales_order.completed", "sales_order.payment_allocated", "task.completed"} <= {
        item["activity_type"] for item in activities
    }
