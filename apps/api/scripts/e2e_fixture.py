import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from recovery_environment import recovery_mode
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url

API_ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(API_ROOT))

from app.auth.tokens import LocalTestTokenIssuer  # noqa: E402
from app.core.database import create_session_factory  # noqa: E402
from app.documents.services import mark_document_available  # noqa: E402
from app.identity.enums import MembershipRole, MembershipStatus  # noqa: E402
from app.identity.models import Organization, OrganizationMembership, User  # noqa: E402
from app.platform.enums import OutboxStatus  # noqa: E402
from app.platform.models import OutboxEvent  # noqa: E402
from app.platform.outbox import IdempotentEventConsumer, outbox_message  # noqa: E402

DATABASE_NAME = "trade_workbench_e2e"
DEFAULT_ADMIN_URL = (
    "postgresql+psycopg://trade_workbench:local-dev-only-change-me@localhost:5432/postgres"
)
TOKEN_SECRET = "playwright-only-secret-with-at-least-32-characters"
TOKEN_ISSUER = "https://issuer.playwright.test"
TOKEN_AUDIENCE = "trade-workbench-playwright"


def issue_browser_token(subject: str, organization_id: UUID) -> str:
    # One isolated browser suite can exceed the unit issuer's five-minute default in CI.
    return LocalTestTokenIssuer(
        secret=TOKEN_SECRET, issuer=TOKEN_ISSUER, audience=TOKEN_AUDIENCE
    ).issue(subject=subject, organization_id=organization_id, expires_in=timedelta(minutes=30))


def _quoted_database_name() -> str:
    if DATABASE_NAME != "trade_workbench_e2e":
        raise RuntimeError("Refusing to manage an unexpected E2E database")
    return f'"{DATABASE_NAME}"'


def _database_urls() -> tuple[str, str]:
    admin_url = make_url(os.getenv("TEST_DATABASE_ADMIN_URL", DEFAULT_ADMIN_URL))
    test_url = admin_url.set(database=DATABASE_NAME)
    return (
        admin_url.render_as_string(hide_password=False),
        test_url.render_as_string(hide_password=False),
    )


def setup() -> None:
    retained = recovery_mode()
    admin_url, test_url = _database_urls()
    print("E2E fixture: connecting to PostgreSQL", flush=True)
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        print("E2E fixture: recreating isolated database", flush=True)
        if retained:
            exists = connection.exec_driver_sql(
                "SELECT 1 FROM pg_database WHERE datname = %s", (DATABASE_NAME,)
            ).scalar()
            if exists:
                raise RuntimeError("Retained recovery database exists; refusing overwrite")
        else:
            connection.exec_driver_sql(
                f"DROP DATABASE IF EXISTS {_quoted_database_name()} WITH (FORCE)"
            )
        connection.exec_driver_sql(f"CREATE DATABASE {_quoted_database_name()}")
    admin_engine.dispose()

    print("E2E fixture: applying migrations", flush=True)
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", test_url.replace("%", "%%"))
    command.upgrade(config, "head")

    print("E2E fixture: seeding organization and users", flush=True)
    engine = create_engine(test_url)
    factory = create_session_factory(engine)
    with factory.begin() as session:
        organization = Organization(
            name="Playwright Export Company",
            name_normalized="playwright export company",
        )
        user = User(
            external_subject="playwright-sales",
            display_name="Playwright Sales",
        )
        manager = User(
            external_subject="playwright-manager",
            display_name="Playwright Manager",
        )
        operations = User(
            external_subject="playwright-operations",
            display_name="Playwright Operations",
        )
        administrator = User(external_subject="playwright-admin", display_name="Playwright Admin")
        session.add_all([organization, user, manager, operations, administrator])
        session.flush()
        session.add_all(
            [
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=administrator.id,
                    role=MembershipRole.ADMIN,
                    status=MembershipStatus.ACTIVE,
                ),
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=user.id,
                    role=MembershipRole.SALES,
                    status=MembershipStatus.ACTIVE,
                ),
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=manager.id,
                    role=MembershipRole.MANAGER,
                    status=MembershipStatus.ACTIVE,
                ),
                OrganizationMembership(
                    organization_id=organization.id,
                    user_id=operations.id,
                    role=MembershipRole.OPERATIONS,
                    status=MembershipStatus.ACTIVE,
                ),
            ]
        )
        session.flush()
        token = issue_browser_token(user.external_subject, organization.id)
        manager_token = issue_browser_token(manager.external_subject, organization.id)
        operations_token = issue_browser_token(operations.external_subject, organization.id)
        dead_event = OutboxEvent(
            organization_id=organization.id,
            event_type="fixture.acceptance_failure.v1",
            aggregate_type="fixture",
            aggregate_id=uuid4(),
            correlation_id=uuid4(),
            status=OutboxStatus.DEAD,
            attempt_count=5,
            last_error="CONSUMER_RECEIPT_TIMEOUT",
        )
        session.add(dead_event)
        session.flush()
        fixture = {
            "dead_event_id": str(dead_event.id),
            "organization_id": str(organization.id),
            "access_token": token,
            "manager_access_token": manager_token,
            "operations_access_token": operations_token,
            "admin_access_token": issue_browser_token(
                administrator.external_subject, organization.id
            ),
        }
    engine.dispose()

    fixture_path = Path(os.environ["E2E_FIXTURE_PATH"])
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    print("E2E fixture: ready", flush=True)


