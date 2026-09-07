from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.documents.enums import DocumentLinkTargetType
from app.documents.repositories import DocumentRepository
from app.export.models import CustomsDeclaration, TaxRefundCase
from app.fulfillment.models import Shipment
from app.sales.models import SalesOrder


def require_target(
    session: Session,
    context: RequestContext,
    *,
    target_type: DocumentLinkTargetType,
    target_id: UUID,
    lock: bool = False,
    allow_finalized: bool = False,
) -> None:
    target_models: dict[
        DocumentLinkTargetType,
        type[SalesOrder] | type[Shipment] | type[CustomsDeclaration] | type[TaxRefundCase],
    ] = {
        DocumentLinkTargetType.SALES_ORDER: SalesOrder,
        DocumentLinkTargetType.SHIPMENT: Shipment,
        DocumentLinkTargetType.CUSTOMS_DECLARATION: CustomsDeclaration,
        DocumentLinkTargetType.TAX_REFUND_CASE: TaxRefundCase,
    }
    target_permissions = {
        DocumentLinkTargetType.SALES_ORDER: Permission.ORDER_READ,
        DocumentLinkTargetType.SHIPMENT: Permission.SHIPMENT_READ,
        DocumentLinkTargetType.CUSTOMS_DECLARATION: Permission.EXPORT_READ,
        DocumentLinkTargetType.TAX_REFUND_CASE: Permission.EXPORT_READ,
    }
    if target_type in target_permissions:
        context.require(target_permissions[target_type])
    model = target_models.get(target_type)
    if model is None:
        raise ApiProblem(
            400,
            "UNSUPPORTED_DOCUMENT_TARGET",
            "Unsupported document target",
            "This document target is not available in the current phase.",
        )
    query = select(model).where(
        model.organization_id == context.organization_id,
        model.id == target_id,
        model.deleted_at.is_(None),
    )
    if lock:
        query = query.with_for_update()
    target = session.scalar(query)
    if not isinstance(target, (SalesOrder, Shipment, CustomsDeclaration, TaxRefundCase)):
        raise ApiProblem(
            404,
            "DOCUMENT_TARGET_NOT_FOUND",
            "Target not found",
            "The link target was not found.",
        )
    if not allow_finalized and target.status in {
        "COMPLETED",
        "DELIVERED",
        "CLEARED",
        "REFUNDED",
        "REJECTED",
        "CANCELLED",
    }:
        raise ApiProblem(
            409,
            "DOCUMENT_TARGET_FINALIZED",
            "Finalized evidence",
            "Finalized business evidence cannot be replaced or extended.",
        )


def require_document_targets(session: Session, context: RequestContext, document_id: UUID) -> None:
    links = DocumentRepository(session).links(
        organization_id=context.organization_id, document_id=document_id
    )
    if not links:
        raise ApiProblem(404, "DOCUMENT_NOT_FOUND", "Not found", "Document not found.")
    for link in links:
        require_target(
            session,
            context,
            target_type=DocumentLinkTargetType(link.target_type),
            target_id=link.target_id,
            allow_finalized=True,
        )
