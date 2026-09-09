from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import permissions_for_role
from app.crm.models import Opportunity
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership
from app.sales.models import SalesOrder
from app.sales.order_enums import SalesOrderStatus
from app.sales.order_schemas import SalesOrderConfirm
from app.sales.order_services import SalesOrderCommandService
from app.sales.services import QuotationCommandService
from app.sales.text_review import (
    CommercialTextReviewRequest,
    CommercialTextReviewService,
    require_content,
)
from sqlalchemy import select
from test_document_review import reviewer
from test_order_confirmation_commands import counts as confirmation_counts
from test_order_confirmation_commands import setup as confirmation_setup
from test_order_list_queries import create_orders
from test_quotation_state_commands import ACTIONS, invoke, setup
from test_sales_repository_paths import snapshots

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration


def foreign_manager(f):
    with f.session_factory.begin() as session:
        member = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_b
            )
        )
        member.role = MembershipRole.MANAGER
        return RequestContext(
            user_id=member.user_id,
            organization_id=f.organization_b,
            permissions=permissions_for_role(MembershipRole.MANAGER),
            request_id=uuid4(),
        )


def commercial_facts(f):
    with f.session_factory() as session:
        opportunities = list(
            session.execute(select(Opportunity.__table__).order_by(Opportunity.id)).mappings()
        )
    return snapshots(f), opportunities


@pytest.mark.parametrize("action", (*ACTIONS, "revise", "mark_customer_review"))
def test_authorized_foreign_manager_cannot_execute_quotation_command(quotation_fixture, action):
    f = quotation_fixture
    preparation = action if action in ACTIONS else "accept"
    quote_id, state = setup(f, preparation)
    foreign = foreign_manager(f)
    if action in ACTIONS:
        request = state
        body = state.model_dump(mode="json")
        path = action
    else:
        body = {"expected_version_id": str(state.expected_version_id)}
        if action == "mark_customer_review":
            body["reason"] = "Synthetic customer review evidence"
        request = body
        path = "revisions" if action == "revise" else "mark-customer-review"
    before = commercial_facts(f)
    response = invoke(
        f, quote_id, path, body, subject="quotation-other", organization=f.organization_b
    )
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "QUOTATION_NOT_FOUND"
    with pytest.raises(ApiProblem) as denied:
        getattr(QuotationCommandService(f.session_factory), action)(
            foreign, UUID(quote_id), request, key="foreign-service"
        )
    assert (denied.value.status, denied.value.code) == (404, "QUOTATION_NOT_FOUND")
    assert commercial_facts(f) == before
    # The same input is actionable for its owner, not merely an invalid command body/state.
    own = invoke(f, quote_id, path, body)
    assert own.status_code == (201 if action == "revise" else 200), own.text


@pytest.mark.parametrize("kind", ("quotation_version", "sales_order"))
def test_foreign_manager_cannot_inspect_or_release_commercial_source(quotation_fixture, kind):
    f = quotation_fixture
    orders, _ = create_orders(f, 1)
    order = next(iter(orders.values()))
    record_id = UUID(order["quotation_version_id"] if kind == "quotation_version" else order["id"])
    _, owner = reviewer(f)
    foreign = foreign_manager(f)
    service = CommercialTextReviewService(f.session_factory)
    preview = service.inspect(owner, kind, record_id)
    request = CommercialTextReviewRequest(
        expected_version=preview.version,
        content_digest=preview.content_digest,
        confirmed=True,
        release=True,
        reason="Reviewed synthetic source",
    )
    before = commercial_facts(f)
    endpoint = f"/api/v1/commercial-text/{kind}/{record_id}/review"
    headers = f.headers("quotation-other", f.organization_b)
    responses = (
        f.client.get(endpoint, headers=headers),
        f.client.post(
            endpoint,
            headers=headers | {"Idempotency-Key": "foreign"},
            json=request.model_dump(mode="json"),
        ),
    )
    for response in responses:
        assert response.status_code == 404, response.text
        assert response.json()["code"] == "COMMERCIAL_TEXT_NOT_FOUND"
    for call in (
        lambda: service.inspect(foreign, kind, record_id),
        lambda: service.decide(foreign, kind, record_id, request, key="foreign-service"),
    ):
        with pytest.raises(ApiProblem) as denied:
            call()
        assert (denied.value.status, denied.value.code) == (404, "COMMERCIAL_TEXT_NOT_FOUND")
    with f.session_factory() as session:
        for lock in (False, True):
            with pytest.raises(ApiProblem) as denied:
                require_content(session, foreign, kind, record_id, lock=lock)
            assert denied.value.status == 404
    assert commercial_facts(f) == before
    released = service.decide(owner, kind, record_id, request, key="owner")
    assert released.released
    assert released.details == preview.details
    after = commercial_facts(f)
    assert service.decide(owner, kind, record_id, request, key="owner") == released
    assert commercial_facts(f) == after


