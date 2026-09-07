from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from alembic import command
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.companies.models import Company
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership
from app.platform.records import AuditRecorder, OutboxRecorder
from app.procurement.models import PurchaseOrder
from app.procurement.services import PurchaseOrderCommandService
from app.work.models import Activity
from legacy_migration import verify_legacy_upgrade
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_migrations import alembic_config
from test_purchase_receiving import confirmed_purchase, receipt
from test_quotation_vertical_slice import QuotationFixture

pytest_plugins = ("test_quotation_vertical_slice",)


def headers(fixture, key="cancel", subject="quotation-manager"):
    return fixture.headers(subject, fixture.organization_a) | {"Idempotency-Key": key}


def change_request(po):
    return {
        "expected_version": po["version"],
        "reason": "Supplier agreed to release remaining quantity",
        "supplier_reference": "SUP-CANCEL-1",
    }


def replacement(po):
    return {
        "sales_order_id": po["sales_order_id"],
        "supplier_company_id": po["supplier_company_id"],
        "currency_code": "CNY",
        "exchange_rate": "0.12800000",
        "items": [
            {
                "sales_order_item_id": item["sales_order_item_id"],
                "quantity": "0.5000",
                "unit_cost": "5.1234",
            }
            for item in po["items"]
        ],
    }


def partially_received(fixture):
    po = confirmed_purchase(fixture)
    response = fixture.client.post(
        f"/api/v1/purchase-orders/{po['id']}/receive",
        headers=headers(fixture, "receipt", "quotation-operations"),
        json=receipt(po),
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] is None
    return fixture.client.get(
        f"/api/v1/purchase-orders/{po['id']}", headers=headers(fixture)
    ).json()


def test_cancel_preserves_received_facts_and_releases_only_remaining_capacity(
    quotation_fixture: QuotationFixture,
):
    f = quotation_fixture
    po = partially_received(f)
    path = f"/api/v1/purchase-orders/{po['id']}"
    data = change_request(po)
    assert (
        f.client.post(
            path + "/cancel", headers=headers(f, subject="quotation-sales"), json=data
        ).status_code
        == 403
    )
    missing_reference = dict(data)
    missing_reference.pop("supplier_reference")
    assert (
        f.client.post(path + "/cancel", headers=headers(f), json=missing_reference).status_code
        == 422
    )
    cancelled = f.client.post(path + "/cancel", headers=headers(f), json=data)
    assert cancelled.status_code == 200, cancelled.text
    cancelled = cancelled.json()
    assert cancelled["status"] == "CANCELLED"
    assert cancelled["items"] == po["items"]
    assert cancelled["total"] == po["total"]
    assert Decimal(cancelled["retained_total"]) == Decimal("4.0000")
    assert Decimal(cancelled["retained_total_order_currency"]) == Decimal("0.5120")
    assert f.client.post(path + "/cancel", headers=headers(f), json=data).json() == cancelled
    assert (
        f.client.post(
            path + "/cancel", headers=headers(f, "again"), json=change_request(cancelled)
        ).status_code
        == 409
    )
    assert (
        f.client.post(
            path + "/receive", headers=headers(f, "late"), json=receipt(cancelled)
        ).status_code
        == 409
    )
    sales = f.client.get(f"/api/v1/sales-orders/{po['sales_order_id']}", headers=headers(f)).json()
    fresh = replacement(po)
    fresh["items"] = [
        {
            "sales_order_item_id": item["id"],
            "quantity": str(Decimal(item["quantity"]) - Decimal("0.5000")),
            "unit_cost": "6.0000",
        }
        for item in sales["items"]
    ]
    excess = {**fresh, "items": [dict(item) for item in fresh["items"]]}
    excess["items"][0]["quantity"] = str(
        Decimal(excess["items"][0]["quantity"]) + Decimal("0.0001")
    )
    assert (
        f.client.post("/api/v1/purchase-orders", headers=headers(f), json=excess).status_code == 409
    )
    assert (
        f.client.post("/api/v1/purchase-orders", headers=headers(f), json=fresh).status_code == 201
    )


def test_amendment_creates_linked_unapproved_snapshot_and_is_idempotent(
    quotation_fixture: QuotationFixture,
):
    f = quotation_fixture
    po = partially_received(f)
    path = f"/api/v1/purchase-orders/{po['id']}"
    data = {**change_request(po), "replacement": replacement(po)}
    created = f.client.post(path + "/amend", headers=headers(f, "amend"), json=data)
    assert created.status_code == 200, created.text
    created = created.json()
    assert created["id"] != po["id"]
    assert created["replaces_purchase_order_id"] == po["id"]
    assert created["status"] == "DRAFT"
    assert created["approved_at"] is None and created["confirmed_at"] is None
    assert all(item["unit_cost"] == "5.1234" for item in created["items"])
    assert f.client.post(path + "/amend", headers=headers(f, "amend"), json=data).json() == created
    old = f.client.get(path, headers=headers(f)).json()
    assert old["status"] == "CANCELLED"
    assert old["items"] == po["items"]
    history = f.client.get(path + "/activities", headers=headers(f)).json()["items"]
    assert any(row["activity_type"] == "purchase_order.replaced" for row in history)
    assert (
        f.client.post(
            path + "/amend",
            headers=headers(f, "another"),
            json={**data, "expected_version": old["version"]},
        ).status_code
        == 409
    )


