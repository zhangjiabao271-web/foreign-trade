from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.companies.models import Company, CompanyRole


class CompanyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_update(self, *, organization_id: UUID, company_id: UUID) -> Company | None:
        return self.session.scalar(
            select(Company)
            .where(
                Company.organization_id == organization_id,
                Company.id == company_id,
                Company.deleted_at.is_(None),
            )
            .with_for_update()
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
