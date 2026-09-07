from concurrent.futures import ThreadPoolExecutor
from datetime import date
from uuid import UUID, uuid4

import pytest
from alembic import command
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission, permissions_for_role
from app.catalog.models import ProductSupplierLink
from app.catalog.supplier_services import (
    SupplierLinkQuery,
    SupplierLinkRepository,
    SupplierLinkService,
)
from app.identity.enums import MembershipRole, MembershipStatus
from app.identity.models import OrganizationMembership, User
from app.platform.records import AuditRecorder, OutboxRecorder
from app.work.models import Activity
from legacy_migration import verify_legacy_guard, verify_legacy_upgrade
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_migrations import alembic_config
from test_quotation_vertical_slice import create_commercial_inputs, post_ok, table_counts

pytest_plugins = ("test_quotation_vertical_slice",)


def headers(f, key="supplier-link", subject="quotation-manager", organization=None):
    return f.headers(subject, organization or f.organization_a) | {"Idempotency-Key": key}


def inputs(f, suffix="A", organization=None, subject="quotation-manager", role="SUPPLIER"):
    h = headers(f, f"company-{suffix}", subject, organization)
    company = f.client.post(
        "/api/v1/companies", headers=h, json={"name": f"Supplier {suffix}", "roles": [role]}
    )
    assert company.status_code == 201, company.text
    if organization == f.organization_b:
        # Foreign cost fixtures use a separately authorized manager, not a promoted sales actor.
        with f.session_factory.begin() as session:
            manager = session.scalar(
                select(User).where(User.external_subject == "supplier-other-manager")
            )
            if manager is None:
                manager = User(
                    external_subject="supplier-other-manager", display_name="Foreign manager"
                )
                session.add(manager)
                session.flush()
                session.add(
                    OrganizationMembership(
                        organization_id=organization,
                        user_id=manager.id,
                        role=MembershipRole.MANAGER,
                        status=MembershipStatus.ACTIVE,
                    )
                )
        h = headers(f, f"product-{suffix}", "supplier-other-manager", organization)
    product = f.client.post(
        "/api/v1/products",
        headers=h,
        json={
            "sku": f"SKU-{suffix}",
            "name": f"Product {suffix}",
            "unit": "set",
            "standard_cost": "7.7777",
            "cost_currency": "CNY",
        },
    )
    assert product.status_code == 201, product.text
    return product.json(), company.json()


def terms(supplier):
    return {
        "supplier_id": supplier["id"],
        "supplier_sku": "FACTORY-001",
        "unit_price": "7.7777",
        "currency": "CNY",
        "lead_time_days": 21,
        "quoted_on": "2026-09-06",
        "valid_until": "2026-10-06",
        "quotation_reference": "Supplier email RFQ-17",
    }


def create(f, product, supplier, key="supplier-link"):
    response = f.client.post(
        f"/api/v1/products/{product['id']}/supplier-links",
        headers=headers(f, key),
        json=terms(supplier),
    )
    assert response.status_code == 201, response.text
    return response.json()


def update_body(row, **changes):
    fields = {
        name: row[name]
        for name in (
            "supplier_sku",
            "unit_price",
            "currency",
            "lead_time_days",
            "quoted_on",
            "valid_until",
            "quotation_reference",
        )
    }
    return (
        fields
        | {"expected_version": row["version"], "reason": "Supplier reconfirmed reference terms"}
        | changes
    )


def test_create_update_replay_and_bounded_history(quotation_fixture):
    f = quotation_fixture
    product, supplier = inputs(f)
    before = table_counts(f)
    row = create(f, product, supplier)
    assert row["unit_price"] == "7.7777"
    assert table_counts(f) == tuple(value + 1 for value in before)
    saved = table_counts(f)
    assert create(f, product, supplier) == row
    assert table_counts(f) == saved
    path = f"/api/v1/products/{product['id']}/supplier-links"
    duplicate = f.client.post(path, headers=headers(f, "duplicate"), json=terms(supplier))
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "SUPPLIER_LINK_EXISTS"
    body = update_body(row, unit_price="8.1250", lead_time_days=14)
    changed = f.client.put(path + f"/{row['id']}", headers=headers(f, "edit"), json=body)
    assert changed.status_code == 200, changed.text
    assert changed.json()["unit_price"] == "8.1250"
    assert changed.json()["version"] == row["version"] + 1
    assert (
        f.client.put(path + f"/{row['id']}", headers=headers(f, "edit"), json=body).json()
        == changed.json()
    )
    assert (
        f.client.put(path + f"/{row['id']}", headers=headers(f, "stale"), json=body).status_code
        == 409
    )
    assert f.client.get(path, headers=headers(f)).json()["items"] == [changed.json()]
    assert f.client.get(path + "/activities?limit=1", headers=headers(f)).json()["has_more"]
    assert (
        len(f.client.get(path + "/activities?limit=1&offset=1", headers=headers(f)).json()["items"])
        == 1
    )
    assert f.client.get(f"/api/v1/products/{product['id']}", headers=headers(f)).json() == product