def test_foreign_manager_cannot_confirm_order_through_http_or_service(quotation_fixture):
    f = quotation_fixture
    order_id, request = confirmation_setup(f)
    foreign = foreign_manager(f)
    before = commercial_facts(f), confirmation_counts(f)
    response = f.client.post(
        f"/api/v1/sales-orders/{order_id}/confirm",
        headers=f.headers("quotation-other", f.organization_b) | {"Idempotency-Key": "foreign"},
        json=request.model_dump(),
    )
    assert response.status_code == 404
    assert response.json()["code"] == "SALES_ORDER_NOT_FOUND"
    with pytest.raises(ApiProblem) as denied:
        SalesOrderCommandService(f.session_factory).confirm(
            foreign, order_id, request, key="foreign-service"
        )
    assert (denied.value.status, denied.value.code) == (404, "SALES_ORDER_NOT_FOUND")
    assert (commercial_facts(f), confirmation_counts(f)) == before


@pytest.mark.parametrize("state", list(SalesOrderStatus))
def test_order_confirmation_state_guards_preserve_rejected_facts(quotation_fixture, state):
    f = quotation_fixture
    order_id, request = confirmation_setup(f)
    _, owner = reviewer(f)
    service = SalesOrderCommandService(f.session_factory)
    if state != SalesOrderStatus.DRAFT:
        service.confirm(owner, order_id, request, key="prepare")
        # Disposable guard isolation, not evidence of natural downstream reachability.
        with f.session_factory.begin() as session:
            session.get(SalesOrder, order_id).status = state
    with f.session_factory() as session:
        request = SalesOrderConfirm(expected_version=session.get(SalesOrder, order_id).version)
    before_facts = commercial_facts(f)
    before_counts = confirmation_counts(f)
    response = f.client.post(
        f"/api/v1/sales-orders/{order_id}/confirm",
        headers=f.headers("quotation-manager", f.organization_a) | {"Idempotency-Key": "state"},
        json=request.model_dump(),
    )
    if state not in {"DRAFT", "DEPOSIT_PENDING", "EXECUTING"}:
        assert response.status_code == 409
        assert response.json()["code"] == "INVALID_STATE_TRANSITION"
        with pytest.raises(ApiProblem) as denied:
            service.confirm(owner, order_id, request, key="service-state")
        assert (denied.value.status, denied.value.code) == (409, "INVALID_STATE_TRANSITION")
        assert commercial_facts(f) == before_facts
        assert confirmation_counts(f) == before_counts
        return
    assert response.status_code == 200, response.text
    assert response.json()["status"] == ("DEPOSIT_PENDING" if state == "DRAFT" else state)
    expected_counts = tuple(value + 1 for value in before_counts)
    if state != "DRAFT":
        expected_counts = (*before_counts[:-1], before_counts[-1] + 1)
        original_rows, original_opportunities = before_facts
        current_rows, current_opportunities = commercial_facts(f)
        # Only the final IdempotencyKey snapshot may change on a guarded no-op.
        assert current_rows[:-1] == original_rows[:-1]
        assert current_opportunities == original_opportunities
    assert confirmation_counts(f) == expected_counts
    after = commercial_facts(f), confirmation_counts(f)
    assert str(service.confirm(owner, order_id, request, key="state").id) == str(order_id)
    assert (commercial_facts(f), confirmation_counts(f)) == after
