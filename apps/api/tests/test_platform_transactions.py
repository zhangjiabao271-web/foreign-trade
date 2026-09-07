from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from threading import Lock
from uuid import UUID, uuid4

import pytest
from alembic import command
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.database import create_session_factory
from app.platform.commands import PlatformCommandService
from app.platform.enums import OutboxStatus
from app.platform.models import AsyncJob, AuditLog, OutboxEvent, ProcessedEvent
from app.platform.outbox import IdempotentEventConsumer, OutboxMessage, OutboxRelay
from app.platform.repositories import OutboxEventRepository
from app.platform.schemas import OutboxEventResponse, ReplayOutboxRequest
from app.platform.services import OutboxAdminService
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from test_migrations import alembic_config, insert_identity_fixture


@dataclass(frozen=True, slots=True)
class PlatformFixture:
    engine: Engine
    session_factory: sessionmaker[Session]
    context: RequestContext


@pytest.fixture
def platform_fixture(test_database_url: str) -> Iterator[PlatformFixture]:
    command.upgrade(alembic_config(test_database_url), "head")
    engine = create_engine(test_database_url)
    with engine.begin() as connection:
        organization_id, _, user_id, _ = insert_identity_fixture(connection)
    factory = create_session_factory(engine)
    yield PlatformFixture(
        engine=engine,
        session_factory=factory,
        context=RequestContext(
            user_id=user_id,
            organization_id=organization_id,
            permissions=frozenset(Permission),
            request_id=uuid4(),
        ),
    )
    engine.dispose()


@dataclass(slots=True)
class RecordingDispatcher:
    messages: list[OutboxMessage] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)

    def publish(self, message: OutboxMessage) -> None:
        with self._lock:
            self.messages.append(message)


class FailingDispatcher:
    def publish(self, message: OutboxMessage) -> None:
        raise RuntimeError(f"dispatch failed for {message['id']}")


def seed_outbox_events(fixture: PlatformFixture, count: int) -> list[UUID]:
    event_ids: list[UUID] = []
    with fixture.session_factory.begin() as session:
        for index in range(count):
            event = OutboxEvent(
                organization_id=fixture.context.organization_id,
                created_by=fixture.context.user_id,
                updated_by=fixture.context.user_id,
                event_type="fixture.created.v1",
                # These fixtures are ready events, independent of host/container clock skew.
                available_at=datetime.now(UTC) - timedelta(minutes=1),
                aggregate_type="fixture",
                aggregate_id=uuid4(),
                payload={"index": index},
                correlation_id=fixture.context.request_id,
            )
            session.add(event)
            session.flush()
            event_ids.append(event.id)
    return event_ids


def test_command_atomically_writes_business_audit_and_outbox(
    platform_fixture: PlatformFixture,
) -> None:
    job = PlatformCommandService(platform_fixture.session_factory).create_job(
        platform_fixture.context,
        job_type="test.atomic",
    )

    with platform_fixture.session_factory() as session:
        audit = session.scalar(select(AuditLog).where(AuditLog.target_id == job.id))
        event = session.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == job.id))
        persisted_job = session.get(AsyncJob, job.id)

    assert persisted_job is not None
    assert audit is not None
    assert event is not None
    assert audit.request_id == platform_fixture.context.request_id
    assert event.correlation_id == platform_fixture.context.request_id


@pytest.mark.parametrize("failure_point", ["business", "audit", "outbox"])
def test_failure_injection_rolls_back_every_record(
    platform_fixture: PlatformFixture,
    failure_point: str,
) -> None:
    def inject(point: str) -> None:
        if point == failure_point:
            raise RuntimeError("injected failure")

    with pytest.raises(RuntimeError, match="injected failure"):
        PlatformCommandService(platform_fixture.session_factory).create_job(
            platform_fixture.context,
            job_type="test.rollback",
            failure_injector=inject,
        )

    with platform_fixture.session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AsyncJob)) == 0
        assert session.scalar(select(func.count()).select_from(AuditLog)) == 0
        assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 0


