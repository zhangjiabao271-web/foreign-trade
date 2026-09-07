from functools import lru_cache

from app.core.config import get_settings
from app.core.database import create_database_engine, create_session_factory
from app.platform.outbox import OutboxMessage
from sqlalchemy.orm import Session, sessionmaker

from worker.app import app as celery_app
from worker.tenant_context import TenantTaskContext


@lru_cache
def worker_session_factory() -> sessionmaker[Session]:
    return create_session_factory(create_database_engine(get_settings().database_url))


class CeleryEventDispatcher:
    def publish(self, message: OutboxMessage) -> None:
        context: TenantTaskContext = {
            "organization_id": message["organization_id"],
            "request_id": message["correlation_id"],
        }
        celery_app.send_task(
            "ai.execute-run"
            if message["event_type"] == "ai.run_requested.v1"
            else "platform.consume-outbox-event",
            kwargs={"context": context, "message": message},
            queue="default",
        )
