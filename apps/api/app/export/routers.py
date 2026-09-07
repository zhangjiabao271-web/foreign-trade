from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.documents.enums import DocumentType
from app.export.schemas import (
    CaseCommand,
    CaseReject,
    CustomsClear,
    CustomsCreate,
    CustomsListResponse,
    CustomsResponse,
    FollowUpSchedule,
    ManualSubmission,
    RefundCreate,
    RefundListResponse,
    RefundReceived,
    RefundResponse,
)
from app.export.services import ExportCommandService, ExportQueryService
from app.work.schemas import ActivityPageResponse, ActivityResponse

router = APIRouter(prefix="/api/v1", tags=["export"], responses=PROBLEM_RESPONSES)
DatabaseSession = Annotated[Session, Depends(get_database_session)]
SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
Reader = Annotated[RequestContext, Depends(require_permissions(Permission.EXPORT_READ))]
Writer = Annotated[RequestContext, Depends(require_permissions(Permission.EXPORT_WRITE))]
CommandKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=255)]


def customs_response(case: CustomsResponse, missing: list[str]) -> CustomsResponse:
    return CustomsResponse(
        **CustomsResponse.model_validate(case).model_dump(exclude={"missing_document_types"}),
        missing_document_types=[DocumentType(value) for value in missing],
    )


def refund_response(case: RefundResponse, missing: list[str]) -> RefundResponse:
    return RefundResponse(
        **RefundResponse.model_validate(case).model_dump(exclude={"missing_document_types"}),
        missing_document_types=[DocumentType(value) for value in missing],
    )


@router.post("/customs-declarations/{case_id}/schedule-follow-up", response_model=CustomsResponse)
def schedule_customs_follow_up(
    case_id: UUID, request: FollowUpSchedule, context: Writer, factory: SessionFactory
) -> CustomsResponse:
    case, missing = ExportCommandService(factory).schedule_follow_up(
        context, case_id, request, refund=False
    )
    assert isinstance(case, CustomsResponse)
    return customs_response(case, missing)


@router.post("/tax-refund-cases/{case_id}/schedule-follow-up", response_model=RefundResponse)
def schedule_refund_follow_up(
    case_id: UUID, request: FollowUpSchedule, context: Writer, factory: SessionFactory
) -> RefundResponse:
    case, missing = ExportCommandService(factory).schedule_follow_up(
        context, case_id, request, refund=True
    )
    assert isinstance(case, RefundResponse)
    return refund_response(case, missing)


