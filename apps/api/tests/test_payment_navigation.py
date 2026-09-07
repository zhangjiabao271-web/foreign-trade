from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.companies.models import Company
from app.finance.models import Payment
from app.finance.repositories import PaymentRepository
from app.finance.services import PaymentQueryService
from sqlalchemy import event

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def seed_payments(f):
    with f.session_factory.begin() as session:
        customers = [
            Company(organization_id=org, name=name, name_normalized=name)
            for org, name in [
                (f.organization_a, "customer"),
                (f.organization_a, "other"),
                (f.organization_b, "foreign"),
            ]
        ]
        session.add_all(customers)
        session.flush()
        tied = datetime(2026, 9, 5, tzinfo=UTC)
        rows = []
        for index in range(126):
            customer = customers[0] if index < 123 else customers[1 if index < 125 else 2]
            row = Payment(
                organization_id=customer.organization_id,
                company_id=customer.id,
                payment_number=f"RC-{index:04}",
                reference="BANK_%_Exact" if index == 0 else f"Bank-{index}",
                amount=Decimal("12.3400"),
                currency_code="EUR" if index != 122 else "USD",
                kind="RECEIPT",
                status="ACTIVE",
                method="BANK_TRANSFER",
                received_at=tied if index else tied - timedelta(days=365),
                created_at=tied,
            )
            session.add(row)
            rows.append(row)
        session.flush()
        return [c.id for c in customers], [r.id for r in rows]


def test_customer_currency_cursor_reaches_old_receipts_without_duplicates(quotation_fixture):
    f = quotation_fixture
    customers, ids = seed_payments(f)
    headers = f.headers("quotation-finance", f.organization_a)
    params = {"company_id": str(customers[0]), "currency_code": "EUR", "limit": 20}
    seen = []
    while True:
        response = f.client.get("/api/v1/payments", params=params, headers=headers)
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["count"] == len(page["items"]) <= 20
        seen.extend(row["id"] for row in page["items"])
        assert all(row["available_amount"] == "12.3400" for row in page["items"])
        if not page["has_more"]:
            assert page["next_cursor"] is None
            break
        params["cursor"] = page["next_cursor"]
    assert len(seen) == len(set(seen)) == 122
    assert seen[-1] == str(ids[0])
    assert set(seen) == {str(row) for row in ids[:122]}


def test_search_literal_wildcards_scope_cursor_and_validation(quotation_fixture):
    f = quotation_fixture
    customers, ids = seed_payments(f)
    headers = f.headers("quotation-finance", f.organization_a)

    def get(**params):
        return f.client.get("/api/v1/payments", params=params, headers=headers)

    for query in ["bank_%_exact", "_%_", "rc-0000", " BANK_%_Exact "]:
        assert [row["id"] for row in get(query=query).json()["items"]] == [str(ids[0])]
    assert get(company_id=str(customers[2])).json()["items"] == []
    for cursor in [uuid4(), ids[-1], ids[123], ids[122]]:
        assert (
            get(company_id=str(customers[0]), currency_code="EUR", cursor=str(cursor)).status_code
            == 404
        )
    assert get(query="no-match", cursor=str(ids[0])).status_code == 404
    for params in [
        {"currency_code": "eur"},
        {"limit": 0},
        {"limit": 101},
        {"query": "x" * 161},
        {"cursor": "bad"},
    ]:
        assert get(**params).status_code == 422
    denied = f.client.get("/api/v1/payments")
    assert denied.status_code == 401
    with f.session_factory() as session:
        context = RequestContext(
            user_id=f.sales_user,
            organization_id=f.organization_a,
            permissions=frozenset(),
            request_id=uuid4(),
        )
        with pytest.raises(ApiProblem) as error:
            PaymentQueryService(PaymentRepository(session)).list(context, limit=20)
        assert error.value.status == 403


def test_receipt_page_batches_allocations(quotation_fixture):
    f = quotation_fixture
    seed_payments(f)
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if "payment_allocations" in statement:
            statements.append(statement)

    event.listen(f.engine, "before_cursor_execute", capture)
    try:
        response = f.client.get(
            "/api/v1/payments", headers=f.headers("quotation-finance", f.organization_a)
        )
        assert response.status_code == 200
        assert response.json()["count"] == 50
        assert len(statements) == 1
    finally:
        event.remove(f.engine, "before_cursor_execute", capture)
