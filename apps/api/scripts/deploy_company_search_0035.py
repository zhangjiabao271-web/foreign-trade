"""One-time local source upgrade after the retained encrypted-copy rehearsal.

Caller must stop the verified acceptance API, worker and beat before invocation.
This script never recreates a database or modifies the retained restore.
"""

import json

from alembic import command
from alembic.config import Config
from app.core.config import Settings
from rehearse_company_search_0035 import INDEXES, SOURCE, TARGET, fingerprints
from sqlalchemy import create_engine, inspect, text


def main():
    settings = Settings()
    if (
        settings.database_name != SOURCE
        or settings.database_host != "trade-fresh-acceptance-postgres-1"
        or settings.database_user != "rehearsal"
    ):
        raise RuntimeError("Source configuration rejected")
    source = create_engine(settings.database_url)
    restored = create_engine(settings.model_copy(update={"database_name": TARGET}).database_url)
    try:
        with source.connect() as connection:
            if connection.scalar(text("SELECT current_database()")) != SOURCE:
                raise RuntimeError("Wrong source")
            if (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                != "20260908_0034"
            ):
                raise RuntimeError("Source revision rejected; refusing rerun")
            if connection.scalar(
                text("SELECT count(*) FROM ai_runs WHERE status IN ('PENDING', 'RUNNING')")
            ):
                raise RuntimeError("Active AI run; do not migrate")
        with restored.connect() as connection:
            if (
                connection.scalar(text("SELECT version_num FROM alembic_version"))
                != "20260908_0035"
            ):
                raise RuntimeError("Retained rehearsal revision rejected")
        before = fingerprints(source)
        if before != fingerprints(restored):
            raise RuntimeError("Source differs from verified backup copy; make a new backup first")
        config = Config("alembic.ini")
        config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))
        command.upgrade(config, "20260908_0035")
        command.check(config)
        after = fingerprints(source)
        if before != after:
            raise RuntimeError(
                "Business fingerprints changed; retain both databases for inspection"
            )
        if not {row["name"] for row in inspect(source).get_indexes("companies")} >= INDEXES:
            raise RuntimeError("Search indexes absent")
        with source.connect() as connection:
            extension = connection.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname='pg_trgm'")
            )
            if not extension:
                raise RuntimeError("Extension absent")
        print(
            json.dumps(
                {
                    "revision": "20260908_0035",
                    "preserved_tables": len(after),
                    "pg_trgm": extension,
                    "preserved": True,
                }
            )
        )
    finally:
        source.dispose()
        restored.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(json.dumps({"deployment": "failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None
