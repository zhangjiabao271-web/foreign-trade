from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.orm import Session

from app.auth.errors import ApiProblem
from app.core.repositories import TenantRepository
from app.sales.enums import QuotationVersionStatus
from app.sales.models import Quotation, QuotationItem, QuotationVersion


class QuotationRepository(TenantRepository[Quotation]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Quotation)

    def get_for_update(self, *, organization_id: UUID, quotation_id: UUID) -> Quotation | None:
        return self.session.scalar(
            self._select_for_organization(organization_id)
            .where(Quotation.id == quotation_id)
            .with_for_update()
        )

    def list_with_current(
        self,
        *,
        organization_id: UUID,
        status: QuotationVersionStatus | None,
        limit: int,
        cursor: UUID | None = None,
    ) -> Sequence[tuple[Quotation, QuotationVersion]]:
        statement = (
            select(Quotation, QuotationVersion)
            .join(
                QuotationVersion,
                (QuotationVersion.organization_id == Quotation.organization_id)
                & (QuotationVersion.quotation_id == Quotation.id),
            )
            .where(
                Quotation.organization_id == organization_id,
                Quotation.deleted_at.is_(None),
                QuotationVersion.deleted_at.is_(None),
                QuotationVersion.is_current.is_(True),
            )
            .order_by(Quotation.created_at.desc(), Quotation.id.desc())
            .limit(limit)
        )
        if status is not None:
            statement = statement.where(QuotationVersion.status == status)
        if cursor is not None:
            anchor = self.get(organization_id=organization_id, record_id=cursor)
            if anchor is None:
                raise ApiProblem(
                    404,
                    "QUOTATION_NOT_FOUND",
                    "Quotation not found",
                    "The cursor quotation is unavailable. Restart the list.",
                )
            statement = statement.where(
                tuple_(Quotation.created_at, Quotation.id) < (anchor.created_at, anchor.id)
            )
        return self.session.execute(statement).tuples().all()

    def versions(self, *, organization_id: UUID, quotation_id: UUID) -> Sequence[QuotationVersion]:
        return self.session.scalars(
            select(QuotationVersion)
            .where(
                QuotationVersion.organization_id == organization_id,
                QuotationVersion.quotation_id == quotation_id,
                QuotationVersion.deleted_at.is_(None),
            )
            .order_by(QuotationVersion.version_number.desc())
        ).all()

    def current_version_for_update(
        self, *, organization_id: UUID, quotation_id: UUID
    ) -> QuotationVersion | None:
        return self.session.scalar(
            select(QuotationVersion)
            .where(
                QuotationVersion.organization_id == organization_id,
                QuotationVersion.quotation_id == quotation_id,
                QuotationVersion.is_current.is_(True),
                QuotationVersion.deleted_at.is_(None),
            )
            .with_for_update()
        )

    def items(self, *, organization_id: UUID, version_id: UUID) -> Sequence[QuotationItem]:
        return self.session.scalars(
            select(QuotationItem)
            .where(
                QuotationItem.organization_id == organization_id,
                QuotationItem.quotation_version_id == version_id,
                QuotationItem.deleted_at.is_(None),
            )
            .order_by(QuotationItem.line_number)
        ).all()
