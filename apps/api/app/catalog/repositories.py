from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import or_, tuple_
from sqlalchemy.orm import Session

from app.auth.errors import ApiProblem
from app.catalog.models import Product
from app.core.repositories import TenantRepository


class ProductRepository(TenantRepository[Product]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Product)

    def search(
        self, *, organization_id: UUID, query: str | None, limit: int, cursor: UUID | None = None
    ) -> Sequence[Product]:
        statement = self._select_for_organization(organization_id)
        if query:
            literal = query.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{literal}%"
            statement = statement.where(
                or_(
                    Product.sku.ilike(pattern, escape="\\"),
                    Product.name.ilike(pattern, escape="\\"),
                )
            )
        if cursor is not None:
            anchor = self.get(organization_id=organization_id, record_id=cursor)
            if anchor is None:
                raise ApiProblem(
                    404, "PRODUCT_NOT_FOUND", "Product not found", "Restart product search."
                )
            statement = statement.where(tuple_(Product.name, Product.id) > (anchor.name, anchor.id))
        return self.session.scalars(statement.order_by(Product.name, Product.id).limit(limit)).all()
