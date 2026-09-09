from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.finance.enums import ReceivableStatus
from app.finance.models import Payment, PaymentAllocation, Receivable
from app.finance.services import ReceivableCommandService
from app.platform.models import AuditLog, OutboxEvent
from app.sales.completion_services import OrderCompletionService
from app.work.models import Activity
from sqlalchemy import event, select
from test_finance_vertical_slice import allocation, counts, payment, receivables
from test_order_procurement_vertical_slice import create_confirmed_order
from test_quotation_vertical_slice import post_ok
from test_shipment_documents_vertical_slice import create_shipment, prepare_and_depart

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice", "test_shipment_documents_vertical_slice")


@pytest.mark.parametrize("waiver", [False, True])
def test_completion_and_due_refresh_preserve_money_and_single_completion(
    quotation_fixture, fake_storage, waiver
):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    rows = receivables(f, order)
    for row in rows:
        if not waiver or row["installment_type"] == "DEPOSIT":
            allocation(f, payment(f, order, row["amount"]), row)
    shipment = create_shipment(
        f,
        [
            {"sales_order_item_id": item["id"], "quantity": item["quantity"]}
            for item in order["items"]
        ],
    )
    prepare_and_depart(f, fake_storage, shipment)
    for command in ("start-transit", "arrive", "deliver"):
        post_ok(f, f"/api/v1/shipments/{shipment['id']}/{command}", "quotation-operations")
    headers = f.headers("quotation-manager", f.organization_a)
    for task in f.client.get(f"/api/v1/sales-orders/{order['id']}/tasks", headers=headers).json()[
        "items"
    ]:
        post_ok(
            f,
            f"/api/v1/sales-orders/{order['id']}/tasks/{task['id']}/complete",
            "quotation-operations",
            {"expected_version": task["version"], "resolution": "Fixture procurement checked"},
        )
    current = f.client.get(f"/api/v1/sales-orders/{order['id']}", headers=headers).json()
    request = {"expected_version": current["version"]}
    if waiver:
        request["financial_waiver_reason"] = "Synthetic authorized unpaid balance waiver"
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    # Model stale derived statuses only in this disposable database. Ledger facts stay real.
    with f.session_factory.begin() as session:
        installments = session.scalars(select(Receivable).order_by(Receivable.id)).all()
        assert len(installments) == 2
        for index, installment in enumerate(installments):
            installment.receivable_number = ("RACE-Z", "RACE-A")[index]
            installment.status = ReceivableStatus.DUE
            installment.due_date = date.today() - timedelta(days=2)

    def money_snapshot():
        with f.session_factory() as session:
            ledger = [
                session.execute(select(model.__table__).order_by(model.id)).all()
                for model in (Payment, PaymentAllocation)
            ]
            amounts = session.execute(
                select(Receivable.id, Receivable.amount, Receivable.currency_code).order_by(
                    Receivable.id
                )
            ).all()
            return ledger, amounts

    before_money = money_snapshot()
    rendezvous = Barrier(2)

    def synchronize_receivable_queries(connection, cursor, statement, parameters, context, many):
        if "FROM receivables" in statement and "FOR UPDATE" in statement:
            rendezvous.wait(timeout=10)

    def bound_lock_wait(connection):
        connection.exec_driver_sql("SET LOCAL lock_timeout = '10s'")

    event.listen(f.engine, "before_cursor_execute", synchronize_receivable_queries)
    event.listen(f.engine, "begin", bound_lock_wait)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            completion = pool.submit(
                OrderCompletionService(f.session_factory).complete,
                context,
                UUID(order["id"]),
                request,
            )
            refresh = pool.submit(
                ReceivableCommandService(f.session_factory).refresh_statuses, context
            )
            assert completion.result(timeout=20).status == "COMPLETED"
            refreshed = refresh.result(timeout=20)
            assert len(refreshed) == 2
    finally:
        event.remove(f.engine, "before_cursor_execute", synchronize_receivable_queries)
        event.remove(f.engine, "begin", bound_lock_wait)
    assert money_snapshot() == before_money
    assert {row.status for row, _ in refreshed} == (
        {ReceivableStatus.PAID, ReceivableStatus.OVERDUE} if waiver else {ReceivableStatus.PAID}
    )
    with f.session_factory() as session:
        for model, predicate in (
            (Activity, Activity.activity_type == "sales_order.completed"),
            (AuditLog, AuditLog.action == "sales_order.completed"),
            (OutboxEvent, OutboxEvent.event_type == "sales_order.completed.v1"),
        ):
            assert len(session.scalars(select(model).where(predicate)).all()) == 1
    after_counts = counts(f)
    assert (
        OrderCompletionService(f.session_factory)
        .complete(context, UUID(order["id"]), request)
        .status
        == "COMPLETED"
    )
    assert counts(f) == after_counts
    assert money_snapshot() == before_money
