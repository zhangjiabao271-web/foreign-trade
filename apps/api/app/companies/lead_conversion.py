from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.companies.conversion_repository import ConversionRepository
from app.companies.enums import CompanyRoleType
from app.companies.models import Company, Contact
from app.companies.normalization import normalize_text


@dataclass(frozen=True, slots=True)
class ConversionSource:
    company_name: str
    country_code: str | None
    contact_name: str | None
    email: str | None
    email_normalized: str | None
    phone: str | None


@dataclass(frozen=True, slots=True)
class ConversionParties:
    company_id: UUID
    contact_id: UUID


def resolve_conversion_parties(
    session: Session, context: RequestContext, source: ConversionSource
) -> ConversionParties:
    """Join the caller's validated lead conversion; never commit or emit separate evidence."""
    context.require(Permission.LEAD_CONVERT)
    conversion = ConversionRepository(session)
    normalized_name = normalize_text(source.company_name)
    company = conversion.find_company(
        organization_id=context.organization_id,
        normalized_name=normalized_name,
    )
    if company is None:
        company = Company(
            organization_id=context.organization_id,
            created_by=context.user_id,
            updated_by=context.user_id,
            name=source.company_name,
            name_normalized=normalized_name,
            country_code=source.country_code,
        )
        company = conversion.insert_company_if_absent(company)
        if company is None:
            company = conversion.find_company(
                organization_id=context.organization_id,
                normalized_name=normalized_name,
            )
        if company is None:
            raise ApiProblem(409, "COMPANY_CHANGED", "Company changed", "Retry the conversion.")
    if (
        conversion.find_role(
            organization_id=context.organization_id,
            company_id=company.id,
            role=CompanyRoleType.CUSTOMER,
        )
        is None
    ):
        conversion.insert_role_if_absent(
            organization_id=context.organization_id,
            actor_id=context.user_id,
            company_id=company.id,
            role=CompanyRoleType.CUSTOMER,
        )
        if (
            conversion.find_role(
                organization_id=context.organization_id,
                company_id=company.id,
                role=CompanyRoleType.CUSTOMER,
            )
            is None
        ):
            raise ApiProblem(
                409,
                "COMPANY_ROLE_INACTIVE",
                "Company role inactive",
                "The existing customer role is inactive; conversion was not applied.",
            )

    contact = Contact(
        organization_id=context.organization_id,
        created_by=context.user_id,
        updated_by=context.user_id,
        company_id=company.id,
        full_name=source.contact_name or source.company_name,
        email=source.email,
        email_normalized=source.email_normalized,
        phone=source.phone,
    )
    session.add(contact)
    session.flush()
    return ConversionParties(company_id=company.id, contact_id=contact.id)
