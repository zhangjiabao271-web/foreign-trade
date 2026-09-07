"""Synthetic document/version fixture and exact DB/object recovery verification."""

import argparse
import json
import os
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from app import models as application_models
from app.core.config import get_settings
from app.core.database import Base
from app.documents.models import Document, DocumentVersion
from app.identity.models import Organization
from minio import Minio
from minio.versioningconfig import ENABLED, VersioningConfig
from sqlalchemy import select
from worker.outbox import worker_session_factory

_ = application_models
BUCKET = "storage-recovery-evidence"
MANIFEST = Path("/tmp/storage-recovery-manifest.json")


def table_fingerprints(factory):
    result = {}
    with factory() as session:
        for name, table in sorted(Base.metadata.tables.items()):
            rows = [
                dict(row)
                for row in session.execute(
                    select(table).order_by(*table.primary_key.columns)
                ).mappings()
            ]
            result[name] = {
                "count": len(rows),
                "sha256": sha256(
                    json.dumps(rows, default=str, sort_keys=True).encode()
                ).hexdigest(),
            }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "verify"])
    args = parser.parse_args()
    settings = get_settings()
    if (
        os.getenv("ACCEPTANCE_REHEARSAL") != "true"
        or settings.app_env != "acceptance"
        or settings.database_name != "trade_recovery_acceptance"
    ):
        raise RuntimeError("Refusing non-acceptance database")
    expected_host = "postgres" if args.action == "prepare" else "postgres-restored"
    if settings.database_host != expected_host:
        raise RuntimeError("Wrong recovery database host")
    storage_host = "minio-source" if args.action == "prepare" else "minio-restored"
    client = Minio(
        f"{storage_host}:9000",
        access_key="rehearsal",
        secret_key="local-isolated-rehearsal-only",
        secure=False,
    )
    factory = worker_session_factory()
    if args.action == "prepare":
        if client.bucket_exists(BUCKET) or MANIFEST.exists():
            raise RuntimeError("Refusing to overwrite existing recovery evidence")
        client.make_bucket(BUCKET)
        client.set_bucket_versioning(BUCKET, VersioningConfig(ENABLED))
        with factory() as session:
            organization = session.scalar(
                select(Organization).where(
                    Organization.name_normalized == "recovery-fixture",
                )
            )
            if organization is None:
                raise RuntimeError("Run queue-recovery fixture preparation first")
            organization_id = organization.id
        document_id = uuid4()
        key = f"{organization_id}/{uuid4()}"
        versions = []
        # Same key deliberately exercises immutable storage pointers after overwrite.
        for number, content in enumerate(
            [b"Original invoice evidence", b"Revised invoice evidence"], 1
        ):
            uploaded = client.put_object(
                BUCKET, key, BytesIO(content), len(content), content_type="text/plain"
            )
            versions.append(
                DocumentVersion(
                    organization_id=organization_id,
                    document_id=document_id,
                    version_number=number,
                    status="AVAILABLE",
                    object_key=key,
                    storage_version_id=uploaded.version_id,
                    file_name="invoice.txt",
                    mime_type="text/plain",
                    expected_size_bytes=len(content),
                    actual_size_bytes=len(content),
                    expected_sha256=sha256(content).hexdigest(),
                    actual_sha256=sha256(content).hexdigest(),
                )
            )
        with factory.begin() as session:
            session.add(
                Document(
                    id=document_id,
                    organization_id=organization_id,
                    title="Restore fixture",
                    document_type="COMMERCIAL_INVOICE",
                    latest_version_number=2,
                )
            )
            session.flush()
            session.add_all(versions)
        client.put_object(
            BUCKET, key, BytesIO(b"Unaccepted overwrite"), 20, content_type="text/plain"
        )
        manifest = {"tables": table_fingerprints(factory), "stored_versions": 3}
        MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print("Prepared two pinned document versions and an unaccepted storage overwrite")
        return
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert table_fingerprints(factory) == manifest["tables"], "Restored database differs"
    assert client.get_bucket_versioning(BUCKET).status == ENABLED
    assert len(list(client.list_objects(BUCKET, recursive=True, include_version=True))) == 3
    with factory() as session:
        versions = list(session.scalars(select(DocumentVersion)))
        assert len(versions) == 2
        for version in versions:
            response = client.get_object(
                BUCKET, version.object_key, version_id=version.storage_version_id
            )
            try:
                content = response.read()
            finally:
                response.close()
                response.release_conn()
            assert len(content) == version.actual_size_bytes
            assert sha256(content).hexdigest() == version.actual_sha256
    print(
        json.dumps(
            {
                "verified_tables": len(manifest["tables"]),
                "pinned_document_versions": 2,
                "storage_versions": 3,
                "checksums_and_original_storage_version_ids": "preserved",
            }
        )
    )


if __name__ == "__main__":
    main()
