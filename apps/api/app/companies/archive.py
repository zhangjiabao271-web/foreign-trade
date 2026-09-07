from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.companies.enums import CompanyRoleType
from app.companies.models import Company, CompanyRole, Contact
from app.companies.normalization import normalize_text
from app.companies.schemas import CompanyCreate, CompanyUpdate, ContactFields, ContactUpdate
from app.core.unit_of_work import UnitOfWork
from app.platform.idempotency import begin_command, complete_command
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.work.content import activity_response
from app.work.models import Activity
from app.work.schemas import ActivityResponse


class CompanyArchiveRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def company(self, organization_id: UUID, record_id: UUID, *, lock: bool = False) -> Company:
        query = select(Company).where(
            Company.organization_id == organization_id,
            Company.id == record_id,
            Company.deleted_at.is_(None),
        )
        if lock:
            query = query.with_for_update()
        row = self.session.scalar(query)
        if row is None:
            raise ApiProblem(
                404, "COMPANY_NOT_FOUND", "Company not found", "The company was not found."
            )
        return row

    def contact(
        self, organization_id: UUID, company_id: UUID, record_id: UUID, *, lock: bool = False
    ) -> Contact:
        query = select(Contact).where(
            Contact.organization_id == organization_id,
            Contact.company_id == company_id,
            Contact.id == record_id,
            Contact.deleted_at.is_(None),
        )
        if lock:
            query = query.with_for_update()
        row = self.session.scalar(query)
        if row is None:
            raise ApiProblem(
                404,
                "CONTACT_NOT_FOUND",
                "Contact not found",
                "The contact was not found for this company.",
            )
        return row

    def companies(
        self,
        organization_id: UUID,
        *,
        query: str | None,
        role: CompanyRoleType | None,
        cursor: UUID | None,
        limit: int,
    ) -> Sequence[Company]:
        statement = select(Company).where(
            Company.organization_id == organization_id, Company.deleted_at.is_(None)
        )
        if query:
            statement = statement.where(
                Company.name_normalized.contains(normalize_text(query), autoescape=True)
            )
        if role:
            statement = statement.where(
                select(CompanyRole.id)
                .where(
                    CompanyRole.organization_id == organization_id,
                    CompanyRole.company_id == Company.id,
                    CompanyRole.role == role,
                    CompanyRole.deleted_at.is_(None),
                )
                .exists()
            )
        if cursor:
            anchor = self.company(organization_id, cursor)
            statement = statement.where(
                tuple_(Company.created_at, Company.id) < (anchor.created_at, anchor.id)
            )
        return self.session.scalars(
            statement.order_by(Company.created_at.desc(), Company.id.desc()).limit(limit + 1)
        ).all()

    def roles(self, organization_id: UUID, ids: list[UUID]) -> dict[UUID, list[CompanyRoleType]]:
        result: dict[UUID, list[CompanyRoleType]] = {record_id: [] for record_id in ids}
        for row in self.session.scalars(
            select(CompanyRole)
            .where(
                CompanyRole.organization_id == organization_id,
                CompanyRole.company_id.in_(ids),
                CompanyRole.deleted_at.is_(None),
            )
            .order_by(CompanyRole.role)
        ):
            result[row.company_id].append(CompanyRoleType(row.role))
        return result

    def contacts(
        self, organization_id: UUID, company_id: UUID, *, cursor: UUID | None, limit: int
    ) -> Sequence[Contact]:
        statement = select(Contact).where(
            Contact.organization_id == organization_id,
            Contact.company_id == company_id,
            Contact.deleted_at.is_(None),
        )
        if cursor:
            anchor = self.contact(organization_id, company_id, cursor)
            statement = statement.where(
                tuple_(Contact.created_at, Contact.id) < (anchor.created_at, anchor.id)
            )
        return self.session.scalars(
            statement.order_by(Contact.created_at.desc(), Contact.id.desc()).limit(limit + 1)
        ).all()

    def history(
        self, organization_id: UUID, company_id: UUID, *, offset: int, limit: int
    ) -> Sequence[Activity]:
        return self.session.scalars(
            select(Activity)
            .where(
                Activity.organization_id == organization_id,
                Activity.subject_type == "company",
                Activity.subject_id == company_id,
                Activity.deleted_at.is_(None),
            )
            .order_by(Activity.occurred_at.desc(), Activity.id.desc())
            .offset(offset)
            .limit(limit + 1)
        ).all()


