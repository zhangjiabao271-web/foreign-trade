from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.companies.enums import CompanyRoleType
from app.companies.models import Company, CompanyRole, Contact
from app.companies.normalization import normalize_text
from app.core.unit_of_work import UnitOfWork
from app.crm.content import lead_response
from app.crm.enums import LeadStatus, OpportunityStatus
from app.crm.models import Lead, Opportunity
from app.crm.repositories import ConversionRepository, LeadRepository
from app.crm.schemas import LeadResponse
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.work.content import activity_response
from app.work.models import Activity
from app.work.schemas import ActivityResponse

TRANSITIONS: dict[tuple[LeadStatus, str], LeadStatus] = {
    (LeadStatus.NEW, "qualify"): LeadStatus.QUALIFIED,
    (LeadStatus.NEW, "disqualify"): LeadStatus.DISQUALIFIED,
    (LeadStatus.QUALIFIED, "contact"): LeadStatus.CONTACTED,
    (LeadStatus.CONTACTED, "respond"): LeadStatus.RESPONDED,
    (LeadStatus.CONTACTED, "no-response"): LeadStatus.NO_RESPONSE,
    (LeadStatus.NO_RESPONSE, "contact"): LeadStatus.CONTACTED,
}


class LeadQueryService:
    def __init__(self, repository: LeadRepository) -> None:
        self._repository = repository

    def list(
        self,
        context: RequestContext,
        *,
        status: LeadStatus | None,
        query: str | None,
        limit: int,
    ) -> Sequence[LeadResponse]:
        context.require(Permission.LEAD_READ)
        rows = self._repository.search(
            organization_id=context.organization_id,
            status=status,
            query=query,
            limit=limit,
        )
        return [lead_response(context, row) for row in rows]

    def get(
        self, context: RequestContext, lead_id: UUID
    ) -> tuple[LeadResponse, Sequence[ActivityResponse]]:
        context.require(Permission.LEAD_READ)
        lead = self._repository.get(organization_id=context.organization_id, record_id=lead_id)
        if lead is None:
            raise ApiProblem(404, "LEAD_NOT_FOUND", "Lead not found", "The lead was not found.")
        activities = self._repository.activities(
            organization_id=context.organization_id,
            lead_id=lead_id,
        )
        return lead_response(context, lead), [activity_response(context, row) for row in activities]


