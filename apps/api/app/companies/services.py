from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.companies.enums import CompanyRoleType
from app.companies.models import CompanyRole
from app.companies.repositories import CompanyRepository
from app.core.unit_of_work import UnitOfWork
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.work.records import record_activity


class CompanyCommandService:
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

    def add_role(
        self,
        context: RequestContext,
        company_id: UUID,
        role_type: CompanyRoleType,
    ) -> CompanyRole:
        context.require(Permission.COMPANY_WRITE)
        with UnitOfWork(self._session_factory) as unit:
            repository = CompanyRepository(unit.session)
            company = repository.get_for_update(
                organization_id=context.organization_id,
                company_id=company_id,
            )
            if company is None:
                raise ApiProblem(
                    404,
                    "COMPANY_NOT_FOUND",
                    "Company not found",
                    "The company was not found.",
                )

            existing = repository.find_role(
                organization_id=context.organization_id,
                company_id=company_id,
                role=role_type,
            )
            if existing is not None:
                unit.commit()
                return existing

            role = CompanyRole(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                company_id=company.id,
                role=role_type,
            )
            unit.session.add(role)
            unit.session.flush()
            event_type = "company.role-added.v1"
            record_activity(
                unit.session,
                context,
                subject_type="company",
                subject_id=company.id,
                activity_type=event_type,
                summary=f"Company role {role_type.value} added",
                details={"role": role_type.value},
            )
            self._audit.record(
                unit.session,
                context,
                action="company.role-added",
                target_type="company",
                target_id=company.id,
                after={"role": role_type.value},
            )
            self._outbox.record(
                unit.session,
                context,
                DomainEvent(
                    event_type=event_type,
                    aggregate_type="company",
                    aggregate_id=company.id,
                    payload={"company_id": str(company.id), "role": role_type.value},
                ),
            )
            unit.commit()
            return role
