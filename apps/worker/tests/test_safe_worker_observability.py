from types import SimpleNamespace
from uuid import uuid4

from worker import observability


def test_worker_observation_keeps_ids_without_arguments_or_result(monkeypatch):
    records = []
    monkeypatch.setattr(observability, "observe", records.append)
    task_id = str(uuid4())
    organization_id, request_id = uuid4(), uuid4()
    observability.task_started(task_id=task_id)
    observability.task_finished(
        task_id=task_id,
        task=SimpleNamespace(name="platform.consume-outbox-event"),
        kwargs={
            "context": {"organization_id": str(organization_id), "request_id": str(request_id)},
            "secret": "DO_NOT_LOG",
        },
        state="SUCCESS",
        retval="DO_NOT_LOG",
        exception=ValueError("DO_NOT_LOG"),
    )
    assert records[0].request_id == request_id
    assert records[0].organization_id == organization_id
    assert records[0].outcome == "succeeded"
    assert records[0].duration_ms >= 0
    assert "DO_NOT_LOG" not in str(records)


def test_worker_untrusted_names_and_invalid_context_are_not_logged(monkeypatch):
    records = []
    monkeypatch.setattr(observability, "observe", records.append)
    observability.task_finished(
        task=SimpleNamespace(name="DO_NOT_LOG"),
        state="RETRY",
        kwargs={"context": {"organization_id": "DO_NOT_LOG", "request_id": "DO_NOT_LOG"}},
    )
    assert records[0].outcome == "retry"
    assert records[0].task_name == "unregistered-task"
    assert records[0].request_id is None and records[0].organization_id is None
    assert "DO_NOT_LOG" not in str(records)