@router.get("/customs-declarations", response_model=CustomsListResponse)
def list_customs(
    context: Reader,
    session: DatabaseSession,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> CustomsListResponse:
    rows, missing, has_more = ExportQueryService(session).customs_page(
        context, cursor=cursor, limit=limit
    )
    return CustomsListResponse(
        items=[customs_response(row, missing[row.id]) for row in rows],
        has_more=has_more,
        next_cursor=str(rows[-1].id) if has_more else None,
    )


@router.get("/customs-declarations/{case_id}", response_model=CustomsResponse)
def read_customs(case_id: UUID, context: Reader, session: DatabaseSession) -> CustomsResponse:
    return customs_response(*ExportQueryService(session).customs(context, case_id))


@router.get("/customs-declarations/{case_id}/activities", response_model=ActivityPageResponse)
def customs_activities(
    case_id: UUID,
    context: Reader,
    session: DatabaseSession,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ActivityPageResponse:
    rows, has_more = ExportQueryService(session).activities(
        context, case_id, refund=False, cursor=cursor, limit=limit
    )
    return ActivityPageResponse(
        items=[ActivityResponse.model_validate(row) for row in rows],
        has_more=has_more,
        next_cursor=rows[-1].id if has_more else None,
    )


@router.post("/customs-declarations", response_model=CustomsResponse, status_code=201)
def create_customs(
    request: CustomsCreate, context: Writer, factory: SessionFactory, idempotency_key: CommandKey
) -> CustomsResponse:
    return customs_response(
        *ExportCommandService(factory).create_customs(context, request, key=idempotency_key)
    )


@router.post("/customs-declarations/{case_id}/prepare", response_model=CustomsResponse)
def prepare_customs(
    case_id: UUID, request: CaseCommand, context: Writer, factory: SessionFactory
) -> CustomsResponse:
    return customs_response(
        *ExportCommandService(factory).customs_command(context, case_id, "prepare", request)
    )


@router.post("/customs-declarations/{case_id}/ready", response_model=CustomsResponse)
def ready_customs(
    case_id: UUID, request: CaseCommand, context: Writer, factory: SessionFactory
) -> CustomsResponse:
    return customs_response(
        *ExportCommandService(factory).customs_command(context, case_id, "ready", request)
    )


@router.post("/customs-declarations/{case_id}/submit", response_model=CustomsResponse)
def submit_customs(
    case_id: UUID, request: ManualSubmission, context: Writer, factory: SessionFactory
) -> CustomsResponse:
    return customs_response(
        *ExportCommandService(factory).customs_command(context, case_id, "submit", request)
    )


@router.post("/customs-declarations/{case_id}/clear", response_model=CustomsResponse)
def clear_customs(
    case_id: UUID, request: CustomsClear, context: Writer, factory: SessionFactory
) -> CustomsResponse:
    return customs_response(
        *ExportCommandService(factory).customs_command(context, case_id, "clear", request)
    )


@router.post("/customs-declarations/{case_id}/reject", response_model=CustomsResponse)
def reject_customs(
    case_id: UUID, request: CaseReject, context: Writer, factory: SessionFactory
) -> CustomsResponse:
    return customs_response(
        *ExportCommandService(factory).customs_command(context, case_id, "reject", request)
    )


@router.get("/tax-refund-cases", response_model=RefundListResponse)
def list_refund(
    context: Reader,
    session: DatabaseSession,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> RefundListResponse:
    rows, missing, has_more = ExportQueryService(session).refund_page(
        context, cursor=cursor, limit=limit
    )
    return RefundListResponse(
        items=[refund_response(row, missing[row.id]) for row in rows],
        has_more=has_more,
        next_cursor=str(rows[-1].id) if has_more else None,
    )


@router.get("/tax-refund-cases/{case_id}", response_model=RefundResponse)
def read_refund(case_id: UUID, context: Reader, session: DatabaseSession) -> RefundResponse:
    return refund_response(*ExportQueryService(session).refund(context, case_id))


@router.get("/tax-refund-cases/{case_id}/activities", response_model=ActivityPageResponse)
def refund_activities(
    case_id: UUID,
    context: Reader,
    session: DatabaseSession,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> ActivityPageResponse:
    rows, has_more = ExportQueryService(session).activities(
        context, case_id, refund=True, cursor=cursor, limit=limit
    )
    return ActivityPageResponse(
        items=[ActivityResponse.model_validate(row) for row in rows],
        has_more=has_more,
        next_cursor=rows[-1].id if has_more else None,
    )


@router.post("/tax-refund-cases", response_model=RefundResponse, status_code=201)
def create_refund(
    request: RefundCreate, context: Writer, factory: SessionFactory, idempotency_key: CommandKey
) -> RefundResponse:
    return refund_response(
        *ExportCommandService(factory).create_refund(context, request, key=idempotency_key)
    )


@router.post("/tax-refund-cases/{case_id}/prepare", response_model=RefundResponse)
def prepare_refund(
    case_id: UUID, request: CaseCommand, context: Writer, factory: SessionFactory
) -> RefundResponse:
    return refund_response(
        *ExportCommandService(factory).refund_command(context, case_id, "prepare", request)
    )


@router.post("/tax-refund-cases/{case_id}/ready", response_model=RefundResponse)
def ready_refund(
    case_id: UUID, request: CaseCommand, context: Writer, factory: SessionFactory
) -> RefundResponse:
    return refund_response(
        *ExportCommandService(factory).refund_command(context, case_id, "ready", request)
    )


@router.post("/tax-refund-cases/{case_id}/submit", response_model=RefundResponse)
def submit_refund(
    case_id: UUID, request: ManualSubmission, context: Writer, factory: SessionFactory
) -> RefundResponse:
    return refund_response(
        *ExportCommandService(factory).refund_command(context, case_id, "submit", request)
    )


@router.post("/tax-refund-cases/{case_id}/process", response_model=RefundResponse)
def process_refund(
    case_id: UUID, request: CaseCommand, context: Writer, factory: SessionFactory
) -> RefundResponse:
    return refund_response(
        *ExportCommandService(factory).refund_command(context, case_id, "process", request)
    )


@router.post("/tax-refund-cases/{case_id}/receive", response_model=RefundResponse)
def receive_refund(
    case_id: UUID, request: RefundReceived, context: Writer, factory: SessionFactory
) -> RefundResponse:
    return refund_response(
        *ExportCommandService(factory).refund_command(context, case_id, "receive", request)
    )


@router.post("/tax-refund-cases/{case_id}/reject", response_model=RefundResponse)
def reject_refund(
    case_id: UUID, request: CaseReject, context: Writer, factory: SessionFactory
) -> RefundResponse:
    return refund_response(
        *ExportCommandService(factory).refund_command(context, case_id, "reject", request)
    )
