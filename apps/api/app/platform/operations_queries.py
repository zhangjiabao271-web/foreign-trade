from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.ai.models import AiRun, ApprovalRequest
from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.core.observability import LATENCY_BOUNDS_MS, RequestMetrics, request_metrics
from app.documents.models import DocumentVersion
from app.platform.models import AsyncJob, OutboxEvent, ProcessedEvent
from app.platform.operations_schemas import OperationsResponse, RequestMetricsResponse

StateModel = (
    type[AiRun] | type[ApprovalRequest] | type[DocumentVersion] | type[AsyncJob] | type[OutboxEvent]
)


class OperationsQuery:
    def __init__(self, session: Session, metrics: RequestMetrics | None = None) -> None:
        self.session = session
        self.metrics = metrics if metrics is not None else request_metrics

    def _states(self, organization_id: UUID, model: StateModel) -> dict[str, int]:
        rows = self.session.execute(
            select(model.status, func.count())
            .where(model.organization_id == organization_id, model.deleted_at.is_(None))
            .group_by(model.status)
        )
        return {row[0]: row[1] for row in rows}

    def read(self, context: RequestContext) -> OperationsResponse:
        context.require(Permission.OPERATIONS_MONITOR)
        organization_id = context.organization_id
        captured = datetime.now(UTC)
        consumed = (
            select(ProcessedEvent.event_id)
            .where(
                ProcessedEvent.organization_id == organization_id,
                ProcessedEvent.event_id == OutboxEvent.id,
                ProcessedEvent.consumer_name == func.concat("worker.", OutboxEvent.event_type),
            )
            .exists()
        )
        awaiting_count, oldest = self.session.execute(
            select(func.count(), func.min(OutboxEvent.created_at)).where(
                OutboxEvent.organization_id == organization_id,
                OutboxEvent.deleted_at.is_(None),
                OutboxEvent.status.in_(["PENDING", "PROCESSING", "PUBLISHED"]),
                ~consumed,
            )
        ).one()
        costs = self.session.execute(
            select(
                func.coalesce(func.sum(AiRun.estimated_cost_usd), 0),
                func.count().filter(AiRun.estimated_cost_usd.is_(None)),
                func.coalesce(func.sum(AiRun.input_tokens), 0),
                func.coalesce(func.sum(AiRun.output_tokens), 0),
            ).where(AiRun.organization_id == organization_id, AiRun.deleted_at.is_(None))
        ).one()
        approvals = self._states(organization_id, ApprovalRequest)
        decided = approvals.get("APPROVED", 0) + approvals.get("REJECTED", 0)
        rate = Decimal(approvals.get("APPROVED", 0)) / Decimal(decided) if decided else None
        raw_metrics = self.metrics.snapshot(organization_id)
        return OperationsResponse(
            captured_at=captured,
            outbox_states=self._states(organization_id, OutboxEvent),
            awaiting_consumer_count=awaiting_count,
            oldest_awaiting_seconds=max(0, (captured - oldest).total_seconds()) if oldest else None,
            job_states=self._states(organization_id, AsyncJob),
            document_states=self._states(organization_id, DocumentVersion),
            ai_run_states=self._states(organization_id, AiRun),
            approval_states=approvals,
            approval_rate=rate,
            known_estimated_cost_usd=Decimal(costs[0]),
            unknown_cost_runs=costs[1],
            ai_input_tokens=costs[2],
            ai_output_tokens=costs[3],
            request_metrics=RequestMetricsResponse.model_validate(raw_metrics)
            if raw_metrics
            else None,
            latency_upper_bounds_ms=[*LATENCY_BOUNDS_MS, None],
        )
