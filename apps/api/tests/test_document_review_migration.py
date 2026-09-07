from uuid import uuid4

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from test_migrations import HEAD_REVISION, alembic_config, insert_identity_fixture

pytestmark = pytest.mark.integration


def test_previous_document_remains_confidential_and_cannot_be_downgraded(test_database_url):
    config = alembic_config(test_database_url)
    command.upgrade(config, "20260906_0023")
    engine = create_engine(test_database_url)
    document_id, version_id = uuid4(), uuid4()
    try:
        with engine.begin() as connection:
            organization, _, _, _ = insert_identity_fixture(connection)
            connection.execute(
                text(
                    "INSERT INTO documents (id, organization_id, title, document_type) "
                    "VALUES (:id, :org, 'Historical cost evidence', 'OTHER')"
                ),
                {"id": document_id, "org": organization},
            )
            connection.execute(
                text(
                    "INSERT INTO document_versions (id, organization_id, document_id, "
                    "version_number, object_key, file_name, mime_type, expected_size_bytes, "
                    "expected_sha256) VALUES (:id, :org, :doc, 1, 'old-key', 'old-file.txt', "
                    "'text/plain', 10, :sha)"
                ),
                {"id": version_id, "org": organization, "doc": document_id, "sha": "a" * 64},
            )
        command.upgrade(config, "head")
        command.check(config)
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT file_name, expected_sha256, released_digest, reviewed_by, reviewed_at "
                    "FROM document_versions WHERE id=:id"
                ),
                {"id": version_id},
            ).one()
            assert tuple(row) == ("old-file.txt", "a" * 64, None, None, None)
        with pytest.raises(RuntimeError, match="Document evidence exists"):
            command.downgrade(config, "20260906_0023")
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version")) == HEAD_REVISION
            )
            assert (
                connection.scalar(
                    text("SELECT title FROM documents WHERE id=:id"), {"id": document_id}
                )
                == "Historical cost evidence"
            )
    finally:
        engine.dispose()
