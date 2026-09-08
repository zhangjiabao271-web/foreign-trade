from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import DateTime, Float, Integer, Numeric, Uuid, create_engine, inspect, text
from sqlalchemy.exc import DBAPIError
from test_migrations import EXPECTED_TABLES, TENANT_TABLES, alembic_config, insert_identity_fixture

pytestmark = pytest.mark.integration


def test_postgres_common_record_fields_and_explicit_special_records(test_database_url):
    command.upgrade(alembic_config(test_database_url), "head")
    engine = create_engine(test_database_url)
    try:
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == EXPECTED_TABLES
        tables = EXPECTED_TABLES - {"alembic_version"}
        for table in sorted(tables):
            columns = {column["name"]: column for column in inspector.get_columns(table)}
            if table in TENANT_TABLES:
                assert isinstance(columns["organization_id"]["type"], Uuid), table
                assert columns["organization_id"]["nullable"] is False, table
            # The deduplication receipt is a connection record, not an editable aggregate.
            if table == "processed_events":
                assert set(columns) == {
                    "organization_id",
                    "event_id",
                    "consumer_name",
                    "processed_at",
                }
                assert inspector.get_pk_constraint(table)["constrained_columns"] == [
                    "organization_id",
                    "event_id",
                    "consumer_name",
                ]
                assert isinstance(columns["event_id"]["type"], Uuid)
                assert all(not column["nullable"] for column in columns.values())
                assert isinstance(columns["processed_at"]["type"], DateTime)
                assert columns["processed_at"]["type"].timezone is True
                assert columns["processed_at"]["default"] is not None
                continue

            assert inspector.get_pk_constraint(table)["constrained_columns"] == ["id"], table
            assert isinstance(columns["id"]["type"], Uuid), table
            assert columns["id"]["nullable"] is False, table
            assert columns["id"]["default"] == "gen_random_uuid()", table
            assert isinstance(columns["created_at"]["type"], DateTime), table
            assert columns["created_at"]["type"].timezone is True, table
            assert columns["created_at"]["nullable"] is False, table
            assert columns["created_at"]["default"] is not None, table

            # Audit has one actor/time; UPDATE and DELETE are separately tested as forbidden.
            if table == "audit_logs":
                assert not {"updated_at", "updated_by", "deleted_at", "version"} & columns.keys()
                assert isinstance(columns["actor_user_id"]["type"], Uuid)
                assert columns["actor_user_id"]["nullable"] is True
                continue

            for field in ("created_by", "updated_by"):
                assert isinstance(columns[field]["type"], Uuid), (table, field)
                assert columns[field]["nullable"] is True, (table, field)
            for field, nullable in (("updated_at", False), ("deleted_at", True)):
                assert isinstance(columns[field]["type"], DateTime), (table, field)
                assert columns[field]["type"].timezone is True, (table, field)
                assert columns[field]["nullable"] is nullable, (table, field)
            assert columns["updated_at"]["default"] is not None, table
            assert isinstance(columns["version"]["type"], Integer), table
            assert columns["version"]["nullable"] is False, table
            assert columns["version"]["default"] == "1", table
    finally:
        engine.dispose()


