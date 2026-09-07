"""Probe only the separately named, non-network-exposed acceptance stack."""

import argparse
import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.core.config import get_settings
from app.identity.enums import MembershipRole
from app.identity.models import Organization, OrganizationMembership, User
from app.platform.commands import PlatformCommandService
from app.platform.models import AsyncJob, OutboxEvent, ProcessedEvent
from app.platform.outbox import OutboxRelay, outbox_message
from sqlalchemy import func, select
from worker.outbox import CeleryEventDispatcher, worker_session_factory
from worker.tasks import consume_outbox_event


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["prepare", "recover", "check", "duplicate"])
    parser.add_argument("scenario", choices=["restart", "broker-loss"])
    args = parser.parse_args()
    settings = get_settings()
    if (
        os.getenv("ACCEPTANCE_REHEARSAL") != "true"
        or settings.app_env != "acceptance"
        or settings.database_name != "trade_recovery_acceptance"
    ):
        raise RuntimeError("Refusing to touch a non-acceptance database")
    factory = worker_session_factory()
    with factory.begin() as session:
        organization = session.scalar(
            select(Organization).where(
                Organization.name_normalized == "recovery-fixture",
            )
        )
        if organization is None:
            if args.action != "prepare":
                raise RuntimeError("Missing rehearsal fixture")
            organization = Organization(name="Recovery fixture", name_normalized="recovery-fixture")
            user = User(external_subject="recovery-fixture", display_name="Rehearsal only")
            session.add_all([organization, user])
            session.flush()
            session.add(
                OrganizationMembership(
                    organization_id=organization.id, user_id=user.id, role=MembershipRole.ADMIN
                )
            )
            session.flush()
        else:
            user = session.scalar(select(User).where(User.external_subject == "recovery-fixture"))
        organization_id, user_id = organization.id, user.id
    context = RequestContext(
        user_id=user_id,
        organization_id=organization_id,
        permissions=frozenset(Permission),
        request_id=uuid4(),
    )
    job_type = f"rehearsal.{args.scenario}"
    with factory() as session:
        job = session.scalar(
            select(AsyncJob).where(
                AsyncJob.organization_id == organization_id,
                AsyncJob.job_type == job_type,
            )
        )
    relay = OutboxRelay(factory, CeleryEventDispatcher(), worker_id="acceptance-probe")
    if args.action == "prepare":
        if job is not None:
            raise RuntimeError("Scenario already exists; refusing to overwrite evidence")
        job = PlatformCommandService(factory).create_job(context, job_type=job_type)
        with factory.begin() as session:
            row = session.scalar(
                select(OutboxEvent).where(
                    OutboxEvent.organization_id == organization_id,
                    OutboxEvent.aggregate_id == job.id,
                )
            )
            row.available_at = datetime.now(UTC) - timedelta(minutes=1)
        assert relay.run_once().published == 1
        # Avoid a 15-minute wait: only this synthetic receipt deadline is backdated.
        with factory.begin() as session:
            row = session.scalar(
                select(OutboxEvent).where(
                    OutboxEvent.organization_id == organization_id,
                    OutboxEvent.aggregate_id == job.id,
                )
            )
            row.published_at = datetime.now(UTC) - timedelta(minutes=30)
        print(f"{args.scenario}: published synthetic job, not yet consumed")
        return
    if job is None:
        raise RuntimeError("Missing scenario job")
    if args.action == "recover":
        assert relay.recover_unconsumed(consumer_name_prefix="worker.") == 1
        assert relay.run_once().published == 1
        print("broker-loss: republished from PostgreSQL")
        return
    with factory() as session:
        row = session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.organization_id == organization_id,
                OutboxEvent.aggregate_id == job.id,
            )
        )
        message = outbox_message(row)
        receipts = session.scalar(
            select(func.count())
            .select_from(ProcessedEvent)
            .where(
                ProcessedEvent.organization_id == organization_id,
                ProcessedEvent.event_id == row.id,
                ProcessedEvent.consumer_name == "worker.async_job.created.v1",
            )
        )
        assert receipts == 1, "Waiting for actual worker receipt"
        assert job.result_reference == f"event:{row.id}", "Missing worker side effect"
        before_updated = job.updated_at
    if args.action == "duplicate":
        task_context = {
            "organization_id": str(organization_id),
            "request_id": message["correlation_id"],
        }
        assert consume_outbox_event(task_context, message) is False
        assert consume_outbox_event(task_context, message) is False
        with factory() as session:
            persisted = session.scalar(
                select(AsyncJob).where(
                    AsyncJob.organization_id == organization_id,
                    AsyncJob.id == job.id,
                )
            )
            assert persisted.updated_at == before_updated
    print(f"{args.scenario}: {args.action} passed; one receipt and stable side effect")


if __name__ == "__main__":
    main()
