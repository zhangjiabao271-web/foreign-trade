from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.companies.models import Company, CompanyRole, Contact
from app.core.repositories import TenantRepository
from app.crm.enums import LeadStatus
from app.crm.models import Lead, Opportunity
from app.work.models import Activity


class LeadRepository(TenantRepository[Lead]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Lead)

    def get_for_update(self, *, organization_id: UUID, lead_id: UUID) -> Lead | None:
        return self.session.scalar(
            self._select_for_organization(organization_id)
            .where(Lead.id == lead_id)
            .with_for_update()
        )

    def search(
        self,
        *,
        organization_id: UUID,
        status: LeadStatus | None,
        query: str | None,
        limit: int,
    ) -> Sequence[Lead]:
        statement = self._select_for_organization(organization_id)
        if status is not None:
            statement = statement.where(Lead.status == status)
        if query:
            pattern = f"%{query.strip()}%"
            statement = statement.where(
                or_(Lead.company_name.ilike(pattern), Lead.contact_name.ilike(pattern))
            )
        return self.session.scalars(statement.order_by(Lead.created_at.desc()).limit(limit)).all()

    def activities(self, *, organization_id: UUID, lead_id: UUID) -> Sequence[Activity]:
        statement = (
            select(Activity)
            .where(
                Activity.organization_id == organization_id,
                Activity.subject_type == "lead",
                Activity.subject_id == lead_id,
                Activity.deleted_at.is_(None),
            )
            .order_by(Activity.occurred_at.desc())
        )
        return self.session.scalars(statement).all()


class ConversionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_company(self, *, organization_id: UUID, normalized_name: str) -> Company | None:
        return self.session.scalar(
            select(Company).where(
                Company.organization_id == organization_id,
                Company.name_normalized == normalized_name,
                Company.deleted_at.is_(None),
            )
        )

    def find_role(
        self,
        *,
        organization_id: UUID,
        company_id: UUID,
        role: str,
    ) -> CompanyRole | None:
        return self.session.scalar(
            select(CompanyRole).where(
                CompanyRole.organization_id == organization_id,
                CompanyRole.company_id == company_id,
                CompanyRole.role == role,
                CompanyRole.deleted_at.is_(None),
            )
        )

    def contact(self, *, organization_id: UUID, contact_id: UUID) -> Contact | None:
        return self.session.scalar(
            select(Contact).where(
                Contact.organization_id == organization_id,
                Contact.id == contact_id,
                Contact.deleted_at.is_(None),
            )
        )

    def opportunity(self, *, organization_id: UUID, opportunity_id: UUID) -> Opportunity | None:
        return self.session.scalar(
            select(Opportunity).where(
                Opportunity.organization_id == organization_id,
                Opportunity.id == opportunity_id,
                Opportunity.deleted_at.is_(None),
            )
        )
