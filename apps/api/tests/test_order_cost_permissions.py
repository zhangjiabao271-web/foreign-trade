from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission, permissions_for_role
from app.identity.enums import MembershipRole, MembershipStatus
from app.identity.models import OrganizationMembership, User
from app.sales.order_repositories import SalesOrderRepository
from app.sales.order_services import SalesOrderCommandService, SalesOrderQueryService
from test_order_procurement_vertical_slice import create_accepted_quotation, phase_four_counts

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration

ORDER_COST_FIELDS = ("total_cost", "gross_profit", "gross_margin")
ITEM_COST_FIELDS = (
    "unit_cost",
    "cost_currency",
    "cost_exchange_rate",
    "allocated_cost",
    "line_cost",
    "line_gross_profit",
)


def assert_projection(actual, privileged, visible):
    expected = {
        **privileged,
        "items": [dict(item) for item in privileged["items"]],
    }
    if not visible:
        expected.update(dict.fromkeys(ORDER_COST_FIELDS))
        expected.update(content_visible=False, payment_terms=None, delivery_terms=None)
        for item in expected["items"]:
            item.update(dict.fromkeys(ITEM_COST_FIELDS))
            item["description_snapshot"] = None
    assert actual == expected


@pytest.mark.parametrize("role", list(MembershipRole))
def test_order_cost_policy_all_roles_api_service_and_replay(quotation_fixture, role):
    f = quotation_fixture
    quote, _, _ = create_accepted_quotation(f)
    subject = f"order-cost-{role}"
    with f.session_factory.begin() as session:
        user = User(external_subject=subject, display_name="Order cost policy fixture")
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
    headers = f.headers(subject, f.organization_a)
    manager_headers = f.headers("quotation-manager", f.organization_a)
    body = {"quotation_id": quote["id"], "deposit_rate": "0.3000"}
    can_write = Permission.ORDER_WRITE in context.permissions
    visible = role in {MembershipRole.ADMIN, MembershipRole.MANAGER, MembershipRole.FINANCE}
    created = f.client.post(
        "/api/v1/sales-orders", json=body, headers=headers if can_write else manager_headers
    )
    assert created.status_code == 201
    order_id = UUID(created.json()["id"])
    path = f"/api/v1/sales-orders/{order_id}"
    privileged = f.client.get(path, headers=manager_headers).json()
    assert all(privileged[field] is not None for field in ORDER_COST_FIELDS)
    if can_write:
        assert_projection(created.json(), privileged, visible)
    before = phase_four_counts(f)
    for response in (
        f.client.get(path, headers=headers),
        f.client.get("/api/v1/sales-orders", headers=headers),
    ):
        assert response.status_code == 200
        result = response.json()
        assert_projection(result["items"][0] if "count" in result else result, privileged, visible)
    with f.session_factory() as session:
        repository = SalesOrderRepository(session)
        stored = repository.get(organization_id=f.organization_a, record_id=order_id)
        stored_items = repository.items(organization_id=f.organization_a, sales_order_id=order_id)
        service = SalesOrderQueryService(repository)
        for result in (service.get(context, order_id), service.list(context, limit=50)[0]):
            assert_projection(result.model_dump(mode="json"), privileged, visible)
        assert str(stored.total_cost) == privileged["total_cost"]
        assert stored.payment_terms == privileged["payment_terms"]
        assert stored.delivery_terms == privileged["delivery_terms"]
        for stored_item, original in zip(stored_items, privileged["items"], strict=True):
            assert stored_item.description_snapshot == original["description_snapshot"]
            for field in ITEM_COST_FIELDS:
                assert str(getattr(stored_item, field)) == original[field]
        session.flush()
        assert not session.dirty
        foreign = replace(context, organization_id=f.organization_b)
        assert service.list(foreign, limit=50) == []
        with pytest.raises(ApiProblem) as missing:
            service.get(foreign, order_id)
        assert missing.value.status == 404
        with pytest.raises(ApiProblem) as denied:
            service.get(replace(context, permissions=frozenset()), order_id)
        assert denied.value.status == 403
    replay = f.client.post("/api/v1/sales-orders", json=body, headers=headers)
    if can_write:
        assert replay.status_code == 201
        assert_projection(replay.json(), privileged, visible)
        result = SalesOrderCommandService(f.session_factory).create(context, body)
        assert_projection(result.model_dump(mode="json"), privileged, visible)
    else:
        assert replay.status_code == 403
        with pytest.raises(ApiProblem) as denied:
            SalesOrderCommandService(f.session_factory).create(context, body)
        assert denied.value.status == 403
    assert phase_four_counts(f) == before


def test_order_commands_project_without_implicit_cost_authority(quotation_fixture):
    f = quotation_fixture
    quote, _, _ = create_accepted_quotation(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission) - {Permission.PROFIT_READ},
        request_id=uuid4(),
    )
    service = SalesOrderCommandService(f.session_factory)
    created = service.create(context, {"quotation_id": quote["id"], "deposit_rate": "0.3"})
    assert created.total_cost is created.gross_profit is created.gross_margin is None
    from app.sales.order_schemas import SalesOrderConfirm

    request = SalesOrderConfirm(expected_version=created.version)
    confirmed = service.confirm(context, created.id, request, key="confirm-cost-projection")
    privileged = f.client.get(
        f"/api/v1/sales-orders/{created.id}",
        headers=f.headers("quotation-manager", f.organization_a),
    ).json()
    assert_projection(confirmed.model_dump(mode="json"), privileged, False)
    before = phase_four_counts(f)
    assert service.confirm(context, created.id, request, key="confirm-cost-projection") == confirmed
    assert phase_four_counts(f) == before
    foreign = replace(context, organization_id=f.organization_b)
    for command in (
        lambda: service.create(foreign, {"quotation_id": quote["id"], "deposit_rate": "0.3"}),
        lambda: service.confirm(foreign, created.id, request, key="confirm-cost-projection"),
    ):
        with pytest.raises(ApiProblem) as missing:
            command()
        assert missing.value.status == 404
    assert phase_four_counts(f) == before
