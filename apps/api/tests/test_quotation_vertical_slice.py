from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from alembic import command
from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.auth.tokens import LocalTestTokenIssuer, LocalTestTokenVerifier
from app.core.database import create_session_factory
from app.crm.models import Opportunity
from app.fulfillment.models import Shipment
from app.identity.enums import MembershipRole, MembershipStatus
from app.identity.models import Organization, OrganizationMembership, User
from app.main import app
from app.platform.models import AuditLog, OutboxEvent
from app.platform.records import DomainEvent, OutboxRecorder
from app.sales.models import Quotation, QuotationItem, QuotationVersion, SalesOrder
from app.sales.order_schemas import SalesOrderConfirm
from app.sales.schemas import QuotationStateCommand
from app.sales.services import QuotationCommandService
from app.work.models import Activity
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from test_migrations import alembic_config

TEST_SECRET = "quotation-integration-secret-with-at-least-32-characters"
TEST_ISSUER = "https://issuer.quotation.integration.test"
TEST_AUDIENCE = "trade-workbench-quotation-integration"


@dataclass(frozen=True, slots=True)
class QuotationFixture:
    engine: Engine
    session_factory: sessionmaker[Session]
    client: TestClient
    issuer: LocalTestTokenIssuer
    organization_a: UUID
    organization_b: UUID
    sales_user: UUID

    def headers(self, subject: str, organization_id: UUID) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.issuer.issue(subject=subject)}",
            "X-Organization-ID": str(organization_id),
        }


def seed_identity(
    factory: sessionmaker[Session],
) -> tuple[UUID, UUID, UUID]:
    with factory.begin() as session:
        organization_a = Organization(name="Sales Organization A", name_normalized="sales org a")
        organization_b = Organization(name="Sales Organization B", name_normalized="sales org b")
        sales = User(external_subject="quotation-sales", display_name="Quotation Sales")
        manager = User(external_subject="quotation-manager", display_name="Quotation Manager")
        operations = User(
            external_subject="quotation-operations", display_name="Quotation Operations"
        )
        finance = User(external_subject="quotation-finance", display_name="Quotation Finance")
        other_sales = User(external_subject="quotation-other", display_name="Other Sales")
        session.add_all(
            [organization_a, organization_b, sales, manager, operations, finance, other_sales]
        )
        session.flush()
        session.add_all(
            [
                OrganizationMembership(
                    organization_id=organization_a.id,
                    user_id=sales.id,
                    role=MembershipRole.SALES,
                    status=MembershipStatus.ACTIVE,
                ),
                OrganizationMembership(
                    organization_id=organization_a.id,
                    user_id=manager.id,
                    role=MembershipRole.MANAGER,
                    status=MembershipStatus.ACTIVE,
                ),
                OrganizationMembership(
                    organization_id=organization_a.id,
                    user_id=operations.id,
                    role=MembershipRole.OPERATIONS,
                    status=MembershipStatus.ACTIVE,
                ),
                OrganizationMembership(
                    organization_id=organization_a.id,
                    user_id=finance.id,
                    role=MembershipRole.FINANCE,
                    status=MembershipStatus.ACTIVE,
                ),
                OrganizationMembership(
                    organization_id=organization_b.id,
                    user_id=other_sales.id,
                    role=MembershipRole.SALES,
                    status=MembershipStatus.ACTIVE,
                ),
            ]
        )
        session.flush()
        return organization_a.id, organization_b.id, sales.id


@pytest.fixture
def quotation_fixture(test_database_url: str) -> Iterator[QuotationFixture]:
    command.upgrade(alembic_config(test_database_url), "head")
    engine = create_engine(test_database_url)
    factory = create_session_factory(engine)
    organization_a, organization_b, sales_user = seed_identity(factory)
    issuer = LocalTestTokenIssuer(
        secret=TEST_SECRET,
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
    )
    app.state.session_factory = factory
    app.state.token_verifier = LocalTestTokenVerifier(
        secret=TEST_SECRET,
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
    )
    with TestClient(app) as client:
        yield QuotationFixture(
            engine=engine,
            session_factory=factory,
            client=client,
            issuer=issuer,
            organization_a=organization_a,
            organization_b=organization_b,
            sales_user=sales_user,
        )
    del app.state.session_factory
    del app.state.token_verifier
    engine.dispose()


def state_request(fixture: QuotationFixture, quotation_id: str) -> QuotationStateCommand:
    with fixture.session_factory() as session:
        current = session.scalar(
            select(QuotationVersion).where(
                QuotationVersion.organization_id == fixture.organization_a,
                QuotationVersion.quotation_id == UUID(quotation_id),
                QuotationVersion.is_current.is_(True),
                QuotationVersion.deleted_at.is_(None),
            )
        )
        assert current is not None
        return QuotationStateCommand(
            expected_version_id=current.id, expected_version=current.version
        )


