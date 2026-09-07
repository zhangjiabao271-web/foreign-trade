from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from alembic import command
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership
from app.platform.models import AuditLog, OutboxEvent
from app.platform.records import AuditRecorder, OutboxRecorder
from app.procurement.models import PurchaseOrder, PurchaseOrderItem
from app.procurement.services import PurchaseOrderCommandService
from app.work.models import Activity
from legacy_migration import verify_legacy_upgrade
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_migrations import alembic_config
from test_order_procurement_vertical_slice import create_confirmed_order
from test_quotation_vertical_slice import QuotationFixture, post_ok

pytest_plugins = ("test_quotation_vertical_slice",)


def confirmed_purchase(fixture: QuotationFixture):
    order, _, company = create_confirmed_order(fixture)
    post_ok(
        fixture, f"/api/v1/companies/{company}/roles", "quotation-sales", {"role": "SUPPLIER"}, 201
    )
    purchase = post_ok(
        fixture,
        "/api/v1/purchase-orders",
        "quotation-manager",
        {
            "sales_order_id": order["id"],
            "supplier_company_id": company,
            "currency_code": "CNY",
            "exchange_rate": "0.12800000",
            "items": [
                {"sales_order_item_id": item["id"], "quantity": "1.0000", "unit_cost": "4.0000"}
                for item in order["items"]
            ],
        },
        201,
    )
    path = f"/api/v1/purchase-orders/{purchase['id']}"
    post_ok(fixture, path + "/approve", "quotation-manager")
    post_ok(fixture, path + "/send", "quotation-operations")
    confirmed = post_ok(
        fixture,
        path + "/confirm",
        "quotation-operations",
        {"expected_delivery_date": date.today().isoformat()},
    )
    assert confirmed["total"] is None
    return fixture.client.get(
        path, headers=fixture.headers("quotation-manager", fixture.organization_a)
    ).json()


def receipt(purchase, quantity="0.5000"):
    return {
        "expected_version": purchase["version"],
        "reference": "RECEIPT-TEST",
        "received_date": date.today().isoformat(),
        "items": [
            {"purchase_order_item_id": item["id"], "quantity": quantity}
            for item in purchase["items"]
        ],
    }


def test_partial_full_close_idempotency_and_guards(quotation_fixture: QuotationFixture):
    f = quotation_fixture
    po = confirmed_purchase(f)
    path = f"/api/v1/purchase-orders/{po['id']}"
    headers = f.headers("quotation-operations", f.organization_a) | {
        "Idempotency-Key": "receipt-first"
    }
    with f.session_factory.begin() as session:
        member = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_b
            )
        )
        member.role = MembershipRole.OPERATIONS
    data = receipt(po)
    denied = f.client.post(
        path + "/receive",
        headers=f.headers("quotation-sales", f.organization_a) | {"Idempotency-Key": "denied"},
        json=data,
    )
    assert denied.status_code == 403
    assert (
        f.client.post(
            path + "/receive",
            headers=f.headers("quotation-other", f.organization_b) | {"Idempotency-Key": "foreign"},
            json=data,
        ).status_code
        == 404
    )
    partial = f.client.post(path + "/receive", headers=headers, json=data)
    assert partial.status_code == 200, partial.text
    partial = partial.json()
    assert partial["status"] == "PARTIALLY_RECEIVED"
    assert all(Decimal(item["received_quantity"]) == Decimal("0.5000") for item in partial["items"])
    assert partial["total"] is None
    assert (
        f.client.get(path, headers=f.headers("quotation-manager", f.organization_a)).json()["total"]
        == po["total"]
    )
    assert f.client.post(path + "/receive", headers=headers, json=data).json() == partial
    assert (
        f.client.post(path + "/receive", headers=headers, json=receipt(po, "0.1000")).status_code
        == 409
    )
    assert (
        f.client.post(
            path + "/receive", headers=headers | {"Idempotency-Key": "stale"}, json=data
        ).status_code
        == 409
    )
    assert (
        f.client.post(
            path + "/close",
            headers=headers | {"Idempotency-Key": "early"},
            json={"expected_version": partial["version"], "reason": "Finish"},
        ).status_code
        == 409
    )
    excessive = f.client.post(
        path + "/receive",
        headers=headers | {"Idempotency-Key": "excess"},
        json=receipt(partial, "0.5001"),
    )
    assert excessive.status_code == 409
    assert excessive.json()["code"] == "RECEIPT_QUANTITY_EXCEEDED"
    assert f.client.get(path, headers=headers).json() == partial
    full = f.client.post(
        path + "/receive", headers=headers | {"Idempotency-Key": "remaining"}, json=receipt(partial)
    ).json()
    assert full["status"] == "RECEIVED"
    assert full["received_at"] is not None
    closed = f.client.post(
        path + "/close",
        headers=headers | {"Idempotency-Key": "close"},
        json={"expected_version": full["version"], "reason": "All quantities checked"},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "CLOSED"
    assert closed.json()["closed_at"] is not None
    history = f.client.get(path + "/activities", headers=headers)
    assert history.status_code == 200
    assert (
        sum(
            row["activity_type"] == "purchase_order.receipt_recorded"
            for row in history.json()["items"]
        )
        == 2
    )
    assert (
        f.client.get(
            path + "/activities", headers=f.headers("quotation-other", f.organization_b)
        ).status_code
        == 404
    )
    assert (
        len(f.client.get(path + "/activities?limit=1&offset=1", headers=headers).json()["items"])
        == 1
    )
    with f.session_factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "purchase_order.receipt_recorded")
            )
            == 2
        )
        assert (
            session.scalar(
                select(func.count())
                .select_from(OutboxEvent)
                .where(OutboxEvent.event_type == "purchase_order.receipt_recorded.v1")
            )
            == 2
        )


