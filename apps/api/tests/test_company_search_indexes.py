import json
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from alembic import command
from app.auth.errors import ApiProblem
from app.companies.archive import CompanyArchiveQuery
from app.companies.assistant_queries import CompanyAssistantQueries
from app.companies.models import Company
from legacy_migration import assert_snapshot, legacy_snapshot
from sqlalchemy import event, inspect, text
from test_document_review import reviewer
from test_order_procurement_vertical_slice import create_confirmed_order

pytestmark = pytest.mark.integration
pytest_plugins = ("test_quotation_vertical_slice",)
INDEXES = {
    "ix_companies_name_trgm_active",
    "ix_companies_normalized_trgm_active",
    "ix_companies_name_fts_active",
}


def test_search_migration_preserves_populated_previous_schema_and_shared_extension(
    quotation_fixture,
):
    f = quotation_fixture
    create_confirmed_order(f)
    with legacy_snapshot(f.engine, "20260908_0034") as (config, target, metadata, expected):
        for _ in range(2):
            command.upgrade(config, "head")
            command.check(config)
            assert_snapshot(target, metadata, expected)
            indexes = {item["name"] for item in inspect(target).get_indexes("companies")}
            assert indexes >= INDEXES
            with target.connect() as connection:
                assert connection.scalar(
                    text("SELECT extversion FROM pg_extension WHERE extname='pg_trgm'")
                )
            command.downgrade(config, "20260908_0034")
            assert_snapshot(target, metadata, expected)
            assert not INDEXES & {item["name"] for item in inspect(target).get_indexes("companies")}
            with target.connect() as connection:
                assert connection.scalar(
                    text("SELECT extversion FROM pg_extension WHERE extname='pg_trgm'")
                )


def test_search_keeps_literal_fulltext_tenant_deleted_limit_and_permissions(quotation_fixture):
    f = quotation_fixture
    _, context = reviewer(f)
    names = ["Aurora Industrial Pump", "Literal %_ Vendor"] + [
        f"Bounded Vendor {i:02}" for i in range(12)
    ]
    with f.session_factory.begin() as session:
        session.add_all(
            Company(organization_id=f.organization_a, name=name, name_normalized=name.lower())
            for name in names
        )
        session.add(
            Company(
                organization_id=f.organization_b,
                name="Aurora Foreign",
                name_normalized="aurora foreign",
            )
        )
        session.add(
            Company(
                organization_id=f.organization_a,
                name="Aurora Archived",
                name_normalized="aurora archived",
                deleted_at=datetime.now(UTC),
            )
        )
    with f.session_factory() as session:
        query = CompanyAssistantQueries(session)
        assert [row["name"] for row in query.search(context, "pump aurora")["items"]] == [names[0]]
        assert [row["name"] for row in query.search(context, "%_")["items"]] == [names[1]]
        assert [row["name"] for row in query.search(context, "AURORA")["items"]] == [names[0]]
        bounded = query.search(context, "Bounded")
        assert len(bounded["items"]) == 10 and bounded["has_more"]
        foreign = query.search(replace(context, organization_id=f.organization_b), "Aurora")
        assert [row["name"] for row in foreign["items"]] == ["Aurora Foreign"]
    with pytest.raises(ApiProblem) as denied:
        CompanyAssistantQueries(None).search(replace(context, permissions=frozenset()), "Aurora")
    assert denied.value.status == 403


def test_actual_search_queries_choose_gin_indexes_on_selective_dataset(quotation_fixture):
    f = quotation_fixture
    _, context = reviewer(f)
    with f.session_factory.begin() as session:
        session.add_all(
            Company(
                organization_id=f.organization_a,
                name=f"Ordinary Vendor {i:05}",
                name_normalized=f"ordinary vendor {i:05}",
            )
            for i in range(6000)
        )
        session.add(
            Company(
                organization_id=f.organization_a,
                name="RareNeedle Industrial Pumps",
                name_normalized="rareneedle industrial pumps",
            )
        )
    # Bulk inserts leave GIN fast-update pending lists; measure after normal
    # maintenance, without forcing enable_seqscan or any planner preference.
    with f.engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text("VACUUM (ANALYZE) companies"))
    statements = []

    def capture(conn, cursor, statement, parameters, execution_context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append((statement, parameters))

    event.listen(f.engine, "before_cursor_execute", capture)
    try:
        with f.session_factory() as session:
            found = CompanyAssistantQueries(session).search(context, "rareneedle")
            assert len(found["items"]) == 1
            rows, _ = CompanyArchiveQuery(session).list(
                context, query="rareneedle", role=None, cursor=None, limit=20
            )
            assert len(rows) == 1
    finally:
        event.remove(f.engine, "before_cursor_execute", capture)
    plans = []
    with f.engine.connect() as connection:
        for sql, params in statements:
            if "FROM companies" in sql:
                plan = connection.exec_driver_sql(
                    "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) " + sql, params
                ).scalar_one()
                plans.append(json.dumps(plan))
    assert len(plans) == 2
    assert "ix_companies_name_trgm_active" in plans[0], (statements[0], plans[0])
    assert "ix_companies_name_fts_active" in plans[0]
    assert "ix_companies_normalized_trgm_active" in plans[1]
