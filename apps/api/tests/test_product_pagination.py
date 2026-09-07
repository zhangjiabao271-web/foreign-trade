from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from alembic import command
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.catalog.models import Product
from app.catalog.repositories import ProductRepository
from app.catalog.services import ProductQueryService
from legacy_migration import assert_snapshot, legacy_snapshot
from sqlalchemy import inspect
from test_quotation_vertical_slice import table_counts

pytest_plugins = ("test_quotation_vertical_slice",)


def seed(f, organization, names):
    with f.session_factory.begin() as session:
        rows = [
            Product(
                organization_id=organization,
                sku=f"SKU-{uuid4()}",
                name=name,
                unit="set",
                standard_cost="1.0000",
                cost_currency="CNY",
            )
            for name in names
        ]
        session.add_all(rows)
        session.flush()
        return [str(row.id) for row in rows]


def test_product_pages_reach_all_equal_names_and_do_not_write_evidence(quotation_fixture):
    f = quotation_fixture
    ids = seed(f, f.organization_a, ["Same product"] * 105)
    seed(f, f.organization_b, ["Same product"] * 3)
    h = f.headers("quotation-sales", f.organization_a)
    before = table_counts(f)
    found = []
    params = {"limit": 50}
    for expected_count in (50, 50, 5):
        response = f.client.get("/api/v1/products", headers=h, params=params)
        assert response.status_code == 200
        page = response.json()
        assert page["count"] == len(page["items"]) == expected_count
        found.extend(row["id"] for row in page["items"])
        assert page["has_more"] == (expected_count == 50)
        if page["has_more"]:
            params["cursor"] = page["next_cursor"]
        else:
            assert page["next_cursor"] is None
    assert found == sorted(ids)
    assert table_counts(f) == before


def test_product_literal_search_cursor_scope_deletion_and_bounds(quotation_fixture):
    f = quotation_fixture
    ids = seed(f, f.organization_a, ["100%_\\ literal", "100 percent", "aaa"])
    foreign = seed(f, f.organization_b, ["100%_\\ literal"])[0]
    h = f.headers("quotation-sales", f.organization_a)
    path = "/api/v1/products"
    result = f.client.get(path, headers=h, params={"query": "%_\\"})
    assert [row["id"] for row in result.json()["items"]] == ids[:1]
    for cursor in (foreign, str(uuid4())):
        assert f.client.get(path, headers=h, params={"cursor": cursor}).status_code == 404
    with f.session_factory.begin() as session:
        session.get(Product, UUID(ids[0])).deleted_at = datetime.now(UTC)
    assert f.client.get(path, headers=h, params={"cursor": ids[0]}).status_code == 404
    assert f.client.get(path, headers=h, params={"query": "%_\\"}).json()["items"] == []
    for params in ({"cursor": "bad"}, {"limit": 0}, {"limit": 101}, {"query": "x" * 241}):
        assert f.client.get(path, headers=h, params=params).status_code == 422
    assert f.client.get(path).status_code == 401
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(),
        request_id=uuid4(),
    )
    with f.session_factory() as session, pytest.raises(ApiProblem) as denied:
        ProductQueryService(ProductRepository(session)).list(context, query=None, limit=50)
    assert denied.value.status == 403


def test_product_cursor_index_upgrade_retains_rows(quotation_fixture):
    f = quotation_fixture
    ids = seed(f, f.organization_a, ["Retained product"])
    with legacy_snapshot(f.engine, "20260906_0023") as (config, target, metadata, expected):
        command.downgrade(config, "20260906_0022")
        assert_snapshot(target, metadata, expected)
        assert "ix_products_org_name_id_active" not in {
            index["name"] for index in inspect(target).get_indexes("products")
        }
        command.upgrade(config, "head")
        command.check(config)
        assert_snapshot(target, metadata, expected)
        indexes = {index["name"]: index for index in inspect(target).get_indexes("products")}
        assert indexes["ix_products_org_name_id_active"]["column_names"] == [
            "organization_id",
            "name",
            "id",
        ]
    response = f.client.get(
        "/api/v1/products", headers=f.headers("quotation-sales", f.organization_a)
    )
    assert [row["id"] for row in response.json()["items"]] == ids