def test_concurrent_receiving_has_one_winner(quotation_fixture: QuotationFixture):
    f = quotation_fixture
    po = confirmed_purchase(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )

    def receive(index):
        try:
            PurchaseOrderCommandService(f.session_factory).receive(
                context,
                UUID(po["id"]),
                receipt(po, "0.6000"),
                idempotency_key=f"concurrent-{index}",
            )
            return "ok"
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(receive, range(2))) == ["VERSION_CONFLICT", "ok"]
    with f.session_factory() as session:
        quantities = session.scalars(
            select(PurchaseOrderItem.received_quantity).where(
                PurchaseOrderItem.purchase_order_id == UUID(po["id"])
            )
        ).all()
        assert all(q == Decimal("0.6000") for q in quantities)


@pytest.mark.parametrize("recorder", [AuditRecorder, OutboxRecorder, Activity])
def test_receipt_failure_rolls_back_quantities_and_version(
    quotation_fixture: QuotationFixture, monkeypatch, recorder
):
    f = quotation_fixture
    po = confirmed_purchase(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )

    def fail(*args, **kwargs):
        raise RuntimeError("injected receipt failure")

    if recorder is Activity:
        original_add = Session.add

        def add(session, instance, *args, **kwargs):
            if isinstance(instance, Activity):
                raise RuntimeError("injected receipt failure")
            return original_add(session, instance, *args, **kwargs)

        monkeypatch.setattr(Session, "add", add)
    else:
        monkeypatch.setattr(recorder, "record", fail)
    with pytest.raises(RuntimeError, match="injected receipt failure"):
        PurchaseOrderCommandService(f.session_factory).receive(
            context, UUID(po["id"]), receipt(po), idempotency_key="rollback"
        )
    with f.session_factory() as session:
        order = session.get(PurchaseOrder, UUID(po["id"]))
        assert order.status == "CONFIRMED"
        assert order.version == po["version"]
        assert all(
            q == 0
            for q in session.scalars(
                select(PurchaseOrderItem.received_quantity).where(
                    PurchaseOrderItem.purchase_order_id == order.id
                )
            )
        )


def test_previous_purchase_data_survives_receiving_migration(quotation_fixture: QuotationFixture):
    f = quotation_fixture
    po = confirmed_purchase(f)
    config = alembic_config(f.engine.url.render_as_string(hide_password=False))

    def check_upgraded(target):
        with Session(target) as session:
            row = session.get(PurchaseOrder, UUID(po["id"]))
            assert row.total == Decimal(po["total"])
            assert row.supplier_reference == po["supplier_reference"]
            assert row.status == "CONFIRMED"
            assert row.received_at is None
            items = session.scalars(
                select(PurchaseOrderItem).where(PurchaseOrderItem.purchase_order_id == row.id)
            ).all()
            assert all(item.received_quantity == 0 for item in items)
            assert all(item.quantity == Decimal("1.0000") for item in items)

    verify_legacy_upgrade(f.engine, "20260906_0011", check=check_upgraded)
    command.check(config)
