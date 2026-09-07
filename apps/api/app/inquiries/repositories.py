from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import tuple_
from sqlalchemy.orm import Session

from app.auth.errors import ApiProblem
from app.core.repositories import TenantRepository
from app.inquiries.enums import InquiryStatus
from app.inquiries.models import Inquiry


class InquiryRepository(TenantRepository[Inquiry]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Inquiry)

    def search(
        self,
        *,
        organization_id: UUID,
        status: InquiryStatus | None,
        limit: int,
        cursor: UUID | None = None,
    ) -> Sequence[Inquiry]:
        statement = self._select_for_organization(organization_id)
        if status is not None:
            statement = statement.where(Inquiry.status == status)
        if cursor is not None:
            anchor = self.get(organization_id=organization_id, record_id=cursor)
            if anchor is None:
                raise ApiProblem(
                    404,
                    "INQUIRY_NOT_FOUND",
                    "Inquiry not found",
                    "The cursor inquiry is unavailable. Restart the list.",
                )
            statement = statement.where(
                tuple_(Inquiry.received_at, Inquiry.id) < (anchor.received_at, anchor.id)
            )
        return self.session.scalars(
            statement.order_by(Inquiry.received_at.desc(), Inquiry.id.desc()).limit(limit)
        ).all()

    def get_for_update(self, *, organization_id: UUID, inquiry_id: UUID) -> Inquiry | None:
        return self.session.scalar(
            self._select_for_organization(organization_id)
            .where(Inquiry.id == inquiry_id)
            .with_for_update()
        )