class CompanyArchiveQuery:
    def __init__(self, session: Session) -> None:
        self.repository = CompanyArchiveRepository(session)

    def get(
        self, context: RequestContext, company_id: UUID
    ) -> tuple[Company, list[CompanyRoleType]]:
        context.require(Permission.COMPANY_READ)
        row = self.repository.company(context.organization_id, company_id)
        return row, self.repository.roles(context.organization_id, [row.id])[row.id]

    def list(
        self,
        context: RequestContext,
        *,
        query: str | None,
        role: CompanyRoleType | None,
        cursor: UUID | None,
        limit: int,
    ) -> tuple[Sequence[Company], dict[UUID, list[CompanyRoleType]]]:
        context.require(Permission.COMPANY_READ)
        rows = self.repository.companies(
            context.organization_id, query=query, role=role, cursor=cursor, limit=limit
        )
        return rows, self.repository.roles(context.organization_id, [row.id for row in rows])

    def contacts(
        self, context: RequestContext, company_id: UUID, *, cursor: UUID | None, limit: int
    ) -> Sequence[Contact]:
        context.require(Permission.COMPANY_READ)
        self.repository.company(context.organization_id, company_id)
        return self.repository.contacts(
            context.organization_id, company_id, cursor=cursor, limit=limit
        )

    def contact(self, context: RequestContext, company_id: UUID, contact_id: UUID) -> Contact:
        context.require(Permission.COMPANY_READ)
        self.repository.company(context.organization_id, company_id)
        return self.repository.contact(context.organization_id, company_id, contact_id)

    def history(
        self, context: RequestContext, company_id: UUID, *, offset: int, limit: int
    ) -> Sequence[ActivityResponse]:
        context.require(Permission.COMPANY_READ)
        self.repository.company(context.organization_id, company_id)
        rows = self.repository.history(
            context.organization_id, company_id, offset=offset, limit=limit
        )
        return [activity_response(context, row) for row in rows]


