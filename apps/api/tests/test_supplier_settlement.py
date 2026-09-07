from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.finance import supplier_services
from app.finance.supplier_models import Payable, SupplierPayment, SupplierPaymentAllocation
from app.finance.supplier_queries import SupplierFinanceQuery
from app.finance.supplier_services import SupplierFinanceService
from app.platform.models import AuditLog, OutboxEvent
from app.procurement.models import PurchaseOrder
from app.work.models import Activity
from legacy_migration import verify_legacy_guard
from sqlalchemy import event, func, select
from test_order_procurement_vertical_slice import create_confirmed_order
from test_quotation_vertical_slice import post_ok

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def purchase(f):
    order, _, supplier = create_confirmed_order(f)
    post_ok(f, f"/api/v1/companies/{supplier}/roles", "quotation-sales", {"role": "SUPPLIER"}, 201)
    row = post_ok(
        f,
        "/api/v1/purchase-orders",
        "quotation-manager",
        {
            "sales_order_id": order["id"],
            "supplier_company_id": supplier,
            "currency_code": "CNY",
            "exchange_rate": "0.128",
            "items": [
                {
                    "sales_order_item_id": order["items"][0]["id"],
                    "quantity": "1",
                    "unit_cost": "100",
                }
            ],
        },
        201,
    )
    for action in ("approve", "send", "confirm"):
        row = post_ok(
            f,
            f"/api/v1/purchase-orders/{row['id']}/{action}",
            "quotation-manager",
            {"supplier_reference": "SUP-001", "expected_delivery_date": "2026-12-01"}
            if action == "confirm"
            else {},
        )
    return row


def request(
    f, path, *, body=None, method="post", status=201, key=None, subject="quotation-finance"
):
    response = getattr(f.client, method)(
        f"/api/v1{path}",
        **({"json": body or {}} if method != "get" else {}),
        headers={**f.headers(subject, f.organization_a), "Idempotency-Key": key or str(uuid4())},
    )
    assert response.status_code == status, response.text
    return response.json()


def payable_body(po, **overrides):
    return {
        "purchase_order_id": po["id"],
        "amount": "100",
        "incurred_on": "2026-01-01",
        "due_date": "2026-01-02",
        "reference": "INV-001",
        "description": "Verified purchase principal",
        "reason": "Reconciled invoice",
        **overrides,
    }


def payment_body(po, **overrides):
    return {
        "supplier_company_id": po["supplier_company_id"],
        "amount": "100",
        "currency_code": "CNY",
        "paid_on": "2026-01-01",
        "method": "BANK_TRANSFER",
        "reference": "BANK-001",
        "reason": "Reconciled bank evidence",
        **overrides,
    }


def allocate_body(payment, payable, amount="100"):
    return {
        "expected_version": payment["version"],
        "reason": "Allocate verified outgoing payment",
        "allocations": [
            {"payable_id": payable["id"], "expected_version": payable["version"], "amount": amount}
        ],
    }


def counts(f):
    with f.session_factory() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (
                Payable,
                SupplierPayment,
                SupplierPaymentAllocation,
                Activity,
                AuditLog,
                OutboxEvent,
            )
        )