def post_state(fixture: QuotationFixture, path: str, subject: str = "quotation-sales"):
    quotation_id = path.split("/")[-2]
    return fixture.client.post(
        path,
        headers=fixture.headers(subject, fixture.organization_a)
        | {"Idempotency-Key": str(uuid4())},
        json=state_request(fixture, quotation_id).model_dump(mode="json"),
    )


def order_confirmation(fixture: QuotationFixture, order_id: UUID | str) -> SalesOrderConfirm:
    with fixture.session_factory() as session:
        row = session.scalar(
            select(SalesOrder).where(
                SalesOrder.organization_id == fixture.organization_a,
                SalesOrder.id == UUID(str(order_id)),
            )
        )
        assert row is not None
        return SalesOrderConfirm(expected_version=row.version)


def purchase_decision(fixture: QuotationFixture, purchase_id: UUID | str) -> dict[str, int]:
    from app.procurement.models import PurchaseOrder

    with fixture.session_factory() as session:
        row = session.scalar(
            select(PurchaseOrder).where(
                PurchaseOrder.organization_id == fixture.organization_a,
                PurchaseOrder.id == UUID(str(purchase_id)),
            )
        )
        assert row is not None
        return {"expected_version": row.version}


def shipment_decision(fixture: QuotationFixture, shipment_id: UUID | str) -> dict[str, int]:
    with fixture.session_factory() as session:
        version = session.scalar(
            select(Shipment.version).where(
                Shipment.organization_id == fixture.organization_a,
                Shipment.id == UUID(str(shipment_id)),
                Shipment.deleted_at.is_(None),
            )
        )
        assert version is not None
        return {"expected_version": version}


def post_ok(
    fixture: QuotationFixture,
    path: str,
    subject: str,
    body: dict[str, object] | None = None,
    expected_status: int = 200,
) -> dict[str, object]:
    if (
        path.startswith("/api/v1/quotations/")
        and path.split("/")[-1] in {"submit", "approve", "send", "accept", "reject", "expire"}
        and body is None
    ):
        response = post_state(fixture, path, subject)
    elif path.startswith("/api/v1/sales-orders/") and path.endswith("/confirm") and body is None:
        response = fixture.client.post(
            path,
            headers={
                **fixture.headers(subject, fixture.organization_a),
                "Idempotency-Key": str(uuid4()),
            },
            json=order_confirmation(fixture, path.split("/")[-2]).model_dump(),
        )
    elif path.startswith("/api/v1/purchase-orders/") and path.split("/")[-1] in {
        "approve",
        "send",
        "confirm",
    }:
        response = fixture.client.post(
            path,
            headers=fixture.headers(subject, fixture.organization_a)
            | {"Idempotency-Key": str(uuid4())},
            json={**purchase_decision(fixture, path.split("/")[-2]), **(body or {})},
        )
    elif path.startswith("/api/v1/shipments/") and path.split("/")[-1] in {
        "book",
        "ready",
        "enter-customs",
        "depart",
        "start-transit",
        "arrive",
        "deliver",
    }:
        response = fixture.client.post(
            path,
            headers=fixture.headers(subject, fixture.organization_a)
            | {"Idempotency-Key": str(uuid4())},
            json={**shipment_decision(fixture, path.split("/")[-2]), **(body or {})},
        )
    else:
        response = fixture.client.post(
            path,
            headers=fixture.headers(subject, fixture.organization_a),
            json=body,
        )
    assert response.status_code == expected_status, response.text
    return cast(dict[str, object], response.json())


def create_opportunity(fixture: QuotationFixture) -> tuple[str, str]:
    lead = post_ok(
        fixture,
        "/api/v1/leads",
        "quotation-sales",
        {"company_name": "Blue Current Imports", "contact_name": "Mara Lin"},
        201,
    )
    lead_id = str(lead["id"])
    for command_name in ("qualify", "contact", "respond"):
        post_ok(fixture, f"/api/v1/leads/{lead_id}/{command_name}", "quotation-sales")
    conversion = post_ok(fixture, f"/api/v1/leads/{lead_id}/convert", "quotation-sales")
    return str(conversion["company_id"]), str(conversion["opportunity_id"])


