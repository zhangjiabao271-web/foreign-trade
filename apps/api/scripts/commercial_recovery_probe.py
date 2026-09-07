"""Read/verify the dedicated synthetic commercial recovery fixture, never a main database."""

import argparse
import copy
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from alembic import command
from alembic.config import Config
from minio import Minio
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.engine import Connection, Engine

API_ROOT = Path(__file__).resolve().parents[1]
ROOT = API_ROOT.parents[1]
sys.path.insert(0, str(API_ROOT))

from app.auth.context import RequestContext  # noqa: E402
from app.auth.errors import ApiProblem  # noqa: E402
from app.auth.permissions import permissions_for_role  # noqa: E402
from app.core.database import create_session_factory  # noqa: E402
from app.finance.repositories import ReceivableRepository  # noqa: E402
from app.finance.services import ReceivableQueryService  # noqa: E402
from app.identity.enums import MembershipRole  # noqa: E402
from app.identity.models import Organization, OrganizationMembership, User  # noqa: E402
from app.sales.order_repositories import SalesOrderRepository  # noqa: E402
from app.sales.order_services import SalesOrderQueryService  # noqa: E402

BACKUP = ROOT / "backups/20260907-commercial-recovery"
BUCKET = "trade-commercial-recovery"
PASSWORD = "local-isolated-rehearsal-only"


def database_url(target: str) -> str:
    if target not in {"source", "restored"}:
        raise ValueError("Unknown recovery target")
    port = 25432 if target == "source" else 25433
    return f"postgresql+psycopg://rehearsal:{PASSWORD}@127.0.0.1:{port}/trade_workbench_e2e"


def require_quiet(connection: Connection) -> None:
    other = connection.exec_driver_sql(
        "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() "
        "AND pid <> pg_backend_pid() AND backend_type = 'client backend'"
    ).scalar_one()
    if other:
        raise RuntimeError("Stop every browser/API fixture writer before taking recovery evidence")


def prepare_isolation() -> None:
    engine = create_engine(database_url("source"))
    factory = create_session_factory(engine)
    with factory.begin() as session:
        require_quiet(session.connection())
        if session.scalar(select(User).where(User.external_subject == "recovery-witness")):
            raise RuntimeError("Recovery witness already exists; refusing repeated fixture writes")
        source = session.scalar(select(User).where(User.external_subject == "playwright-manager"))
        if source is None:
            raise RuntimeError("Expected retained browser fixture is absent")
        organization = Organization(
            name="Recovery isolation witness", name_normalized="recovery isolation witness"
        )
        user = User(external_subject="recovery-witness", display_name="Synthetic recovery witness")
        session.add_all([organization, user])
        session.flush()
        session.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role=MembershipRole.MANAGER,
                status="ACTIVE",
            )
        )
    engine.dispose()


def database_manifest(engine: Engine) -> dict[str, Any]:
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        connection.exec_driver_sql("SET LOCAL TIME ZONE 'UTC'")
        require_quiet(connection)
        tables: dict[str, Any] = {}
        for name in sorted(inspect(connection).get_table_names(schema="public")):
            quoted = connection.dialect.identifier_preparer.quote(name)
            digest = hashlib.sha256()
            count = 0
            for row in connection.exec_driver_sql(
                f"SELECT to_jsonb(t)::text FROM public.{quoted} t ORDER BY to_jsonb(t)::text"
            ):
                digest.update(row[0].encode("utf8") + b"\n")
                count += 1
            tables[name] = {"rows": count, "sha256": digest.hexdigest()}
        definitions = {
            "constraints": connection.exec_driver_sql(
                "SELECT conrelid::regclass::text, conname, contype, convalidated, "
                "pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE connamespace = 'public'::regnamespace ORDER BY 1,2"
            ).all(),
            "indexes": connection.exec_driver_sql(
                "SELECT tablename,indexname,indexdef FROM pg_indexes "
                "WHERE schemaname='public' ORDER BY 1,2"
            ).all(),
            "triggers": connection.exec_driver_sql(
                "SELECT tgrelid::regclass::text,tgname,pg_get_triggerdef(oid) FROM pg_trigger "
                "WHERE NOT tgisinternal AND tgrelid IN (SELECT oid FROM pg_class "
                "WHERE relnamespace='public'::regnamespace) ORDER BY 1,2"
            ).all(),
        }
        schema = {key: [list(row) for row in rows] for key, rows in definitions.items()}
        if any(not row[3] for row in schema["constraints"]):
            raise RuntimeError("Unvalidated database constraints")
        required = {
            "converted_leads": "SELECT count(*) FROM leads WHERE status='CONVERTED'",
            "won_opportunities": "SELECT count(*) FROM opportunities WHERE status='WON'",
            "accepted_versions": "SELECT count(*) FROM quotation_versions WHERE status='ACCEPTED'",
            "superseded_versions": (
                "SELECT count(*) FROM quotation_versions WHERE status='SUPERSEDED'"
            ),
            "completed_orders": "SELECT count(*) FROM sales_orders WHERE status='COMPLETED'",
            "delivered_shipments": "SELECT count(*) FROM shipments WHERE status='DELIVERED'",
            "cleared_customs": "SELECT count(*) FROM customs_declarations WHERE status='CLEARED'",
            "received_refunds": (
                "SELECT count(*) FROM tax_refund_cases "
                "WHERE status='REFUNDED' AND refunded_amount>0"
            ),
        }
        coverage = {
            name: connection.exec_driver_sql(sql).scalar_one() for name, sql in required.items()
        }
        if not all(coverage.values()):
            raise RuntimeError(f"Incomplete commercial chain: {coverage}")
        for table, minimum in {
            "organizations": 2,
            "payments": 2,
            "payment_allocations": 2,
            "purchase_orders": 1,
            "activities": 1,
            "audit_logs": 1,
            "outbox_events": 1,
            "documents": 2,
            "document_versions": 3,
        }.items():
            if tables[table]["rows"] < minimum:
                raise RuntimeError(f"Missing recovery evidence: {table}")
        versions = [
            dict(row)
            for row in connection.exec_driver_sql(
                "SELECT id::text, object_key, storage_version_id, actual_sha256, actual_size_bytes "
                "FROM document_versions WHERE status='AVAILABLE' ORDER BY id"
            ).mappings()
        ]
        return {
            "tables": tables,
            "schema": schema,
            "coverage": coverage,
            "available_versions": versions,
        }