class CompanyArchiveService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def write_company(
        self,
        context: RequestContext,
        data: dict[str, object],
        *,
        key: str,
        company_id: UUID | None = None,
    ) -> Company:
        context.require(Permission.COMPANY_WRITE)
        request = (
            CompanyCreate.model_validate(data)
            if company_id is None
            else CompanyUpdate.model_validate(data)
        )
        action = "company.created" if company_id is None else "company.updated"
        try:
            with UnitOfWork(self.factory) as uow:
                session = uow.session
                command = begin_command(
                    session,
                    context,
                    scope=action,
                    key=key,
                    payload={
                        "company_id": str(company_id) if company_id else None,
                        **request.model_dump(),
                    },
                )
                repository = CompanyArchiveRepository(session)
                if command.resource_id is not None:
                    row = repository.company(context.organization_id, command.resource_id)
                    uow.commit()
                    return row
                values = request.model_dump(exclude={"roles", "expected_version", "reason"})
                reason = None
                before = None
                if isinstance(request, CompanyCreate):
                    row = Company(
                        organization_id=context.organization_id,
                        created_by=context.user_id,
                        updated_by=context.user_id,
                        name_normalized=normalize_text(request.name),
                        **values,
                    )
                    session.add(row)
                    session.flush()
                    for role in request.roles:
                        session.add(
                            CompanyRole(
                                organization_id=context.organization_id,
                                company_id=row.id,
                                role=role,
                                created_by=context.user_id,
                                updated_by=context.user_id,
                            )
                        )
                    values["roles"] = [role.value for role in request.roles]
                else:
                    assert company_id is not None
                    row = repository.company(context.organization_id, company_id, lock=True)
                    self._version(row.version, request.expected_version)
                    before = {field: getattr(row, field) for field in values}
                    for field, value in values.items():
                        setattr(row, field, value)
                    row.name_normalized = normalize_text(request.name)
                    row.updated_by = context.user_id
                    reason = request.reason
                self._record(session, context, row.id, row.id, action, before, values, reason)
                complete_command(command, row.id, "company")
                uow.commit()
                return row
        except IntegrityError as error:
            diagnostic = getattr(error.orig, "diag", None)
            if (
                getattr(diagnostic, "constraint_name", None)
                == "uq_companies_organization_id_name_normalized_active"
            ):
                raise ApiProblem(
                    409,
                    "COMPANY_NAME_EXISTS",
                    "Company already exists",
                    "Use the existing company and add the required role.",
                ) from error
            raise

    def write_contact(
        self,
        context: RequestContext,
        company_id: UUID,
        data: dict[str, object],
        *,
        key: str,
        contact_id: UUID | None = None,
    ) -> Contact:
        context.require(Permission.COMPANY_WRITE)
        request = (
            ContactFields.model_validate(data)
            if contact_id is None
            else ContactUpdate.model_validate(data)
        )
        action = "contact.created" if contact_id is None else "contact.updated"
        with UnitOfWork(self.factory) as uow:
            session = uow.session
            command = begin_command(
                session,
                context,
                scope=action,
                key=key,
                payload={
                    "company_id": str(company_id),
                    "contact_id": str(contact_id) if contact_id else None,
                    **request.model_dump(),
                },
            )
            repository = CompanyArchiveRepository(session)
            repository.company(context.organization_id, company_id, lock=True)
            if command.resource_id is not None:
                row = repository.contact(context.organization_id, company_id, command.resource_id)
                uow.commit()
                return row
            values = request.model_dump(exclude={"expected_version", "reason"})
            before = None
            reason = None
            if isinstance(request, ContactUpdate):
                assert contact_id is not None
                row = repository.contact(context.organization_id, company_id, contact_id, lock=True)
                self._version(row.version, request.expected_version)
                before = {field: getattr(row, field) for field in values}
                for field, value in values.items():
                    setattr(row, field, value)
                row.updated_by = context.user_id
                reason = request.reason
            else:
                row = Contact(
                    organization_id=context.organization_id,
                    company_id=company_id,
                    created_by=context.user_id,
                    updated_by=context.user_id,
                    **values,
                )
                session.add(row)
            row.email_normalized = normalize_text(request.email) if request.email else None
            session.flush()
            self._record(session, context, company_id, row.id, action, before, values, reason)
            complete_command(command, row.id, "contact")
            uow.commit()
            return row

    @staticmethod
    def _version(actual: int, expected: int) -> None:
        if actual != expected:
            raise ApiProblem(
                409, "VERSION_CONFLICT", "Version conflict", "Refresh the record before submitting."
            )

    @staticmethod
    def _record(
        session: Session,
        context: RequestContext,
        company_id: UUID,
        record_id: UUID,
        action: str,
        before: dict[str, object] | None,
        after: dict[str, object],
        reason: str | None,
    ) -> None:
        target = action.split(".")[0]
        session.add(
            Activity(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                subject_type="company",
                subject_id=company_id,
                activity_type=action,
                summary=reason or ("建立客商档案" if target == "company" else "新增联系人"),
                details={"record_id": str(record_id), "changed_fields": list(after)},
                correlation_id=context.request_id,
            )
        )
        AuditRecorder().record(
            session,
            context,
            action=action,
            target_type=target,
            target_id=record_id,
            before=before,
            after=after,
            reason=reason,
        )
        OutboxRecorder().record(
            session,
            context,
            DomainEvent(
                f"{action}.v1",
                target,
                record_id,
                {"company_id": str(company_id), "record_id": str(record_id)},
            ),
        )
        session.flush()
