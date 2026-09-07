from collections.abc import Sequence
from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.unit_of_work import UnitOfWork
from app.documents.checklists import missing_document_types
from app.documents.enums import DocumentLinkTargetType
from app.export.content import case_response
from app.export.enums import CustomsStatus, TaxRefundStatus
from app.export.models import CustomsDeclaration, TaxRefundCase
from app.export.repositories import CustomsRepository, RefundRepository
from app.export.schemas import (
    CaseCommand,
    CaseReject,
    CustomsClear,
    CustomsCreate,
    CustomsResponse,
    FollowUpSchedule,
    ManualSubmission,
    RefundCreate,
    RefundReceived,
    RefundResponse,
)
from app.fulfillment.repositories import ShipmentRepository
from app.platform.idempotency import begin_command, complete_command
from app.platform.numbering import next_document_number
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.work.content import activity_response
from app.work.models import Activity
from app.work.schemas import ActivityResponse
from app.work.timeline import activity_page

type ExportCase = CustomsDeclaration | TaxRefundCase
type TransitionRequest = CaseCommand | ManualSubmission | CustomsClear | RefundReceived | CaseReject

CUSTOMS_TRANSITIONS = {
    "prepare": (CustomsStatus.DRAFT, CustomsStatus.DOCUMENTS_PENDING),
    "ready": (CustomsStatus.DOCUMENTS_PENDING, CustomsStatus.READY),
    "submit": (CustomsStatus.READY, CustomsStatus.SUBMITTED),
    "clear": (CustomsStatus.SUBMITTED, CustomsStatus.CLEARED),
    "reject": (CustomsStatus.SUBMITTED, CustomsStatus.REJECTED),
}
REFUND_TRANSITIONS = {
    "prepare": (TaxRefundStatus.NOT_READY, TaxRefundStatus.DOCUMENTS_PENDING),
    "ready": (TaxRefundStatus.DOCUMENTS_PENDING, TaxRefundStatus.READY),
    "submit": (TaxRefundStatus.READY, TaxRefundStatus.SUBMITTED),
    "process": (TaxRefundStatus.SUBMITTED, TaxRefundStatus.PROCESSING),
    "receive": (TaxRefundStatus.PROCESSING, TaxRefundStatus.REFUNDED),
    "reject": (TaxRefundStatus.PROCESSING, TaxRefundStatus.REJECTED),
}

EVENT_VERBS = {
    "created": "created",
    "follow_up": "follow_up_scheduled",
    "prepare": "documents_requested",
    "ready": "readiness_confirmed",
    "submit": "submitted",
    "clear": "cleared",
    "reject": "rejected",
    "process": "processing_recorded",
    "receive": "refund_received",
}


def case_not_found() -> ApiProblem:
    return ApiProblem(
        404, "EXPORT_CASE_NOT_FOUND", "Case not found", "The export case was not found."
    )


def case_target(case: ExportCase) -> DocumentLinkTargetType:
    return (
        DocumentLinkTargetType.CUSTOMS_DECLARATION
        if isinstance(case, CustomsDeclaration)
        else DocumentLinkTargetType.TAX_REFUND_CASE
    )


def checklist(session: Session, context: RequestContext, case: ExportCase) -> list[str]:
    return missing_document_types(
        session,
        organization_id=context.organization_id,
        target_type=case_target(case),
        requirements={case.id: case.required_document_types},
    )[case.id]


class ExportQueryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def activities(
        self,
        context: RequestContext,
        case_id: UUID,
        *,
        refund: bool,
        cursor: UUID | None,
        limit: int,
    ) -> tuple[Sequence[ActivityResponse], bool]:
        context.require(Permission.EXPORT_READ)
        repository = RefundRepository(self.session) if refund else CustomsRepository(self.session)
        if repository.get(organization_id=context.organization_id, record_id=case_id) is None:
            raise case_not_found()
        rows, has_more = activity_page(
            self.session,
            organization_id=context.organization_id,
            subject_type="tax_refund_case" if refund else "customs_declaration",
            subject_id=case_id,
            cursor=cursor,
            limit=limit,
        )
        return [activity_response(context, row) for row in rows], has_more

    def customs(
        self, context: RequestContext, record_id: UUID
    ) -> tuple[CustomsResponse, list[str]]:
        context.require(Permission.EXPORT_READ)
        case = CustomsRepository(self.session).get(
            organization_id=context.organization_id, record_id=record_id
        )
        if case is None:
            raise case_not_found()
        return case_response(context, case), checklist(self.session, context, case)

    def refund(self, context: RequestContext, record_id: UUID) -> tuple[RefundResponse, list[str]]:
        context.require(Permission.EXPORT_READ)
        case = RefundRepository(self.session).get(
            organization_id=context.organization_id, record_id=record_id
        )
        if case is None:
            raise case_not_found()
        return case_response(context, case), checklist(self.session, context, case)

    def customs_page(
        self, context: RequestContext, *, cursor: UUID | None, limit: int
    ) -> tuple[Sequence[CustomsResponse], dict[UUID, list[str]], bool]:
        context.require(Permission.EXPORT_READ)
        rows = CustomsRepository(self.session).page(
            organization_id=context.organization_id, cursor=cursor, limit=limit
        )
        page = rows[:limit]
        missing = missing_document_types(
            self.session,
            organization_id=context.organization_id,
            target_type=DocumentLinkTargetType.CUSTOMS_DECLARATION,
            requirements={row.id: row.required_document_types for row in page},
        )
        return [case_response(context, row) for row in page], missing, len(rows) > limit

    def refund_page(
        self, context: RequestContext, *, cursor: UUID | None, limit: int
    ) -> tuple[Sequence[RefundResponse], dict[UUID, list[str]], bool]:
        context.require(Permission.EXPORT_READ)
        rows = RefundRepository(self.session).page(
            organization_id=context.organization_id, cursor=cursor, limit=limit
        )
        page = rows[:limit]
        missing = missing_document_types(
            self.session,
            organization_id=context.organization_id,
            target_type=DocumentLinkTargetType.TAX_REFUND_CASE,
            requirements={row.id: row.required_document_types for row in page},
        )
        return [case_response(context, row) for row in page], missing, len(rows) > limit


