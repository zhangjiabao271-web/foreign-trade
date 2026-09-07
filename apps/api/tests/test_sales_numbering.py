from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from threading import Barrier
from uuid import uuid4

import pytest
from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.identity.models import OrganizationMembership
from app.platform.models import AuditLog, DocumentSequence, OutboxEvent
from app.platform.numbering import next_document_number
from app.sales.models import Quotation, QuotationItem, SalesOrder, SalesOrderItem
from app.sales.order_schemas import SalesOrderCreate
from app.sales.order_services import SalesOrderCommandService
from app.sales.schemas import QuotationCreate
from app.sales.services import QuotationCommandService
from app.work.models import Activity
from sqlalchemy import event, func, select
from test_quotation_vertical_slice import create_commercial_inputs, post_ok

pytest_plugins = ("test_quotation_vertical_slice",)
pytestmark = pytest.mark.integration


def prepare(f, kind, monkeypatch):
    import test_quotation_vertical_slice as fixtures

    original = fixtures.post_ok

    def unique_products(fixture, path, subject, body=None, expected_status=200):
        if path == "/api/v1/products":
            body = {**body, "sku": f"{body['sku']}-{uuid4().hex[:8]}"}
        return original(fixture, path, subject, body, expected_status)

    monkeypatch.setattr(fixtures, "post_ok", unique_products)
    bodies = []
    for _ in range(2):
        raw, _, _ = create_commercial_inputs(f)
        if kind == "QUOTATION":
            bodies.append(QuotationCreate.model_validate(raw).model_dump())
        else:
            quote = post_ok(f, "/api/v1/quotations", "quotation-manager", raw, 201)
            for action, subject in (
                ("submit", "quotation-sales"),
                ("approve", "quotation-manager"),
                ("send", "quotation-sales"),
                ("accept", "quotation-sales"),
            ):
                post_ok(f, f"/api/v1/quotations/{quote['id']}/{action}", subject)
            bodies.append(
                SalesOrderCreate.model_validate({"quotation_id": quote["id"]}).model_dump()
            )
    return bodies


def context(f):
    return RequestContext(
        user_id=f.sales_user,
        organization_id=f.organization_a,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )


def create(f, kind, body):
    if kind == "QUOTATION":
        record = QuotationCommandService(f.session_factory).create(context(f), deepcopy(body))
        return record.quotation_number
    record = SalesOrderCommandService(f.session_factory).create(context(f), deepcopy(body))
    return record.order_number


def state(f, kind):
    models = (Quotation, QuotationItem) if kind == "QUOTATION" else (SalesOrder, SalesOrderItem)
    with f.session_factory() as session:
        counts = tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (*models, Activity, AuditLog, OutboxEvent)
        )
        sequence = session.scalar(
            select(DocumentSequence.next_value).where(
                DocumentSequence.organization_id == f.organization_a,
                DocumentSequence.document_type == kind,
            )
        )
        return counts, sequence


@pytest.mark.parametrize("kind", ["QUOTATION", "SALES_ORDER"])
def test_concurrent_first_numbers_on_distinct_aggregates(quotation_fixture, monkeypatch, kind):
    f = quotation_fixture
    bodies = prepare(f, kind, monkeypatch)
    before, sequence = state(f, kind)
    assert sequence is None
    start = Barrier(2)
    legacy_reads = Barrier(2)

    def synchronize_legacy_read(_connection, _cursor, statement, *_args):
        sql = statement.lower()
        if sql.startswith("select") and "from document_sequences" in sql:
            # Force both legacy empty-row reads to finish before either insert.
            # Atomic upserts do not take this read path.
            legacy_reads.wait(timeout=10)

    def run(index):
        start.wait(timeout=10)
        return create(f, kind, bodies[index])

    event.listen(f.engine, "after_cursor_execute", synchronize_legacy_read)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            numbers = list(pool.map(run, (0, 1)))
    finally:
        event.remove(f.engine, "after_cursor_execute", synchronize_legacy_read)
    prefix = "Q" if kind == "QUOTATION" else "SO"
    year = datetime.now(UTC).year
    assert sorted(numbers) == [f"{prefix}-{year}-000001", f"{prefix}-{year}-000002"]
    after, sequence = state(f, kind)
    assert sequence == 3
    # Quotation creation also advances each opportunity and records its evidence.
    deltas = (2, 4, 4, 4, 4) if kind == "QUOTATION" else (2, 4, 2, 2, 2)
    assert after == tuple(value + delta for value, delta in zip(before, deltas, strict=True))


@pytest.mark.parametrize("kind", ["QUOTATION", "SALES_ORDER"])
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
def test_failed_command_rolls_back_first_or_existing_number(
    quotation_fixture, monkeypatch, kind, existing, table
):
    f = quotation_fixture
    bodies = prepare(f, kind, monkeypatch)
    if existing:
        assert create(f, kind, bodies[0]).endswith("000001")
    before = state(f, kind)

    def fail(_connection, _cursor, statement, *_args):
        if statement.lower().startswith(f"insert into {table} "):
            raise RuntimeError("injected numbered-command failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected numbered-command failure"):
            create(f, kind, bodies[1])
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert state(f, kind) == before
    assert create(f, kind, bodies[1]).endswith("000002" if existing else "000001")


def test_shared_numbering_partitions_by_organization_type_and_utc_year(
    quotation_fixture, monkeypatch
):
    import app.platform.numbering as numbering

    f = quotation_fixture

    class Clock:
        year = 2026

        @classmethod
        def now(cls, timezone):
            assert timezone == UTC
            return datetime(cls.year, 1, 1, tzinfo=UTC)

    monkeypatch.setattr(numbering, "datetime", Clock)
    a = context(f)
    with f.session_factory.begin() as session:
        other_user = session.scalar(
            select(OrganizationMembership.user_id).where(
                OrganizationMembership.organization_id == f.organization_b
            )
        )
        b = replace(a, organization_id=f.organization_b, user_id=other_user)
        assert next_document_number(session, a, "QUOTATION", "Q") == "Q-2026-000001"
        assert next_document_number(session, a, "SALES_ORDER", "SO") == "SO-2026-000001"
        assert next_document_number(session, b, "QUOTATION", "Q") == "Q-2026-000001"
        assert next_document_number(session, a, "QUOTATION", "Q") == "Q-2026-000002"
        Clock.year = 2027
        assert next_document_number(session, a, "QUOTATION", "Q") == "Q-2027-000001"
    with f.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(DocumentSequence)) == 4
