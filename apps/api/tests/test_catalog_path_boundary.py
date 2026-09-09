from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.catalog.models import Product, ProductSupplierLink
from app.catalog.repositories import ProductRepository
from app.catalog.services import ProductCommandService
from app.catalog.supplier_services import SupplierLinkRepository
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.work.models import Activity
from sqlalchemy import event, select
from test_product_suppliers import create, headers, inputs

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration


def snapshot(f):
    with f.session_factory() as session:
        return {
            model.__tablename__: list(session.execute(select(model.__table__).order_by(model.id)))
            for model in (
                Product,
                ProductSupplierLink,
                Activity,
                AuditLog,
                OutboxEvent,
                IdempotencyKey,
            )
        }


def test_catalog_repository_reads_reject_foreign_product_link_and_supplier(quotation_fixture):
    f = quotation_fixture
    product, supplier = inputs(f)
    link = create(f, product, supplier)
    product_id, supplier_id, link_id = UUID(product["id"]), UUID(supplier["id"]), UUID(link["id"])
    before = snapshot(f)
    with f.session_factory() as session:
        products = ProductRepository(session)
        assert products.get(organization_id=f.organization_b, record_id=product_id) is None
        assert not products.list(organization_id=f.organization_b)
        assert products.count(organization_id=f.organization_b) == 0
        assert not products.search(organization_id=f.organization_b, query="Product", limit=25)
        with pytest.raises(ApiProblem) as denied:
            products.search(
                organization_id=f.organization_b, query=None, limit=25, cursor=product_id
            )
        assert denied.value.status == 404
        links = SupplierLinkRepository(session)
        for operation in (
            lambda: links.product(f.organization_b, product_id),
            lambda: links.get(f.organization_b, product_id, link_id),
            lambda: links.list(f.organization_b, product_id, cursor=link_id, limit=25),
        ):
            with pytest.raises(ApiProblem) as denied:
                operation()
            assert denied.value.status == 404
        assert not links.list(f.organization_b, product_id, cursor=None, limit=25)
        assert not links.history(f.organization_b, product_id, offset=0, limit=25)
        assert links.supplier_names(f.organization_b, [supplier_id]) == {}
    assert snapshot(f) == before


def test_product_text_review_foreign_manager_cannot_inspect_or_release(quotation_fixture):
    f = quotation_fixture
    product, _ = inputs(f)
    inputs(f, "B", f.organization_b, "quotation-other")
    path = f"/api/v1/products/{product['id']}/text-review"
    inspected = f.client.get(path, headers=headers(f))
    assert inspected.status_code == 200
    original = inspected.json()
    foreign = headers(f, "foreign-review", "supplier-other-manager", f.organization_b)
    assert f.client.get("/api/v1/me/context", headers=foreign).status_code == 200
    body = {
        "expected_version": original["version"],
        "content_digest": original["content_digest"],
        "release": True,
        "reason": "Synthetic foreign review denial",
        "confirmed": True,
    }
    before = snapshot(f)
    for method in ("GET", "POST"):
        response = f.client.request(
            method, path, headers=foreign, **({"json": body} if method == "POST" else {})
        )
        assert response.status_code == 404
        assert response.json()["code"] == "PRODUCT_TEXT_NOT_FOUND"
        assert snapshot(f) == before
    assert f.client.get(path, headers=headers(f)).json() == original


@pytest.mark.parametrize("table", ["audit_logs", "outbox_events"])
def test_product_creation_failure_rolls_back_product_and_evidence(quotation_fixture, table):
    f = quotation_fixture
    ctx = RequestContext(f.sales_user, f.organization_a, frozenset(Permission), uuid4())
    body = {
        "sku": "ATOMIC-PRODUCT",
        "name": "Synthetic product",
        "unit": "set",
        "standard_cost": "3.1250",
        "cost_currency": "USD",
    }
    before = snapshot(f)
    inserted = []

    def fail_after_insert(_connection, _cursor, statement, *_args):
        if statement.lstrip().lower().startswith(f"insert into {table} "):
            inserted.append(table)
            raise RuntimeError("injected catalog evidence failure")

    event.listen(f.engine, "after_cursor_execute", fail_after_insert)
    try:
        with pytest.raises(RuntimeError, match="injected catalog evidence failure"):
            ProductCommandService(f.session_factory).create(ctx, body)
    finally:
        event.remove(f.engine, "after_cursor_execute", fail_after_insert)
    assert inserted == [table]
    assert snapshot(f) == before
    result = ProductCommandService(f.session_factory).create(ctx, body)
    assert str(result.standard_cost) == "3.1250"
    after = snapshot(f)
    for name in ("products", "audit_logs", "outbox_events"):
        assert len(after[name]) == len(before[name]) + 1
    assert after["activities"] == before["activities"]
    with pytest.raises(ApiProblem) as duplicate:
        ProductCommandService(f.session_factory).create(ctx, body)
    assert duplicate.value.code == "PRODUCT_SKU_EXISTS"
    assert snapshot(f) == after
