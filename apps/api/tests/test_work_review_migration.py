from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from test_migrations import HEAD_REVISION, alembic_config, insert_identity_fixture

pytestmark = pytest.mark.integration


def test_legacy_work_text_is_preserved_and_defaults_confidential(test_database_url):
    config = alembic_config(test_database_url)
    command.upgrade(config, "20260906_0024")
    engine = create_engine(test_database_url)
    task_id, activity_id, order_id = uuid4(), uuid4(), uuid4()
    try:
        with engine.begin() as connection:
            organization, _, _, _ = insert_identity_fixture(connection)
            connection.execute(
                text(
                    "INSERT INTO tasks (id, organization_id, subject_type, subject_id, "
                    "task_type, title, details) VALUES (:id, :org, 'sales_order', :subject, "
                    "'LEGACY', 'Legacy cost 500', '{\"note\":\"profit 90\"}')"
                ),
                {"id": task_id, "org": organization, "subject": order_id},
            )
            connection.execute(
                text(
                    "INSERT INTO activities (id, organization_id, subject_type, subject_id, "
                    "activity_type, summary, details, correlation_id) "
                    "VALUES (:id, :org, 'sales_order', :subject, 'legacy.note', "
                    "'Legacy cost 500', '{\"note\":\"profit 90\"}', :correlation)"
                ),
                {
                    "id": activity_id,
                    "org": organization,
                    "subject": order_id,
                    "correlation": uuid4(),
                },
            )
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as connection:
            for table, field, record_id in (
                ("tasks", "title", task_id),
                ("activities", "summary", activity_id),
            ):
                row = connection.execute(
                    text(
                        f"SELECT {field}, details, released_digest, reviewed_by, reviewed_at "
                        f"FROM {table} WHERE id=:id"
                    ),
                    {"id": record_id},
                ).one()
                assert tuple(row) == ("Legacy cost 500", {"note": "profit 90"}, None, None, None)
        with pytest.raises(RuntimeError, match="Work evidence exists"):
            command.downgrade(config, "20260906_0024")
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD_REVISION
            )
    finally:
        engine.dispose()
