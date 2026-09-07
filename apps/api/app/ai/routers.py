from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session, sessionmaker

from app.ai.approvals import ApprovalService
from app.ai.disclosure import AiDisclosureService
from app.ai.schemas import (
    AiApprovalRequest,
    AiDisclosureDecision,
    AiDisclosureList,
    AiDisclosureResponse,
    AiDisclosureRevision,
    AiDisclosureSubmit,
    AiRunCreate,
    AiRunList,
    AiRunResponse,
    AiToolCallResponse,
    ApprovalDecision,
    ApprovalList,
    ApprovalResponse,
)
from app.ai.services import AiCommandService, AiQueryService
from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.core.config import get_settings

router = APIRouter(prefix="/api/v1/ai", tags=["ai"], responses=PROBLEM_RESPONSES)
Reader = Annotated[RequestContext, Depends(require_permissions(Permission.AI_READ))]
Runner = Annotated[RequestContext, Depends(require_permissions(Permission.AI_RUN))]
Database = Annotated[Session, Depends(get_database_session)]
Factory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
Approver = Annotated[RequestContext, Depends(require_permissions(Permission.AI_APPROVE))]


@router.post("/runs/{run_id}/request-approval", response_model=ApprovalResponse, status_code=201)
def request_approval(
    run_id: UUID, request: AiApprovalRequest, context: Runner, factory: Factory
) -> ApprovalResponse:
    return ApprovalResponse.model_validate(
        ApprovalService(factory).request(context, run_id, request)
    )


@router.get("/approvals", response_model=ApprovalList)
def list_approvals(
    context: Reader,
    session: Database,
    factory: Factory,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> ApprovalList:
    rows = ApprovalService(factory).page(session, context, cursor=cursor, limit=limit)
    items = rows[:limit]
    return ApprovalList(
        items=[ApprovalResponse.model_validate(row) for row in items],
        has_more=len(rows) > limit,
        next_cursor=str(items[-1].id) if len(rows) > limit else None,
    )


@router.get("/approvals/{approval_id}", response_model=ApprovalResponse)
def read_approval(
    approval_id: UUID, context: Reader, session: Database, factory: Factory
) -> ApprovalResponse:
    return ApprovalResponse.model_validate(
        ApprovalService(factory).get(session, context, approval_id)
    )


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalResponse)
def approve(
    approval_id: UUID, request: ApprovalDecision, context: Approver, factory: Factory
) -> ApprovalResponse:
    return ApprovalResponse.model_validate(
        ApprovalService(factory).decide(context, approval_id, request, approve=True)
    )


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalResponse)
def reject(
    approval_id: UUID, request: ApprovalDecision, context: Approver, factory: Factory
) -> ApprovalResponse:
    return ApprovalResponse.model_validate(
        ApprovalService(factory).decide(context, approval_id, request, approve=False)
    )


@router.post("/runs", response_model=AiRunResponse, status_code=202)
def create_run(
    request: AiRunCreate,
    context: Runner,
    factory: Factory,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=255)],
) -> AiRunResponse:
    return AiRunResponse.model_validate(
        AiCommandService(factory, get_settings()).create(context, request, key=idempotency_key)
    )


@router.get("/runs", response_model=AiRunList)
def list_runs(
    context: Reader,
    session: Database,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> AiRunList:
    rows = AiQueryService(session).page(context, cursor=cursor, limit=limit)
    items = rows[:limit]
    return AiRunList(
        items=[AiRunResponse.model_validate(row) for row in items],
        has_more=len(rows) > limit,
        next_cursor=str(items[-1].id) if len(rows) > limit else None,
    )


@router.get("/runs/{run_id}", response_model=AiRunResponse)
def read_run(run_id: UUID, context: Reader, session: Database) -> AiRunResponse:
    return AiQueryService(session).get(context, run_id)


@router.get("/runs/{run_id}/tool-calls", response_model=list[AiToolCallResponse])
def read_tool_calls(run_id: UUID, context: Reader, session: Database) -> list[AiToolCallResponse]:
    return [
        AiToolCallResponse.model_validate(row)
        for row in AiQueryService(session).calls(context, run_id)
    ]


Reviewer = Annotated[
    RequestContext, Depends(require_permissions(Permission.AI_READ, Permission.PROFIT_READ))
]
CommandKey = Annotated[str, Header(min_length=1, max_length=255)]


@router.post(
    "/runs/{run_id}/submit-disclosure", response_model=AiDisclosureResponse, status_code=201
)
def submit_disclosure(
    run_id: UUID,
    request: AiDisclosureSubmit,
    context: Runner,
    factory: Factory,
    idempotency_key: CommandKey,
) -> AiDisclosureResponse:
    return AiDisclosureService(factory).submit(context, run_id, request, key=idempotency_key)


@router.get("/disclosures", response_model=AiDisclosureList)
def list_disclosures(
    context: Reader,
    factory: Factory,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> AiDisclosureList:
    rows = AiDisclosureService(factory).page(context, cursor=cursor, limit=limit)
    items = rows[:limit]
    return AiDisclosureList(
        items=items,
        has_more=len(rows) > limit,
        next_cursor=str(items[-1].id) if len(rows) > limit else None,
    )


@router.get("/disclosures/{record_id}", response_model=AiDisclosureResponse)
def read_disclosure(record_id: UUID, context: Reader, factory: Factory) -> AiDisclosureResponse:
    return AiDisclosureService(factory).inspect(context, record_id)


@router.post("/disclosures/{record_id}/decide", response_model=AiDisclosureResponse)
def decide_disclosure(
    record_id: UUID,
    request: AiDisclosureDecision,
    context: Reviewer,
    factory: Factory,
    idempotency_key: CommandKey,
) -> AiDisclosureResponse:
    return AiDisclosureService(factory).change(context, record_id, request, key=idempotency_key)


@router.post(
    "/disclosures/{record_id}/revise", response_model=AiDisclosureResponse, status_code=201
)
def revise_disclosure(
    record_id: UUID,
    request: AiDisclosureRevision,
    context: Reviewer,
    factory: Factory,
    idempotency_key: CommandKey,
) -> AiDisclosureResponse:
    return AiDisclosureService(factory).change(context, record_id, request, key=idempotency_key)
