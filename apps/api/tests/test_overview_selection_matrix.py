"""Independent nonempty queue predicates; state seeding is disposable-test-only."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from app.crm.enums import LeadStatus
from app.crm.models import Lead
from app.export.enums import CustomsStatus, TaxRefundStatus
from app.export.models import CustomsDeclaration, TaxRefundCase
from app.finance.models import Receivable
from app.fulfillment.enums import ShipmentStatus
from app.fulfillment.models import Shipment
from app.sales.enums import QuotationVersionStatus
from app.sales.models import Quotation, QuotationVersion, SalesOrder
from app.sales.order_enums import SalesOrderStatus
from sqlalchemy import select
from test_finance_vertical_slice import allocation, finance_post, payment, receivables
from test_order_procurement_vertical_slice import create_confirmed_order
from test_shipment_documents_vertical_slice import create_shipment, executing_order

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


@pytest.mark.parametrize(
    "queue,model,states,included,path",
    [
        (
            "leads",
            Lead,
            LeadStatus,
            {"NEW", "QUALIFIED", "CONTACTED", "RESPONDED", "NO_RESPONSE"},
            "/leads",
        ),
        (
            "quotations",
            QuotationVersion,
            QuotationVersionStatus,
            {"SENT", "CUSTOMER_REVIEW"},
            "/quotations",
        ),
        ("deposits", SalesOrder, SalesOrderStatus, {"DEPOSIT_PENDING"}, "/orders"),
        ("preparation", SalesOrder, SalesOrderStatus, {"EXECUTING", "READY_TO_SHIP"}, "/orders"),
        (
            "shipments",
            Shipment,
            ShipmentStatus,
            {"PLANNING", "BOOKED", "READY", "CUSTOMS"},
            "/shipments",
        ),
        (
            "customs",
            CustomsDeclaration,
            CustomsStatus,
            {"DRAFT", "DOCUMENTS_PENDING", "READY", "SUBMITTED"},
            "/export/customs",
        ),
        (
            "refunds",
            TaxRefundCase,
            TaxRefundStatus,
            {"NOT_READY", "DOCUMENTS_PENDING", "READY", "SUBMITTED", "PROCESSING"},
            "/export/refunds",
        ),
    ],
)
def test_nonempty_queue_state_selection_and_live_tenant_boundaries(
    quotation_fixture, queue, model, states, included, path
):
    f = quotation_fixture
    order = executing_order(f)
    shipment = create_shipment(
        f,
        [
            {"sales_order_item_id": item["id"], "quantity": item["quantity"]}
            for item in order["items"]
        ],
    )
    # Only query predicates are under test here, not legal business transitions.
    with f.session_factory.begin() as session:
        customs = CustomsDeclaration(
            organization_id=f.organization_a,
            shipment_id=UUID(shipment["id"]),
            declaration_number="QUEUE-CUSTOMS",
            declared_amount=Decimal("1"),
            currency_code="EUR",
            required_document_types=["COMMERCIAL_INVOICE"],
        )
        session.add(customs)
        session.flush()
        session.add(
            TaxRefundCase(
                organization_id=f.organization_a,
                customs_declaration_id=customs.id,
                case_number="QUEUE-REFUND",
                expected_amount=Decimal("1"),
                currency_code="EUR",
                required_document_types=["COMMERCIAL_INVOICE"],
            )
        )
    with f.session_factory() as session:
        record = session.scalars(
            select(model).where(
                model.organization_id == f.organization_a,
            )
        ).one()
        record_id = record.id
        target_id = record.quotation_id if queue == "quotations" else record_id

    headers = f.headers("quotation-manager", f.organization_a)
    other = f.headers("quotation-other", f.organization_b)
    for state in states:
        with f.session_factory.begin() as session:
            row = session.get(model, record_id)
            row.status = state.value
        response = f.client.get(f"/api/v1/overview/{queue}", headers=headers)
        assert response.status_code == 200, response.text
        items = response.json()["items"]
        assert [item["id"] for item in items] == (
            [str(record_id)] if state.value in included else []
        ), (queue, state, items)
        if items:
            assert items[0]["href"] == f"{path}/{target_id}"
            assert items[0]["status"] == state.value
            assert items[0]["next_action"]
            if queue in {"customs", "refunds"}:
                assert items[0]["missing_document_types"] == ["COMMERCIAL_INVOICE"]
            elif queue == "shipments":
                assert items[0]["missing_document_types"] == ["COMMERCIAL_INVOICE", "PACKING_LIST"]
        foreign = f.client.get(f"/api/v1/overview/{queue}", headers=other)
        assert foreign.status_code == 200, foreign.text
        assert foreign.json()["items"] == []

    with f.session_factory.begin() as session:
        row = session.get(model, record_id)
        row.status = sorted(included)[0]
        row.deleted_at = datetime.now(UTC)
    deleted = f.client.get(f"/api/v1/overview/{queue}", headers=headers)
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["items"] == []
    if queue == "quotations":
        with f.session_factory.begin() as session:
            row = session.get(QuotationVersion, record_id)
            row.deleted_at = None
            row.is_current = False
        assert f.client.get(f"/api/v1/overview/{queue}", headers=headers).json()["items"] == []
        with f.session_factory.begin() as session:
            session.get(QuotationVersion, record_id).is_current = True
            session.get(Quotation, target_id).deleted_at = datetime.now(UTC)
        assert f.client.get(f"/api/v1/overview/{queue}", headers=headers).json()["items"] == []


def test_due_queue_filters_before_pagination_and_reopens_reversed_receipts(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    installments = {row["installment_type"]: row for row in receivables(f, order)}
    deposit, balance = installments["DEPOSIT"], installments["BALANCE"]
    headers = f.headers("quotation-finance", f.organization_a)

    def page(offset=0):
        response = f.client.get(
            "/api/v1/overview/receivables",
            headers=headers,
            params={"offset": offset, "limit": 1},
        )
        assert response.status_code == 200, response.text
        return response.json()

    today = date.fromisoformat(page()["business_date"])
    with f.session_factory.begin() as session:
        session.get(Receivable, UUID(deposit["id"])).due_date = today - timedelta(days=1)
        session.get(Receivable, UUID(balance["id"])).due_date = today + timedelta(days=1)
    first = page()
    assert [item["id"] for item in first["items"]] == [deposit["id"]]
    assert first["has_more"] is False  # Future balance is excluded before LIMIT.
    with f.session_factory.begin() as session:
        session.get(Receivable, UUID(balance["id"])).due_date = today
    first, second = page(), page(1)
    assert first["has_more"] is True and first["next_offset"] == 1
    assert first["items"][0]["status"] == "OVERDUE"
    assert first["items"][0]["overdue"] is True
    assert [item["id"] for item in second["items"]] == [balance["id"]]
    assert second["items"][0]["status"] == "DUE"
    assert second["items"][0]["overdue"] is False
    assert second["items"][0]["href"] == f"/orders/{order['id']}"
    assert second["has_more"] is False and second["next_offset"] is None

    receipt = payment(f, order, order["total"])
    allocation(f, receipt, deposit, "1.0000")
    assert page()["items"][0]["id"] == deposit["id"]  # Part-paid still due.
    allocation(f, receipt, deposit, Decimal(deposit["amount"]) - Decimal("1"))
    paid_first = page()
    assert [item["id"] for item in paid_first["items"]] == [balance["id"]]
    assert paid_first["has_more"] is False  # Paid earlier row cannot consume the limit.
    allocation(f, receipt, balance)
    assert page()["items"] == []
    finance_post(f, f"/api/v1/payments/{receipt['id']}/reverse", {"reason": "Test reversal"})
    assert page()["items"][0]["id"] == deposit["id"]
    assert page(1)["items"][0]["id"] == balance["id"]
    with f.session_factory.begin() as session:
        session.get(Receivable, UUID(deposit["id"])).deleted_at = datetime.now(UTC)
    assert page()["items"][0]["id"] == balance["id"]
    assert page()["has_more"] is False
