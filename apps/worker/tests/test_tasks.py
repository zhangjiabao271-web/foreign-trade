from uuid import uuid4

import pytest
from app.platform.outbox import OutboxMessage
from worker import outbox as worker_outbox
from worker.app import app
from worker.outbox import CeleryEventDispatcher
from worker.tasks import consume_outbox_event, ping_payload, tenant_context_probe
from worker.tenant_context import TenantTaskContext


def test_ping_payload_is_stable() -> None:
    assert ping_payload() == {"service": "worker", "status": "ready"}


def test_business_task_requires_explicit_tenant_context() -> None:
    context: TenantTaskContext = {
        "organization_id": str(uuid4()),
        "request_id": str(uuid4()),
    }

    assert tenant_context_probe(context) == context


def test_business_task_rejects_invalid_tenant_context() -> None:
    with pytest.raises(ValueError):
        tenant_context_probe({"organization_id": "not-a-uuid", "request_id": str(uuid4())})


def outbox_message(organization_id: str) -> OutboxMessage:
    return {
        "id": str(uuid4()),
        "organization_id": organization_id,
        "event_type": "async_job.created.v1",
        "aggregate_type": "async_job",
        "aggregate_id": str(uuid4()),
        "payload": {},
        "correlation_id": str(uuid4()),
    }


def test_celery_dispatcher_propagates_tenant_context(monkeypatch: pytest.MonkeyPatch) -> None:
    organization_id = str(uuid4())
    message = outbox_message(organization_id)
    published: dict[str, object] = {}

    def capture(task_name: str, **options: object) -> None:
        published["task_name"] = task_name
        published.update(options)

    monkeypatch.setattr(worker_outbox.celery_app, "send_task", capture)

    CeleryEventDispatcher().publish(message)

    assert published["task_name"] == "platform.consume-outbox-event"
    assert published["kwargs"] == {
        "context": {
            "organization_id": organization_id,
            "request_id": message["correlation_id"],
        },
        "message": message,
    }


def test_consumer_rejects_cross_tenant_task_before_database_access() -> None:
    context: TenantTaskContext = {
        "organization_id": str(uuid4()),
        "request_id": str(uuid4()),
    }

    with pytest.raises(ValueError, match="do not match"):
        consume_outbox_event(context, outbox_message(str(uuid4())))


def test_guide_reserved_queues_have_explicit_durable_routing() -> None:
    expected = {"default", "email", "documents", "ai", "acquisition", "exports"}
    assert set(app.conf.task_queues) == expected
    queues = app.amqp.Queues(app.conf.task_queues)
    assert set(queues) == expected
    for name in expected:
        queue = queues[name]
        assert queue.name == name
        assert queue.exchange.name == name
        assert queue.exchange.type == "direct"
        assert queue.routing_key == name
        assert queue.durable and queue.exchange.durable
        assert not queue.auto_delete


@pytest.mark.parametrize(
    "event_type,task_name",
    [
        ("async_job.created.v1", "platform.consume-outbox-event"),
        ("ai.run_requested.v1", "ai.execute-run"),
        ("document.uploaded.v1", "platform.consume-outbox-event"),
    ],
)
def test_reservations_do_not_reroute_existing_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    event_type: str,
    task_name: str,
) -> None:
    message = outbox_message(str(uuid4()))
    message["event_type"] = event_type
    published: dict[str, object] = {}

    def capture(name: str, **options: object) -> None:
        published["name"] = name
        published.update(options)

    monkeypatch.setattr(worker_outbox.celery_app, "send_task", capture)
    CeleryEventDispatcher().publish(message)
    assert published["name"] == task_name
    assert published["queue"] == "default"
    assert published["kwargs"] == {
        "context": {
            "organization_id": message["organization_id"],
            "request_id": message["correlation_id"],
        },
        "message": message,
    }
    assert app.conf.task_default_queue == "default"
