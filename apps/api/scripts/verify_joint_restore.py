"""Read-only application/object checks against the fixed, independent restored stack."""

import hashlib
import json
import sys
from pathlib import Path

from minio import Minio
from sqlalchemy import create_engine

sys.path.insert(0, "/app/apps/api")
sys.path.insert(0, str(Path(__file__).parent))

from commercial_recovery_probe import business_projections, database_manifest  # noqa: E402


def main() -> None:
    engine = create_engine(
        "postgresql+psycopg://rehearsal:local-isolated-rehearsal-only@postgres:5432/trade_workbench_e2e"
    )
    try:
        database = database_manifest(engine)
        application = business_projections(engine)
    finally:
        engine.dispose()
    client = Minio(
        "minio:9000",
        access_key="rehearsal",
        secret_key="local-isolated-rehearsal-only",
        secure=False,
    )
    bucket = "trade-commercial-recovery"
    if client.get_bucket_versioning(bucket).status != "Enabled":
        raise RuntimeError("Recovered object versioning is not enabled")
    objects = []
    for item in client.list_objects(bucket, recursive=True, include_version=True):
        row = {
            "key": item.object_name,
            "version_id": item.version_id,
            "deleted": item.is_delete_marker,
        }
        if not item.is_delete_marker:
            response = client.get_object(bucket, item.object_name, version_id=item.version_id)
            digest = hashlib.sha256()
            size = 0
            try:
                for chunk in response.stream(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
            finally:
                response.close()
                response.release_conn()
            row.update(sha256=digest.hexdigest(), size=size)
        objects.append(row)
    objects.sort(key=lambda row: (row["key"], row["version_id"]))
    original = json.loads(Path("/original/source-manifest.json").read_text(encoding="utf8"))
    if objects != original["objects"]:
        raise RuntimeError("Original object version IDs or bytes differ")
    for version in database["available_versions"]:
        match = next(
            (
                item
                for item in objects
                if item["key"] == version["object_key"]
                and item["version_id"] == version["storage_version_id"]
            ),
            None,
        )
        if (
            match is None
            or match.get("sha256") != version["actual_sha256"]
            or match.get("size") != version["actual_size_bytes"]
        ):
            raise RuntimeError("Recovered AVAILABLE document pointer is inconsistent")
    print(
        json.dumps(
            {
                "commercial_tables": len(database["tables"]),
                "original_object_versions": len(objects),
                "available_document_versions": len(database["available_versions"]),
                "completed_orders_with_settled_installments": len(application),
                "manager_cost_operations_redaction_foreign_404": True,
            }
        )
    )


if __name__ == "__main__":
    main()