class ExportCommandService:
    def __init__(
        self,
        factory: sessionmaker[Session],
        *,
        audit: AuditRecorder | None = None,
        outbox: OutboxRecorder | None = None,
    ) -> None:
        self.factory = factory
        self.audit = audit or AuditRecorder()
        self.outbox = outbox or OutboxRecorder()

    def schedule_follow_up(
        self, context: RequestContext, case_id: UUID, request: FollowUpSchedule, *, refund: bool
    ) -> tuple[CustomsResponse | RefundResponse, list[str]]:
        context.require(Permission.EXPORT_WRITE)
        with UnitOfWork(self.factory) as unit:
            repository = (
                RefundRepository(unit.session) if refund else CustomsRepository(unit.session)
            )
            case = repository.locked(organization_id=context.organization_id, record_id=case_id)
            if case is None:
                raise case_not_found()
            if case.version != request.expected_version:
                raise ApiProblem(409, "VERSION_CONFLICT", "Version conflict", "Reload this case.")
            if case.status in {
                CustomsStatus.CLEARED,
                CustomsStatus.REJECTED,
                TaxRefundStatus.REFUNDED,
                TaxRefundStatus.REJECTED,
            }:
                raise ApiProblem(
                    409,
                    "EXPORT_CASE_FINALIZED",
                    "Finalized case",
                    "Finalized cases cannot be rescheduled.",
                )
            before: dict[str, object] = {
                "follow_up_date": str(case.follow_up_date) if case.follow_up_date else None
            }
            case.follow_up_date = request.follow_up_date
            case.updated_by = context.user_id
            self._record(
                unit.session, context, case, "follow_up", before=before, reason=request.reason
            )
            unit.session.flush()
            missing = checklist(unit.session, context, case)
            unit.commit()
            return case_response(context, case), missing

    def create_customs(
        self, context: RequestContext, request: CustomsCreate, *, key: str
    ) -> tuple[CustomsResponse, list[str]]:
        context.require(Permission.EXPORT_WRITE)
        with UnitOfWork(self.factory) as unit:
            session = unit.session
            command = begin_command(
                session, context, scope="customs.create", key=key, payload=request.model_dump()
            )
            if command.resource_id is not None:
                case = CustomsRepository(session).get(
                    organization_id=context.organization_id, record_id=command.resource_id
                )
                if case is None:
                    raise case_not_found()
                missing = checklist(session, context, case)
                unit.commit()
                return case_response(context, case), missing
            shipment = ShipmentRepository(session).get_for_update(
                organization_id=context.organization_id, shipment_id=request.shipment_id
            )
            if shipment is None:
                raise ApiProblem(
                    404, "SHIPMENT_NOT_FOUND", "Shipment not found", "Shipment not found."
                )
            if (
                CustomsRepository(session).by_shipment(
                    organization_id=context.organization_id, shipment_id=shipment.id
                )
                is not None
            ):
                raise ApiProblem(
                    409,
                    "CUSTOMS_ALREADY_EXISTS",
                    "Declaration exists",
                    "Open the existing declaration for this shipment.",
                )
            case = CustomsDeclaration(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                declaration_number=next_document_number(session, context, "CUSTOMS", "CUS"),
                status=CustomsStatus.DRAFT,
                **request.model_dump(),
            )
            session.add(case)
            session.flush()
            self._record(session, context, case, "created", before=None, reason=request.notes)
            complete_command(command, case.id, "customs_declaration")
            missing = checklist(session, context, case)
            unit.commit()
            return case_response(context, case), missing

    def create_refund(
        self, context: RequestContext, request: RefundCreate, *, key: str
    ) -> tuple[RefundResponse, list[str]]:
        context.require(Permission.EXPORT_WRITE)
        with UnitOfWork(self.factory) as unit:
            session = unit.session
            command = begin_command(
                session, context, scope="refund.create", key=key, payload=request.model_dump()
            )
            if command.resource_id is not None:
                case = RefundRepository(session).get(
                    organization_id=context.organization_id, record_id=command.resource_id
                )
                if case is None:
                    raise case_not_found()
                missing = checklist(session, context, case)
                unit.commit()
                return case_response(context, case), missing
            declaration = CustomsRepository(session).locked(
                organization_id=context.organization_id, record_id=request.customs_declaration_id
            )
            if declaration is None:
                raise case_not_found()
            if declaration.status == CustomsStatus.REJECTED:
                raise ApiProblem(
                    409,
                    "CUSTOMS_REJECTED",
                    "Declaration rejected",
                    "A rejected declaration cannot support a refund case.",
                )
            if (
                RefundRepository(session).by_declaration(
                    organization_id=context.organization_id, declaration_id=declaration.id
                )
                is not None
            ):
                raise ApiProblem(
                    409, "REFUND_ALREADY_EXISTS", "Refund case exists", "Open the existing case."
                )
            case = TaxRefundCase(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                case_number=next_document_number(session, context, "TAX_REFUND", "REF"),
                status=TaxRefundStatus.NOT_READY,
                currency_code=declaration.currency_code,
                **request.model_dump(),
            )
            session.add(case)
            session.flush()
            self._record(session, context, case, "created", before=None, reason=request.notes)
            complete_command(command, case.id, "tax_refund_case")
            missing = checklist(session, context, case)
            unit.commit()
            return case_response(context, case), missing

    def customs_command(
        self, context: RequestContext, case_id: UUID, command: str, request: TransitionRequest
    ) -> tuple[CustomsResponse, list[str]]:
        context.require(Permission.EXPORT_WRITE)
        with UnitOfWork(self.factory) as unit:
            case = CustomsRepository(unit.session).locked(
                organization_id=context.organization_id, record_id=case_id
            )
            if case is None:
                raise case_not_found()
            self._transition(unit.session, context, case, command, request)
            missing = checklist(unit.session, context, case)
            unit.commit()
            return case_response(context, case), missing

    def refund_command(
        self, context: RequestContext, case_id: UUID, command: str, request: TransitionRequest
    ) -> tuple[RefundResponse, list[str]]:
        context.require(Permission.EXPORT_WRITE)
        with UnitOfWork(self.factory) as unit:
            case = RefundRepository(unit.session).locked(
                organization_id=context.organization_id, record_id=case_id
            )
            if case is None:
                raise case_not_found()
            self._transition(unit.session, context, case, command, request)
            missing = checklist(unit.session, context, case)
            unit.commit()
            return case_response(context, case), missing

    def _transition(
        self,
        session: Session,
        context: RequestContext,
        case: ExportCase,
        command: str,
        request: TransitionRequest,
    ) -> None:
        transitions = (
            CUSTOMS_TRANSITIONS if isinstance(case, CustomsDeclaration) else REFUND_TRANSITIONS
        )
        if command not in transitions:
            raise ApiProblem(
                400, "UNKNOWN_EXPORT_COMMAND", "Unknown command", "Unsupported export command."
            )
        source, target = transitions[command]
        if case.version != request.expected_version:
            raise ApiProblem(
                409, "VERSION_CONFLICT", "Version conflict", "Reload this case before proceeding."
            )
        if case.status != source:
            raise ApiProblem(
                409,
                "INVALID_STATE_TRANSITION",
                "Invalid state",
                f"The {command} command requires {source}.",
            )
        if command in {"ready", "submit"}:
            if checklist(session, context, case):
                raise ApiProblem(
                    409,
                    "EXPORT_DOCUMENTS_INCOMPLETE",
                    "Documents incomplete",
                    "Upload and scan the required documents for this case.",
                )
            if isinstance(case, TaxRefundCase):
                declaration = CustomsRepository(session).get(
                    organization_id=context.organization_id, record_id=case.customs_declaration_id
                )
                if declaration is None or declaration.status != CustomsStatus.CLEARED:
                    raise ApiProblem(
                        409,
                        "CUSTOMS_NOT_CLEARED",
                        "Customs not cleared",
                        "Record customs clearance before refund readiness.",
                    )
        self._apply_manual_fact(case, command, request)
        previous = case.status
        case.status = target
        case.updated_by = context.user_id
        self._record(
            session, context, case, command, before={"status": previous}, reason=request.reason
        )
        session.flush()

    @staticmethod
    def _apply_manual_fact(case: ExportCase, command: str, request: TransitionRequest) -> None:
        if command == "submit":
            if not isinstance(request, ManualSubmission):
                raise ApiProblem(
                    422,
                    "SUBMISSION_FACT_REQUIRED",
                    "Submission fact required",
                    "Provide the manual reference and submission date.",
                )
            case.external_reference = request.external_reference
            case.submitted_on = request.occurred_on
        elif command == "clear" and isinstance(case, CustomsDeclaration):
            if not isinstance(request, CustomsClear):
                raise ApiProblem(
                    422, "CLEARANCE_DATE_REQUIRED", "Date required", "Provide clearance date."
                )
            ExportCommandService._check_date(case.submitted_on, request.occurred_on)
            case.cleared_on = request.occurred_on
        elif command == "receive" and isinstance(case, TaxRefundCase):
            if not isinstance(request, RefundReceived):
                raise ApiProblem(
                    422, "REFUND_FACT_REQUIRED", "Refund fact required", "Provide amount and date."
                )
            ExportCommandService._check_date(case.submitted_on, request.occurred_on)
            if request.refunded_amount > case.expected_amount:
                raise ApiProblem(
                    409,
                    "REFUND_AMOUNT_EXCEEDED",
                    "Refund amount exceeded",
                    "The recorded refund cannot exceed the case estimate.",
                )
            case.refunded_amount = request.refunded_amount
            case.refunded_on = request.occurred_on
        elif command == "reject":
            if not isinstance(request, CaseReject):
                raise ApiProblem(
                    422, "REJECTION_REASON_REQUIRED", "Reason required", "Provide rejection reason."
                )
            case.rejection_reason = request.reason

    @staticmethod
    def _check_date(submitted: date | None, occurred: date) -> None:
        if submitted is None or occurred < submitted:
            raise ApiProblem(
                409,
                "EXPORT_DATE_INVALID",
                "Invalid event date",
                "Completion cannot be earlier than manual submission.",
            )

    def _record(
        self,
        session: Session,
        context: RequestContext,
        case: ExportCase,
        verb: str,
        *,
        before: dict[str, object] | None,
        reason: str | None,
    ) -> None:
        subject = (
            "customs_declaration" if isinstance(case, CustomsDeclaration) else "tax_refund_case"
        )
        action = f"{subject}.{EVENT_VERBS[verb]}"
        after: dict[str, object] = {"status": case.status, "manual_tracking_only": True}
        after.update(
            follow_up_date=str(case.follow_up_date) if case.follow_up_date else None,
            external_reference=case.external_reference,
            submitted_on=str(case.submitted_on) if case.submitted_on else None,
            rejection_reason=case.rejection_reason,
        )
        if isinstance(case, TaxRefundCase):
            after.update(
                expected_amount=str(case.expected_amount),
                refunded_amount=str(case.refunded_amount),
                refunded_on=str(case.refunded_on) if case.refunded_on else None,
            )
        else:
            after["declared_amount"] = str(case.declared_amount)
            after["cleared_on"] = str(case.cleared_on) if case.cleared_on else None
        session.add(
            Activity(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                subject_type=subject,
                subject_id=case.id,
                activity_type=action,
                summary=f"Manual {subject}: {verb}",
                details=after,
                correlation_id=context.request_id,
            )
        )
        self.audit.record(
            session,
            context,
            action=action,
            target_type=subject,
            target_id=case.id,
            before=before,
            after=after,
            reason=reason,
        )
        self.outbox.record(
            session,
            context,
            DomainEvent(
                f"{action}.v1",
                subject,
                case.id,
                {"case_id": str(case.id), "status": case.status},
            ),
        )
