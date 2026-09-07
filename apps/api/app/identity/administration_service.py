from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.core.unit_of_work import UnitOfWork
from app.identity.administration_repository import AdministrationRepository
from app.identity.models import Organization, OrganizationMembership, User
from app.identity.schemas import (
    IdentityVersionCommand,
    MemberCreate,
    MemberRoleChange,
    OrganizationUpdate,
)
from app.platform.idempotency import begin_command, complete_command
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.work.models import Activity


def rejected(code: str, detail: str) -> ApiProblem:
    return ApiProblem(409, code, "Administration command rejected", detail)


def snapshot(row: Organization | OrganizationMembership) -> dict[str, object]:
    if isinstance(row, Organization):
        return {"name": row.name, "timezone": row.timezone, "version": row.version}
    return {
        "user_id": str(row.user_id),
        "role": row.role,
        "status": row.status,
        "version": row.version,
    }


def check_version(actual: int, expected: int) -> None:
    if actual != expected:
        raise rejected("VERSION_CONFLICT", "Refresh and review the record before retrying.")


class AdministrationService:
    def __init__(
        self,
        factory: sessionmaker[Session],
        *,
        audit_recorder: AuditRecorder | None = None,
        outbox_recorder: OutboxRecorder | None = None,
    ) -> None:
        self.factory = factory
        self.audit = audit_recorder or AuditRecorder()
        self.outbox = outbox_recorder or OutboxRecorder()

    def _evidence(
        self,
        session: Session,
        context: RequestContext,
        row: Organization | OrganizationMembership,
        *,
        action: str,
        reason: str,
        before: dict[str, object] | None = None,
    ) -> None:
        kind = "organization" if isinstance(row, Organization) else "organization_membership"
        session.add(
            Activity(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                subject_type="organization",
                subject_id=context.organization_id,
                activity_type=action,
                summary=action,
                details={"target_id": str(row.id)},
                correlation_id=context.request_id,
            )
        )
        self.audit.record(
            session,
            context,
            action=action,
            target_type=kind,
            target_id=row.id,
            before=before,
            after=snapshot(row),
            reason=reason,
        )
        self.outbox.record(
            session, context, DomainEvent(f"{action}.v1", kind, row.id, {"target_id": str(row.id)})
        )

    def update_organization(
        self, context: RequestContext, data: dict[str, object], *, key: str
    ) -> UUID:
        context.require(Permission.ORGANIZATION_MANAGE)
        request = OrganizationUpdate.model_validate(data)
        with UnitOfWork(self.factory) as uow:
            session = uow.session
            row = AdministrationRepository(session).authorize_admin(context)
            command = begin_command(
                session,
                context,
                scope="organization.updated",
                key=key,
                payload=request.model_dump(),
            )
            if command.resource_id:
                uow.commit()
                return row.id
            check_version(row.version, request.expected_version)
            before = snapshot(row)
            row.name = request.name
            row.name_normalized = request.name.casefold()
            row.timezone = request.timezone
            row.updated_by = context.user_id
            row.version += 1
            session.flush()
            self._evidence(
                session,
                context,
                row,
                action="organization.updated",
                reason=request.reason,
                before=before,
            )
            complete_command(command, row.id, "organization")
            uow.commit()
            return row.id

    def add_member(self, context: RequestContext, data: dict[str, object], *, key: str) -> UUID:
        context.require(Permission.MEMBER_MANAGE)
        request = MemberCreate.model_validate(data)
        with UnitOfWork(self.factory) as uow:
            session = uow.session
            repository = AdministrationRepository(session)
            repository.authorize_admin(context)
            command = begin_command(
                session, context, scope="membership.created", key=key, payload=request.model_dump()
            )
            if command.resource_id:
                repository.member(context.organization_id, command.resource_id)
                uow.commit()
                return command.resource_id
            # Global mapping may race across organizations; never update an existing identity.
            session.execute(
                insert(User)
                .values(
                    id=uuid4(),
                    external_subject=request.external_subject,
                    display_name=request.display_name,
                    status="ACTIVE",
                    created_by=context.user_id,
                    updated_by=context.user_id,
                )
                .on_conflict_do_nothing(index_elements=[User.external_subject])
            )
            user = session.scalar(
                select(User).where(User.external_subject == request.external_subject)
            )
            if user is None:
                raise RuntimeError("Identity insert did not resolve a user")
            if user.status != "ACTIVE" or user.deleted_at is not None:
                raise rejected("IDENTITY_UNAVAILABLE", "This identity cannot receive membership.")
            existing = session.scalar(
                select(OrganizationMembership.id).where(
                    OrganizationMembership.organization_id == context.organization_id,
                    OrganizationMembership.user_id == user.id,
                )
            )
            if existing is not None:
                raise rejected("MEMBERSHIP_EXISTS", "Use the existing membership commands.")
            row = OrganizationMembership(
                organization_id=context.organization_id,
                user_id=user.id,
                role=request.role,
                status="ACTIVE",
                created_by=context.user_id,
                updated_by=context.user_id,
            )
            session.add(row)
            session.flush()
            self._evidence(
                session, context, row, action="membership.created", reason=request.reason
            )
            complete_command(command, row.id, "organization_membership")
            uow.commit()
            return row.id

    def change_member(
        self,
        context: RequestContext,
        member_id: UUID,
        data: dict[str, object],
        *,
        action: Literal["role_changed", "disabled", "reactivated"],
        key: str,
    ) -> UUID:
        context.require(Permission.MEMBER_MANAGE)
        if action == "role_changed":
            request: IdentityVersionCommand = MemberRoleChange.model_validate(data)
        else:
            request = IdentityVersionCommand.model_validate(data)
        with UnitOfWork(self.factory) as uow:
            session = uow.session
            repository = AdministrationRepository(session)
            repository.authorize_admin(context)
            command = begin_command(
                session,
                context,
                scope=f"membership.{action}",
                key=key,
                payload={"member_id": str(member_id), **request.model_dump()},
            )
            row, user = repository.member(context.organization_id, member_id)
            if command.resource_id:
                uow.commit()
                return row.id
            check_version(row.version, request.expected_version)
            before = snapshot(row)
            role = row.role
            status = row.status
            if isinstance(request, MemberRoleChange):
                role = request.role
            elif action == "disabled":
                if status == "DISABLED":
                    raise rejected("MEMBERSHIP_INACTIVE", "Membership is already disabled.")
                status = "DISABLED"
            elif action == "reactivated":
                if status != "DISABLED":
                    raise rejected(
                        "MEMBERSHIP_NOT_DISABLED", "Only disabled members can reactivate."
                    )
                if user.status != "ACTIVE" or user.deleted_at is not None:
                    raise rejected(
                        "IDENTITY_UNAVAILABLE", "This identity cannot receive membership."
                    )
                status = "ACTIVE"
            else:
                raise ValueError("Unknown membership command")
            if (
                row.role == "ADMIN"
                and row.status == "ACTIVE"
                and user.status == "ACTIVE"
                and user.deleted_at is None
                and (role != "ADMIN" or status != "ACTIVE")
                and repository.eligible_admin_count(context.organization_id) <= 1
            ):
                raise rejected("LAST_ADMINISTRATOR", "Keep at least one active administrator.")
            row.role = role
            row.status = status
            row.updated_by = context.user_id
            row.version += 1
            session.flush()
            self._evidence(
                session,
                context,
                row,
                action=f"membership.{action}",
                reason=request.reason,
                before=before,
            )
            complete_command(command, row.id, "organization_membership")
            uow.commit()
            return row.id
