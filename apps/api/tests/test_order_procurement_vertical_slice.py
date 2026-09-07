from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.platform.models import AuditLog, OutboxEvent
from app.platform.records import DomainEvent, OutboxRecorder
from app.procurement.models import PurchaseOrder
from app.sales.models import SalesOrder
from app.sales.order_services import SalesOrderCommandService
from app.work.models import Activity, Task
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_quotation_vertical_slice import (
    QuotationFixture,
    create_commercial_inputs,
    post_ok,
    purchase_decision,
)

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def create_accepted_quotation(
    fixture: QuotationFixture,
) -> tuple[dict[str, object], dict[str, object], str]:
    request, company_id, _ = create_commercial_inputs(fixture)
    quotation = post_ok(fixture, "/api/v1/quotations", "quotation-manager", request, 201)
    quotation_id = str(quotation["id"])
    post_ok(fixture, f"/api/v1/quotations/{quotation_id}/submit", "quotation-sales")
    post_ok(fixture, f"/api/v1/quotations/{quotation_id}/approve", "quotation-manager")
    post_ok(fixture, f"/api/v1/quotations/{quotation_id}/send", "quotation-sales")
    accepted = post_ok(fixture, f"/api/v1/quotations/{quotation_id}/accept", "quotation-sales")
    assert accepted["total_cost"] is None
    detail = fixture.client.get(
        f"/api/v1/quotations/{quotation_id}",
        headers=fixture.headers("quotation-manager", fixture.organization_a),
    )
    assert detail.status_code == 200
    accepted = detail.json()["current_version"]
    return quotation, accepted, company_id


def create_confirmed_order(
    fixture: QuotationFixture,
) -> tuple[dict[str, object], dict[str, object], str]:
    quotation, accepted, company_id = create_accepted_quotation(fixture)
    created = post_ok(
        fixture,
        "/api/v1/sales-orders",
        "quotation-sales",
        {
            "quotation_id": str(quotation["id"]),
            "deposit_rate": "0.3000",
            "deposit_due_date": (date.today() + timedelta(days=7)).isoformat(),
        },
        201,
    )
    confirmed = post_ok(
        fixture,
        f"/api/v1/sales-orders/{created['id']}/confirm",
        "quotation-manager",
    )
    return confirmed, accepted, company_id


def phase_four_counts(fixture: QuotationFixture) -> tuple[int, int, int, int, int]:
    with fixture.session_factory() as session:
        return (
            session.scalar(select(func.count()).select_from(SalesOrder)) or 0,
            session.scalar(select(func.count()).select_from(PurchaseOrder)) or 0,
            session.scalar(select(func.count()).select_from(Task)) or 0,
            session.scalar(select(func.count()).select_from(Activity)) or 0,
            (session.scalar(select(func.count()).select_from(AuditLog)) or 0)
            + (session.scalar(select(func.count()).select_from(OutboxEvent)) or 0),
        )


def test_accepted_quotation_creates_stable_idempotent_order_and_procurement_task(
    quotation_fixture: QuotationFixture,
) -> None:
    quotation, accepted, _ = create_accepted_quotation(quotation_fixture)
    request = {
        "quotation_id": str(quotation["id"]),
        "deposit_rate": "0.3000",
        "deposit_due_date": (date.today() + timedelta(days=7)).isoformat(),
    }
    before = phase_four_counts(quotation_fixture)
    created = post_ok(
        quotation_fixture,
        "/api/v1/sales-orders",
        "quotation-manager",
        request,
        201,
    )
    repeated = post_ok(
        quotation_fixture,
        "/api/v1/sales-orders",
        "quotation-manager",
        request,
        201,
    )
    assert repeated == created
    assert created["quotation_version_id"] == accepted["id"]
    assert created["currency_code"] == accepted["currency_code"]
    assert created["total"] == accepted["total"]
    assert created["gross_profit"] == accepted["gross_profit"]
    assert Decimal(str(created["deposit_amount"])) == (
        Decimal(str(accepted["total"])) * Decimal("0.3000")
    ).quantize(Decimal("0.0001"))
    assert created["items"] == [
        {
            **item,
            "id": order_item["id"],
            "quotation_item_id": item["id"],
        }
        for item, order_item in zip(accepted["items"], created["items"], strict=True)
    ]
    after_create = phase_four_counts(quotation_fixture)
    assert after_create[0] == before[0] + 1

    sales_confirm = quotation_fixture.client.post(
        f"/api/v1/sales-orders/{created['id']}/confirm",
        headers=quotation_fixture.headers("quotation-sales", quotation_fixture.organization_a),
    )
    assert sales_confirm.status_code == 403
    confirmed = post_ok(
        quotation_fixture,
        f"/api/v1/sales-orders/{created['id']}/confirm",
        "quotation-manager",
    )
    assert confirmed["status"] == "DEPOSIT_PENDING"
    assert confirmed["confirmed_at"] is not None
    after_confirm = phase_four_counts(quotation_fixture)
    assert after_confirm[2] == before[2] + 1
    assert phase_four_counts(quotation_fixture) == after_confirm
    assert (
        post_ok(
            quotation_fixture,
            f"/api/v1/sales-orders/{created['id']}/confirm",
            "quotation-manager",
        )
        == confirmed
    )
    assert phase_four_counts(quotation_fixture) == after_confirm

    other_headers = quotation_fixture.headers("quotation-other", quotation_fixture.organization_b)
    assert quotation_fixture.client.get("/api/v1/sales-orders", headers=other_headers).json() == {
        "items": [],
        "count": 0,
        "has_more": False,
        "next_cursor": None,
    }
    assert (
        quotation_fixture.client.get(
            f"/api/v1/sales-orders/{created['id']}", headers=other_headers
        ).status_code
        == 404
    )