def create_commercial_inputs(
    fixture: QuotationFixture,
) -> tuple[dict[str, object], str, str]:
    company_id, opportunity_id = create_opportunity(fixture)
    inquiry = post_ok(
        fixture,
        "/api/v1/inquiries",
        "quotation-sales",
        {
            "company_id": company_id,
            "opportunity_id": opportunity_id,
            "customer_reference": "RFQ-88",
            "description": "Two pump assemblies for the Rotterdam program",
            "received_at": datetime.now(UTC).isoformat(),
        },
        201,
    )
    product_cny = post_ok(
        fixture,
        "/api/v1/products",
        "quotation-manager",
        {
            "sku": "PUMP-CN",
            "name": "Stainless pump assembly",
            "description": "316L sanitary pump",
            "unit": "set",
            "standard_cost": "7.7777",
            "cost_currency": "CNY",
        },
        201,
    )
    product_usd = post_ok(
        fixture,
        "/api/v1/products",
        "quotation-manager",
        {
            "sku": "KIT-US",
            "name": "Seal service kit",
            "unit": "kit",
            "standard_cost": "4.2500",
            "cost_currency": "USD",
        },
        201,
    )
    request: dict[str, object] = {
        "inquiry_id": str(inquiry["id"]),
        "currency_code": "EUR",
        "base_currency_code": "USD",
        "exchange_rate": "1.08765432",
        "valid_until": (date.today() + timedelta(days=30)).isoformat(),
        "payment_terms": "30% deposit, 70% before shipment",
        "delivery_terms": "FOB Shanghai",
        "items": [
            {
                "product_id": str(product_cny["id"]),
                "quantity": "3.3333",
                "unit_price": "19.9955",
                "cost_exchange_rate": "0.12876543",
                "tax_amount": "1.2555",
                "freight_amount": "2.1000",
                "allocated_cost": "0.5000",
            },
            {
                "product_id": str(product_usd["id"]),
                "quantity": "2.0000",
                "unit_price": "12.5000",
                "cost_exchange_rate": "0.92000000",
                "tax_amount": "0.5000",
                "freight_amount": "1.0000",
            },
        ],
    }
    return request, company_id, opportunity_id


@pytest.mark.integration
def test_v1_v2_approval_acceptance_and_three_currency_math(
    quotation_fixture: QuotationFixture,
) -> None:
    request, _, opportunity_id = create_commercial_inputs(quotation_fixture)
    quotation = post_ok(
        quotation_fixture,
        "/api/v1/quotations",
        "quotation-manager",
        request,
        201,
    )
    quotation_id = str(quotation["id"])
    v1 = cast(dict[str, object], quotation["current_version"])
    assert v1["version_number"] == 1
    assert v1["currency_code"] == "EUR"
    assert v1["base_currency_code"] == "USD"

    expected_first_subtotal = (Decimal("3.3333") * Decimal("19.9955")).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )
    expected_first_cost = (
        Decimal("3.3333") * Decimal("7.7777") * Decimal("0.12876543") + Decimal("0.5000")
    ).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    first_item = cast(list[dict[str, object]], v1["items"])[0]
    assert Decimal(str(first_item["line_subtotal"])) == expected_first_subtotal
    assert Decimal(str(first_item["line_cost"])) == expected_first_cost

    revised_items = cast(list[dict[str, object]], request["items"])
    revised_items = [dict(item) for item in revised_items]
    revised_items[0]["unit_price"] = "21.2500"
    v2 = post_ok(
        quotation_fixture,
        f"/api/v1/quotations/{quotation_id}/revisions",
        "quotation-manager",
        {"items": revised_items},
        201,
    )
    assert v2["version_number"] == 2
    assert v2["status"] == "DRAFT"
    assert Decimal(str(v2["total"])) > Decimal(str(v1["total"]))

    detail = quotation_fixture.client.get(
        f"/api/v1/quotations/{quotation_id}",
        headers=quotation_fixture.headers("quotation-sales", quotation_fixture.organization_a),
    )
    assert detail.status_code == 200
    versions = detail.json()["versions"]
    assert [version["status"] for version in versions] == ["DRAFT", "SUPERSEDED"]

    submitted = post_ok(
        quotation_fixture,
        f"/api/v1/quotations/{quotation_id}/submit",
        "quotation-sales",
    )
    assert submitted["status"] == "INTERNAL_REVIEW"

    unapproved_send = post_state(
        quotation_fixture,
        f"/api/v1/quotations/{quotation_id}/send",
    )
    assert unapproved_send.status_code == 409
    assert unapproved_send.json()["code"] == "INVALID_STATE_TRANSITION"

    sales_approval = quotation_fixture.client.post(
        f"/api/v1/quotations/{quotation_id}/approve",
        headers=quotation_fixture.headers("quotation-sales", quotation_fixture.organization_a),
    )
    assert sales_approval.status_code == 403
    assert sales_approval.json()["code"] == "PERMISSION_DENIED"

    approved = post_ok(
        quotation_fixture,
        f"/api/v1/quotations/{quotation_id}/approve",
        "quotation-manager",
    )
    assert approved["status"] == "INTERNAL_REVIEW"
    assert approved["approved_by"] is not None
    assert approved["approved_at"] is not None
    assert (
        post_ok(
            quotation_fixture,
            f"/api/v1/quotations/{quotation_id}/send",
            "quotation-sales",
        )["status"]
        == "SENT"
    )

    before_accept = table_counts(quotation_fixture)
    accepted = post_ok(
        quotation_fixture,
        f"/api/v1/quotations/{quotation_id}/accept",
        "quotation-sales",
    )
    assert accepted["status"] == "ACCEPTED"
    after_accept = table_counts(quotation_fixture)
    repeated = post_ok(
        quotation_fixture,
        f"/api/v1/quotations/{quotation_id}/accept",
        "quotation-sales",
    )
    assert repeated == accepted
    assert table_counts(quotation_fixture) == after_accept
    assert tuple(
        after - before for before, after in zip(before_accept, after_accept, strict=True)
    ) == (
        2,  # quotation acceptance and CRM-owned opportunity win each have atomic evidence
        2,
        2,
    )

    with quotation_fixture.session_factory() as session:
        opportunity = session.scalar(
            select(Opportunity).where(Opportunity.id == UUID(opportunity_id))
        )
        assert opportunity is not None
        assert opportunity.status == "WON"
        persisted_v1 = session.get(QuotationVersion, UUID(str(v1["id"])))
        persisted_v2 = session.get(QuotationVersion, UUID(str(v2["id"])))
        assert persisted_v1 is not None and persisted_v1.status == "SUPERSEDED"
        assert persisted_v2 is not None and persisted_v2.status == "ACCEPTED"


