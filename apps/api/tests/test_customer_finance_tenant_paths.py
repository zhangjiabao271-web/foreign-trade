from decimal import Decimal
from uuid import UUID

import pytest
from app.auth.errors import ApiProblem
from app.finance.models import Payment, PaymentAllocation, Receivable
from app.finance.repositories import PaymentRepository, ReceivableRepository
from sqlalchemy import select
from test_finance_vertical_slice import allocation, finance_post, payment, receivables
from test_order_procurement_vertical_slice import create_confirmed_order
from test_sales_foreign_commands import foreign_manager
from test_shipment_parent_atomicity import snapshot

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def facts(f):
    with f.session_factory() as session:
        return snapshot(f) | {
            model.__tablename__: [
                dict(row)
                for row in session.execute(select(model.__table__).order_by(model.id)).mappings()
            ]
            for model in (Payment, PaymentAllocation, Receivable)
        }


def test_customer_finance_repositories_and_foreign_manager_http(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    rows = receivables(f, order)
    receipt = payment(f, order, "1")
    allocation(f, receipt, rows[0], "1")
    reversal = finance_post(
        f, f"/api/v1/payments/{receipt['id']}/reverse", {"reason": "Synthetic scope evidence"}
    )
    foreign_manager(f)
    order_id, payment_id = UUID(order["id"]), UUID(receipt["id"])
    receivable_ids = {UUID(row["id"]) for row in rows}
    with f.session_factory() as session:
        payments = PaymentRepository(session)
        receivable_repository = ReceivableRepository(session)
        for organization_id, own in ((f.organization_a, True), (f.organization_b, False)):
            assert bool(payments.get(organization_id=organization_id, record_id=payment_id)) == own
            assert len(payments.list(organization_id=organization_id)) == (2 if own else 0)
            assert payments.count(organization_id=organization_id) == (2 if own else 0)
            assert (
                bool(
                    payments.get_for_update(organization_id=organization_id, payment_id=payment_id)
                )
                == own
            )
            found = payments.reversal_for(organization_id=organization_id, payment_id=payment_id)
            assert (found.id if found else None) == (UUID(reversal["id"]) if own else None)
            assert (
                bool(payments.allocations(organization_id=organization_id, payment_id=payment_id))
                == own
            )
            assert (
                bool(
                    payments.allocations_for_payments(
                        organization_id=organization_id, payment_ids={payment_id}
                    )
                )
                == own
            )
            assert payments.allocated_amount(
                organization_id=organization_id, payment_id=payment_id
            ) == Decimal(int(own))
            assert (
                bool(
                    receivable_repository.get(
                        organization_id=organization_id, record_id=UUID(rows[0]["id"])
                    )
                )
                == own
            )
            assert len(receivable_repository.list(organization_id=organization_id)) == (
                len(rows) if own else 0
            )
            assert receivable_repository.count(organization_id=organization_id) == (
                len(rows) if own else 0
            )
            assert (
                bool(
                    receivable_repository.locked(
                        organization_id=organization_id, ids=receivable_ids
                    )
                )
                == own
            )
            assert (
                bool(
                    receivable_repository.locked_for_order(
                        organization_id=organization_id, sales_order_id=order_id
                    )
                )
                == own
            )
            assert (
                bool(
                    receivable_repository.list_with_allocated(
                        organization_id=organization_id, sales_order_id=order_id, limit=100
                    )
                )
                == own
            )
            totals = receivable_repository.allocated_totals(
                organization_id=organization_id, receivable_ids=receivable_ids
            )
            assert totals == ({UUID(rows[0]["id"]): Decimal(0)} if own else {})
        assert (
            payments.allocations_for_payments(organization_id=f.organization_a, payment_ids=set())
            == []
        )
        assert (
            receivable_repository.allocated_totals(
                organization_id=f.organization_a, receivable_ids=set()
            )
            == {}
        )
        assert payments.list_recent(organization_id=f.organization_b, limit=100) == []
        with pytest.raises(ApiProblem) as denied:
            payments.list_recent(organization_id=f.organization_b, limit=100, cursor=payment_id)
        assert denied.value.status == 404

    headers = {
        **f.headers("quotation-other", f.organization_b),
        "Idempotency-Key": "foreign-finance",
    }
    before = facts(f)
    paths = (
        ("GET", f"/api/v1/payments/{payment_id}", None, 404),
        ("GET", f"/api/v1/payments?cursor={payment_id}", None, 404),
        ("GET", f"/api/v1/payments/{payment_id}/text-review", None, 404),
        (
            "POST",
            f"/api/v1/payments/{payment_id}/text-review",
            {
                "expected_version": 1,
                "content_digest": "0" * 64,
                "release": False,
                "confirmed": True,
                "reason": "Synthetic denied review",
            },
            404,
        ),
        (
            "POST",
            "/api/v1/payments",
            {
                "company_id": order["company_id"],
                "amount": "1",
                "currency_code": order["currency_code"],
                "method": "BANK_TRANSFER",
                "received_at": "2026-09-05T00:00:00Z",
            },
            404,
        ),
        (
            "POST",
            f"/api/v1/payments/{payment_id}/allocate",
            {
                "allocations": [{"receivable_id": rows[0]["id"], "amount": "1"}],
            },
            404,
        ),
        (
            "POST",
            f"/api/v1/payments/{payment_id}/reverse",
            {"reason": "Synthetic denied reversal"},
            404,
        ),
        (
            "POST",
            f"/api/v1/sales-orders/{order_id}/generate-receivables",
            {"balance_due_date": "2026-10-01"},
            404,
        ),
        ("POST", f"/api/v1/sales-orders/{order_id}/complete", {"expected_version": 1}, 404),
        ("GET", f"/api/v1/receivables?sales_order_id={order_id}", None, 200),
        ("GET", f"/api/v1/payments?company_id={order['company_id']}", None, 200),
        ("POST", "/api/v1/receivables/refresh-statuses", None, 200),
    )
    for method, path, body, status in paths:
        response = f.client.request(method, path, headers=headers, json=body)
        assert response.status_code == status, (path, response.text)
        if status == 200:
            assert response.json()["items"] == []
        assert facts(f) == before
