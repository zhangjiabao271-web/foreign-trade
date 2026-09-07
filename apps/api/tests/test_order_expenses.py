from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.finance.expense_models import Expense
from app.finance.expense_services import ExpenseQuery, ExpenseService
from app.platform.models import AuditLog, OutboxEvent
from app.sales.models import SalesOrder
from app.work.models import Activity
from legacy_migration import verify_legacy_guard
from sqlalchemy import event, func, select
from test_order_procurement_vertical_slice import create_confirmed_order

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def request(
    f, order, method="post", suffix="", body=None, key=None, subject="quotation-finance", status=201
):
    result = getattr(f.client, method)(
        f"/api/v1/sales-orders/{order['id']}/expenses{suffix}",
        **({"json": body or {}} if method != "get" else {}),
        headers={**f.headers(subject, f.organization_a), "Idempotency-Key": key or str(uuid4())},
    )
    assert result.status_code == status, result.text
    return result.json()


def payload(order, **overrides):
    return {
        "category": "FREIGHT",
        "cost_treatment": "ADDITIONAL",
        "amount": "12.3456",
        "currency_code": order["currency_code"],
        "exchange_rate": "1",
        "incurred_on": "2026-01-01",
        "description": "Carrier ancillary charge",
        "evidence_reference": "invoice-EX-001",
        "reason": "Verified carrier invoice",
        **overrides,
    }


def counts(f):
    with f.session_factory() as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (Expense, Activity, AuditLog, OutboxEvent)
        )


def test_expense_facts_summary_reversal_and_replay(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    first = request(f, order, body=payload(order), key="expense-once")
    before = counts(f)
    assert request(f, order, body=payload(order), key="expense-once") == first
    assert counts(f) == before
    request(f, order, body=payload(order, amount="10", cost_treatment="INCLUDED_IN_QUOTATION"))
    summary = request(f, order, "get", "/summary", status=200)
    assert Decimal(summary["net_additional_cost"]) == Decimal("12.3456")
    assert Decimal(summary["net_included_cost"]) == 10
    assert Decimal(summary["adjusted_forecast_gross_profit"]) == Decimal(
        summary["quoted_gross_profit"]
    ) - Decimal("12.3456")
    reversal_body = {"expected_version": first["version"], "reason": "Duplicate invoice correction"}
    reversal = request(
        f, order, suffix=f"/{first['id']}/reverse", body=reversal_body, key="reverse-once"
    )
    before = counts(f)
    assert (
        request(f, order, suffix=f"/{first['id']}/reverse", body=reversal_body, key="reverse-once")
        == reversal
    )
    assert counts(f) == before
    original = request(f, order, "get", f"/{first['id']}", status=200)
    assert original["reversed_by_expense_id"] == reversal["id"]
    assert original["version"] == first["version"] and original["amount"] == first["amount"]
    assert request(f, order, "get", "/summary", status=200)["net_additional_cost"] == "0.0000"
    request(f, order, suffix=f"/{first['id']}/reverse", body=reversal_body, status=409)
    request(f, order, suffix=f"/{reversal['id']}/reverse", body=reversal_body, status=409)
    page = request(f, order, "get", "?limit=1", status=200)
    page2 = request(f, order, "get", f"?limit=1&cursor={page['next_cursor']}", status=200)
    assert page["has_more"] and page["items"][0]["id"] != page2["items"][0]["id"]


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"exchange_rate": "2"}, "EXPENSE_SAME_CURRENCY_RATE"),
        ({"incurred_on": "2099-01-01"}, "EXPENSE_DATE_IN_FUTURE"),
        (
            {
                "currency_code": "JPY",
                "amount": "99999999999999.9999",
                "exchange_rate": "9999999999",
            },
            "EXPENSE_AMOUNT_OVERFLOW",
        ),
    ],
)
def test_expense_invalid_business_inputs_do_not_write(quotation_fixture, overrides, code):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    before = counts(f)
    assert request(f, order, body=payload(order, **overrides), status=422)["code"] == code
    assert counts(f) == before


def test_expense_permissions_tenant_parent_and_rounding(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    first = request(
        f, order, body=payload(order, currency_code="JPY", amount="1", exchange_rate="0.12345")
    )
    assert first["order_currency_amount"] == "0.1235"
    for subject in ("quotation-sales", "quotation-operations"):
        request(f, order, body=payload(order), subject=subject, status=403)
        request(f, order, "get", subject=subject, status=403)
    other = f.client.get(
        f"/api/v1/sales-orders/{order['id']}/expenses",
        headers=f.headers("quotation-other", f.organization_b),
    )
    assert other.status_code == 403
    other_context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_b,
        permissions=frozenset({Permission.EXPENSE_READ}),
        request_id=uuid4(),
    )
    with f.session_factory() as session, pytest.raises(ApiProblem) as error:
        ExpenseQuery(session).get(other_context, UUID(order["id"]), UUID(first["id"]))
    assert error.value.status == 404
    request(f, {"id": str(uuid4())}, "get", f"/{first['id']}", status=404)
    request(f, order, "get", f"?cursor={uuid4()}", status=404)
    request(
        f,
        order,
        suffix=f"/{first['id']}/reverse",
        body={"expected_version": 999, "reason": "Stale correction"},
        status=409,
    )
    request(f, order, body=payload(order, status="PAID"), status=422)


@pytest.mark.parametrize("state", ["COMPLETED", "CANCELLED"])
def test_late_expenses_preserve_finalized_orders(quotation_fixture, state):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    with f.session_factory.begin() as session:
        session.get(SalesOrder, UUID(order["id"])).status = state
    request(f, order, body=payload(order))
    with f.session_factory() as session:
        assert session.get(SalesOrder, UUID(order["id"])).status == state
    with f.session_factory.begin() as session:
        session.get(SalesOrder, UUID(order["id"])).confirmed_at = None
    assert request(f, order, body=payload(order), status=409)["code"] == "ORDER_NOT_CONFIRMED"


@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
@pytest.mark.parametrize("reverse", [False, True])
def test_expense_evidence_failure_rolls_back(quotation_fixture, table, reverse):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    first = request(f, order, body=payload(order)) if reverse else None
    before = counts(f)

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith(f"INSERT INTO {table}"):
            raise RuntimeError("Injected expense failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="Injected expense failure"):
            if first:
                request(
                    f,
                    order,
                    suffix=f"/{first['id']}/reverse",
                    body={
                        "expected_version": first["version"],
                        "reason": "Correct duplicate charge",
                    },
                )
            else:
                request(f, order, body=payload(order))
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert counts(f) == before


def test_concurrent_reversal_creates_one_fact(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    first = request(f, order, body=payload(order))
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset({Permission.EXPENSE_WRITE}),
        request_id=uuid4(),
    )

    def run(_):
        try:
            return (
                ExpenseService(f.session_factory)
                .reverse(
                    context,
                    UUID(order["id"]),
                    UUID(first["id"]),
                    {"expected_version": first["version"], "reason": "Duplicate invoice reversal"},
                    key=str(uuid4()),
                )
                .id
            )
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, range(2)))
    assert sum(isinstance(result, UUID) for result in results) == 1
    assert "EXPENSE_NOT_REVERSIBLE" in results
    verify_legacy_guard(f.engine, "20260906_0019", "20260906_0018", "Expense facts exist")
    assert counts(f)[0] == 2