def object_manifest(target: str) -> list[dict[str, Any]]:
    port = 29000 if target == "source" else 29001
    client = Minio(f"127.0.0.1:{port}", access_key="rehearsal", secret_key=PASSWORD, secure=False)
    if client.get_bucket_versioning(BUCKET).status != "Enabled":
        raise RuntimeError("Object versioning was not restored")
    results: list[dict[str, Any]] = []
    for item in client.list_objects(BUCKET, recursive=True, include_version=True):
        if not item.version_id or item.version_id == "null":
            raise RuntimeError("Unversioned recovery object")
        row: dict[str, Any] = {
            "key": item.object_name,
            "version_id": item.version_id,
            "deleted": item.is_delete_marker,
        }
        if not item.is_delete_marker:
            response = client.get_object(BUCKET, item.object_name, version_id=item.version_id)
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
        results.append(row)
    return sorted(results, key=lambda row: (row["key"], row["version_id"]))


def business_projections(engine: Engine) -> dict[str, Any]:
    factory = create_session_factory(engine)
    with factory() as session:
        members = session.execute(
            select(User, OrganizationMembership)
            .join(OrganizationMembership, OrganizationMembership.user_id == User.id)
            .where(
                User.external_subject.in_(
                    ["playwright-manager", "playwright-operations", "recovery-witness"]
                )
            )
        ).all()
        contexts = {
            user.external_subject: RequestContext(
                user_id=user.id,
                organization_id=member.organization_id,
                permissions=permissions_for_role(MembershipRole(member.role)),
                request_id=uuid4(),
            )
            for user, member in members
        }
        high, low, other = (
            contexts[name]
            for name in ["playwright-manager", "playwright-operations", "recovery-witness"]
        )
        service = SalesOrderQueryService(SalesOrderRepository(session))
        orders = service.list(high, limit=100)
        completed = [order for order in orders if order.status == "COMPLETED"]
        if not completed:
            raise RuntimeError("Application cannot read a completed order after recovery")
        result = {}
        for order in completed:
            protected = service.get(low, order.id)
            if order.total_cost is None or protected.total_cost is not None:
                raise RuntimeError("Restored role cost policy differs from expected authority")
            try:
                service.get(other, order.id)
            except ApiProblem as error:
                if error.status != 404:
                    raise
            else:
                raise RuntimeError("Restored organization isolation failed")
            receivables = ReceivableQueryService(ReceivableRepository(session)).list(
                high, sales_order_id=order.id, limit=100
            )
            if len(receivables) < 2 or any(
                record.amount != allocated for record, allocated in receivables
            ):
                raise RuntimeError("Recovered deposit/balance are not settled")
            result[str(order.id)] = {
                "manager": order.model_dump(mode="json"),
                "operations": protected.model_dump(mode="json"),
                "receivables": sorted(
                    [str(row.id), str(row.amount), str(allocated)] for row, allocated in receivables
                ),
            }
        return result


