from uuid import UUID

import pytest
from app.platform.models import AuditLog, IdempotencyKey, OutboxEvent
from app.sales.contract_models import SalesContract
from app.work.models import Activity
from sqlalchemy import event, func, select
from test_order_procurement_vertical_slice import create_confirmed_order
from test_sales_contracts import create, request

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)


def snapshot(f):
    with f.session_factory() as session:
        contracts = [
            dict(row)
            for row in session.execute(
                select(SalesContract.__table__).order_by(SalesContract.id)
            ).mappings()
        ]
        evidence = tuple(
            session.scalar(select(func.count()).select_from(model))
            for model in (Activity, AuditLog, OutboxEvent, IdempotencyKey)
        )
        return contracts, evidence


@pytest.mark.parametrize("action", ["update", "void"])
@pytest.mark.parametrize("table", ["activities", "audit_logs", "outbox_events"])
def test_draft_changes_roll_back_case_and_durable_key_at_each_evidence_failure(
    quotation_fixture, action, table
):
    f = quotation_fixture
    order, _, _ = create_confirmed_order(f)
    contract = create(f, order)
    before = snapshot(f)
    suffix = f"/{contract['id']}"
    method = "put"
    body = {"expected_version": contract["version"], "reason": "Synthetic draft correction"}
    if action == "void":
        method = "post"
        suffix += "/void"
    else:
        body.update(external_reference="REVISED-REF", notes="Revised synthetic notes")

    def fail(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith(f"INSERT INTO {table}"):
            raise RuntimeError("Injected draft evidence failure")

    event.listen(f.engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="Injected draft evidence failure"):
            request(f, order, method, suffix, body, key="draft-retry")
    finally:
        event.remove(f.engine, "before_cursor_execute", fail)
    assert snapshot(f) == before

    result = request(f, order, method, suffix, body, key="draft-retry")
    after, counts = snapshot(f)
    assert counts == tuple(count + 1 for count in before[1])
    assert after[0]["id"] == UUID(contract["id"])
    assert after[0]["commercial_snapshot"] == before[0][0]["commercial_snapshot"]
    assert result["status"] == ("VOIDED" if action == "void" else "DRAFT")
    assert result["version"] == contract["version"] + 1
    if action == "update":
        assert result["external_reference"] == after[0]["external_reference"] == "REVISED-REF"
        assert result["notes"] == after[0]["notes"] == "Revised synthetic notes"
    assert request(f, order, method, suffix, body, key="draft-retry") == result
    assert snapshot(f) == (after, counts)
