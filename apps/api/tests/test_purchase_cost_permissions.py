from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission, permissions_for_role
from app.identity.enums import MembershipRole, MembershipStatus
from app.identity.models import OrganizationMembership, User
from app.procurement.repositories import PurchaseOrderRepository
from app.procurement.schemas import PurchaseOrderDecision
from app.procurement.services import PurchaseOrderCommandService, PurchaseOrderQueryService
from sqlalchemy import select
from test_purchase_changes import change_request, replacement
from test_purchase_creation_idempotency import counts, request, setup
from test_purchase_receiving import confirmed_purchase, receipt

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration

COST_FIELDS = (
    "currency_code",
    "exchange_rate",
    "total",
    "total_order_currency",
    "retained_total",
    "retained_total_order_currency",
)


def assert_costs(actual, original, visible):
    for field in COST_FIELDS:
        assert actual[field] == (original[field] if visible else None)
    for item, source in zip(actual["items"], original["items"], strict=True):
        for field in ("unit_cost", "line_total"):
            assert item[field] == (source[field] if visible else None)
        assert item["quantity"] == source["quantity"]
        assert item["received_quantity"] == source["received_quantity"]


@pytest.mark.parametrize("role", list(MembershipRole))
def test_purchase_cost_policy_covers_reads_histories_and_denied_commands(quotation_fixture, role):
    f = quotation_fixture
    purchase = confirmed_purchase(f)
    subject = f"purchase-cost-{role}"
    with f.session_factory.begin() as session:
        user = User(external_subject=subject, display_name="Purchase policy fixture")
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
    visible = role in {MembershipRole.ADMIN, MembershipRole.MANAGER, MembershipRole.FINANCE}
    headers = f.headers(subject, f.organization_a) | {"Idempotency-Key": "denied-pricing"}
    path = f"/api/v1/purchase-orders/{purchase['id']}"
    before = counts(f)
    detail = f.client.get(path, headers=headers)
    page = f.client.get("/api/v1/purchase-orders", headers=headers)
    assert detail.status_code == page.status_code == 200
    assert_costs(detail.json(), purchase, visible)
    assert_costs(page.json()["items"][0], purchase, visible)
    history = f.client.get(path + "/activities", headers=headers)
    assert history.status_code == 200
    created = next(
        row for row in history.json()["items"] if row["activity_type"] == "purchase_order.created"
    )
    assert ("total" in created["details"]["command_result"]) == visible
    with f.session_factory() as session:
        repository = PurchaseOrderRepository(session)
        cached = repository.get(organization_id=f.organization_a, record_id=UUID(purchase["id"]))
        service = PurchaseOrderQueryService(repository)
        for output in (service.get(context, cached.id), service.list(context, limit=50)[0]):
            assert_costs(output.model_dump(mode="json"), purchase, visible)
        assert str(cached.total) == purchase["total"]
        assert not session.dirty
        foreign = replace(context, organization_id=f.organization_b)
        assert service.list(foreign, limit=50) == []
        for read in (
            lambda: service.get(foreign, cached.id),
            lambda: service.activities(foreign, cached.id, offset=0, limit=20),
        ):
            with pytest.raises(ApiProblem) as missing:
                read()
            assert missing.value.status == 404
    if role not in {MembershipRole.ADMIN, MembershipRole.MANAGER}:
        for route, body in (
            ("/api/v1/purchase-orders", replacement(purchase)),
            (path + "/approve", {}),
            (path + "/cancel", change_request(purchase)),
            (path + "/amend", {**change_request(purchase), "replacement": replacement(purchase)}),
        ):
            assert f.client.post(route, headers=headers, json=body).status_code == 403
    assert counts(f) == before


def test_cost_authority_is_required_before_create_replay_or_validation(quotation_fixture):
    f = quotation_fixture
    purchase = confirmed_purchase(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission) - {Permission.PROFIT_READ},
        request_id=uuid4(),
    )
    service = PurchaseOrderCommandService(f.session_factory)
    before = counts(f)
    for operation in (
        lambda: service.create(context, {}, idempotency_key="denied"),
        lambda: service.approve(
            context,
            UUID(purchase["id"]),
            PurchaseOrderDecision(expected_version=purchase["version"]),
            idempotency_key="denied",
        ),
        lambda: service.cancel(context, UUID(purchase["id"]), {}, idempotency_key="denied"),
        lambda: service.amend(context, UUID(purchase["id"]), {}, idempotency_key="denied"),
    ):
        with pytest.raises(ApiProblem) as denied:
            operation()
        assert denied.value.status == 403
    assert counts(f) == before
    result = service.receive(
        context, UUID(purchase["id"]), receipt(purchase), idempotency_key="receipt"
    )
    assert all(getattr(result, field) is None for field in COST_FIELDS)
    after = counts(f)
    assert (
        service.receive(context, result.id, receipt(purchase), idempotency_key="receipt") == result
    )
    assert counts(f) == after


def test_downgraded_creator_cannot_replay_pricing_with_existing_token(quotation_fixture):
    f = quotation_fixture
    _, body = setup(f)
    created = request(f, body, "before-downgrade")
    assert created.status_code == 201
    purchase = created.json()
    headers = f.headers("quotation-manager", f.organization_a)
    with f.session_factory.begin() as session:
        user = session.scalar(select(User).where(User.external_subject == "quotation-manager"))
        member = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_a,
                OrganizationMembership.user_id == user.id,
            )
        )
        member.role = MembershipRole.OPERATIONS
    before = counts(f)
    replay = f.client.post(
        "/api/v1/purchase-orders",
        headers=headers | {"Idempotency-Key": "before-downgrade"},
        json=body,
    )
    assert replay.status_code == 403
    detail = f.client.get(f"/api/v1/purchase-orders/{purchase['id']}", headers=headers)
    assert detail.status_code == 200
    assert_costs(detail.json(), purchase, False)
    assert counts(f) == before
