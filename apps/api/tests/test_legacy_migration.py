from graphlib import CycleError

import pytest
from legacy_migration import ordered_inserts
from sqlalchemy import Column, ForeignKeyConstraint, Integer, MetaData, Table, create_engine, select


def self_referencing_table():
    metadata = MetaData()
    return Table(
        "copy_facts",
        metadata,
        Column("organization_id", Integer, primary_key=True),
        Column("id", Integer, primary_key=True),
        Column("parent_id", Integer),
        ForeignKeyConstraint(
            ["organization_id", "parent_id"], ["copy_facts.organization_id", "copy_facts.id"]
        ),
    )


def test_self_reference_copy_orders_parents_first_without_mutating_facts():
    table = self_referencing_table()
    rows = [
        {"organization_id": 1, "id": 1, "parent_id": 9},
        {"organization_id": 2, "id": 1, "parent_id": None},
        {"organization_id": 1, "id": 9, "parent_id": 10},
        {"organization_id": 1, "id": 10, "parent_id": None},
    ]
    original = [dict(row) for row in rows]
    result = ordered_inserts(table, rows)
    assert rows == original
    positions = {(row["organization_id"], row["id"]): index for index, row in enumerate(result)}
    assert positions[(1, 10)] < positions[(1, 9)] < positions[(1, 1)]
    assert len(result) == len(rows)


def test_unresolvable_self_reference_fails_without_relaxing_constraints():
    table = self_referencing_table()
    with pytest.raises(CycleError):
        ordered_inserts(
            table,
            [
                {"organization_id": 1, "id": 1, "parent_id": 2},
                {"organization_id": 1, "id": 2, "parent_id": 1},
            ],
        )
    with pytest.raises(KeyError):
        ordered_inserts(table, [{"organization_id": 1, "id": 1, "parent_id": 2}])


@pytest.mark.integration
def test_legacy_copy_keeps_real_postgres_composite_foreign_keys_enabled(test_database_url):
    engine = create_engine(test_database_url)
    table = self_referencing_table()
    rows = [
        {"organization_id": 1, "id": 1, "parent_id": 9},
        {"organization_id": 1, "id": 9, "parent_id": None},
    ]
    try:
        table.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(table.insert(), ordered_inserts(table, rows))
        with engine.connect() as connection:
            assert list(connection.execute(select(table).order_by(table.c.id)).mappings()) == rows
    finally:
        engine.dispose()
