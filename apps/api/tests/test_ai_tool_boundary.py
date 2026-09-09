from uuid import UUID, uuid4

import pytest
from app.ai.tools import ApplicationTools
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.live_context import live_context
from app.auth.permissions import Permission
from app.identity.models import OrganizationMembership
from app.sales.models import SalesOrder, SalesOrderItem
from sqlalchemy import select
from test_order_procurement_vertical_slice import create_confirmed_order
from test_purchase_finance_boundary import rows

pytest_plugins = ("test_quotation_vertical_slice",)


def test_model_tool_catalog_contains_only_the_four_approved_reads():
    expected = {
        "SEARCH": {"search_companies"},
        "TIMELINE": {"read_order", "order_timeline"},
        "PROFIT": {"read_order", "order_timeline", "order_profit"},
        "EMAIL_DRAFT": {"read_order", "order_timeline"},
        "TASK_DRAFT": {"read_order", "order_timeline"},
    }
    assert set(ApplicationTools.schemas) == {
        "read_order",
        "order_timeline",
        "order_profit",
        "search_companies",
    }
    for intent, names in expected.items():
        definitions = ApplicationTools.definitions(intent)
        assert {item["name"] for item in definitions} == names
        assert len(definitions) == len(names)
        for item in definitions:
            assert item["strict"] is True
            assert item["parameters"]["additionalProperties"] is False
            assert set(item["parameters"]["properties"]) == (
                {"term"} if intent == "SEARCH" else {"order_id"}
            )


@pytest.mark.parametrize(
    "name,intent,required",
    [
        ("read_order", "TIMELINE", Permission.ORDER_READ),
        ("order_timeline", "TIMELINE", Permission.ORDER_READ),
        ("order_profit", "PROFIT", Permission.PROFIT_READ),
        ("search_companies", "SEARCH", Permission.COMPANY_READ),
    ],
)
@pytest.mark.parametrize("remove_ai", [False, True])
def test_each_tool_requires_authority_before_database_access(name, intent, required, remove_ai):
    order_id = uuid4()
    context = RequestContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        request_id=uuid4(),
        permissions=frozenset(Permission) - {Permission.AI_RUN if remove_ai else required},
    )
    with pytest.raises(ApiProblem) as denied:
        ApplicationTools.execute(
            None,
            context,
            name=name,
            intent=intent,
            subject_id=order_id,
            search_term="Fixture",
            arguments={"term": "Fixture"} if intent == "SEARCH" else {"order_id": str(order_id)},
        )
    assert denied.value.code == "PERMISSION_DENIED"


@pytest.mark.integration
@pytest.mark.parametrize(
    "name,intent",
    [
        ("read_order", "TIMELINE"),
        ("order_timeline", "TIMELINE"),
        ("order_profit", "PROFIT"),
    ],
)
def test_order_tools_recheck_tenant_even_when_run_subject_matches(quotation_fixture, name, intent):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    order_id = UUID(order["id"])
    with f.session_factory.begin() as session:
        member = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_b
            )
        )
        member.role = "MANAGER"
        other_user = member.user_id
    before = {model: rows(f, model) for model in (SalesOrder, SalesOrderItem)}
    with f.session_factory() as session:
        context = live_context(
            session, organization_id=f.organization_b, user_id=other_user, request_id=uuid4()
        )
        with pytest.raises(ApiProblem) as denied:
            ApplicationTools.execute(
                session,
                context,
                name=name,
                intent=intent,
                subject_id=order_id,
                search_term=None,
                arguments={"order_id": str(order_id)},
            )
        assert denied.value.code == "SALES_ORDER_NOT_FOUND"
        assert denied.value.status == 404
    assert {model: rows(f, model) for model in before} == before


@pytest.mark.parametrize(
    "intent,name,arguments",
    [
        ("SEARCH", "search_companies", {"term": "Different scope"}),
        ("TIMELINE", "read_order", {"order_id": str(uuid4())}),
    ],
)
def test_matching_tool_cannot_expand_human_selected_scope(intent, name, arguments):
    context = RequestContext(uuid4(), uuid4(), frozenset(Permission), uuid4())
    with pytest.raises(ApiProblem) as denied:
        ApplicationTools.execute(
            None,
            context,
            name=name,
            intent=intent,
            subject_id=uuid4(),
            search_term="Original scope",
            arguments=arguments,
        )
    assert denied.value.code in {"AI_SCOPE_DENIED", "SALES_ORDER_NOT_FOUND"}