def test_relay_cannot_claim_uncommitted_event(platform_fixture: PlatformFixture) -> None:
    dispatcher = RecordingDispatcher()
    relay = OutboxRelay(
        platform_fixture.session_factory,
        dispatcher,
        worker_id="visibility-test",
    )
    session = platform_fixture.session_factory()
    transaction = session.begin()
    try:
        session.add(
            OutboxEvent(
                organization_id=platform_fixture.context.organization_id,
                created_by=platform_fixture.context.user_id,
                updated_by=platform_fixture.context.user_id,
                event_type="fixture.uncommitted.v1",
                aggregate_type="fixture",
                aggregate_id=uuid4(),
                correlation_id=platform_fixture.context.request_id,
            )
        )
        session.flush()

        result = relay.run_once()

        assert result.claimed == 0
        assert dispatcher.messages == []
    finally:
        transaction.rollback()
        session.close()


def test_two_relays_do_not_claim_the_same_event(platform_fixture: PlatformFixture) -> None:
    event_ids = seed_outbox_events(platform_fixture, 12)
    dispatcher = RecordingDispatcher()
    relays = [
        OutboxRelay(
            platform_fixture.session_factory,
            dispatcher,
            worker_id=f"relay-{index}",
        )
        for index in range(2)
    ]

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda relay: relay.run_once(limit=12), relays))

    published_ids = [UUID(message["id"]) for message in dispatcher.messages]
    assert sum(result.claimed for result in results) == 12
    assert set(published_ids) == set(event_ids)
    assert len(published_ids) == len(set(published_ids))


def test_failed_dispatch_becomes_dead_at_attempt_limit(platform_fixture: PlatformFixture) -> None:
    event_id = seed_outbox_events(platform_fixture, 1)[0]
    relay = OutboxRelay(
        platform_fixture.session_factory,
        FailingDispatcher(),
        worker_id="failure-test",
        max_attempts=1,
    )

    result = relay.run_once()

    with platform_fixture.session_factory() as session:
        event = session.get(OutboxEvent, event_id)
    assert result.failed == 1
    assert event is not None
    assert event.status == OutboxStatus.DEAD
    assert event.last_error is not None


def test_authorized_replay_resets_dead_event_and_writes_audit(
    platform_fixture: PlatformFixture,
) -> None:
    event_id = seed_outbox_events(platform_fixture, 1)[0]
    with platform_fixture.session_factory.begin() as session:
        event = session.get(OutboxEvent, event_id)
        assert event is not None
        event.status = OutboxStatus.DEAD
        event.attempt_count = 5
        event.last_error = "fixture failure"

    with platform_fixture.session_factory() as session:
        event = OutboxAdminService(OutboxEventRepository(session)).replay(
            platform_fixture.context,
            event_id,
            reason="Dependency recovered",
        )

    with platform_fixture.session_factory() as session:
        audits = list(session.scalars(select(AuditLog).where(AuditLog.target_id == event_id)))
    assert event.status == OutboxStatus.PENDING
    assert event.attempt_count == 0
    assert len(audits) == 1
    assert audits[0].reason == "Dependency recovered"


def test_concurrent_replay_has_one_winner(platform_fixture: PlatformFixture) -> None:
    fixture = platform_fixture
    event_id = seed_outbox_events(fixture, 1)[0]
    with fixture.session_factory.begin() as session:
        session.get(OutboxEvent, event_id).status = OutboxStatus.DEAD

    def replay(_: int) -> str:
        with fixture.session_factory() as session:
            try:
                OutboxAdminService(OutboxEventRepository(session)).replay(
                    fixture.context, event_id, reason="Dependency restored", expected_version=2
                )
                return "requeued"
            except ApiProblem as error:
                assert error.status == 409
                return error.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(replay, range(2)))
    assert sorted(results) == ["OUTBOX_EVENT_NOT_DEAD", "requeued"]
    with fixture.session_factory() as session:
        assert session.get(OutboxEvent, event_id).version == 3
        assert session.scalar(select(func.count()).select_from(AuditLog)) == 1


def test_replay_rejects_invalid_context_reason_and_version(
    platform_fixture: PlatformFixture,
) -> None:
    fixture = platform_fixture
    event_id = seed_outbox_events(fixture, 1)[0]
    with fixture.session_factory.begin() as session:
        session.get(OutboxEvent, event_id).status = OutboxStatus.DEAD
    cases = [
        (replace(fixture.context, permissions=frozenset()), "Recovered", 1, 403),
        (replace(fixture.context, organization_id=uuid4()), "Recovered", 1, 404),
        (fixture.context, "  ", 1, 422),
        (fixture.context, "Recovered", 1, 409),
    ]
    with fixture.session_factory() as session:
        service = OutboxAdminService(OutboxEventRepository(session))
        for context, reason, version, status in cases:
            with pytest.raises(ApiProblem) as raised:
                service.replay(context, event_id, reason=reason, expected_version=version)
            assert raised.value.status == status
        assert session.get(OutboxEvent, event_id).status == OutboxStatus.DEAD
        assert session.scalar(select(func.count()).select_from(AuditLog)) == 0
        with pytest.raises(ApiProblem) as raised:
            service.list_dead(replace(fixture.context, permissions=frozenset()))
        assert raised.value.status == 403
    with pytest.raises(ValidationError):
        ReplayOutboxRequest(reason="  ")