def test_postgres_declared_tenant_relationships_and_unique_keys_are_scoped(test_database_url):
    command.upgrade(alembic_config(test_database_url), "head")
    engine = create_engine(test_database_url)
    try:
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == EXPECTED_TABLES
        unconstrained_ids = set()
        for table in sorted(TENANT_TABLES):
            foreign_keys = inspector.get_foreign_keys(table)
            referenced_columns = {
                column for fk in foreign_keys for column in fk["constrained_columns"]
            }
            unconstrained_ids.update(
                (table, column["name"])
                for column in inspector.get_columns(table)
                if isinstance(column["type"], Uuid)
                and column["name"] != "id"
                and column["name"] not in referenced_columns
            )
            assert any(
                fk["constrained_columns"] == ["organization_id"]
                and fk["referred_table"] == "organizations"
                and fk["referred_columns"] == ["id"]
                for fk in foreign_keys
            ), table
            for fk in foreign_keys:
                if fk["referred_table"] in TENANT_TABLES:
                    pairs = list(
                        zip(fk["constrained_columns"], fk["referred_columns"], strict=True)
                    )
                    assert ("organization_id", "organization_id") in pairs, (table, fk["name"])
                assert fk["options"].get("ondelete") == "RESTRICT", (table, fk["name"])
            for unique in inspector.get_unique_constraints(table):
                assert "organization_id" in unique["column_names"], (table, unique["name"])
            for index in inspector.get_indexes(table):
                if index["unique"]:
                    assert "organization_id" in index["column_names"], (table, index["name"])

            # Identity bootstrap actors refer to global users; ordinary tenant actors must
            # reference membership in this same organization, not merely an existing user.
            if table == "organization_memberships" or table == "processed_events":
                continue
            actors = ("actor_user_id",) if table == "audit_logs" else ("created_by", "updated_by")
            for actor in actors:
                assert any(
                    fk["constrained_columns"] == ["organization_id", actor]
                    and fk["referred_table"] == "organization_memberships"
                    and fk["referred_columns"] == ["organization_id", "user_id"]
                    for fk in foreign_keys
                ), (table, actor)

        # These IDs are polymorphic owner references or correlation/lease identifiers, not
        # single-table foreign keys. Their application authorization needs separate tests.
        # An added unconstrained business reference must fail this inventory, not be skipped.
        assert unconstrained_ids == {
            ("ai_runs", "subject_id"),
            ("ai_runs", "lease_id"),
            ("document_links", "target_id"),
            ("audit_logs", "target_id"),
            ("audit_logs", "request_id"),
            ("audit_logs", "correlation_id"),
            ("outbox_events", "aggregate_id"),
            ("outbox_events", "correlation_id"),
            ("async_jobs", "correlation_id"),
            ("idempotency_keys", "resource_id"),
            ("activities", "subject_id"),
            ("activities", "correlation_id"),
            ("tasks", "subject_id"),
        }
        with engine.connect() as connection:
            # Reflected names alone cannot prove that PostgreSQL validated the keys.
            assert (
                connection.execute(
                    text("""
                SELECT count(*) FROM pg_constraint c
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE n.nspname = 'public' AND c.contype IN ('f', 'u', 'p')
                  AND NOT c.convalidated
            """)
                ).scalar_one()
                == 0
            )
            assert (
                connection.execute(
                    text("""
                SELECT count(*) FROM pg_trigger t
                JOIN pg_constraint c ON c.oid = t.tgconstraint
                JOIN pg_namespace n ON n.oid = c.connamespace
                WHERE n.nspname = 'public' AND c.contype = 'f'
                  AND t.tgenabled NOT IN ('O', 'A')
            """)
                ).scalar_one()
                == 0
            )
    finally:
        engine.dispose()


def test_postgres_numeric_columns_match_precision_baseline(test_database_url):
    command.upgrade(alembic_config(test_database_url), "head")
    engine = create_engine(test_database_url)
    try:
        inspector = inspect(engine)
        numeric_columns = set()
        for table in inspector.get_table_names():
            for column in inspector.get_columns(table):
                kind = column["type"]
                assert not isinstance(kind, Float), (table, column["name"])
                if not isinstance(kind, Numeric):
                    continue
                key = (table, column["name"])
                numeric_columns.add(key)
                expected = (18, 4)
                if column["name"] in {"exchange_rate", "cost_exchange_rate"}:
                    expected = (18, 8)
                elif key == ("ai_runs", "estimated_cost_usd"):
                    # Provider micro-cost estimate, not a commercial amount or cash fact.
                    expected = (18, 8)
                elif key == ("async_jobs", "progress"):
                    expected = (5, 2)
                assert (kind.precision, kind.scale) == expected, key
        assert {
            ("payments", "amount"),
            ("payment_allocations", "amount"),
            ("receivables", "amount"),
            ("sales_orders", "total"),
            ("sales_orders", "total_cost"),
            ("sales_order_items", "quantity"),
            ("purchase_order_items", "received_quantity"),
            ("expenses", "amount"),
            ("payables", "amount"),
            ("supplier_payments", "amount"),
            ("supplier_payment_allocations", "amount"),
            ("tax_refund_cases", "refunded_amount"),
        } <= numeric_columns
    finally:
        engine.dispose()


def test_postgres_rejects_audit_delete_and_keeps_original_evidence(test_database_url):
    command.upgrade(alembic_config(test_database_url), "head")
    engine = create_engine(test_database_url)
    audit_id = uuid4()
    try:
        with engine.begin() as connection:
            org, _, actor, _ = insert_identity_fixture(connection)
            connection.execute(
                text("""
                INSERT INTO audit_logs
                    (id, organization_id, actor_user_id, action, target_type,
                     request_id, correlation_id)
                VALUES (:id, :org, :actor, 'fixture.created', 'fixture', :request, :correlation)
            """),
                {
                    "id": audit_id,
                    "org": org,
                    "actor": actor,
                    "request": uuid4(),
                    "correlation": uuid4(),
                },
            )
        with pytest.raises(DBAPIError) as denied, engine.begin() as connection:
            connection.execute(
                text("DELETE FROM audit_logs WHERE organization_id=:org AND id=:id"),
                {"org": org, "id": audit_id},
            )
        assert denied.value.orig.sqlstate == "55000"
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT action FROM audit_logs WHERE organization_id=:org AND id=:id"),
                    {"org": org, "id": audit_id},
                ).scalar_one()
                == "fixture.created"
            )
    finally:
        engine.dispose()