@pytest.mark.parametrize(
    "changes",
    [
        {"unit_price": "-0.0001"},
        {"unit_price": "1.00001"},
        {"unit_price": "NaN"},
        {"currency": "cny"},
        {"currency": "人民币"},
        {"lead_time_days": -1},
        {"lead_time_days": 1.5},
        {"valid_until": "2026-09-01"},
        {"supplier_sku": " "},
    ],
)
def test_invalid_supplier_terms_have_no_partial_evidence(quotation_fixture, changes):
    f = quotation_fixture
    product, supplier = inputs(f)
    before = table_counts(f)
    response = f.client.post(
        f"/api/v1/products/{product['id']}/supplier-links",
        headers=headers(f),
        json=terms(supplier) | changes,
    )
    assert response.status_code == 422
    assert table_counts(f) == before


def test_tenant_parent_role_and_permission_boundaries(quotation_fixture):
    f = quotation_fixture
    product, supplier = inputs(f)
    row = create(f, product, supplier)
    foreign_product, foreign_supplier = inputs(f, "B", f.organization_b, "quotation-other")
    path = f"/api/v1/products/{product['id']}/supplier-links"
    foreign = headers(f, subject="supplier-other-manager", organization=f.organization_b)
    for suffix in ("", f"/{row['id']}", "/activities", f"?cursor={row['id']}"):
        assert f.client.get(path + suffix, headers=foreign).status_code == 404
    assert f.client.post(path, headers=foreign, json=terms(foreign_supplier)).status_code == 404
    assert (
        f.client.put(path + f"/{row['id']}", headers=foreign, json=update_body(row)).status_code
        == 404
    )
    assert (
        f.client.post(
            path, headers=headers(f, "foreign-supplier"), json=terms(foreign_supplier)
        ).status_code
        == 404
    )
    other_path = f"/api/v1/products/{foreign_product['id']}/supplier-links"
    assert f.client.get(other_path + f"?cursor={row['id']}", headers=foreign).status_code == 404
    product2, customer = inputs(f, "C", role="CUSTOMER")
    assert (
        f.client.post(path, headers=headers(f, "customer"), json=terms(customer)).json()["code"]
        == "SUPPLIER_ROLE_REQUIRED"
    )
    wrong_parent = f"/api/v1/products/{product2['id']}/supplier-links/{row['id']}"
    assert f.client.get(wrong_parent, headers=headers(f)).status_code == 404
    assert (
        f.client.put(wrong_parent, headers=headers(f, "parent"), json=update_body(row)).status_code
        == 404
    )
    assert (
        f.client.put(
            path + f"/{row['id']}",
            headers=headers(f, "move"),
            json=update_body(row, supplier_id=customer["id"]),
        ).status_code
        == 422
    )
    assert (
        f.client.post(
            path, headers=headers(f, subject="quotation-finance"), json=terms(supplier)
        ).status_code
        == 403
    )
    assert f.client.get(path, headers=headers(f, subject="quotation-finance")).status_code == 200
    with f.session_factory.begin() as session:
        viewer = User(external_subject="supplier-viewer", display_name="Viewer")
        session.add(viewer)
        session.flush()
        session.add(
            OrganizationMembership(
                organization_id=f.organization_a,
                user_id=viewer.id,
                role=MembershipRole.VIEWER,
                status=MembershipStatus.ACTIVE,
            )
        )
    assert f.client.get(path, headers=headers(f, subject="supplier-viewer")).status_code == 403
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=permissions_for_role(MembershipRole.VIEWER),
        request_id=uuid4(),
    )
    with f.session_factory() as session, pytest.raises(ApiProblem) as denied:
        SupplierLinkQuery(session).get(context, UUID(product["id"]), UUID(row["id"]))
    assert denied.value.status == 403
    with pytest.raises(ApiProblem) as denied:
        SupplierLinkService(f.session_factory).write(
            context, UUID(product["id"]), terms(supplier), key="deny-service"
        )
    assert denied.value.status == 403


@pytest.mark.parametrize("recorder", [Activity, AuditRecorder, OutboxRecorder])
@pytest.mark.parametrize("editing", [False, True])
def test_evidence_failure_rolls_back_supplier_terms(
    quotation_fixture, monkeypatch, recorder, editing
):
    f = quotation_fixture
    product, supplier = inputs(f)
    row = create(f, product, supplier) if editing else None
    before = table_counts(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )

    def fail(*args, **kwargs):
        raise RuntimeError("supplier evidence failure")

    if recorder is Activity:
        original = Session.add

        def add(session, record, *args, **kwargs):
            if isinstance(record, Activity):
                fail()
            return original(session, record, *args, **kwargs)

        monkeypatch.setattr(Session, "add", add)
    else:
        monkeypatch.setattr(recorder, "record", fail)
    with pytest.raises(RuntimeError, match="supplier evidence failure"):
        SupplierLinkService(f.session_factory).write(
            context,
            UUID(product["id"]),
            update_body(row, unit_price="10.0000") if row else terms(supplier),
            key="fail",
            link_id=UUID(row["id"]) if row else None,
        )
    assert table_counts(f) == before
    with f.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(ProductSupplierLink)) == int(editing)
        if row:
            assert (
                str(session.get(ProductSupplierLink, UUID(row["id"])).unit_price)
                == row["unit_price"]
            )