def test_replay_audit_failure_rolls_back_in_same_session(
    platform_fixture: PlatformFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.platform.records import AuditRecorder

    fixture = platform_fixture
    event_id = seed_outbox_events(fixture, 1)[0]
    with fixture.session_factory.begin() as session:
        row = session.get(OutboxEvent, event_id)
        row.status = OutboxStatus.DEAD
        row.attempt_count = 5
        row.last_error = "fixture failure"

    def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(AuditRecorder, "record", fail)
    with fixture.session_factory() as session:
        with pytest.raises(RuntimeError, match="audit unavailable"):
            OutboxAdminService(OutboxEventRepository(session)).replay(
                fixture.context, event_id, reason="Recovered", expected_version=2
            )
        row = session.get(OutboxEvent, event_id)
        assert row.status == OutboxStatus.DEAD
        assert row.version == 2
        assert row.attempt_count == 5
        assert row.last_error == "fixture failure"
        assert session.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_dead_list_is_bounded_tenant_scoped_and_redacts_errors(
    platform_fixture: PlatformFixture,
) -> None:
    fixture = platform_fixture
    event_ids = seed_outbox_events(fixture, 4)
    with fixture.session_factory.begin() as session:
        for event_id in event_ids[:3]:
            row = session.get(OutboxEvent, event_id)
            row.status = OutboxStatus.DEAD
            row.last_error = "amqp://synthetic-secret@broker"
    with fixture.session_factory() as session:
        service = OutboxAdminService(OutboxEventRepository(session))
        first = service.list_dead(fixture.context, limit=2)
        second = service.list_dead(fixture.context, offset=2, limit=2)
        assert len(first) == 2
        assert len(second) == 1
        assert {row.id for row in [*first, *second]} == set(event_ids[:3])
        assert service.list_dead(replace(fixture.context, organization_id=uuid4())) == []
        serialized = OutboxEventResponse.model_validate(first[0]).model_dump(mode="json")
        assert serialized["last_error"] == "EVENT_DELIVERY_FAILED"
        first[0].last_error = "CONSUMER_RECEIPT_TIMEOUT"
        assert OutboxEventResponse.model_validate(first[0]).model_dump()["last_error"] == (
            "CONSUMER_RECEIPT_TIMEOUT"
        )


def test_duplicate_delivery_applies_side_effect_once(platform_fixture: PlatformFixture) -> None:
    job = PlatformCommandService(platform_fixture.session_factory).create_job(
        platform_fixture.context,
        job_type="test.consumer",
    )
    with platform_fixture.session_factory() as session:
        event = session.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == job.id))
        assert event is not None
        message: OutboxMessage = {
            "id": str(event.id),
            "organization_id": str(event.organization_id),
            "event_type": event.event_type,
            "aggregate_type": event.aggregate_type,
            "aggregate_id": str(event.aggregate_id),
            "payload": event.payload,
            "correlation_id": str(event.correlation_id),
        }

    def increment_attempt(session: Session, received: OutboxMessage) -> None:
        persisted_job = session.get(AsyncJob, UUID(received["aggregate_id"]))
        assert persisted_job is not None
        persisted_job.attempt_count += 1

    consumer = IdempotentEventConsumer(platform_fixture.session_factory)
    first = consumer.consume(
        consumer_name="test.consumer",
        message=message,
        handler=increment_attempt,
    )
    second = consumer.consume(
        consumer_name="test.consumer",
        message=message,
        handler=increment_attempt,
    )

    with platform_fixture.session_factory() as session:
        persisted_job = session.get(AsyncJob, job.id)
        processed_count = session.scalar(select(func.count()).select_from(ProcessedEvent))
    assert first is True
    assert second is False
    assert persisted_job is not None
    assert persisted_job.attempt_count == 1
    assert processed_count == 1


