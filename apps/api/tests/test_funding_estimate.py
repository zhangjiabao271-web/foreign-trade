from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission, permissions_for_role
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership
from app.sales.models import SalesOrder
from sqlalchemy import event, select
from test_finance_vertical_slice import allocation, counts, finance_post, payment, receivables
from test_order_expenses import payload, request
from test_order_procurement_vertical_slice import create_confirmed_order
from test_quotation_vertical_slice import create_opportunity, post_ok

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def estimate(f, order):
    response = f.client.get(
        f"/api/v1/sales-orders/{order['id']}/funding-estimate",
        headers=f.headers("quotation-finance", f.organization_a),
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_funding_net_expenses_allocations_reversals_and_zero_floor(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    rows = receivables(f, order)
    receipt = payment(f, order, order["total"])
    original = estimate(f, order)
    cost = Decimal(order["total_cost"])
    assert Decimal(original["estimated_funding_need"]) == cost
    assert original["net_allocated_receipts"] == "0.0000"  # Unallocated cash is excluded.
    extra = request(f, order, body=payload(order, amount="12.3456"))
    request(f, order, body=payload(order, amount="99", cost_treatment="INCLUDED_IN_QUOTATION"))
    for row in rows:
        allocation(f, receipt, row)
    paid = estimate(f, order)
    assert paid["quoted_total_cost"] == order["total_cost"]
    assert paid["net_additional_cost"] == "12.3456"
    assert Decimal(paid["net_allocated_receipts"]) == Decimal(order["total"])
    assert Decimal(paid["estimated_funding_need"]) == max(
        cost + Decimal("12.3456") - Decimal(order["total"]), Decimal(0)
    )
    finance_post(f, f"/api/v1/payments/{receipt['id']}/reverse", {"reason": "Synthetic correction"})
    assert Decimal(estimate(f, order)["estimated_funding_need"]) == cost + Decimal("12.3456")
    request(
        f,
        order,
        suffix=f"/{extra['id']}/reverse",
        body={
            "expected_version": extra["version"],
            "reason": "Synthetic expense correction",
        },
    )
    final = estimate(f, order)
    assert Decimal(final["estimated_funding_need"]) == cost
    assert final["net_additional_cost"] == "0.0000"
    assert final["net_allocated_receipts"] == "0.0000"


@pytest.mark.parametrize("role", list(MembershipRole))
def test_funding_service_roles_one_statement_and_no_writes(quotation_fixture, role):
    from app.finance.funding import FundingQuery

    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=permissions_for_role(role),
        request_id=uuid4(),
    )
    statements = []

    def capture(conn, cursor, statement, parameters, execution_context, executemany):
        statements.append(statement)

    before = counts(f)
    event.listen(f.engine, "before_cursor_execute", capture)
    try:
        with f.session_factory() as session:
            if role in {MembershipRole.ADMIN, MembershipRole.MANAGER, MembershipRole.FINANCE}:
                result = FundingQuery(session).get(context, UUID(order["id"]))
                assert result.quoted_total_cost == Decimal(order["total_cost"])
                assert len(statements) == 1 and statements[0].startswith("SELECT")
            else:
                with pytest.raises(ApiProblem) as denied:
                    FundingQuery(session).get(context, UUID(order["id"]))
                assert denied.value.status == 403
                assert statements == []
    finally:
        event.remove(f.engine, "before_cursor_execute", capture)
    assert counts(f) == before
    if Permission.PROFIT_READ in context.permissions:
        with f.session_factory() as session, pytest.raises(ApiProblem) as foreign:
            FundingQuery(session).get(
                replace(context, organization_id=f.organization_b), UUID(order["id"])
            )
        assert foreign.value.status == 404


def test_funding_http_denies_low_roles(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    for subject in ("quotation-sales", "quotation-operations"):
        response = f.client.get(
            f"/api/v1/sales-orders/{order['id']}/funding-estimate",
            headers=f.headers(subject, f.organization_a),
        )
        assert response.status_code == 403
        assert "quoted_total_cost" not in response.text


@pytest.mark.parametrize("role", list(MembershipRole))
def test_funding_http_role_matrix(quotation_fixture, role):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    with f.session_factory.begin() as session:
        membership = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_a,
                OrganizationMembership.user_id == f.sales_user,
            )
        )
        membership.role = role
    response = f.client.get(
        f"/api/v1/sales-orders/{order['id']}/funding-estimate",
        headers=f.headers("quotation-sales", f.organization_a),
    )
    allowed = role in {MembershipRole.ADMIN, MembershipRole.MANAGER, MembershipRole.FINANCE}
    assert response.status_code == (200 if allowed else 403), response.text
    assert ("quoted_total_cost" in response.json()) == allowed


