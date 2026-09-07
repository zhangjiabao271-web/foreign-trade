from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.database import TenantRecordMixin


class TenantRepository[TenantModel: TenantRecordMixin]:
    """Read boundary that always requires and applies an organization scope."""

    def __init__(self, session: Session, model: type[TenantModel]) -> None:
        self._session = session
        self._model = model

    @property
    def session(self) -> Session:
        return self._session

    def _select_for_organization(self, organization_id: UUID) -> Select[tuple[TenantModel]]:
        return select(self._model).where(
            self._model.organization_id == organization_id,
            self._model.deleted_at.is_(None),
        )

    def get(self, *, organization_id: UUID, record_id: UUID) -> TenantModel | None:
        statement = self._select_for_organization(organization_id).where(
            self._model.id == record_id
        )
        return self._session.scalar(statement)

    def list(self, *, organization_id: UUID, limit: int = 100) -> Sequence[TenantModel]:
        statement = self._select_for_organization(organization_id).limit(limit)
        return self._session.scalars(statement).all()

    def count(self, *, organization_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(self._model)
            .where(
                self._model.organization_id == organization_id,
                self._model.deleted_at.is_(None),
            )
        )
        return self._session.scalar(statement) or 0
