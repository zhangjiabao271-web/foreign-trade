from uuid import UUID

import pytest
from app.finance.models import Payment, PaymentAllocation, Receivable
from app.finance.supplier_models import Payable, SupplierPayment, SupplierPaymentAllocation
from app.procurement.models import PurchaseOrder, PurchaseOrderItem
from app.sales.models import SalesOrder
from sqlalchemy import select
from test_purchase_changes import change_request, headers, replacement
from test_purchase_receiving import receipt
from test_supplier_settlement import allocate_body, payable_body, payment_body, purchase, request

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def rows(f, model):
    with f.session_factory() as session:
        return [
            dict(row)
            for row in session.execute(
                select(model.__table__)
                .where(model.organization_id == f.organization_a)
                .order_by(model.id)
            ).mappings()
        ]


@pytest.mark.parametrize("command", ["cancel", "amend"])
@pytest.mark.parametrize("received", [False, True])
def test_procurement_change_preserves_recorded_supplier_debt_and_payment(
    quotation_fixture, command, received
):
    f = quotation_fixture
    po = purchase(f)
    if received:
        po = request(
            f,
            f"/purchase-orders/{po['id']}/receive",
            body=receipt(po, "0.2500"),
            status=200,
            subject="quotation-manager",
        )
        assert po["status"] == "PARTIALLY_RECEIVED"
    payable = request(f, "/payables", body=payable_body(po, amount="60"))
    payment = request(f, "/supplier-payments", body=payment_body(po, amount="40"))
    allocated = request(
        f,
        f"/supplier-payments/{payment['id']}/allocate",
        body=allocate_body(payment, payable, "25"),
        status=200,
    )
    assert allocated["available_amount"] == "15.0000"
    models = (
        Payable,
        SupplierPayment,
        SupplierPaymentAllocation,
        Payment,
        PaymentAllocation,
        Receivable,
        SalesOrder,
    )
    before = {model: rows(f, model) for model in models}
    original_items = rows(f, PurchaseOrderItem)
    original_purchase = rows(f, PurchaseOrder)[0]
    data = change_request(po)
    if command == "amend":
        data["replacement"] = replacement(po)
    path = f"/api/v1/purchase-orders/{po['id']}/{command}"
    response = f.client.post(path, headers=headers(f, command), json=data)
    assert response.status_code == 200, response.text
    result = response.json()
    assert {model: rows(f, model) for model in models} == before
    assert [
        row for row in rows(f, PurchaseOrderItem) if row["purchase_order_id"] == UUID(po["id"])
    ] == original_items
    old = next(row for row in rows(f, PurchaseOrder) if row["id"] == UUID(po["id"]))
    assert old["status"] == "CANCELLED"
    for field in (
        "total",
        "total_order_currency",
        "currency_code",
        "exchange_rate",
        "supplier_company_id",
        "confirmed_at",
        "supplier_reference",
    ):
        assert old[field] == original_purchase[field], field
    if command == "amend":
        assert result["status"] == "DRAFT"
        assert result["replaces_purchase_order_id"] == po["id"]
        assert result["approved_at"] is None and result["confirmed_at"] is None
    assert f.client.post(path, headers=headers(f, command), json=data).json() == result
    assert {model: rows(f, model) for model in models} == before
    current = request(f, f"/payables/{payable['id']}", method="get", status=200)
    assert current["amount"] == "60.0000"
    assert current["paid_amount"] == "25.0000" and current["balance"] == "35.0000"

    # A cancelled confirmed purchase may receive a manually reconciled late invoice.
    # The cap remains original principal, not the lower retained received value.
    late = request(f, "/payables", body=payable_body(po, amount="40", reference="LATE-INV"))
    assert late["amount"] == late["balance"] == "40.0000"
    before_overcap = {model: rows(f, model) for model in models}
    request(
        f, "/payables", body=payable_body(po, amount="0.0001", reference="OVER-CAP"), status=409
    )
    assert {model: rows(f, model) for model in models} == before_overcap