def table_counts(fixture: QuotationFixture) -> tuple[int, int, int]:
    with fixture.session_factory() as session:
        return (
            session.scalar(select(func.count()).select_from(Activity)) or 0,
            session.scalar(select(func.count()).select_from(AuditLog)) or 0,
            session.scalar(select(func.count()).select_from(OutboxEvent)) or 0,
        )


@pytest.mark.integration
def test_sent_revision_copies_snapshot_without_mutating_commercial_history(
    quotation_fixture: QuotationFixture,
) -> None:
    request, _, _ = create_commercial_inputs(quotation_fixture)
    quotation = post_ok(
        quotation_fixture,
        "/api/v1/quotations",
        "quotation-manager",
        request,
        201,
    )
    quotation_id = str(quotation["id"])
    sent_version = cast(dict[str, object], quotation["current_version"])
    sent_version_id = UUID(str(sent_version["id"]))
    post_ok(
        quotation_fixture,
        f"/api/v1/quotations/{quotation_id}/submit",
        "quotation-sales",
    )
    post_ok(
        quotation_fixture,
        f"/api/v1/quotations/{quotation_id}/approve",
        "quotation-manager",
    )
    sent_version = post_ok(
        quotation_fixture,
        f"/api/v1/quotations/{quotation_id}/send",
        "quotation-sales",
    )

    commercial_fields = (
        "currency_code",
        "base_currency_code",
        "exchange_rate",
        "payment_terms",
        "delivery_terms",
        "subtotal",
        "tax_amount",
        "freight_amount",
        "total",
        "total_cost",
        "gross_profit",
        "gross_margin",
    )
    item_fields = (
        "line_number",
        "product_id",
        "sku_snapshot",
        "description_snapshot",
        "unit_snapshot",
        "quantity",
        "unit_price",
        "unit_cost",
        "cost_currency",
        "cost_exchange_rate",
        "tax_amount",
        "freight_amount",
        "allocated_cost",
        "line_subtotal",
        "line_total",
        "line_cost",
        "line_gross_profit",
    )
    sent_snapshot = {field: sent_version[field] for field in commercial_fields}
    sent_items = [
        {field: item[field] for field in item_fields}
        for item in cast(list[dict[str, object]], sent_version["items"])
    ]

    revised_valid_until = (date.today() + timedelta(days=60)).isoformat()
    revision = post_ok(
        quotation_fixture,
        f"/api/v1/quotations/{quotation_id}/revisions",
        "quotation-sales",
        {"valid_until": revised_valid_until},
        201,
    )
    assert revision["version_number"] == 2
    assert revision["status"] == "DRAFT"
    assert revision["valid_until"] == revised_valid_until
    assert {field: revision[field] for field in commercial_fields} == sent_snapshot
    assert [
        {field: item[field] for field in item_fields}
        for item in cast(list[dict[str, object]], revision["items"])
    ] == sent_items

    detail = quotation_fixture.client.get(
        f"/api/v1/quotations/{quotation_id}",
        headers=quotation_fixture.headers("quotation-sales", quotation_fixture.organization_a),
    )
    assert detail.status_code == 200
    persisted_sent = next(
        version for version in detail.json()["versions"] if UUID(version["id"]) == sent_version_id
    )
    assert persisted_sent["status"] == "SUPERSEDED"
    assert persisted_sent["is_current"] is False
    assert {field: persisted_sent[field] for field in commercial_fields} == sent_snapshot
    assert [
        {field: item[field] for field in item_fields} for item in persisted_sent["items"]
    ] == sent_items


