from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.finance.models import Payment, PaymentAllocation, Receivable
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.platform.records import AuditRecorder, OutboxRecorder
from app.sales.models import SalesOrder, SalesOrderItem
from app.sales.settlement import OrderSettlementPort
from app.work.models import Activity
from sqlalchemy import select
from test_order_procurement_vertical_slice import create_confirmed_order

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def snapshot(f):
    with f.session_factory() as session:
        return {
            model.__tablename__: [
                dict(row)
                for row in session.execute(select(model.__table__).order_by(model.id)).mappings()
            ]
            for model in (
                SalesOrder,
                SalesOrderItem,
                Payment,
                PaymentAllocation,
                Receivable,
                Activity,
                AuditLog,
                OutboxEvent,
                IdempotencyKey,
            )
        }


@pytest.mark.parametrize("reverse", [False, True])
def test_settlement_port_requires_originating_permission_before_any_write(
    quotation_fixture, reverse
):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    required = Permission.PAYMENT_REVERSE if reverse else Permission.PAYMENT_ALLOCATE
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission) - {required},
        request_id=uuid4(),
    )
    before = snapshot(f)
    with f.session_factory.begin() as session:
        row = session.scalar(
            select(SalesOrder)
            .where(
                SalesOrder.organization_id == f.organization_a,
                SalesOrder.id == UUID(order["id"]),
            )
            .with_for_update()
        )
        with pytest.raises(ApiProblem) as error:
            OrderSettlementPort(AuditRecorder(), OutboxRecorder()).record_allocation(
                session,
                context,
                row,
                deposit=True,
                settled=not reverse,
                reversed=reverse,
                payment_id=str(uuid4()),
                amount="1.0000",
            )
        assert error.value.status == 403
        assert error.value.code == "PERMISSION_DENIED"
        assert not session.new and not session.dirty
    assert snapshot(f) == before


@pytest.mark.parametrize("reverse", [False, True])
def test_settlement_port_tenant_and_caller_rollback_preserve_all_facts(quotation_fixture, reverse):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    order_id = UUID(order["id"])
    if reverse:
        with f.session_factory.begin() as session:
            session.get(SalesOrder, order_id).status = "EXECUTING"
    required = Permission.PAYMENT_REVERSE if reverse else Permission.PAYMENT_ALLOCATE
    context = RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset({required}),
        request_id=uuid4(),
    )
    port = OrderSettlementPort(AuditRecorder(), OutboxRecorder())
    evidence = {
        "deposit": True,
        "settled": not reverse,
        "reversed": reverse,
        "payment_id": str(uuid4()),
        "amount": "1.0000",
    }
    before = snapshot(f)
    with f.session_factory.begin() as session:
        row = session.get(SalesOrder, order_id, with_for_update=True)
        with pytest.raises(ApiProblem) as error:
            port.record_allocation(
                session, replace(context, organization_id=f.organization_b), row, **evidence
            )
        assert error.value.status == 404
        assert not session.new and not session.dirty
    assert snapshot(f) == before
    with pytest.raises(RuntimeError, match="caller rollback"), f.session_factory.begin() as session:
        row = session.get(SalesOrder, order_id, with_for_update=True)
        port.record_allocation(session, context, row, **evidence)
        session.flush()
        assert row.status == ("DEPOSIT_PENDING" if reverse else "EXECUTING")
        raise RuntimeError("caller rollback")
    assert snapshot(f) == before
