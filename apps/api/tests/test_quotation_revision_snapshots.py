from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from app.catalog.models import Product
from app.identity.enums import MembershipRole, MembershipStatus
from app.identity.models import OrganizationMembership, User
from app.platform.models import AuditLog
from sqlalchemy import select
from test_quotation_revision_idempotency import counts, request, setup
from test_quotation_vertical_slice import QuotationFixture, post_ok

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration

SNAPSHOT_FIELDS = (
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


@pytest.mark.parametrize("mode", ["copy", "source"])
def test_revision_and_order_keep_complete_snapshots_after_catalog_change(quotation_fixture, mode):
    f = quotation_fixture
    quote, body = setup(f)
    previous = quote["current_version"]["items"]
    with f.session_factory.begin() as session:
        for item in previous:
            product = session.get(Product, UUID(item["product_id"]))
            product.sku = "CHANGED-" + product.sku
            product.name = "Renamed product"
            product.description = "Changed description"
            product.unit = "box"
            product.standard_cost = Decimal("999.0000")
            product.cost_currency = "GBP"
    if mode == "source":
        body["items"] = [
            {
                "source_item_id": item["id"],
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "unit_price": item["unit_price"],
            }
            for item in reversed(previous)
        ]
        previous = list(reversed(previous))
    response = request(f, quote, body, "snapshots")
    assert response.status_code == 201, response.text
    revised = response.json()
    assert revised["total_cost"] is None
    detail = f.client.get(
        f"/api/v1/quotations/{quote['id']}",
        headers=f.headers("quotation-manager", f.organization_a),
    )
    assert detail.status_code == 200
    revised = detail.json()["current_version"]
    for old, new in zip(previous, revised["items"], strict=True):
        assert {key: new[key] for key in SNAPSHOT_FIELDS} == {
            key: old[key] for key in SNAPSHOT_FIELDS
        }
        assert new["id"] != old["id"]
    for action, subject in (
        ("submit", "quotation-sales"),
        ("approve", "quotation-manager"),
        ("send", "quotation-sales"),
        ("accept", "quotation-sales"),
    ):
        post_ok(f, f"/api/v1/quotations/{quote['id']}/{action}", subject)
    order = post_ok(
        f, "/api/v1/sales-orders", "quotation-sales", {"quotation_id": quote["id"]}, 201
    )
    assert order["total_cost"] is order["gross_profit"] is None
    detail = f.client.get(
        f"/api/v1/sales-orders/{order['id']}",
        headers=f.headers("quotation-manager", f.organization_a),
    )
    assert detail.status_code == 200
    order = detail.json()
    for source, item in zip(revised["items"], order["items"], strict=True):
        assert {key: item[key] for key in SNAPSHOT_FIELDS} == {
            key: source[key] for key in SNAPSHOT_FIELDS
        }
        assert item["quotation_item_id"] == source["id"]


def test_copy_of_archived_product_uses_existing_snapshot(quotation_fixture):
    f = quotation_fixture
    quote, body = setup(f)
    with f.session_factory.begin() as session:
        product = session.get(Product, UUID(quote["current_version"]["items"][0]["product_id"]))
        product.deleted_at = datetime.now(UTC)
    response = request(f, quote, body, "archived-snapshot")
    assert response.status_code == 201, response.text
    assert response.json()["items"][0]["sku_snapshot"] == "PUMP-CN"
    baseline = counts(f)
    as_new = request(
        f,
        quote,
        {
            "expected_version_id": response.json()["id"],
            "items": [{"product_id": product.id.hex, "quantity": "1", "unit_price": "1"}],
        },
        "archived-new",
    )
    assert as_new.status_code == 404
    assert counts(f) == baseline


def test_invalid_source_or_mismatched_product_has_no_partial_facts(quotation_fixture):
    f = quotation_fixture
    quote, body = setup(f)
    first, second = quote["current_version"]["items"]
    baseline = counts(f)
    for source, product, expected in (
        (str(uuid4()), first["product_id"], 404),
        (first["id"], second["product_id"], 409),
    ):
        response = request(
            f,
            quote,
            {
                **body,
                "items": [
                    {
                        "source_item_id": source,
                        "product_id": product,
                        "quantity": "1",
                        "unit_price": "1",
                    }
                ],
            },
            str(uuid4()),
        )
        assert response.status_code == expected, response.text
        assert counts(f) == baseline


def test_sourced_overrides_and_new_lines_have_distinct_defaults_and_audit(quotation_fixture):
    f = quotation_fixture
    quote, body = setup(f)
    original = quote["current_version"]["items"][0]
    with f.session_factory.begin() as session:
        product = session.get(Product, UUID(original["product_id"]))
        product.sku = "CURRENT-PUMP"
        product.unit = "box"
        product.standard_cost = Decimal("999.0000")
    body["items"] = [
        {
            "source_item_id": original["id"],
            "product_id": original["product_id"],
            "quantity": "4.0000",
            "unit_price": "0.0000",
            "unit_cost": "0.0000",
            "description": "Explicit new description",
            "tax_amount": "0.0000",
        },
        {
            "product_id": original["product_id"],
            "quantity": "1.0000",
            "unit_price": "1000.0000",
            "cost_exchange_rate": original["cost_exchange_rate"],
        },
    ]
    response = request(f, quote, body, "mixed-lines", subject="quotation-manager")
    assert response.status_code == 201, response.text
    copied, new = response.json()["items"]
    assert (copied["sku_snapshot"], copied["unit_snapshot"]) == ("PUMP-CN", "set")
    assert (
        copied["quantity"],
        copied["unit_price"],
        copied["unit_cost"],
        copied["tax_amount"],
    ) == ("4.0000", "0.0000", "0.0000", "0.0000")
    assert copied["description_snapshot"] == "Explicit new description"
    assert copied["freight_amount"] == original["freight_amount"]
    assert (new["sku_snapshot"], new["unit_snapshot"], new["unit_cost"]) == (
        "CURRENT-PUMP",
        "box",
        "999.0000",
    )
    with f.session_factory() as session:
        audit = session.scalar(
            select(AuditLog).where(AuditLog.target_id == UUID(response.json()["id"]))
        )
        assert audit.after_data["source_items"] == [
            {"line_number": 1, "source_item_id": original["id"]}
        ]
    detail = f.client.get(
        f"/api/v1/quotations/{quote['id']}",
        headers=f.headers("quotation-manager", f.organization_a),
    ).json()
    previous = next(
        item for item in detail["versions"] if item["id"] == quote["current_version"]["id"]
    )
    assert previous["items"][0] == original
    baseline = counts(f)
    stale_source = request(
        f,
        quote,
        {**body, "expected_version_id": response.json()["id"]},
        "old-source",
        subject="quotation-manager",
    )
    assert stale_source.status_code == 404
    assert counts(f) == baseline


def test_real_foreign_source_line_is_not_usable(quotation_fixture, monkeypatch):
    f = quotation_fixture
    quote, body = setup(f)
    original_headers = QuotationFixture.headers
    other = replace(f, organization_a=f.organization_b)
    with f.session_factory.begin() as session:
        manager = User(external_subject="revision-other-manager", display_name="Other Manager")
        session.add(manager)
        session.flush()
        session.add(
            OrganizationMembership(
                organization_id=f.organization_b,
                user_id=manager.id,
                role=MembershipRole.MANAGER,
                status=MembershipStatus.ACTIVE,
            )
        )
    with monkeypatch.context() as patch:
        patch.setattr(
            QuotationFixture,
            "headers",
            lambda self, subject, organization: original_headers(
                self,
                "revision-other-manager" if subject == "quotation-manager" else "quotation-other",
                organization,
            ),
        )
        foreign_quote, _ = setup(other)
    foreign_item = foreign_quote["current_version"]["items"][0]
    baseline = counts(f)
    response = request(
        f,
        quote,
        {
            **body,
            "items": [
                {
                    "source_item_id": foreign_item["id"],
                    "product_id": foreign_item["product_id"],
                    "quantity": "1",
                    "unit_price": "1",
                }
            ],
        },
        "foreign-source",
    )
    assert response.status_code == 404
    assert response.json()["code"] == "QUOTATION_ITEM_NOT_FOUND"
    assert counts(f) == baseline