def collect(target: str) -> dict[str, Any]:
    engine = create_engine(database_url(target))
    try:
        database = database_manifest(engine)
        objects = object_manifest(target)
        lookup = {(row["key"], row["version_id"]): row for row in objects}
        for version in database["available_versions"]:
            stored = lookup.get((version["object_key"], version["storage_version_id"]))
            if (
                not stored
                or stored["deleted"]
                or stored["sha256"] != version["actual_sha256"]
                or stored["size"] != version["actual_size_bytes"]
            ):
                raise RuntimeError("Immutable document pointer/checksum was not preserved")
        return {
            "database": database,
            "objects": objects,
            "application": business_projections(engine),
        }
    finally:
        engine.dispose()


def difference_paths(expected: Any, actual: Any, path: str = "root") -> list[str]:
    if isinstance(expected, dict) and isinstance(actual, dict):
        differences = []
        for key in sorted(expected.keys() | actual.keys()):
            child = f"{path}.{key}"
            if key not in expected or key not in actual:
                differences.append(child)
            else:
                differences.extend(difference_paths(expected[key], actual[key], child))
        return differences
    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            return [f"{path}.length"]
        return [
            difference
            for index, (left, right) in enumerate(zip(expected, actual, strict=True))
            for difference in difference_paths(left, right, f"{path}[{index}]")
        ]
    return [] if expected == actual else [path]


def canonical_check(connection: Connection, table: str, definition: str) -> str:
    """Reparse generated CHECK DDL against the exact column types in a rollback-only temp table."""
    if not definition.startswith("CHECK (") or ";" in definition or "--" in definition:
        raise ValueError("Expected one generated CHECK definition")
    quote = connection.dialect.identifier_preparer.quote
    temporary = f"recovery_check_{uuid4().hex}"
    connection.exec_driver_sql(
        f"CREATE TEMP TABLE {quote(temporary)} (LIKE public.{quote(table)}) ON COMMIT DROP"
    )
    connection.exec_driver_sql(
        f"ALTER TABLE pg_temp.{quote(temporary)} ADD CONSTRAINT normalized {definition}"
    )
    result = connection.exec_driver_sql(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = %s::regclass AND conname = 'normalized'",
        (f"pg_temp.{temporary}",),
    ).scalar_one()
    if not isinstance(result, str):
        raise RuntimeError("PostgreSQL returned no normalized CHECK definition")
    return result


def compare_manifests(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    left, right = copy.deepcopy(expected), copy.deepcopy(actual)
    before = left["database"]["schema"]["constraints"]
    after = right["database"]["schema"]["constraints"]
    equivalent = []
    engine = create_engine(database_url("restored"))
    try:
        # This connection rolls back every temporary DDL statement; persisted schema is untouched.
        with engine.connect() as connection:
            if len(before) == len(after):
                for source, restored in zip(before, after, strict=True):
                    if source[:4] == restored[:4] and source[2] == "c" and source[4] != restored[4]:
                        original = canonical_check(connection, source[0], source[4])
                        recovered = canonical_check(connection, restored[0], restored[4])
                        if original == recovered:
                            equivalent.append(f"{source[0]}.{source[1]}")
                            source[4] = restored[4] = original
    finally:
        engine.dispose()
    if left != right:
        raise RuntimeError(f"Restore differs at: {difference_paths(left, right)[:40]}")
    return equivalent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare-isolation", "snapshot", "verify"])
    action = parser.parse_args().action
    if action == "prepare-isolation":
        prepare_isolation()
        print("Synthetic second-organization witness prepared")
        return
    if action == "snapshot":
        if BACKUP.exists():
            raise RuntimeError("Backup directory already exists; refusing overwrite")
        result = collect("source")
        BACKUP.mkdir(parents=True)
        (BACKUP / "source-manifest.json").write_text(json.dumps(result, indent=2), encoding="utf8")
        print(
            f"Source manifest recorded: {len(result['database']['tables'])} tables, "
            f"{len(result['objects'])} object versions"
        )
        return
    expected = json.loads((BACKUP / "source-manifest.json").read_text(encoding="utf8"))
    actual = collect("restored")
    equivalent = compare_manifests(expected, actual)
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url("restored"))
    command.check(config)
    report = {
        "verified_at": datetime.now(UTC).isoformat(),
        "result": "passed",
        "tables": len(actual["database"]["tables"]),
        "object_versions": len(actual["objects"]),
        "coverage": actual["database"]["coverage"],
        "postgres_reparsed_equivalent_checks": equivalent,
        "logto_recovery": "not verified",
        "scope": (
            "Dedicated synthetic full commercial chain; "
            "exact facts, schema, binary versions and application projections"
        ),
    }
    with (BACKUP / "verification.json").open("x", encoding="utf8") as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps(report))


if __name__ == "__main__":
    main()
