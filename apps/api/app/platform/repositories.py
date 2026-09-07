from uuid import UUID

from sqlalchemy.orm import Session

from app.core.repositories import TenantRepository
from app.platform.enums import OutboxStatus
from app.platform.models import AsyncJob, OutboxEvent


class AsyncJobRepository(TenantRepository[AsyncJob]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AsyncJob)


class OutboxEventRepository(TenantRepository[OutboxEvent]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, OutboxEvent)

    def get_for_update(self, *, organization_id: UUID, record_id: UUID) -> OutboxEvent | None:
        return self._session.scalar(
            self._select_for_organization(organization_id)
            .where(OutboxEvent.id == record_id)
            .with_for_update()
        )

    def list_dead(
        self, *, organization_id: UUID, offset: int = 0, limit: int = 25
    ) -> list[OutboxEvent]:
        statement = (
            self._select_for_organization(organization_id)
            .where(OutboxEvent.status == OutboxStatus.DEAD)
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .offset(offset)
            .limit(limit)
        )
        return list(self._session.scalars(statement))
