from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import permissions_for_role
from app.identity.enums import MembershipRole
from app.identity.models import OrganizationMembership
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.sales.models import Quotation, QuotationItem, QuotationVersion, SalesOrder, SalesOrderItem
from app.sales.order_repositories import SalesOrderRepository
from app.sales.order_services import SalesOrderQueryService
from app.sales.repositories import QuotationRepository
from app.sales.services import QuotationQueryService
from app.work.models import Activity
from sqlalchemy import event, select
from test_order_list_queries import create_orders

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration


def snapshots(f):
    with f.session_factory() as session:
        return tuple(
            list(session.execute(select(model.__table__).order_by(model.id)).mappings())
            for model in (
                Quotation,
                QuotationVersion,
                QuotationItem,
                SalesOrder,
                SalesOrderItem,
                Activity,
                AuditLog,
                OutboxEvent,
                IdempotencyKey,
            )
        )


def test_sales_queries_reject_foreign_ids_at_each_repository_and_service_path(quotation_fixture):
    f = quotation_fixture
    orders, _ = create_orders(f, 1)
    order = next(iter(orders.values()))
    order_id = UUID(order["id"])
    quotation_id = UUID(order["quotation_id"])
    item_ids = [UUID(item["id"]) for item in order["items"]]
    with f.session_factory.begin() as session:
        member = session.scalar(
            select(OrganizationMembership).where(
                OrganizationMembership.organization_id == f.organization_b
            )
        )
        member.role = MembershipRole.MANAGER
        foreign = RequestContext(
            user_id=member.user_id,
            organization_id=f.organization_b,
            permissions=permissions_for_role(MembershipRole.MANAGER),
            request_id=uuid4(),
        )
        version_id = session.scalar(
            select(QuotationVersion.id).where(QuotationVersion.quotation_id == quotation_id)
        )
    before = snapshots(f)
    with f.session_factory() as session:
        quotations = QuotationRepository(session)
        sales_orders = SalesOrderRepository(session)
        for repository, record_id in ((quotations, quotation_id), (sales_orders, order_id)):
            assert repository.get(organization_id=f.organization_b, record_id=record_id) is None
            assert repository.list(organization_id=f.organization_b) == []
            assert repository.count(organization_id=f.organization_b) == 0
            assert repository.get(organization_id=f.organization_a, record_id=record_id) is not None
        assert (
            quotations.get_for_update(organization_id=f.organization_b, quotation_id=quotation_id)
            is None
        )
        assert (
            quotations.current_version_for_update(
                organization_id=f.organization_b, quotation_id=quotation_id
            )
            is None
        )
        assert (
            quotations.versions(organization_id=f.organization_b, quotation_id=quotation_id) == []
        )
        assert quotations.items(organization_id=f.organization_b, version_id=version_id) == []
        assert (
            quotations.list_with_current(organization_id=f.organization_b, status=None, limit=10)
            == []
        )
        assert (
            sales_orders.get_by_quotation(
                organization_id=f.organization_b, quotation_id=quotation_id
            )
            is None
        )
        assert (
            sales_orders.get_for_update(organization_id=f.organization_b, sales_order_id=order_id)
            is None
        )
        assert sales_orders.list_recent(organization_id=f.organization_b, limit=10) == []
        assert sales_orders.items(organization_id=f.organization_b, sales_order_id=order_id) == []
        assert sales_orders.items_for_orders(
            organization_id=f.organization_b, sales_order_ids=[order_id]
        ) == {order_id: []}
        assert sales_orders.source_lines(organization_id=f.organization_b, item_ids=item_ids) == []
        assert (
            sales_orders.locked_items(
                organization_id=f.organization_b, sales_order_id=order_id, item_ids=set(item_ids)
            )
            == []
        )
        quote_queries = QuotationQueryService(quotations)
        order_queries = SalesOrderQueryService(sales_orders)
        assert quote_queries.list(foreign, status=None, limit=10) == []
        assert order_queries.list(foreign, limit=10) == []
        for invoke in (
            lambda: quote_queries.get(foreign, quotation_id),
            lambda: quote_queries.list(foreign, status=None, limit=10, cursor=quotation_id),
            lambda: order_queries.get(foreign, order_id),
            lambda: order_queries.list(foreign, limit=10, cursor=order_id),
            lambda: order_queries.source_lines(foreign, item_ids),
        ):
            with pytest.raises(ApiProblem) as denied:
                invoke()
            assert denied.value.status == 404

        # Permission rejection must precede any persistence access, including empty inputs.
        def prohibit_sql(*_args):
            pytest.fail("An unauthorized Sales query reached SQL")

        unauthorized = replace(foreign, permissions=frozenset())
        event.listen(f.engine, "before_cursor_execute", prohibit_sql)
        try:
            for invoke in (
                lambda: quote_queries.get(unauthorized, quotation_id),
                lambda: quote_queries.list(unauthorized, status=None, limit=10),
                lambda: order_queries.get(unauthorized, order_id),
                lambda: order_queries.list(unauthorized, limit=10),
                lambda: order_queries.source_lines(unauthorized, item_ids),
                lambda: order_queries.source_lines(unauthorized, []),
            ):
                with pytest.raises(ApiProblem) as denied:
                    invoke()
                assert denied.value.status == 403
        finally:
            event.remove(f.engine, "before_cursor_execute", prohibit_sql)

    headers = f.headers("quotation-other", f.organization_b)
    for path, record_id in (("quotations", quotation_id), ("sales-orders", order_id)):
        response = f.client.get(f"/api/v1/{path}", headers=headers)
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["count"] == 0
        assert f.client.get(f"/api/v1/{path}/{record_id}", headers=headers).status_code == 404
        assert (
            f.client.get(
                f"/api/v1/{path}", headers=headers, params={"cursor": str(record_id)}
            ).status_code
            == 404
        )
    assert snapshots(f) == before
