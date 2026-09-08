from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from uuid import UUID

import pytest
from app.finance.models import Receivable
from app.finance.repositories import ReceivableRepository
from sqlalchemy import select, text
from test_finance_vertical_slice import counts, receivables
from test_order_procurement_vertical_slice import create_confirmed_order

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def test_order_receivable_locks_wait_for_first_uuid_without_holding_later_uuid(
    quotation_fixture,
):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    rows = receivables(f, order)
    ids = sorted(UUID(row["id"]) for row in rows)
    assert len(ids) == 2
    # Deliberately oppose number order and UUID order in this disposable fixture.
    with f.session_factory.begin() as session:
        session.get(Receivable, ids[0]).receivable_number = "LOCK-Z"
        session.get(Receivable, ids[1]).receivable_number = "LOCK-A"
    before = counts(f)
    started = Event()
    backend = []

    def lock_order_receivables():
        with f.session_factory.begin() as session:
            session.execute(text("SET LOCAL lock_timeout = '10s'"))
            backend.append(session.scalar(text("SELECT pg_backend_pid()")))
            started.set()
            return [
                row.id
                for row in ReceivableRepository(session).locked_for_order(
                    organization_id=f.organization_a, sales_order_id=UUID(order["id"])
                )
            ]

    with ThreadPoolExecutor(max_workers=1) as pool:
        with f.session_factory.begin() as holder:
            holder.scalar(
                select(Receivable)
                .where(Receivable.organization_id == f.organization_a, Receivable.id == ids[0])
                .with_for_update()
            )
            future = pool.submit(lock_order_receivables)
            assert started.wait(timeout=10)
            deadline = monotonic() + 5
            with f.engine.connect() as observer:
                while not observer.scalar(
                    text("SELECT cardinality(pg_blocking_pids(:pid)) > 0"), {"pid": backend[0]}
                ):
                    assert monotonic() < deadline, "Competing query never reached its row-lock wait"
                    sleep(0.02)
            # Models the UUID-first refresh/allocator owning its first row. The competing
            # order query must not already hold the later row and invert acquisition order.
            holder.scalar(
                select(Receivable)
                .where(Receivable.organization_id == f.organization_a, Receivable.id == ids[1])
                .with_for_update(nowait=True)
            )
        assert future.result(timeout=10) == [ids[1], ids[0]]
    assert counts(f) == before
