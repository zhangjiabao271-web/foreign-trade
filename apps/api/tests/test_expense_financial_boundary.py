from decimal import Decimal

import pytest
from app.finance.expense_models import Expense
from app.finance.models import Payment, PaymentAllocation, Receivable
from app.finance.supplier_models import Payable, SupplierPayment, SupplierPaymentAllocation
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership
from app.procurement.models import PurchaseOrder, PurchaseOrderItem
from app.sales.models import Quotation, QuotationItem, QuotationVersion, SalesOrder, SalesOrderItem
from sqlalchemy import select
from test_finance_vertical_slice import allocation, payment, receivables
from test_order_expenses import counts, payload, request
from test_order_procurement_vertical_slice import create_confirmed_order
from test_purchase_finance_boundary import rows
from test_supplier_settlement import (
    allocate_body,
    payable_body,
    payment_body,
    purchase,
)
from test_supplier_settlement import (
    request as supplier_request,
)

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


@pytest.mark.parametrize("treatment", ["ADDITIONAL", "INCLUDED_IN_QUOTATION"])
def test_expense_corrections_preserve_populated_cash_debt_and_commercial_snapshots(
    quotation_fixture, treatment
):
    f = quotation_fixture
    po = purchase(f)
    order = f.client.get(
        f"/api/v1/sales-orders/{po['sales_order_id']}",
        headers=f.headers("quotation-manager", f.organization_a),
    ).json()
    installments = receivables(f, order)
    received = payment(f, order, order["total"])
    allocation(f, received, installments[0], "1")
    debt = supplier_request(f, "/payables", body=payable_body(po, amount="60"))
    outgoing = supplier_request(f, "/supplier-payments", body=payment_body(po, amount="40"))
    supplier_request(
        f,
        f"/supplier-payments/{outgoing['id']}/allocate",
        body=allocate_body(outgoing, debt, "25"),
        status=200,
    )
    protected = (
        Payment,
        PaymentAllocation,
        Receivable,
        Payable,
        SupplierPayment,
        SupplierPaymentAllocation,
        PurchaseOrder,
        PurchaseOrderItem,
        Quotation,
        QuotationVersion,
        QuotationItem,
        SalesOrder,
        SalesOrderItem,
    )
    before = {model: rows(f, model) for model in protected}
    assert all(before.values()), "Every protected table must have actual fixture facts"
    baseline = counts(f)
    total = Decimal("0")
    # Independent expected conversions include the HALF_UP tie at the fourth place.
    cases = [
        ("FREIGHT", "JPY", "1", "0.12345", "0.1235"),
        ("INSPECTION", "CNY", "2", "0.128", "0.2560"),
        ("BANK_FEE", order["currency_code"], "3", "1", "3.0000"),
        ("CUSTOMS", "JPY", "4", "0.12345", "0.4938"),
        ("OTHER", "CNY", "5", "0.128", "0.6400"),
    ]
    originals = []
    for category, currency, amount, rate, converted in cases:
        data = payload(
            order,
            category=category,
            cost_treatment=treatment,
            currency_code=currency,
            amount=amount,
            exchange_rate=rate,
        )
        original = request(f, order, body=data, key=category)
        assert original["order_currency_amount"] == converted
        originals.append(original)
        total += Decimal(converted)
        assert {model: rows(f, model) for model in protected} == before
        after = counts(f)
        assert request(f, order, body=data, key=category) == original
        assert counts(f) == after
    assert counts(f) == tuple(count + 5 for count in baseline)
    summary = request(f, order, "get", "/summary", status=200)
    additional = total if treatment == "ADDITIONAL" else Decimal(0)
    assert Decimal(summary["net_additional_cost"]) == additional
    assert Decimal(summary["net_included_cost"]) == total - additional
    assert Decimal(summary["adjusted_forecast_gross_profit"]) == (
        Decimal(order["gross_profit"]) - additional
    )
    posted = rows(f, Expense)
    for original in originals:
        body = {"expected_version": original["version"], "reason": "Verified full correction"}
        suffix = f"/{original['id']}/reverse"
        key = f"reverse-{original['id']}"
        reverse = request(f, order, suffix=suffix, body=body, key=key)
        assert reverse["reversal_of_expense_id"] == original["id"]
        for field in (
            "amount",
            "currency_code",
            "exchange_rate",
            "order_currency_amount",
            "order_currency_code",
            "category",
            "cost_treatment",
            "description",
            "evidence_reference",
        ):
            assert reverse[field] == original[field], field
        after = counts(f)
        assert request(f, order, suffix=suffix, body=body, key=key) == reverse
        assert counts(f) == after
        assert {model: rows(f, model) for model in protected} == before
    assert counts(f) == tuple(count + 10 for count in baseline)
    assert [row for row in rows(f, Expense) if row["kind"] == "EXPENSE"] == posted
    final = request(f, order, "get", "/summary", status=200)
    assert final["net_additional_cost"] == final["net_included_cost"] == "0.0000"
    assert Decimal(final["adjusted_forecast_gross_profit"]) == Decimal(order["gross_profit"])


@pytest.mark.parametrize("role", list(MembershipRole))
def test_expense_http_read_record_and_reverse_six_role_matrix(quotation_fixture, role):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    original = request(f, order, body=payload(order))
    with f.session_factory.begin() as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_a,
                OrganizationMembership.user_id == f.sales_user,
            )
        )
        membership.role = role
    allowed = role in {MembershipRole.ADMIN, MembershipRole.MANAGER, MembershipRole.FINANCE}
    before = counts(f)
    for suffix in ("", f"/{original['id']}", "/summary"):
        result = request(
            f, order, "get", suffix, subject="quotation-sales", status=200 if allowed else 403
        )
        if not allowed:
            assert result["code"] == "PERMISSION_DENIED"
            assert original["description"] not in str(result)
    request(
        f, order, body=payload(order), subject="quotation-sales", status=201 if allowed else 403
    )
    request(
        f,
        order,
        suffix=f"/{original['id']}/reverse",
        body={"expected_version": original["version"], "reason": "Verified correction"},
        subject="quotation-sales",
        status=201 if allowed else 403,
    )
    assert counts(f) == tuple(count + (2 if allowed else 0) for count in before)