class LeadCommandService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        audit_recorder: AuditRecorder | None = None,
        outbox_recorder: OutboxRecorder | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._audit = audit_recorder or AuditRecorder()
        self._outbox = outbox_recorder or OutboxRecorder()

    def create(self, context: RequestContext, data: dict[str, object]) -> LeadResponse:
        context.require(Permission.LEAD_WRITE)
        with UnitOfWork(self._session_factory) as unit:
            email = data.get("email")
            lead = Lead(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                **data,
                email_normalized=normalize_text(email) if isinstance(email, str) else None,
            )
            unit.session.add(lead)
            unit.session.flush()
            self._record_change(unit.session, context, lead, "created", None)
            unit.commit()
            return lead_response(context, lead)

    def transition(self, context: RequestContext, lead_id: UUID, command: str) -> LeadResponse:
        context.require(Permission.LEAD_WRITE)
        with UnitOfWork(self._session_factory) as unit:
            lead = self._locked_lead(unit.session, context.organization_id, lead_id)
            old_status = LeadStatus(lead.status)
            new_status = TRANSITIONS.get((old_status, command))
            if new_status is None:
                raise ApiProblem(
                    409,
                    "INVALID_STATE_TRANSITION",
                    "Invalid state transition",
                    f"Lead cannot run {command} from {old_status.value}.",
                )
            lead.status = new_status
            lead.updated_by = context.user_id
            self._record_change(unit.session, context, lead, command, old_status)
            unit.commit()
            return lead_response(context, lead)

    def convert(
        self, context: RequestContext, lead_id: UUID
    ) -> tuple[LeadResponse, UUID, UUID, UUID]:
        context.require(Permission.LEAD_CONVERT)
        with UnitOfWork(self._session_factory) as unit:
            lead = self._locked_lead(unit.session, context.organization_id, lead_id)
            if lead.status == LeadStatus.CONVERTED:
                result = self._conversion_ids(lead)
                unit.commit()
                return lead_response(context, result[0]), *result[1:]
            if lead.status != LeadStatus.RESPONDED:
                raise ApiProblem(
                    409,
                    "INVALID_STATE_TRANSITION",
                    "Invalid state transition",
                    "Lead must be RESPONDED before conversion.",
                )

            conversion = ConversionRepository(unit.session)
            normalized_name = normalize_text(lead.company_name)
            company = conversion.find_company(
                organization_id=context.organization_id,
                normalized_name=normalized_name,
            )
            if company is None:
                company = Company(
                    organization_id=context.organization_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    name=lead.company_name,
                    name_normalized=normalized_name,
                    country_code=lead.country_code,
                )
                unit.session.add(company)
                unit.session.flush()
            if (
                conversion.find_role(
                    organization_id=context.organization_id,
                    company_id=company.id,
                    role=CompanyRoleType.CUSTOMER,
                )
                is None
            ):
                unit.session.add(
                    CompanyRole(
                        organization_id=context.organization_id,
                        created_by=context.user_id,
                        updated_by=context.user_id,
                        company_id=company.id,
                        role=CompanyRoleType.CUSTOMER,
                    )
                )

            contact = Contact(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                company_id=company.id,
                full_name=lead.contact_name or lead.company_name,
                email=lead.email,
                email_normalized=lead.email_normalized,
                phone=lead.phone,
            )
            unit.session.add(contact)
            unit.session.flush()
            opportunity = Opportunity(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                company_id=company.id,
                contact_id=contact.id,
                source_lead_id=lead.id,
                name=f"{lead.company_name} opportunity",
                status=OpportunityStatus.OPEN,
            )
            unit.session.add(opportunity)
            unit.session.flush()
            old_status = LeadStatus(lead.status)
            lead.status = LeadStatus.CONVERTED
            lead.converted_company_id = company.id
            lead.converted_contact_id = contact.id
            lead.converted_opportunity_id = opportunity.id
            lead.converted_at = datetime.now(UTC)
            lead.updated_by = context.user_id
            self._record_change(unit.session, context, lead, "converted", old_status)
            unit.commit()
            return lead_response(context, lead), company.id, contact.id, opportunity.id

    def _locked_lead(self, session: Session, organization_id: UUID, lead_id: UUID) -> Lead:
        lead = LeadRepository(session).get_for_update(
            organization_id=organization_id,
            lead_id=lead_id,
        )
        if lead is None:
            raise ApiProblem(404, "LEAD_NOT_FOUND", "Lead not found", "The lead was not found.")
        return lead

    def _conversion_ids(self, lead: Lead) -> tuple[Lead, UUID, UUID, UUID]:
        company_id = lead.converted_company_id
        contact_id = lead.converted_contact_id
        opportunity_id = lead.converted_opportunity_id
        if company_id is None or contact_id is None or opportunity_id is None:
            raise RuntimeError("Converted lead is missing conversion references")
        return lead, company_id, contact_id, opportunity_id

    def _record_change(
        self,
        session: Session,
        context: RequestContext,
        lead: Lead,
        command: str,
        before_status: LeadStatus | None,
    ) -> None:
        event_type = f"lead.{command}.v1"
        session.add(
            Activity(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                subject_type="lead",
                subject_id=lead.id,
                activity_type=event_type,
                summary=f"Lead {command.replace('-', ' ')}",
                details={"status": str(lead.status)},
                correlation_id=context.request_id,
            )
        )
        self._audit.record(
            session,
            context,
            action=event_type.removesuffix(".v1"),
            target_type="lead",
            target_id=lead.id,
            before={"status": before_status.value} if before_status else None,
            after={"status": str(lead.status)},
        )
        self._outbox.record(
            session,
            context,
            DomainEvent(
                event_type=event_type,
                aggregate_type="lead",
                aggregate_id=lead.id,
                payload={"lead_id": str(lead.id), "status": str(lead.status)},
            ),
        )
