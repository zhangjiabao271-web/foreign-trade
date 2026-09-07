"""Explicit, version-bound private draft submission. No task or external action execution."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, tuple_
from sqlalchemy.orm import Session, sessionmaker

from app.ai.content import candidate_digest, is_released, latest_disclosure, run_digest
from app.ai.models import AiDisclosure, AiRun
from app.ai.schemas import (
    AiArtifact,
    AiDisclosureDecision,
    AiDisclosureResponse,
    AiDisclosureRevision,
    AiDisclosureSubmit,
)
from app.ai.services import get_run, record_ai_event
from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.unit_of_work import UnitOfWork
from app.platform.idempotency import begin_command, complete_command


def conflict() -> ApiProblem:
    return ApiProblem(
        409, "VERSION_CONFLICT", "Changed draft", "Reload and review the current candidate."
    )


def review_permissions(context: RequestContext, run: AiRun) -> None:
    context.require(Permission.AI_READ, Permission.PROFIT_READ)
    context.require(Permission.COMPANY_READ if run.intent == "SEARCH" else Permission.ORDER_READ)


def snapshot(
    session: Session,
    context: RequestContext,
    row: AiDisclosure,
    run: AiRun,
    *,
    latest_revision: int | None = None,
) -> AiDisclosureResponse:
    if latest_revision is None:
        latest = latest_disclosure(session, run)
        latest_revision = latest.revision if latest else 0
    current = latest_revision == row.revision and row.run_digest == run_digest(run)
    if row.status == "APPROVED" and not is_released(row, run):
        current = False
    privileged = Permission.PROFIT_READ in context.permissions
    return AiDisclosureResponse(
        id=row.id,
        run_id=row.run_id,
        parent_id=row.parent_id,
        revision=row.revision,
        version=row.version,
        status=row.status,
        current=current,
        candidate=AiArtifact.model_validate(row.candidate)
        if privileged or (current and is_released(row, run))
        else None,
        content_digest=candidate_digest(row) if privileged else None,
        reviewed_by=row.reviewed_by,
        reviewed_at=row.reviewed_at,
        created_at=row.created_at,
    )


class AiDisclosureService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def load(
        self, session: Session, context: RequestContext, record_id: UUID
    ) -> tuple[AiDisclosure, AiRun]:
        context.require(Permission.AI_READ)
        row = session.scalar(
            select(AiDisclosure).where(
                AiDisclosure.organization_id == context.organization_id,
                AiDisclosure.id == record_id,
                AiDisclosure.deleted_at.is_(None),
            )
        )
        if row is None:
            raise ApiProblem(
                404, "AI_DISCLOSURE_NOT_FOUND", "Not found", "Submitted draft not found."
            )
        run = session.scalar(
            select(AiRun).where(
                AiRun.organization_id == context.organization_id,
                AiRun.id == row.run_id,
                AiRun.deleted_at.is_(None),
            )
        )
        if run is None:
            raise ApiProblem(404, "AI_RUN_NOT_FOUND", "Not found", "Run not found.")
        if run.created_by == context.user_id:
            get_run(session, context, run.id)
        else:
            if Permission.PROFIT_READ not in context.permissions:
                raise ApiProblem(
                    404, "AI_DISCLOSURE_NOT_FOUND", "Not found", "Submitted draft not found."
                )
            review_permissions(context, run)
        return row, run

    def inspect(self, context: RequestContext, record_id: UUID) -> AiDisclosureResponse:
        with self.factory() as session:
            row, run = self.load(session, context, record_id)
            return snapshot(session, context, row, run)

    def page(
        self, context: RequestContext, *, cursor: UUID | None, limit: int
    ) -> list[AiDisclosureResponse]:
        context.require(Permission.AI_READ)
        with self.factory() as session:
            latest = (
                select(AiDisclosure.run_id, func.max(AiDisclosure.revision).label("revision"))
                .where(
                    AiDisclosure.organization_id == context.organization_id,
                    AiDisclosure.deleted_at.is_(None),
                )
                .group_by(AiDisclosure.run_id)
                .subquery()
            )
            query = (
                select(AiDisclosure, AiRun, latest.c.revision)
                .join(latest, latest.c.run_id == AiDisclosure.run_id)
                .join(
                    AiRun,
                    (AiRun.organization_id == AiDisclosure.organization_id)
                    & (AiRun.id == AiDisclosure.run_id),
                )
                .where(
                    AiDisclosure.organization_id == context.organization_id,
                    AiDisclosure.deleted_at.is_(None),
                    AiRun.deleted_at.is_(None),
                )
            )
            if Permission.PROFIT_READ not in context.permissions:
                query = query.where(
                    AiRun.created_by == context.user_id,
                    AiRun.required_permissions.contained_by([p.value for p in context.permissions]),
                )
            else:
                # Review access never implies the underlying domain read authority.
                if Permission.COMPANY_READ not in context.permissions:
                    query = query.where(AiRun.intent != "SEARCH")
                if Permission.ORDER_READ not in context.permissions:
                    query = query.where(AiRun.intent == "SEARCH")
            if cursor:
                anchor, _ = self.load(session, context, cursor)
                query = query.where(
                    tuple_(AiDisclosure.created_at, AiDisclosure.id)
                    < (anchor.created_at, anchor.id)
                )
            rows = session.execute(
                query.order_by(AiDisclosure.created_at.desc(), AiDisclosure.id.desc()).limit(
                    limit + 1
                )
            ).all()
            return [
                snapshot(session, context, row, run, latest_revision=revision)
                for row, run, revision in rows
            ]

    def submit(
        self, context: RequestContext, run_id: UUID, request: AiDisclosureSubmit, *, key: str
    ) -> AiDisclosureResponse:
        context.require(Permission.AI_RUN)
        with UnitOfWork(self.factory) as unit:
            session = unit.session
            command = begin_command(
                session,
                context,
                scope=f"ai.disclosure.submit.{context.user_id}",
                key=key,
                payload={"run_id": run_id, **request.model_dump()},
            )
            run = get_run(session, context, run_id, lock=True)
            if command.resource_id:
                row, _ = self.load(session, context, command.resource_id)
            else:
                if run.version != request.expected_version:
                    raise conflict()
                if run.status != "SUCCEEDED" or not run.output:
                    raise ApiProblem(
                        409, "AI_DRAFT_REQUIRED", "Draft required", "A completed draft is required."
                    )
                previous = latest_disclosure(session, run)
                if previous and previous.run_digest == run_digest(run):
                    raise ApiProblem(
                        409,
                        "AI_ALREADY_SUBMITTED",
                        "Already submitted",
                        "This draft has already been submitted.",
                    )
                row = AiDisclosure(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    run_id=run.id,
                    parent_id=previous.id if previous else None,
                    revision=previous.revision + 1 if previous else 1,
                    run_version=run.version,
                    run_digest=run_digest(run),
                    candidate=AiArtifact.model_validate(run.output.get("artifact")).model_dump(
                        mode="json"
                    ),
                )
                session.add(row)
                session.flush()
                complete_command(command, row.id, "ai_disclosure")
                record_ai_event(
                    session,
                    context,
                    target_id=run.id,
                    action="ai.disclosure_submitted",
                    details={"disclosure_id": str(row.id), "revision": row.revision},
                )
            result = snapshot(session, context, row, run)
            unit.commit()
            return result

    def change(
        self,
        context: RequestContext,
        record_id: UUID,
        request: AiDisclosureDecision | AiDisclosureRevision,
        *,
        key: str,
    ) -> AiDisclosureResponse:
        context.require(Permission.AI_READ, Permission.PROFIT_READ)
        revision = isinstance(request, AiDisclosureRevision)
        if isinstance(request, AiDisclosureDecision) and not request.confirmed:
            raise ApiProblem(
                422, "CONFIRMATION_REQUIRED", "Confirm review", "Confirm this content decision."
            )
        with UnitOfWork(self.factory) as unit:
            session = unit.session
            command = begin_command(
                session,
                context,
                scope=f"ai.disclosure.{'revision' if revision else 'decision'}",
                key=key,
                payload={"record_id": record_id, **request.model_dump(mode="json")},
            )
            row, run = self.load(session, context, record_id)
            review_permissions(context, run)
            # Serialize on the run before reloading the candidate.
            locked_run = session.scalar(
                select(AiRun)
                .where(
                    AiRun.organization_id == context.organization_id,
                    AiRun.id == run.id,
                    AiRun.deleted_at.is_(None),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            locked_row = session.scalar(
                select(AiDisclosure)
                .where(
                    AiDisclosure.organization_id == context.organization_id,
                    AiDisclosure.id == record_id,
                    AiDisclosure.deleted_at.is_(None),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if locked_run is None or locked_row is None:
                raise ApiProblem(
                    404, "AI_DISCLOSURE_NOT_FOUND", "Not found", "Submitted draft not found."
                )
            run, row = locked_run, locked_row
            if command.resource_id:
                row, run = self.load(session, context, command.resource_id)
            else:
                latest = latest_disclosure(session, run)
                if (
                    latest is None
                    or latest.id != row.id
                    or run_digest(run) != row.run_digest
                    or row.version != request.expected_version
                    or candidate_digest(row) != request.content_digest
                ):
                    raise conflict()
                if isinstance(request, AiDisclosureRevision):
                    row = AiDisclosure(
                        organization_id=context.organization_id,
                        created_by=context.user_id,
                        updated_by=context.user_id,
                        run_id=run.id,
                        parent_id=row.id,
                        revision=row.revision + 1,
                        run_version=run.version,
                        run_digest=run_digest(run),
                        candidate=request.candidate.model_dump(mode="json"),
                    )
                    session.add(row)
                else:
                    row.status = "APPROVED" if request.release else "REJECTED"
                    row.released_digest = candidate_digest(row) if request.release else None
                    row.reviewed_by = context.user_id
                    row.reviewed_at = datetime.now(UTC)
                    row.updated_by = context.user_id
                session.flush()
                complete_command(command, row.id, "ai_disclosure")
                record_ai_event(
                    session,
                    context,
                    target_id=run.id,
                    action="ai.disclosure_revised" if revision else "ai.disclosure_decided",
                    details={
                        "disclosure_id": str(row.id),
                        "revision": row.revision,
                        "status": row.status,
                        "content_digest": candidate_digest(row),
                    },
                    reason=request.reason if isinstance(request, AiDisclosureDecision) else None,
                )
            result = snapshot(session, context, row, run)
            unit.commit()
            return result