def test_failed_replacement_rolls_back_cancellation(quotation_fixture: QuotationFixture):
    f = quotation_fixture
    po = confirmed_purchase(f)
    path = f"/api/v1/purchase-orders/{po['id']}"
    invalid = replacement(po)
    invalid["items"][0]["quantity"] = "999.0000"
    result = f.client.post(
        path + "/amend", headers=headers(f), json={**change_request(po), "replacement": invalid}
    )
    assert result.status_code == 409
    assert f.client.get(path, headers=headers(f)).json() == po


def test_replacement_outbox_failure_rolls_back_old_and_new(
    quotation_fixture: QuotationFixture, monkeypatch
):
    f = quotation_fixture
    po = confirmed_purchase(f)
    original = OutboxRecorder.record

    def record(self, session, context, event):
        if event.event_type == "purchase_order.created.v1":
            raise RuntimeError("replacement event failed")
        return original(self, session, context, event)

    monkeypatch.setattr(OutboxRecorder, "record", record)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    with pytest.raises(RuntimeError, match="replacement event failed"):
        PurchaseOrderCommandService(f.session_factory).amend(
            context,
            UUID(po["id"]),
            {**change_request(po), "replacement": replacement(po)},
            idempotency_key="failure",
        )
    with f.session_factory() as session:
        assert session.get(PurchaseOrder, UUID(po["id"])).status == "CONFIRMED"
        assert session.scalar(select(func.count()).select_from(PurchaseOrder)) == 1


def test_cancel_and_receipt_cannot_both_use_same_version(quotation_fixture: QuotationFixture):
    f = quotation_fixture
    po = confirmed_purchase(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )

    def execute(kind):
        service = PurchaseOrderCommandService(f.session_factory)
        try:
            if kind == "cancel":
                service.cancel(context, UUID(po["id"]), change_request(po), idempotency_key=kind)
            else:
                service.receive(context, UUID(po["id"]), receipt(po), idempotency_key=kind)
            return "ok"
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(execute, ["cancel", "receive"])) == ["VERSION_CONFLICT", "ok"]


@pytest.mark.parametrize("kind", ["cancel", "amend"])
def test_authorized_foreign_member_cannot_change_purchase(quotation_fixture, kind):
    f = quotation_fixture
    po = confirmed_purchase(f)
    with f.session_factory.begin() as session:
        member = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_b
            )
        )
        member.role = MembershipRole.MANAGER
    data = change_request(po)
    if kind == "amend":
        data["replacement"] = replacement(po)
    response = f.client.post(
        f"/api/v1/purchase-orders/{po['id']}/{kind}",
        headers=f.headers("quotation-other", f.organization_b) | {"Idempotency-Key": kind},
        json=data,
    )
    assert response.status_code == 404, response.text
    assert f.client.get(f"/api/v1/purchase-orders/{po['id']}", headers=headers(f)).json() == po


@pytest.mark.parametrize("kind", ["cancel", "amend"])
@pytest.mark.parametrize("recorder", [AuditRecorder, OutboxRecorder, Activity])
def test_change_failure_rolls_back_all_facts(quotation_fixture, monkeypatch, kind, recorder):
    f = quotation_fixture
    po = confirmed_purchase(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )

    def fail(*args, **kwargs):
        raise RuntimeError("injected change failure")

    if recorder is Activity:
        original_add = Session.add

        def add(session, instance, *args, **kwargs):
            if isinstance(instance, Activity):
                fail()
            return original_add(session, instance, *args, **kwargs)

        monkeypatch.setattr(Session, "add", add)
    else:
        monkeypatch.setattr(recorder, "record", fail)
    data = change_request(po)
    if kind == "amend":
        data["replacement"] = replacement(po)
    with pytest.raises(RuntimeError, match="injected change failure"):
        getattr(PurchaseOrderCommandService(f.session_factory), kind)(
            context, UUID(po["id"]), data, idempotency_key="rollback"
        )
    assert f.client.get(f"/api/v1/purchase-orders/{po['id']}", headers=headers(f)).json() == po
    with f.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PurchaseOrder)) == 1


def test_previous_receipt_facts_survive_change_migration(quotation_fixture):
    f = quotation_fixture
    po = partially_received(f)
    config = alembic_config(f.engine.url.render_as_string(hide_password=False))
    verify_legacy_upgrade(f.engine, "20260906_0012")
    command.check(config)
    assert f.client.get(f"/api/v1/purchase-orders/{po['id']}", headers=headers(f)).json() == po


def test_foreign_replacement_supplier_does_not_cancel_original(quotation_fixture):
    f = quotation_fixture
    po = confirmed_purchase(f)
    foreign_id = uuid4()
    with f.session_factory.begin() as session:
        session.add(
            Company(
                id=foreign_id,
                organization_id=f.organization_b,
                name="Foreign supplier",
                name_normalized="foreign supplier",
            )
        )
    data = replacement(po)
    data["supplier_company_id"] = str(foreign_id)
    path = f"/api/v1/purchase-orders/{po['id']}"
    response = f.client.post(
        path + "/amend", headers=headers(f), json={**change_request(po), "replacement": data}
    )
    assert response.status_code == 404
    assert f.client.get(path, headers=headers(f)).json() == po


def test_received_purchase_rejects_cancellation(quotation_fixture):
    f = quotation_fixture
    po = confirmed_purchase(f)
    path = f"/api/v1/purchase-orders/{po['id']}"
    response = f.client.post(
        path + "/receive", headers=headers(f, "full-receipt"), json=receipt(po, "1.0000")
    )
    assert response.status_code == 200, response.text
    received = response.json()
    assert received["status"] == "RECEIVED"
    response = f.client.post(path + "/cancel", headers=headers(f), json=change_request(received))
    assert response.status_code == 409
    assert f.client.get(path, headers=headers(f)).json() == received
