import os
from collections.abc import Iterator
from contextlib import contextmanager
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

DEFAULT_ADMIN_URL = (
    "postgresql+psycopg://trade_workbench:local-dev-only-change-me@localhost:5432/postgres"
)


def quote_database_name(database_name: str) -> str:
    if not database_name.replace("_", "").isalnum():
        raise ValueError("Generated test database name is not a safe identifier")
    return f'"{database_name}"'


@contextmanager
def disposable_database_url() -> Iterator[str]:
    admin_url = make_url(os.getenv("TEST_DATABASE_ADMIN_URL", DEFAULT_ADMIN_URL))

    database_name = f"trade_workbench_test_{uuid4().hex}"
    test_url = admin_url.set(database=database_name)
    admin_engine = create_engine(
        admin_url,
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
        connect_args={"connect_timeout": 5},
    )

    try:
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(f"CREATE DATABASE {quote_database_name(database_name)}")
    except OperationalError as error:
        admin_engine.dispose()
        pytest.fail(
            "A PostgreSQL test server is required. Start the Compose postgres service "
            "or set TEST_DATABASE_ADMIN_URL. "
            f"Connection failed: {error}"
        )

    try:
        yield test_url.render_as_string(hide_password=False)
    finally:
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(
                f"DROP DATABASE IF EXISTS {quote_database_name(database_name)} WITH (FORCE)"
            )
        admin_engine.dispose()


@pytest.fixture
def test_database_url() -> Iterator[str]:
    with disposable_database_url() as database_url:
        yield database_url