@pytest.mark.integration
def test_quotation_is_tenant_scoped_and_invalid_transition_has_no_partial_write(
    quotation_fixture: QuotationFixture,
) -> None:
    request, _, _ = create_commercial_inputs(quotation_fixture)
    quotation = post_ok(
        quotation_fixture,
        "/api/v1/quotations",
        "quotation-manager",
        request,
        201,
    )
    quotation_id = str(quotation["id"])
    other_headers = quotation_fixture.headers("quotation-other", quotation_fixture.organization_b)
    assert quotation_fixture.client.get("/api/v1/quotations", headers=other_headers).json() == {
        "items": [],
        "count": 0,
        "has_more": False,
        "next_cursor": None,
    }
    hidden = quotation_fixture.client.get(
        f"/api/v1/quotations/{quotation_id}", headers=other_headers
    )
    assert hidden.status_code == 404
    assert hidden.json()["code"] == "QUOTATION_NOT_FOUND"

    before = table_counts(quotation_fixture)
    invalid_accept = post_state(
        quotation_fixture,
        f"/api/v1/quotations/{quotation_id}/accept",
    )
    assert invalid_accept.status_code == 409
    assert invalid_accept.json()["code"] == "INVALID_STATE_TRANSITION"
    assert table_counts(quotation_fixture) == before
    with quotation_fixture.session_factory() as session:
        current = session.scalar(
            select(QuotationVersion).where(
                QuotationVersion.quotation_id == UUID(quotation_id),
                QuotationVersion.is_current.is_(True),
            )
        )
        assert current is not None and current.status == "DRAFT"


class FailingOutboxRecorder(OutboxRecorder):
    def record(
        self,
        session: Session,
        context: RequestContext,
        event: DomainEvent,
    ) -> OutboxEvent:
        raise RuntimeError("injected quotation outbox failure")


@pytest.mark.integration
def test_quotation_creation_rolls_back_all_facts_when_outbox_fails(
    quotation_fixture: QuotationFixture,
) -> None:
    request, _, opportunity_id = create_commercial_inputs(quotation_fixture)
    before = table_counts(quotation_fixture)
    service = QuotationCommandService(
        quotation_fixture.session_factory,
        outbox_recorder=FailingOutboxRecorder(),
    )
    context = RequestContext(
        user_id=quotation_fixture.sales_user,
        organization_id=quotation_fixture.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    data = dict(request)
    data["inquiry_id"] = UUID(str(data["inquiry_id"]))
    data["valid_until"] = date.fromisoformat(str(data["valid_until"]))
    data["exchange_rate"] = Decimal(str(data["exchange_rate"]))
    data["items"] = [
        {
            **item,
            "product_id": UUID(str(item["product_id"])),
            "quantity": Decimal(str(item["quantity"])),
            "unit_price": Decimal(str(item["unit_price"])),
            "cost_exchange_rate": Decimal(str(item["cost_exchange_rate"])),
            "tax_amount": Decimal(str(item["tax_amount"])),
            "freight_amount": Decimal(str(item["freight_amount"])),
            "allocated_cost": Decimal(str(item.get("allocated_cost", 0))),
        }
        for item in cast(list[dict[str, object]], data["items"])
    ]
    with pytest.raises(RuntimeError, match="injected quotation outbox failure"):
        service.create(context, data)

    assert table_counts(quotation_fixture) == before
    with quotation_fixture.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Quotation)) == 0
        assert session.scalar(select(func.count()).select_from(QuotationVersion)) == 0
        assert session.scalar(select(func.count()).select_from(QuotationItem)) == 0
        opportunity = session.get(Opportunity, UUID(opportunity_id))
        assert opportunity is not None and opportunity.status == "INQUIRY"