def test_payable_payment_allocation_reversal_and_void(quotation_fixture):
    f = quotation_fixture
    po = purchase(f)
    payable = request(f, "/payables", body=payable_body(po), key="payable-once")
    assert payable["status"] == "OVERDUE" and payable["balance"] == "100.0000"
    before = counts(f)
    assert request(f, "/payables", body=payable_body(po), key="payable-once") == payable
    assert counts(f) == before
    payment = request(f, "/supplier-payments", body=payment_body(po), key="payment-once")
    assert request(f, "/supplier-payments", body=payment_body(po), key="payment-once") == payment
    allocated = request(
        f,
        f"/supplier-payments/{payment['id']}/allocate",
        body=allocate_body(payment, payable, "40.1234"),
        key="allocate-once",
        status=200,
    )
    before = counts(f)
    assert (
        request(
            f,
            f"/supplier-payments/{payment['id']}/allocate",
            body=allocate_body(payment, payable, "40.1234"),
            key="allocate-once",
            status=200,
        )
        == allocated
    )
    assert counts(f) == before
    current = request(f, f"/payables/{payable['id']}", method="get", status=200)
    assert current["balance"] == "59.8766" and current["status"] == "PARTIALLY_PAID"
    request(
        f,
        f"/payables/{current['id']}/void",
        body={"expected_version": current["version"], "reason": "Cannot erase settled debt"},
        status=409,
    )
    allocated = request(
        f,
        f"/supplier-payments/{payment['id']}/allocate",
        body=allocate_body(allocated, current, "59.8766"),
        status=200,
    )
    current = request(f, f"/payables/{payable['id']}", method="get", status=200)
    assert current["status"] == "PAID" and allocated["available_amount"] == "0.0000"
    reverse_body = {
        "expected_version": allocated["version"],
        "reason": "Correct erroneous bank record",
    }
    reverse = request(
        f, f"/supplier-payments/{payment['id']}/reverse", body=reverse_body, key="reverse-once"
    )
    assert len(reverse["allocations"]) == 2
    before = counts(f)
    assert (
        request(
            f, f"/supplier-payments/{payment['id']}/reverse", body=reverse_body, key="reverse-once"
        )
        == reverse
    )
    assert counts(f) == before
    original = request(f, f"/supplier-payments/{payment['id']}", method="get", status=200)
    assert original["reversed_by_payment_id"] == reverse["id"]
    assert (
        original["amount"] == payment["amount"]
        and original["allocations"] == allocated["allocations"]
    )
    request(f, f"/supplier-payments/{payment['id']}/reverse", body=reverse_body, status=409)
    current = request(f, f"/payables/{payable['id']}", method="get", status=200)
    assert current["balance"] == "100.0000" and current["paid_amount"] == "0.0000"
    voided = request(
        f,
        f"/payables/{current['id']}/void",
        body={"expected_version": current["version"], "reason": "Replace incorrect invoice"},
        status=200,
    )
    assert (
        voided["status"] == "VOIDED"
        and voided["amount"] == "100.0000"
        and voided["balance"] == "0.0000"
    )
    request(f, "/payables", body=payable_body(po, reference="CORRECTED-001"))


@pytest.mark.parametrize(
    "case,expected", [("cap", 409), ("future", 422), ("unconfirmed", 409), ("unknown_field", 422)]
)
def test_payable_rejects_invalid_obligation_without_writes(quotation_fixture, case, expected):
    f = quotation_fixture
    po = purchase(f)
    body = payable_body(po)
    if case == "cap":
        body["amount"] = "100.0001"
    if case == "future":
        body["incurred_on"] = "2099-01-01"
    if case == "unknown_field":
        body["balance"] = "0"
    if case == "unconfirmed":
        with f.session_factory.begin() as session:
            session.get(PurchaseOrder, UUID(po["id"])).confirmed_at = None
    before = counts(f)
    request(f, "/payables", body=body, status=expected)
    assert counts(f) == before


@pytest.mark.parametrize(
    "case,code",
    [
        ("currency", "SUPPLIER_SETTLEMENT_MISMATCH"),
        ("payment", "SUPPLIER_PAYMENT_OVERALLOCATION"),
        ("payable", "PAYABLE_OVERALLOCATION"),
        ("version", "VERSION_CONFLICT"),
    ],
)
def test_allocation_guards_are_atomic(quotation_fixture, case, code):
    f = quotation_fixture
    po = purchase(f)
    payable = request(f, "/payables", body=payable_body(po, amount="40"))
    payment = request(
        f,
        "/supplier-payments",
        body=payment_body(
            po,
            amount="30" if case == "payment" else "100",
            currency_code="USD" if case == "currency" else "CNY",
        ),
    )
    body = allocate_body(payment, payable, "50" if case == "payable" else "40")
    if case == "version":
        body["expected_version"] = 99
    before = counts(f)
    assert (
        request(f, f"/supplier-payments/{payment['id']}/allocate", body=body, status=409)["code"]
        == code
    )
    assert counts(f) == before


