from dataclasses import replace
from uuid import uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.work.overview import OverviewQueryService, QueueKind
from sqlalchemy import event
from test_finance_vertical_slice import allocation, payment, receivables
from test_order_procurement_vertical_slice import create_confirmed_order

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice", "test_shipment_documents_vertical_slice")


def test_overview_uses_live_unpaid_facts_and_isolates_all_queues(quotation_fixture):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    rows = receivables(f, order)
    deposit = next(row for row in rows if row["installment_type"] == "DEPOSIT")
    headers = f.headers("quotation-finance", f.organization_a)
    other = f.headers("quotation-other", f.organization_b)
    for queue in QueueKind:
        response = f.client.get(f"/api/v1/overview/{queue}", headers=headers)
        assert response.status_code == 200, response.text
        empty = f.client.get(f"/api/v1/overview/{queue}", headers=other)
        assert empty.status_code == 200, empty.text
        assert empty.json()["items"] == []
    due = f.client.get("/api/v1/overview/receivables", headers=headers).json()
    assert [item["id"] for item in due["items"]] == [deposit["id"]]
    assert due["items"][0]["overdue"] is True
    assert due["items"][0]["href"] == f"/orders/{order['id']}"
    allocation(f, payment(f, order, deposit["amount"]), deposit)
    assert f.client.get("/api/v1/overview/receivables", headers=headers).json()["items"] == []
    assert f.client.get("/api/v1/overview/deposits", headers=headers).json()["items"] == []
    preparation = f.client.get("/api/v1/overview/preparation", headers=headers).json()
    assert preparation["items"][0]["id"] == order["id"]


def test_overview_checks_domain_permission_and_has_bounded_queries(quotation_fixture):
    f = quotation_fixture
    create_confirmed_order(f)
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    statements = []

    def counted(*args):
        statements.append(args[2])

    with f.session_factory() as session:
        service = OverviewQueryService(session)
        restricted = replace(context, permissions=frozenset({Permission.OVERVIEW_READ}))
        with pytest.raises(ApiProblem) as denied:
            service.page(restricted, QueueKind.DEPOSITS, offset=0, limit=20)
        assert denied.value.status == 403
        engine = session.get_bind()
        event.listen(engine, "before_cursor_execute", counted)
        try:
            for queue in QueueKind:
                statements.clear()
                service.page(context, queue, offset=0, limit=20)
                assert len(statements) <= 3
        finally:
            event.remove(engine, "before_cursor_execute", counted)
