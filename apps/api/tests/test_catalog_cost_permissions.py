from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission, permissions_for_role
from app.catalog.models import Product
from app.catalog.repositories import ProductRepository
from app.catalog.services import ProductCommandService, ProductQueryService
from app.catalog.supplier_services import SupplierLinkQuery, SupplierLinkService
from app.identity.enums import MembershipRole, MembershipStatus
from app.identity.models import OrganizationMembership, User
from test_product_suppliers import create, inputs, terms, update_body
from test_quotation_vertical_slice import table_counts

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration


@pytest.mark.parametrize("role", list(MembershipRole))
def test_catalog_cost_policy_for_every_role(quotation_fixture, role):
    f = quotation_fixture
    product, supplier = inputs(f)
    link = create(f, product, supplier)
    with f.session_factory.begin() as session:
        user = User(external_subject=f"cost-{role}", display_name="Cost policy fixture")
        session.add(user)
        session.flush()
        user_id = user.id
        session.add(
            OrganizationMembership(
                organization_id=f.organization_a,
                user_id=user_id,
                role=role,
                status=MembershipStatus.ACTIVE,
            )
        )
    context = RequestContext(
        user_id=user_id,
        organization_id=f.organization_a,
        permissions=permissions_for_role(role),
        request_id=uuid4(),
    )
    headers = f.headers(f"cost-{role}", f.organization_a) | {"Idempotency-Key": "supplier-link"}
    visible = role in {MembershipRole.ADMIN, MembershipRole.MANAGER, MembershipRole.FINANCE}
    before = table_counts(f)
    detail = f.client.get(f"/api/v1/products/{product['id']}", headers=headers)
    page = f.client.get("/api/v1/products", headers=headers)
    assert detail.status_code == page.status_code == 200
    for result in (detail.json(), page.json()["items"][0]):
        assert result["standard_cost"] == ("7.7777" if visible else None)
        assert result["cost_currency"] == ("CNY" if visible else None)
        assert result["sku"] == product["sku"]
    path = f"/api/v1/products/{product['id']}/supplier-links"
    for suffix in ("", f"/{link['id']}", "/activities"):
        assert f.client.get(path + suffix, headers=headers).status_code == (200 if visible else 403)
    with f.session_factory() as session:
        repository = ProductRepository(session)
        cached = repository.get(organization_id=f.organization_a, record_id=UUID(product["id"]))
        projected = ProductQueryService(repository).get(context, UUID(product["id"]))
        assert projected.standard_cost == (cached.standard_cost if visible else None)
        assert str(cached.standard_cost) == "7.7777"
        if not visible:
            with pytest.raises(ApiProblem) as denied:
                SupplierLinkQuery(session).get(context, UUID(product["id"]), UUID(link["id"]))
            assert denied.value.status == 403
    if role not in {MembershipRole.ADMIN, MembershipRole.MANAGER}:
        assert (
            f.client.post(
                "/api/v1/products",
                headers=headers,
                json={
                    "sku": "DENIED",
                    "name": "Denied",
                    "unit": "set",
                    "standard_cost": "9",
                    "cost_currency": "USD",
                },
            ).status_code
            == 403
        )
        assert f.client.post(path, headers=headers, json=terms(supplier)).status_code == 403
        assert (
            f.client.put(
                path + f"/{link['id']}", headers=headers, json=update_body(link)
            ).status_code
            == 403
        )
    assert table_counts(f) == before
    with f.session_factory() as session:
        assert str(session.get(Product, UUID(product["id"])).standard_cost) == "7.7777"


def test_catalog_services_require_cost_authority_even_with_write_permissions(quotation_fixture):
    f = quotation_fixture
    product, supplier = inputs(f)
    link = create(f, product, supplier)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission) - {Permission.PROFIT_READ},
        request_id=uuid4(),
    )
    before = table_counts(f)
    with pytest.raises(ApiProblem) as denied:
        ProductCommandService(f.session_factory).create(context, {})
    assert denied.value.status == 403
    with pytest.raises(ApiProblem) as denied:
        SupplierLinkService(f.session_factory).write(
            context, UUID(product["id"]), terms(supplier), key="supplier-link"
        )
    assert denied.value.status == 403
    with f.session_factory() as session:
        service = SupplierLinkQuery(session)
        for read in (
            lambda: service.get(context, UUID(product["id"]), UUID(link["id"])),
            lambda: service.list(context, UUID(product["id"]), cursor=None, limit=25),
            lambda: service.history(context, UUID(product["id"]), offset=0, limit=25),
            lambda: service.supplier_names(context, []),
        ):
            with pytest.raises(ApiProblem) as denied:
                read()
            assert denied.value.status == 403
        foreign = replace(context, organization_id=f.organization_b)
        with pytest.raises(ApiProblem) as missing:
            ProductQueryService(ProductRepository(session)).get(foreign, UUID(product["id"]))
        assert missing.value.status == 404
    assert table_counts(f) == before
