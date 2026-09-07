from collections.abc import Sequence
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.companies.models import Company
from app.core.unit_of_work import UnitOfWork
from app.crm.enums import OpportunityStatus
from app.crm.opportunity_services import advance_from_evidence, opportunity_record
from app.inquiries.content import response
from app.inquiries.enums import InquiryStatus
from app.inquiries.models import Inquiry
from app.inquiries.repositories import InquiryRepository
from app.inquiries.schemas import InquiryCreate, InquiryResponse
from app.platform.idempotency import begin_command, complete_command
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.work.models import Activity


class InquiryQueryService:
    def __init__(self, repository: InquiryRepository) -> None:
        self._repository = repository

    def list(
        self,
        context: RequestContext,
        *,
        status: InquiryStatus | None,
        limit: int,
        cursor: UUID | None = None,
    ) -> Sequence[InquiryResponse]:
        context.require(Permission.INQUIRY_READ)
        rows = self._repository.search(
            organization_id=context.organization_id, status=status, limit=limit, cursor=cursor
        )
        return [response(context, row) for row in rows]

    def get(self, context: RequestContext, inquiry_id: UUID) -> InquiryResponse:
        context.require(Permission.INQUIRY_READ)
        inquiry = self._repository.get(
            organization_id=context.organization_id, record_id=inquiry_id
        )
        if inquiry is None:
            raise ApiProblem(
                404, "INQUIRY_NOT_FOUND", "Inquiry not found", "The inquiry was not found."
            )
        return response(context, inquiry)


class InquiryCommandService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        audit_recorder: AuditRecorder | None = None,
        outbox_recorder: OutboxRecorder | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._audit_recorder = audit_recorder or AuditRecorder()
        self._outbox_recorder = outbox_recorder or OutboxRecorder()

    def create(
        self, context: RequestContext, data: dict[str, object], *, key: str | None = None
    ) -> InquiryResponse:
        context.require(Permission.INQUIRY_WRITE)
        data = InquiryCreate.model_validate(data).model_dump()
        with UnitOfWork(self._session_factory) as unit_of_work:
            command = begin_command(
                unit_of_work.session,
                context,
                scope="inquiry.create",
                key=key if key is not None else str(uuid4()),
                payload=data,
            )
            if command.resource_id is not None:
                original = InquiryRepository(unit_of_work.session).get_for_update(
                    organization_id=context.organization_id, inquiry_id=command.resource_id
                )
                if original is None:
                    raise ApiProblem(
                        404, "INQUIRY_NOT_FOUND", "Inquiry not found", "The inquiry was not found."
                    )
                result = response(context, original)
                unit_of_work.commit()
                return result
            opportunity = opportunity_record(
                unit_of_work.session, context, UUID(str(data["opportunity_id"])), lock=True
            )
            company = unit_of_work.session.scalar(
                select(Company).where(
                    Company.id == data["company_id"],
                    Company.organization_id == context.organization_id,
                    Company.deleted_at.is_(None),
                )
            )
            if company is None or opportunity.company_id != company.id:
                raise ApiProblem(
                    404,
                    "COMPANY_NOT_FOUND",
                    "Company not found",
                    "The company was not found for this opportunity.",
                )
            if opportunity.status not in {OpportunityStatus.OPEN, OpportunityStatus.INQUIRY}:
                raise ApiProblem(
                    409,
                    "INVALID_STATE_TRANSITION",
                    "Invalid state transition",
                    "Opportunity cannot receive an inquiry in its current state.",
                )

            inquiry = Inquiry(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                **data,
            )
            unit_of_work.session.add(inquiry)
            unit_of_work.session.flush()
            advance_from_evidence(
                unit_of_work.session,
                context,
                opportunity.id,
                event="inquiry",
                evidence_id=inquiry.id,
            )
            unit_of_work.session.add(
                Activity(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    subject_type="opportunity",
                    subject_id=opportunity.id,
                    activity_type="inquiry.created",
                    summary="Customer inquiry recorded",
                    details={"inquiry_id": str(inquiry.id)},
                    correlation_id=context.request_id,
                )
            )
            self._audit_recorder.record(
                unit_of_work.session,
                context,
                action="inquiry.created",
                target_type="inquiry",
                target_id=inquiry.id,
                after={"opportunity_id": str(opportunity.id), "status": inquiry.status},
            )
            self._outbox_recorder.record(
                unit_of_work.session,
                context,
                DomainEvent(
                    "inquiry.created.v1", "inquiry", inquiry.id, {"inquiry_id": str(inquiry.id)}
                ),
            )
            complete_command(command, inquiry.id, "inquiry")
            unit_of_work.commit()
            return response(context, inquiry)