@pytest.mark.parametrize(
    "missing",
    [
        Permission.ORDER_READ,
        Permission.EXPENSE_READ,
        Permission.RECEIVABLE_READ,
        Permission.PROFIT_READ,
    ],
)
def test_funding_requires_each_permission_before_repository_access(missing):
    from app.finance.funding import FundingQuery

    context = RequestContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        request_id=uuid4(),
        permissions=permissions_for_role(MembershipRole.ADMIN) - {missing},
    )
    # None deliberately fails if a denied read ever reaches the database.
    with pytest.raises(ApiProblem) as denied:
        FundingQuery(None).get(context, uuid4())
    assert denied.value.status == 403


def test_funding_uses_stored_fx_rounding_and_hides_deleted_order(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    expense = request(
        f,
        order,
        body=payload(
            order,
            currency_code="JPY",
            amount="1",
            exchange_rate="0.12345",
        ),
    )
    assert expense["order_currency_amount"] == "0.1235"
    result = estimate(f, order)
    assert result["net_additional_cost"] == "0.1235"
    assert Decimal(result["estimated_funding_need"]) == Decimal(order["total_cost"]) + Decimal(
        "0.1235"
    )
    with f.session_factory.begin() as session:
        session.scalar(
            select(SalesOrder).where(
                SalesOrder.organization_id == f.organization_a,
                SalesOrder.id == UUID(order["id"]),
            )
        ).deleted_at = datetime.now(UTC)
    response = f.client.get(
        f"/api/v1/sales-orders/{order['id']}/funding-estimate",
        headers=f.headers("quotation-manager", f.organization_a),
    )
    assert response.status_code == 404
    assert "quoted_total_cost" not in response.json()


def test_funding_excludes_other_order_of_same_customer(quotation_fixture):
    f = quotation_fixture
    first, accepted, company_id = create_confirmed_order(f)
    second_company, opportunity_id = create_opportunity(f)
    assert second_company == company_id
    inquiry = post_ok(
        f,
        "/api/v1/inquiries",
        "quotation-sales",
        {
            "company_id": company_id,
            "opportunity_id": opportunity_id,
            "description": "Second independent order for funding isolation",
            "customer_reference": "SECOND-FUNDING-ORDER",
            "received_at": datetime.now(UTC).isoformat(),
        },
        201,
    )
    quotation = post_ok(
        f,
        "/api/v1/quotations",
        "quotation-manager",
        {
            "inquiry_id": inquiry["id"],
            "currency_code": accepted["currency_code"],
            "base_currency_code": accepted["base_currency_code"],
            "exchange_rate": accepted["exchange_rate"],
            "valid_until": accepted["valid_until"],
            "items": [
                {
                    key: item[key]
                    for key in (
                        "product_id",
                        "quantity",
                        "unit_price",
                        "cost_exchange_rate",
                    )
                }
                for item in accepted["items"]
            ],
        },
        201,
    )
    for command, subject in (
        ("submit", "quotation-sales"),
        ("approve", "quotation-manager"),
        ("send", "quotation-sales"),
        ("accept", "quotation-sales"),
    ):
        post_ok(f, f"/api/v1/quotations/{quotation['id']}/{command}", subject)
    second = post_ok(
        f,
        "/api/v1/sales-orders",
        "quotation-sales",
        {
            "quotation_id": quotation["id"],
            "deposit_rate": "0.3",
            "deposit_due_date": first["deposit_due_date"],
        },
        201,
    )
    second = post_ok(f, f"/api/v1/sales-orders/{second['id']}/confirm", "quotation-manager")
    original = estimate(f, first)
    extra = request(f, second, body=payload(second, amount="25"))
    receipt = payment(f, second, second["total"])
    for row in receivables(f, second):
        allocation(f, receipt, row)
    assert estimate(f, first) == original
    result = estimate(f, second)
    assert result["net_additional_cost"] == extra["order_currency_amount"]
    assert result["net_allocated_receipts"] == second["total"]
