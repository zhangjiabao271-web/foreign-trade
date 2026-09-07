from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from random import uniform
from typing import Any, Protocol, TypedDict, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from app.platform.enums import OutboxStatus
from app.platform.models import AsyncJob, OutboxEvent, ProcessedEvent


class OutboxMessage(TypedDict):
    id: str
    organization_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    payload: dict[str, object]
    correlation_id: str


class EventDispatcher(Protocol):
    def publish(self, message: OutboxMessage) -> None: ...


@dataclass(frozen=True, slots=True)
class RelayResult:
    claimed: int
    published: int
    failed: int


def outbox_message(event: OutboxEvent) -> OutboxMessage:
    return {
        "id": str(event.id),
        "organization_id": str(event.organization_id),
        "event_type": event.event_type,
        "aggregate_type": event.aggregate_type,
        "aggregate_id": str(event.aggregate_id),
        "payload": event.payload,
        "correlation_id": str(event.correlation_id),
    }


class OutboxRelay:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        dispatcher: EventDispatcher,
        *,
        worker_id: str,
        max_attempts: int = 5,
    ) -> None:
        self._session_factory = session_factory
        self._dispatcher = dispatcher
        self._worker_id = worker_id
        self._max_attempts = max_attempts

    def claim_batch(self, *, limit: int = 50) -> list[OutboxMessage]:
        now = datetime.now(UTC)
        with self._session_factory.begin() as session:
            statement = (
                select(OutboxEvent)
                .where(
                    OutboxEvent.status == OutboxStatus.PENDING,
                    OutboxEvent.available_at <= now,
                )
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
            events = list(session.scalars(statement))
            for event in events:
                event.status = OutboxStatus.PROCESSING
                event.locked_at = now
                event.locked_by = self._worker_id
                event.attempt_count += 1
            return [outbox_message(event) for event in events]

    def run_once(self, *, limit: int = 50) -> RelayResult:
        messages = self.claim_batch(limit=limit)
        published = 0
        failed = 0
        for message in messages:
            try:
                self._dispatcher.publish(message)
            except Exception as error:
                self._mark_failed(message, error)
                failed += 1
            else:
                self._mark_published(message)
                published += 1
        return RelayResult(claimed=len(messages), published=published, failed=failed)

    def recover_stale(self, *, older_than: timedelta = timedelta(minutes=5)) -> int:
        cutoff = datetime.now(UTC) - older_than
        with self._session_factory.begin() as session:
            result = cast(
                CursorResult[Any],
                session.execute(
                    update(OutboxEvent)
                    .where(
                        OutboxEvent.status == OutboxStatus.PROCESSING,
                        OutboxEvent.locked_at < cutoff,
                    )
                    .values(
                        status=OutboxStatus.PENDING,
                        locked_at=None,
                        locked_by=None,
                        available_at=datetime.now(UTC),
                    )
                ),
            )
            return result.rowcount

    def recover_unconsumed(
        self,
        *,
        consumer_name_prefix: str,
        older_than: timedelta = timedelta(minutes=15),
        limit: int = 50,
    ) -> int:
        """Requeue published messages lacking their intended consumer's durable receipt.

        A broker acknowledgement is not a business acknowledgement. Recovery may race
        with an in-flight consumer; its transactional receipt must still deduplicate.
        """
        if not consumer_name_prefix or older_than <= timedelta(0) or not 1 <= limit <= 500:
            raise ValueError("Invalid outbox recovery policy")
        now = datetime.now(UTC)
        receipt = select(ProcessedEvent.event_id).where(
            ProcessedEvent.organization_id == OutboxEvent.organization_id,
            ProcessedEvent.event_id == OutboxEvent.id,
            ProcessedEvent.consumer_name == consumer_name_prefix + OutboxEvent.event_type,
        )
        with self._session_factory.begin() as session:
            events = list(
                session.scalars(
                    select(OutboxEvent)
                    .where(
                        OutboxEvent.status == OutboxStatus.PUBLISHED,
                        OutboxEvent.published_at < now - older_than,
                        ~receipt.exists(),
                    )
                    .order_by(OutboxEvent.published_at, OutboxEvent.id)
                    .with_for_update(skip_locked=True)
                    .limit(limit)
                )
            )
            for event in events:
                event.status = (
                    OutboxStatus.DEAD
                    if event.attempt_count >= self._max_attempts
                    else OutboxStatus.PENDING
                )
                event.available_at = now
                event.last_error = "CONSUMER_RECEIPT_TIMEOUT"
            return len(events)

    def _mark_published(self, message: OutboxMessage) -> None:
        with self._session_factory.begin() as session:
            event = self._locked_event(session, message)
            if event is None:
                return
            event.status = OutboxStatus.PUBLISHED
            event.published_at = datetime.now(UTC)
            event.locked_at = None
            event.locked_by = None
            event.last_error = None

    def _mark_failed(self, message: OutboxMessage, error: Exception) -> None:
        with self._session_factory.begin() as session:
            event = self._locked_event(session, message)
            if event is None:
                return
            event.last_error = str(error)[:2000]
            event.locked_at = None
            event.locked_by = None
            if event.attempt_count >= self._max_attempts:
                event.status = OutboxStatus.DEAD
                return
            delay = min(300, 2 ** (event.attempt_count - 1))
            delay += uniform(0, delay * 0.2)
            event.status = OutboxStatus.PENDING
            event.available_at = datetime.now(UTC) + timedelta(seconds=delay)

    def _locked_event(
        self,
        session: Session,
        message: OutboxMessage,
    ) -> OutboxEvent | None:
        return session.scalar(
            select(OutboxEvent)
            .where(
                OutboxEvent.organization_id == UUID(message["organization_id"]),
                OutboxEvent.id == UUID(message["id"]),
                OutboxEvent.status == OutboxStatus.PROCESSING,
                OutboxEvent.locked_by == self._worker_id,
            )
            .with_for_update()
        )


EventHandler = Callable[[Session, OutboxMessage], None]


class IdempotentEventConsumer:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def consume(
        self,
        *,
        consumer_name: str,
        message: OutboxMessage,
        handler: EventHandler,
    ) -> bool:
        organization_id = UUID(message["organization_id"])
        event_id = UUID(message["id"])
        with self._session_factory.begin() as session:
            statement = (
                insert(ProcessedEvent)
                .values(
                    organization_id=organization_id,
                    event_id=event_id,
                    consumer_name=consumer_name,
                )
                .on_conflict_do_nothing(
                    index_elements=["organization_id", "event_id", "consumer_name"]
                )
                .returning(ProcessedEvent.event_id)
            )
            if session.scalar(statement) is None:
                return False
            handler(session, message)
            return True


def mark_async_job_event_consumed(session: Session, message: OutboxMessage) -> None:
    result = cast(
        CursorResult[Any],
        session.execute(
            update(AsyncJob)
            .where(
                AsyncJob.organization_id == UUID(message["organization_id"]),
                AsyncJob.id == UUID(message["aggregate_id"]),
            )
            .values(result_reference=f"event:{message['id']}")
        ),
    )
    if result.rowcount != 1:
        raise ValueError("Async job aggregate was not found in the event organization")
