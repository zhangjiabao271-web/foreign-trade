from celery import Celery

from worker.config import get_worker_settings
from worker.observability import connect_worker_observers

settings = get_worker_settings()
connect_worker_observers()

app = Celery(
    "trade_workbench",
    broker=settings.celery_broker_url,
    include=["worker.tasks"],
)
app.conf.update(
    broker_connection_retry_on_startup=True,
    enable_utc=True,
    task_default_queue="default",
    task_ignore_result=True,
    task_serializer="json",
    task_soft_time_limit=30,
    task_time_limit=45,
    timezone="UTC",
    beat_schedule={
        "recover-unconsumed-outbox": {
            "task": "platform.recover-outbox",
            "schedule": 60.0,
        },
        "relay-outbox": {
            "task": "platform.relay-outbox",
            "schedule": 1.0,
        },
    },
)
