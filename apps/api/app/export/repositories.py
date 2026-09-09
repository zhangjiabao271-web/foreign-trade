from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import tuple_
from sqlalchemy.orm import Session

from app.auth.errors import ApiProblem
from app.core.repositories import TenantRepository
from app.export.models import CustomsDeclaration, TaxRefundCase


class CaseRepository[Case: CustomsDeclaration | TaxRefundCase](TenantRepository[Case]):
    def page(
        self,
        *,
        organization_id: UUID,
        cursor: UUID | None,
        limit: int,
    ) -> Sequence[Case]:
        statement = self._select_for_organization(organization_id)
        if cursor is not None:
            anchor = self.get(organization_id=organization_id, record_id=cursor)
            if anchor is None:
                raise ApiProblem(
                    404, "INVALID_CURSOR", "Invalid cursor", "Restart case pagination."
                )
            statement = statement.where(
                tuple_(self._model.created_at, self._model.id) < (anchor.created_at, anchor.id)
            )
        return self.session.scalars(
            statement.order_by(self._model.created_at.desc(), self._model.id.desc()).limit(
                limit + 1
            )
        ).all()

    def locked(self, *, organization_id: UUID, record_id: UUID) -> Case | None:
        return self.session.scalar(
            self._select_for_organization(organization_id)
            .where(self._model.id == record_id)
            .with_for_update()
        )


class CustomsRepository(CaseRepository[CustomsDeclaration]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, CustomsDeclaration)

    def by_shipment(self, *, organization_id: UUID, shipment_id: UUID) -> CustomsDeclaration | None:
        return self.session.scalar(
            self._select_for_organization(organization_id).where(
                CustomsDeclaration.shipment_id == shipment_id
            )
        )


class RefundRepository(CaseRepository[TaxRefundCase]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, TaxRefundCase)

    def by_declaration(
        self, *, organization_id: UUID, declaration_id: UUID
    ) -> TaxRefundCase | None:
        return self.session.scalar(
            self._select_for_organization(organization_id).where(
                TaxRefundCase.customs_declaration_id == declaration_id
            )
        )
