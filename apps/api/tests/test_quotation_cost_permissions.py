from copy import deepcopy
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission, permissions_for_role
from app.identity.enums import MembershipRole, MembershipStatus
from app.identity.models import OrganizationMembership, User
from app.sales.models import QuotationVersion
from app.sales.repositories import QuotationRepository
from app.sales.services import QuotationCommandService, QuotationQueryService
from test_quotation_vertical_slice import (
    create_commercial_inputs,
    post_ok,
    state_request,
    table_counts,
)

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration
ITEM_COSTS = (
    "unit_cost",
    "cost_currency",
    "cost_exchange_rate",
    "allocated_cost",
    "line_cost",
    "line_gross_profit",
)
VERSION_COSTS = ("total_cost", "gross_profit", "gross_margin")


def assert_snapshot(actual, source, visible):
    for field in VERSION_COSTS:
        assert actual[field] == (source[field] if visible else None)
    assert actual["total"] == source["total"]
    for item, original in zip(actual["items"], source["items"], strict=True):
        for field in ITEM_COSTS:
            assert item[field] == (original[field] if visible else None)
        assert item["unit_price"] == original["unit_price"]


@pytest.mark.parametrize("role", list(MembershipRole))
def test_quotation_projection_at_http_and_service_boundaries(quotation_fixture, role):
    f = quotation_fixture
    body, _, _ = create_commercial_inputs(f)
    quote = post_ok(f, "/api/v1/quotations", "quotation-manager", body, 201)
    source = quote["current_version"]
    subject = f"quote-cost-{role}"
    with f.session_factory.begin() as session:
        user = User(external_subject=subject, display_name="Quote policy")
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
    visible = Permission.PROFIT_READ in context.permissions
    headers = f.headers(subject, f.organization_a)
    detail = f.client.get(f"/api/v1/quotations/{quote['id']}", headers=headers)
    assert detail.status_code == 200
    for version in detail.json()["versions"]:
        assert_snapshot(version, source, visible)
    rows = f.client.get("/api/v1/quotations", headers=headers).json()["items"]
    for field in ("gross_profit", "gross_margin"):
        assert rows[0][field] == (source[field] if visible else None)
    with f.session_factory() as session:
        service = QuotationQueryService(QuotationRepository(session))
        cached = session.get(QuotationVersion, UUID(source["id"]))
        result = service.get(context, UUID(quote["id"]))
        assert_snapshot(result.current_version.model_dump(mode="json"), source, visible)
        assert str(cached.total_cost) == source["total_cost"]
        assert not session.dirty
        foreign = replace(context, organization_id=f.organization_b)
        assert service.list(foreign, status=None, limit=50) == []
        with pytest.raises(ApiProblem) as missing:
            service.get(foreign, UUID(quote["id"]))
        assert missing.value.status == 404


def test_sales_revision_inherits_protected_snapshot_and_redacts_replay(quotation_fixture):
    f = quotation_fixture
    body, _, _ = create_commercial_inputs(f)
    quote = post_ok(f, "/api/v1/quotations", "quotation-manager", body, 201)
    original = quote["current_version"]
    headers = f.headers("quotation-sales", f.organization_a) | {"Idempotency-Key": "safe-revision"}
    payload = {"expected_version_id": original["id"], "valid_until": original["valid_until"]}
    path = f"/api/v1/quotations/{quote['id']}/revisions"
    revised = f.client.post(path, json=payload, headers=headers)
    assert revised.status_code == 201, revised.text
    assert_snapshot(revised.json(), original, False)
    assert f.client.post(path, json=payload, headers=headers).json() == revised.json()
    full = f.client.get(
        f"/api/v1/quotations/{quote['id']}",
        headers=f.headers("quotation-manager", f.organization_a),
    ).json()
    assert_snapshot(full["current_version"], original, True)
    for field in ITEM_COSTS:
        assert full["current_version"]["items"][0][field] == original["items"][0][field]


@pytest.mark.parametrize(
    "field", ["unit_cost", "cost_currency", "cost_exchange_rate", "allocated_cost"]
)
def test_sales_cannot_submit_protected_inputs_even_as_null(quotation_fixture, field):
    f = quotation_fixture
    body, _, _ = create_commercial_inputs(f)
    body = deepcopy(body)
    for item in body["items"]:
        for key in ITEM_COSTS:
            item.pop(key, None)
    body["items"][0][field] = None
    before = table_counts(f)
    response = f.client.post(
        "/api/v1/quotations", json=body, headers=f.headers("quotation-sales", f.organization_a)
    )
    assert response.status_code == 403
    assert table_counts(f) == before
    assert (
        f.client.get(
            "/api/v1/quotations", headers=f.headers("quotation-manager", f.organization_a)
        ).json()["items"]
        == []
    )


def test_sales_new_draft_requires_resolvable_cost_currency(quotation_fixture):
    f = quotation_fixture
    body, _, _ = create_commercial_inputs(f)
    body["items"] = [body["items"][0]]
    for key in ITEM_COSTS:
        body["items"][0].pop(key, None)
    headers = f.headers("quotation-sales", f.organization_a)
    rejected = f.client.post("/api/v1/quotations", json=body, headers=headers)
    assert rejected.status_code == 409
    assert rejected.json()["code"] == "COST_PREPARATION_REQUIRED"
    body["currency_code"] = "CNY"
    created = f.client.post("/api/v1/quotations", json=body, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["current_version"]["total_cost"] is None
    full = f.client.get(
        f"/api/v1/quotations/{created.json()['id']}",
        headers=f.headers("quotation-manager", f.organization_a),
    ).json()["current_version"]
    assert full["items"][0]["unit_cost"] == "7.7777"
    assert full["items"][0]["cost_exchange_rate"] == "1.00000000"


def test_command_returns_and_replays_apply_current_cost_permission(quotation_fixture):
    f = quotation_fixture
    body, _, _ = create_commercial_inputs(f)
    quote = post_ok(f, "/api/v1/quotations", "quotation-manager", body, 201)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission) - {Permission.PROFIT_READ},
        request_id=uuid4(),
    )
    service = QuotationCommandService(f.session_factory)
    for operation in (
        service.submit,
        service.approve,
        service.approve,
        service.send,
        service.accept,
        service.accept,
    ):
        output = operation(
            context, UUID(quote["id"]), state_request(f, quote["id"]), key=str(uuid4())
        )
        assert_snapshot(output.model_dump(mode="json"), quote["current_version"], False)


def test_currency_revision_cannot_silently_reuse_old_cost_rate(quotation_fixture):
    f = quotation_fixture
    body, _, _ = create_commercial_inputs(f)
    quote = post_ok(f, "/api/v1/quotations", "quotation-manager", body, 201)
    before = table_counts(f)
    path = f"/api/v1/quotations/{quote['id']}/revisions"
    for subject in ("quotation-sales", "quotation-manager"):
        response = f.client.post(
            path, json={"currency_code": "GBP"}, headers=f.headers(subject, f.organization_a)
        )
        assert response.status_code == 409
        assert response.json()["code"] == "COST_PREPARATION_REQUIRED"
        assert table_counts(f) == before
    detail = f.client.get(
        f"/api/v1/quotations/{quote['id']}",
        headers=f.headers("quotation-manager", f.organization_a),
    ).json()
    assert detail == quote