@pytest.mark.parametrize("operation", ["payable", "void", "payment", "allocate", "reverse"])
@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
def test_supplier_finance_rolls_back_each_evidence_failure(quotation_fixture, operation, table):
    f = quotation_fixture
    po = purchase(f)
    payable = (
        request(f, "/payables", body=payable_body(po))
        if operation in {"void", "allocate", "reverse"}
        else None
    )
    payment = (
        request(f, "/supplier-payments", body=payment_body(po))
        if operation in {"allocate", "reverse"}
        else None
    )
    if operation == "reverse":
        payment = request(
            f,
            f"/supplier-payments/{payment['id']}/allocate",
            body=allocate_body(payment, payable),
            status=200,
        )
    before = counts(f)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith(f"INSERT INTO {table}"):
            raise RuntimeError("Injected settlement failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="Injected settlement failure"):
            if operation == "payable":
                request(f, "/payables", body=payable_body(po))
            elif operation == "payment":
                request(f, "/supplier-payments", body=payment_body(po))
            elif operation == "void":
                request(
                    f,
                    f"/payables/{payable['id']}/void",
                    body={"expected_version": payable["version"], "reason": "Correct invoice"},
                    status=200,
                )
            elif operation == "allocate":
                request(
                    f,
                    f"/supplier-payments/{payment['id']}/allocate",
                    body=allocate_body(payment, payable),
                    status=200,
                )
            else:
                request(
                    f,
                    f"/supplier-payments/{payment['id']}/reverse",
                    body={"expected_version": payment["version"], "reason": "Correct payment"},
                )
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert counts(f) == before
    if payable:
        current = request(f, f"/payables/{payable['id']}", method="get", status=200)
        assert current["voided_at"] is None
        assert current["paid_amount"] == ("100.0000" if operation == "reverse" else "0.0000")


def test_supplier_finance_permissions_tenant_and_cursor_scope(quotation_fixture):
    f = quotation_fixture
    po = purchase(f)
    first = request(f, "/payables", body=payable_body(po, amount="40"))
    second = request(f, "/payables", body=payable_body(po, amount="60", reference="INV-002"))
    for subject in ("quotation-sales", "quotation-operations"):
        request(f, "/payables", method="get", subject=subject, status=403)
        request(f, "/supplier-payments", body=payment_body(po), subject=subject, status=403)
    page = request(f, "/payables?limit=1", method="get", status=200)
    assert page["items"][0]["id"] == second["id"] and page["has_more"]
    page2 = request(f, f"/payables?limit=1&cursor={page['next_cursor']}", method="get", status=200)
    assert page2["items"][0]["id"] == first["id"] and not page2["has_more"]
    request(f, f"/payables?currency_code=USD&cursor={first['id']}", method="get", status=404)
    other = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_b,
        permissions=frozenset({Permission.PAYABLE_READ}),
        request_id=uuid4(),
    )
    with f.session_factory() as session, pytest.raises(ApiProblem) as error:
        SupplierFinanceQuery(session).payable(other, UUID(first["id"]))
    assert error.value.status == 404


def test_concurrent_allocations_cannot_overpay_and_downgrade_preserves_facts(quotation_fixture):
    f = quotation_fixture
    po = purchase(f)
    payable = request(f, "/payables", body=payable_body(po))
    payments = [request(f, "/supplier-payments", body=payment_body(po)) for _ in range(2)]
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset({Permission.SUPPLIER_PAYMENT_ALLOCATE}),
        request_id=uuid4(),
    )

    def run(payment):
        try:
            return SupplierFinanceService(f.session_factory).allocate(
                context, UUID(payment["id"]), allocate_body(payment, payable), key=str(uuid4())
            )
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, payments))
    assert sum(isinstance(result, UUID) for result in results) == 1
    assert "VERSION_CONFLICT" in results
    current = request(f, f"/payables/{payable['id']}", method="get", status=200)
    assert Decimal(current["paid_amount"]) == 100
    verify_legacy_guard(
        f.engine, "20260906_0020", "20260906_0019", "Supplier financial facts exist"
    )