def test_published_recovery_requires_intended_receipt_and_respects_retry_limit(
    platform_fixture: PlatformFixture,
) -> None:
    fixture = platform_fixture
    event_ids = seed_outbox_events(fixture, 4)
    with fixture.session_factory.begin() as session:
        for index, event_id in enumerate(event_ids):
            row = session.get(OutboxEvent, event_id)
            row.status = OutboxStatus.PUBLISHED
            row.published_at = datetime.now(UTC) - timedelta(minutes=30 if index != 2 else 0)
            row.attempt_count = 5 if index == 3 else 1
        session.add_all(
            [
                ProcessedEvent(
                    organization_id=fixture.context.organization_id,
                    event_id=event_ids[0],
                    consumer_name="worker.fixture.created.v1",
                ),
                ProcessedEvent(
                    organization_id=fixture.context.organization_id,
                    event_id=event_ids[1],
                    consumer_name="unrelated.fixture.created.v1",
                ),
            ]
        )
    relay = OutboxRelay(fixture.session_factory, RecordingDispatcher(), worker_id="recovery")
    assert relay.recover_unconsumed(consumer_name_prefix="worker.") == 2
    with fixture.session_factory() as session:
        assert [session.get(OutboxEvent, event_id).status for event_id in event_ids] == [
            OutboxStatus.PUBLISHED,
            OutboxStatus.PENDING,
            OutboxStatus.PUBLISHED,
            OutboxStatus.DEAD,
        ]
        assert session.get(OutboxEvent, event_ids[3]).last_error == "CONSUMER_RECEIPT_TIMEOUT"
    assert relay.recover_unconsumed(consumer_name_prefix="worker.") == 0


def test_concurrent_receipt_recovery_is_bounded_and_claims_each_event_once(
    platform_fixture: PlatformFixture,
) -> None:
    fixture = platform_fixture
    event_ids = seed_outbox_events(fixture, 12)
    with fixture.session_factory.begin() as session:
        for event_id in event_ids:
            row = session.get(OutboxEvent, event_id)
            row.status = OutboxStatus.PUBLISHED
            row.published_at = datetime.now(UTC) - timedelta(minutes=30)
            row.attempt_count = 1
    relays = [
        OutboxRelay(fixture.session_factory, RecordingDispatcher(), worker_id=f"r-{index}")
        for index in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        counts = list(
            executor.map(
                lambda relay: relay.recover_unconsumed(
                    consumer_name_prefix="worker.",
                    limit=6,
                ),
                relays,
            )
        )
    assert counts == [6, 6]
    assert relays[0].recover_unconsumed(consumer_name_prefix="worker.") == 0


def test_lost_broker_message_is_republished_and_late_duplicate_has_one_side_effect(
    platform_fixture: PlatformFixture,
) -> None:
    fixture = platform_fixture
    job = PlatformCommandService(fixture.session_factory).create_job(
        fixture.context,
        job_type="test.lost-broker-message",
    )
    dispatcher = RecordingDispatcher()
    relay = OutboxRelay(fixture.session_factory, dispatcher, worker_id="loss-test")
    with fixture.session_factory.begin() as session:
        row = session.scalar(select(OutboxEvent).where(OutboxEvent.aggregate_id == job.id))
        row.available_at = datetime.now(UTC) - timedelta(minutes=1)
    assert relay.run_once().published == 1
    lost_message = dispatcher.messages.pop()
    with fixture.session_factory.begin() as session:
        row = session.get(OutboxEvent, UUID(lost_message["id"]))
        row.published_at = datetime.now(UTC) - timedelta(minutes=30)
    assert relay.recover_unconsumed(consumer_name_prefix="worker.") == 1
    assert relay.run_once().published == 1
    assert dispatcher.messages == [lost_message]

    def increment(session, message):
        row = session.scalar(
            select(AsyncJob).where(
                AsyncJob.organization_id == UUID(message["organization_id"]),
                AsyncJob.id == UUID(message["aggregate_id"]),
            )
        )
        row.attempt_count += 1

    consumer = IdempotentEventConsumer(fixture.session_factory)
    name = "worker.async_job.created.v1"
    assert consumer.consume(consumer_name=name, message=dispatcher.messages[0], handler=increment)
    assert not consumer.consume(consumer_name=name, message=lost_message, handler=increment)
    with fixture.session_factory() as session:
        assert session.get(AsyncJob, job.id).attempt_count == 1