def test_concurrent_duplicates_and_updates_have_one_winner(quotation_fixture):
    f = quotation_fixture
    product, supplier = inputs(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )

    def run(index, row=None):
        try:
            SupplierLinkService(f.session_factory).write(
                context,
                UUID(product["id"]),
                update_body(row, unit_price=str(8 + index)) if row else terms(supplier),
                key=f"{'edit' if row else 'create'}-{index}",
                link_id=UUID(row["id"]) if row else None,
            )
            return "ok"
        except ApiProblem as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(run, range(2))) == ["SUPPLIER_LINK_EXISTS", "ok"]
    row = f.client.get(
        f"/api/v1/products/{product['id']}/supplier-links", headers=headers(f)
    ).json()["items"][0]
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda index: run(index, row), range(2))) == [
            "VERSION_CONFLICT",
            "ok",
        ]


def test_migration_preserves_existing_products_and_database_rejects_cross_tenant_links(
    quotation_fixture,
):
    f = quotation_fixture
    product, supplier = inputs(f)
    config = alembic_config(f.engine.url.render_as_string(hide_password=False))
    verify_legacy_upgrade(f.engine, "20260906_0015")
    command.check(config)
    assert f.client.get(f"/api/v1/products/{product['id']}", headers=headers(f)).json() == product
    _, foreign_supplier = inputs(f, "B", f.organization_b, "quotation-other")
    with pytest.raises(IntegrityError), f.session_factory.begin() as session:
        session.add(
            ProductSupplierLink(
                organization_id=f.organization_a,
                product_id=UUID(product["id"]),
                supplier_id=UUID(foreign_supplier["id"]),
                supplier_sku="BAD",
                unit_price=1,
                currency="CNY",
                lead_time_days=1,
                quoted_on=date(2026, 9, 6),
            )
        )
    create(f, product, supplier)
    verify_legacy_guard(f.engine, "20260906_0016", "20260906_0015", "references exist")


def test_reference_price_changes_do_not_reprice_quotation_snapshots(quotation_fixture):
    f = quotation_fixture
    request, _, _ = create_commercial_inputs(f)
    quote = post_ok(f, "/api/v1/quotations", "quotation-manager", request, 201)
    for action, subject in (
        ("submit", "quotation-sales"),
        ("approve", "quotation-manager"),
        ("send", "quotation-sales"),
    ):
        post_ok(f, f"/api/v1/quotations/{quote['id']}/{action}", subject)
    quote = f.client.get(f"/api/v1/quotations/{quote['id']}", headers=headers(f)).json()
    assert quote["current_version"]["status"] == "SENT"
    product_id = request["items"][0]["product_id"]
    _, supplier = inputs(f, "quote-supplier")
    row = create(f, {"id": product_id}, supplier)
    result = f.client.put(
        f"/api/v1/products/{product_id}/supplier-links/{row['id']}",
        headers=headers(f, "new-price"),
        json=update_body(row, unit_price="123.4567", currency="USD"),
    )
    assert result.status_code == 200, result.text
    persisted = f.client.get(f"/api/v1/quotations/{quote['id']}", headers=headers(f)).json()
    assert persisted["current_version"] == quote["current_version"]


def test_supplier_cursor_pages_and_locked_reads_refresh_cached_versions(quotation_fixture):
    f = quotation_fixture
    product, supplier = inputs(f)
    older = create(f, product, supplier)
    _, second_supplier = inputs(f, "second")
    newer = create(f, product, second_supplier, "second-link")
    path = f"/api/v1/products/{product['id']}/supplier-links"
    first = f.client.get(path + "?limit=1", headers=headers(f)).json()
    assert first["items"] == [newer]
    assert first["has_more"] and first["next_cursor"] == newer["id"]
    last = f.client.get(path + f"?limit=1&cursor={newer['id']}", headers=headers(f)).json()
    assert last["items"] == [older]
    assert not last["has_more"] and last["next_cursor"] is None
    with f.session_factory() as session:
        repository = SupplierLinkRepository(session)
        cached = repository.get(f.organization_a, UUID(product["id"]), UUID(older["id"]))
        updated = f.client.put(
            path + f"/{older['id']}",
            headers=headers(f, "external-change"),
            json=update_body(older, unit_price="9.5000"),
        )
        assert updated.status_code == 200
        locked = repository.get(f.organization_a, UUID(product["id"]), UUID(older["id"]), lock=True)
        assert locked is cached
        assert locked.version == updated.json()["version"]
        assert str(locked.unit_price) == "9.5000"
