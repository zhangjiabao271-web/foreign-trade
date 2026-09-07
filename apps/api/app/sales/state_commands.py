from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.platform.idempotency import begin_command
from app.platform.models import IdempotencyKey
from app.sales.models import Quotation, QuotationVersion
from app.sales.quotation_projections import version_response
from app.sales.repositories import QuotationRepository
from app.sales.schemas import QuotationStateCommand, QuotationVersionResponse


def begin_state_command(
    session: Session,
    context: RequestContext,
    quotation: Quotation,
    current: QuotationVersion,
    request: QuotationStateCommand,
    *,
    action: str,
    key: str,
) -> tuple[IdempotencyKey, QuotationVersionResponse | None]:
    """Caller owns permission checks and quotation/current-version locks."""
    command = begin_command(
        session,
        context,
        scope=f"quotation.{action}",
        key=key,
        payload={"quotation_id": str(quotation.id), **request.model_dump()},
    )
    if command.resource_id is not None:
        original = session.scalar(
            select(QuotationVersion).where(
                QuotationVersion.organization_id == context.organization_id,
                QuotationVersion.quotation_id == quotation.id,
                QuotationVersion.id == command.resource_id,
                QuotationVersion.deleted_at.is_(None),
            )
        )
        if original is None:
            raise ApiProblem(
                404, "QUOTATION_NOT_FOUND", "Quotation not found", "Version not found."
            )
        items = QuotationRepository(session).items(
            organization_id=context.organization_id, version_id=original.id
        )
        return command, version_response(context, original, items)
    if current.id != request.expected_version_id or current.version != request.expected_version:
        raise ApiProblem(
            409,
            "VERSION_CONFLICT",
            "Version conflict",
            "报价已发生变化，请刷新并核对版本后重新操作。",
        )
    return command, None