def test_recording_supplier_lock_does_not_block_reversal_foreign_key(
    quotation_fixture, monkeypatch
):
    f = quotation_fixture
    po = purchase(f)
    payment = request(f, "/supplier-payments", body=payment_body(po))
    recording = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset({Permission.SUPPLIER_PAYMENT_RECORD}),
        request_id=uuid4(),
    )
    reversing = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset({Permission.SUPPLIER_PAYMENT_REVERSE}),
        request_id=uuid4(),
    )
    company_locked = Event()
    reversal_done = Event()
    original_number = supplier_services.next_document_number

    def hold_recording(session, context, kind, prefix):
        if context.request_id == recording.request_id:
            company_locked.set()
            if not reversal_done.wait(5):
                raise RuntimeError("Recording company lock blocked reversal")
        return original_number(session, context, kind, prefix)

    monkeypatch.setattr(supplier_services, "next_document_number", hold_recording)
    service = SupplierFinanceService(f.session_factory)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(service.record_payment, recording, payment_body(po), key=str(uuid4()))
        try:
            assert company_locked.wait(5)
            service.reverse(
                reversing,
                UUID(payment["id"]),
                {"expected_version": payment["version"], "reason": "Correct recorded transfer"},
                key=str(uuid4()),
            )
        finally:
            reversal_done.set()
        assert isinstance(future.result(timeout=5), UUID)


def test_one_supplier_payment_settles_multiple_payables_and_pages(quotation_fixture):
    f = quotation_fixture
    po = purchase(f)
    payables = [
        request(f, "/payables", body=payable_body(po, amount="50", reference=f"INV-{index}"))
        for index in range(2)
    ]
    payment = request(f, "/supplier-payments", body=payment_body(po))
    body = {
        "expected_version": payment["version"],
        "reason": "Settle both verified installments",
        "allocations": [
            {"payable_id": p["id"], "expected_version": p["version"], "amount": "50"}
            for p in payables
        ],
    }
    result = request(f, f"/supplier-payments/{payment['id']}/allocate", body=body, status=200)
    assert len(result["allocations"]) == 2 and result["available_amount"] == "0.0000"
    reverse = request(
        f,
        f"/supplier-payments/{payment['id']}/reverse",
        body={"expected_version": result["version"], "reason": "Correct both allocations"},
    )
    page = request(f, "/supplier-payments?limit=1", method="get", status=200)
    assert page["items"][0]["id"] == reverse["id"] and page["has_more"]
    second = request(
        f, f"/supplier-payments?limit=1&cursor={page['next_cursor']}", method="get", status=200
    )
    assert second["items"][0]["id"] == payment["id"] and not second["has_more"]
    for p in payables:
        assert request(f, f"/payables/{p['id']}", method="get", status=200)["balance"] == "50.0000"


def test_concurrent_supplier_reversal_appends_exactly_one_fact(quotation_fixture):
    f = quotation_fixture
    po = purchase(f)
    payment = request(f, "/supplier-payments", body=payment_body(po))
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset({Permission.SUPPLIER_PAYMENT_REVERSE}),
        request_id=uuid4(),
    )

    def run(_):
        try:
            return SupplierFinanceService(f.session_factory).reverse(
                context,
                UUID(payment["id"]),
                {
                    "expected_version": payment["version"],
                    "reason": "Correct duplicate bank evidence",
                },
                key=str(uuid4()),
            )
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert sum(isinstance(result, UUID) for result in results) == 1
    assert "SUPPLIER_PAYMENT_INACTIVE" in results
    assert counts(f)[1] == 2
