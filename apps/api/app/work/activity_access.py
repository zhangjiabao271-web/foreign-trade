"""Read-only domain access port for the explicitly supported non-order timelines."""

from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.companies.models import Company
from app.crm.models import Lead, Opportunity
from app.export.models import CustomsDeclaration, TaxRefundCase
from app.procurement.models import PurchaseOrder

ActivitySubject = Literal[
    "lead", "company", "opportunity", "customs_declaration", "tax_refund_case", "purchase_order"
]


def require_activity_subject(
    session: Session,
    context: RequestContext,
    subject_type: ActivitySubject,
    subject_id: UUID,
    *,
    lock: bool = False,
) -> None:
    models: dict[
        str,
        type[Lead]
        | type[Company]
        | type[Opportunity]
        | type[CustomsDeclaration]
        | type[TaxRefundCase]
        | type[PurchaseOrder],
    ] = {
        "lead": Lead,
        "company": Company,
        "opportunity": Opportunity,
        "customs_declaration": CustomsDeclaration,
        "tax_refund_case": TaxRefundCase,
        "purchase_order": PurchaseOrder,
    }
    permissions = {
        "lead": Permission.LEAD_READ,
        "company": Permission.COMPANY_READ,
        "opportunity": Permission.OPPORTUNITY_READ,
        "customs_declaration": Permission.EXPORT_READ,
        "tax_refund_case": Permission.EXPORT_READ,
        "purchase_order": Permission.PROCUREMENT_READ,
    }
    model = models.get(subject_type)
    if model is None:
        raise ApiProblem(404, "WORK_CONTENT_NOT_FOUND", "Not found", "Unsupported timeline.")
    context.require(permissions[subject_type])
    query = select(model).where(
        model.organization_id == context.organization_id,
        model.id == subject_id,
        model.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update()
    if session.scalar(query) is None:
        raise ApiProblem(404, "WORK_CONTENT_NOT_FOUND", "Not found", "Timeline owner not found.")