def test_purchase_order_lifecycle_enforces_supplier_quantity_amount_and_permissions(
    quotation_fixture: QuotationFixture,
) -> None:
    order, _, company_id = create_confirmed_order(quotation_fixture)
    post_ok(
        quotation_fixture,
        f"/api/v1/companies/{company_id}/roles",
        "quotation-sales",
        {"role": "SUPPLIER"},
        201,
    )
    order_items = order["items"]
    request = {
        "sales_order_id": str(order["id"]),
        "supplier_company_id": company_id,
        "currency_code": "CNY",
        "exchange_rate": "0.12800000",
        "items": [
            {
                "sales_order_item_id": str(order_items[0]["id"]),
                "quantity": "1.3333",
                "unit_cost": "8.0000",
            },
            {
                "sales_order_item_id": str(order_items[1]["id"]),
                "quantity": "2.0000",
                "unit_cost": "4.5000",
            },
        ],
    }
    before = phase_four_counts(quotation_fixture)
    forbidden = quotation_fixture.client.post(
        "/api/v1/purchase-orders",
        headers=quotation_fixture.headers("quotation-sales", quotation_fixture.organization_a),
        json=request,
    )
    assert forbidden.status_code == 403
    assert phase_four_counts(quotation_fixture) == before

    purchase_order = post_ok(
        quotation_fixture,
        "/api/v1/purchase-orders",
        "quotation-manager",
        request,
        201,
    )
    expected_total = Decimal("1.3333") * Decimal("8.0000") + Decimal("2.0000") * Decimal("4.5000")
    assert Decimal(str(purchase_order["total"])) == expected_total.quantize(Decimal("0.0001"))
    assert Decimal(str(purchase_order["total_order_currency"])) == (
        expected_total * Decimal("0.12800000")
    ).quantize(Decimal("0.0001"))

    premature_confirm = quotation_fixture.client.post(
        f"/api/v1/purchase-orders/{purchase_order['id']}/confirm",
        headers=quotation_fixture.headers("quotation-operations", quotation_fixture.organization_a)
        | {"Idempotency-Key": str(uuid4())},
        json={
            **purchase_decision(quotation_fixture, purchase_order["id"]),
            "expected_delivery_date": (date.today() + timedelta(days=20)).isoformat(),
        },
    )
    assert premature_confirm.status_code == 409
    assert premature_confirm.json()["code"] == "INVALID_STATE_TRANSITION"
    assert (
        post_ok(
            quotation_fixture,
            f"/api/v1/purchase-orders/{purchase_order['id']}/approve",
            "quotation-manager",
        )["status"]
        == "APPROVED"
    )
    assert (
        post_ok(
            quotation_fixture,
            f"/api/v1/purchase-orders/{purchase_order['id']}/send",
            "quotation-operations",
        )["status"]
        == "SENT"
    )
    confirmed = post_ok(
        quotation_fixture,
        f"/api/v1/purchase-orders/{purchase_order['id']}/confirm",
        "quotation-operations",
        {
            "supplier_reference": "SUP-ACK-77",
            "expected_delivery_date": (date.today() + timedelta(days=20)).isoformat(),
        },
    )
    assert confirmed["status"] == "CONFIRMED"
    assert confirmed["supplier_reference"] == "SUP-ACK-77"

    counts_before_excess = phase_four_counts(quotation_fixture)
    excess_request = {
        **request,
        "items": [
            {
                "sales_order_item_id": str(order_items[0]["id"]),
                "quantity": "2.0001",
                "unit_cost": "8.0000",
            }
        ],
    }
    excess = quotation_fixture.client.post(
        "/api/v1/purchase-orders",
        headers=quotation_fixture.headers("quotation-manager", quotation_fixture.organization_a),
        json=excess_request,
    )
    assert excess.status_code == 409
    assert excess.json()["code"] == "PURCHASE_QUANTITY_EXCEEDED"
    assert phase_four_counts(quotation_fixture) == counts_before_excess


class FailingOrderOutboxRecorder(OutboxRecorder):
    def record(self, session: Session, context: RequestContext, event: DomainEvent) -> OutboxEvent:
        raise RuntimeError("injected sales order outbox failure")


def test_sales_order_creation_rolls_back_when_outbox_fails(
    quotation_fixture: QuotationFixture,
) -> None:
    quotation, _, _ = create_accepted_quotation(quotation_fixture)
    before = phase_four_counts(quotation_fixture)
    service = SalesOrderCommandService(
        quotation_fixture.session_factory,
        outbox_recorder=FailingOrderOutboxRecorder(),
    )
    context = RequestContext(
        user_id=quotation_fixture.sales_user,
        organization_id=quotation_fixture.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    with pytest.raises(RuntimeError, match="injected sales order outbox failure"):
        service.create(
            context,
            {
                "quotation_id": UUID(str(quotation["id"])),
                "deposit_rate": Decimal("0.3000"),
                "deposit_due_date": date.today() + timedelta(days=7),
            },
        )
    assert phase_four_counts(quotation_fixture) == before
