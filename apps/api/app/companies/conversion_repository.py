from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.companies.models import Company, CompanyRole


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

    def insert_company_if_absent(self, company: Company) -> Company | None:
        return self.session.scalar(
            insert(Company)
            .values(
                organization_id=company.organization_id,
                created_by=company.created_by,
                updated_by=company.updated_by,
                name=company.name,
                name_normalized=company.name_normalized,
                country_code=company.country_code,
            )
            .on_conflict_do_nothing(
                index_elements=[Company.organization_id, Company.name_normalized],
                index_where=Company.deleted_at.is_(None),
            )
            .returning(Company)
        )

    def insert_role_if_absent(
        self, *, organization_id: UUID, company_id: UUID, role: str, actor_id: UUID
    ) -> None:
        self.session.execute(
            insert(CompanyRole)
            .values(
                organization_id=organization_id,
                company_id=company_id,
                role=role,
                created_by=actor_id,
                updated_by=actor_id,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    CompanyRole.organization_id,
                    CompanyRole.company_id,
                    CompanyRole.role,
                ]
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
