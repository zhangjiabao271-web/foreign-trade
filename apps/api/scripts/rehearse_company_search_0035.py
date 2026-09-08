"""One-time migration of the existing0035 rehearsal copy; never writes the source database."""

import hashlib
import json

from alembic import command
from alembic.config import Config
from app.core.config import Settings
from sqlalchemy import MetaData, create_engine, inspect, select, text

SOURCE = "trade_fresh_acceptance"
TARGET = "trade_migration_0035_acceptance"
INDEXES = {
    "ix_companies_name_trgm_active",
    "ix_companies_normalized_trgm_active",
    "ix_companies_name_fts_active",
}


def fingerprints(engine):
    with (
        engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection,
        connection.begin(),
    ):
        connection.execute(text("SET TRANSACTION READ ONLY"))
        metadata = MetaData()
        metadata.reflect(connection)
        tables = sorted(set(metadata.tables) - {"alembic_version"})
        if len(tables) != 45:
            raise RuntimeError("Unexpected business table inventory")
        result = {}
        for name in tables:
            table = metadata.tables[name]
            digest = hashlib.sha256()
            count = 0
            for row in connection.execute(
                select(table).order_by(*table.primary_key.columns)
            ).mappings():
                digest.update(json.dumps(dict(row), sort_keys=True, default=str).encode("utf-8"))
                digest.update(b"\n")
                count += 1
            result[name] = {"count": count, "sha256": digest.hexdigest()}
        return result


def main():
    settings = Settings()
    if (
        settings.database_name != TARGET
        or settings.database_host != "trade-fresh-acceptance-postgres-1"
        or settings.database_user != "rehearsal"
    ):
        raise RuntimeError("Rehearsal target configuration rejected")
    target = create_engine(settings.database_url)
    source = create_engine(settings.model_copy(update={"database_name": SOURCE}).database_url)
    try:
        with target.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != TARGET:
                raise RuntimeError("Wrong target database")
            if (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                != "20260908_0034"
            ):
                raise RuntimeError("Target is not the untouched0034 restore; refusing rerun")
        original = fingerprints(source)
        before = fingerprints(target)
        if original != before:
            raise RuntimeError("Source and restored fingerprints differ; inspect before upgrading")
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
        command.upgrade(config, "20260908_0035")
        command.check(config)
        after = fingerprints(target)
        if before != after:
            raise RuntimeError("Migration changed business fingerprints")
        actual_indexes = {row["name"] for row in inspect(target).get_indexes("companies")}
        if not actual_indexes >= INDEXES:
            raise RuntimeError("Required search indexes absent")
        with target.connect() as connection:
            extension = connection.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname='pg_trgm'")
            )
            if not extension:
                raise RuntimeError("Required extension absent")
        print(
            json.dumps(
                {
                    "target": TARGET,
                    "revision": "20260908_0035",
                    "pg_trgm": extension,
                    "tables": after,
                    "preserved": True,
                },
                sort_keys=True,
            )
        )
    finally:
        source.dispose()
        target.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Do not emit database diagnostics, URLs or business data on failure.
        print(json.dumps({"rehearsal": "failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None
