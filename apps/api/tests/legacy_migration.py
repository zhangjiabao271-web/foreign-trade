"""Exercise real previous schemas on isolated copies, never downgrade current evidence."""

from contextlib import contextmanager
from graphlib import TopologicalSorter

import pytest
from alembic import command
from conftest import disposable_database_url
from sqlalchemy import MetaData, create_engine, select
from test_migrations import alembic_config

# These nullable back-references close the Lead/Opportunity and Quotation/Version cycles.
# Insert their targets first, then restore the exact values, with all FK checks still enabled.
BACK_REFERENCES = {
    "leads": ("converted_opportunity_id",),
    "quotations": ("accepted_version_id",),
}


def ordered_inserts(table, rows):
    """Insert self-referencing facts after their parents without relaxing DB constraints."""
    constraints = [fk for fk in table.foreign_key_constraints if fk.referred_table is table]
    if not constraints:
        return rows
    keys = [column.key for column in table.primary_key.columns]
    indexed = {tuple(row[key] for key in keys): row for row in rows}
    graph = TopologicalSorter()
    for key in indexed:
        graph.add(key)
    for constraint in constraints:
        local = [element.parent.key for element in constraint.elements]
        remote = [element.column.key for element in constraint.elements]
        targets = {tuple(row[column] for column in remote): key for key, row in indexed.items()}
        for key, row in indexed.items():
            reference = tuple(row[column] for column in local)
            if any(value is None for value in reference):
                continue
            parent = targets[reference]
            if parent != key:
                graph.add(key, parent)
    return [indexed[key] for key in graph.static_order()]


def assert_snapshot(engine, metadata, expected):
    with engine.connect() as connection:
        for name, rows in expected.items():
            table = metadata.tables[name]
            actual = [
                dict(row)
                for row in connection.execute(
                    select(table).order_by(*table.primary_key.columns)
                ).mappings()
            ]
            assert actual == rows, f"Legacy facts changed in {name}"


@contextmanager
def legacy_snapshot(source, revision):
    with disposable_database_url() as database_url:
        config = alembic_config(database_url)
        command.upgrade(config, revision)
        target = create_engine(database_url)
        try:
            metadata = MetaData()
            metadata.reflect(target)
            metadata.remove(metadata.tables["alembic_version"])
            for name, columns in BACK_REFERENCES.items():
                if name in metadata.tables:
                    for constraint in metadata.tables[name].foreign_key_constraints:
                        if any(column in constraint.column_keys for column in columns):
                            constraint.use_alter = True
            expected = {}
            pending = []
            # Source stays read-only; destination was freshly allocated above. Only columns
            # belonging to the requested historical schema are part of the legacy fixture.
            with source.connect() as reader, target.begin() as writer:
                for table in metadata.sorted_tables:
                    rows = [
                        dict(row)
                        for row in reader.execute(
                            select(table).order_by(*table.primary_key.columns)
                        ).mappings()
                    ]
                    expected[table.name] = rows
                    if not rows:
                        continue
                    inserts = [dict(row) for row in rows]
                    for row in inserts:
                        restore = {}
                        for column in BACK_REFERENCES.get(table.name, ()):
                            if row.get(column) is not None:
                                restore[column] = row[column]
                                row[column] = None
                        if restore:
                            pending.append((table, row["id"], restore))
                    writer.execute(table.insert(), ordered_inserts(table, inserts))
                for table, record_id, restore in pending:
                    writer.execute(table.update().where(table.c.id == record_id).values(**restore))
            assert_snapshot(target, metadata, expected)
            yield config, target, metadata, expected
        finally:
            target.dispose()


def verify_legacy_upgrade(source, revision, *, check=None):
    with legacy_snapshot(source, revision) as (config, target, metadata, expected):
        command.upgrade(config, "head")
        command.check(config)
        assert_snapshot(target, metadata, expected)
        if check is not None:
            check(target)


def verify_legacy_guard(source, installed_revision, destination_revision, message):
    with legacy_snapshot(source, installed_revision) as (config, target, metadata, expected):
        with pytest.raises(RuntimeError, match=message):
            command.downgrade(config, destination_revision)
        assert_snapshot(target, metadata, expected)