def teardown() -> None:
    if recovery_mode():
        print("E2E recovery fixture retained; no database cleanup performed", flush=True)
        return
    admin_url, _ = _database_urls()
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as connection:
        connection.exec_driver_sql(
            f"DROP DATABASE IF EXISTS {_quoted_database_name()} WITH (FORCE)"
        )
    admin_engine.dispose()


def process_documents() -> None:
    _, test_url = _database_urls()
    engine = create_engine(test_url)
    factory = create_session_factory(engine)
    with factory() as session:
        events = session.scalars(
            select(OutboxEvent)
            .where(OutboxEvent.event_type == "document.uploaded.v1")
            .order_by(OutboxEvent.created_at)
        ).all()
    consumer = IdempotentEventConsumer(factory)
    processed = sum(
        consumer.consume(
            consumer_name="playwright.document-scan",
            message=outbox_message(event),
            handler=mark_document_available,
        )
        for event in events
    )
    engine.dispose()
    print(f"E2E fixture: processed {processed} document scan event(s)", flush=True)


def process_ai() -> None:
    """Explicit scripted provider for the isolated E2E database, with no network traffic."""
    from uuid import uuid4

    from app.ai.models import AiRun
    from app.ai.provider import ProviderTurn
    from app.ai.runner import AiRunner
    from app.core.config import Settings

    class FixtureProvider:
        def next_turn(self, *, model, inputs, tools):
            if inputs[-1].get("type") != "function_call_output":
                intent = json.loads(inputs[0]["content"])
                return ProviderTurn(
                    [
                        {
                            "type": "function_call",
                            "name": "read_order",
                            "call_id": "e2e-read",
                            "arguments": json.dumps({"order_id": intent["subject_id"]}),
                        }
                    ],
                    100,
                    20,
                )
            return ProviderTurn(
                [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "inferences": ["建议内部复核文件准备进度"],
                                        "draft": "请核对本订单文件准备进度，勿对外承诺新交期。",
                                        "task_title": "复核订单文件准备进度",
                                    }
                                ),
                            }
                        ],
                    }
                ],
                120,
                30,
            )

    _, test_url = _database_urls()
    engine = create_engine(test_url)
    factory = create_session_factory(engine)
    with factory.begin() as session:
        runs = session.scalars(select(AiRun).where(AiRun.status == "PENDING")).all()
        for run in runs:
            run.model = "e2e-scripted-fixture"
    for run in runs:
        AiRunner(factory, FixtureProvider(), Settings()).execute(
            organization_id=run.organization_id, run_id=run.id, request_id=uuid4()
        )
    engine.dispose()
    print(f"E2E fixture: processed {len(runs)} explicitly scripted AI run(s)", flush=True)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "setup":
        setup()
    elif action == "teardown":
        teardown()
    elif action == "process-documents":
        process_documents()
    elif action == "process-ai":
        process_ai()
    else:
        raise SystemExit("Usage: e2e_fixture.py setup|teardown|process-documents|process-ai")
