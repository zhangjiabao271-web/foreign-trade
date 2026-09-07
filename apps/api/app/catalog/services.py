from collections.abc import Sequence
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.catalog.content import response
from app.catalog.models import Product
from app.catalog.repositories import ProductRepository
from app.catalog.schemas import ProductResponse
from app.core.unit_of_work import UnitOfWork
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder


class ProductQueryService:
    def __init__(self, repository: ProductRepository) -> None:
        self._repository = repository

    def list(
        self, context: RequestContext, *, query: str | None, limit: int, cursor: UUID | None = None
    ) -> Sequence[ProductResponse]:
        context.require(Permission.PRODUCT_READ)
        if not 1 <= limit <= 100:
            raise ApiProblem(
                422, "INVALID_PAGE_SIZE", "Invalid page size", "Use a limit from 1 to 100."
            )
        products = self._repository.search(
            organization_id=context.organization_id, query=query, limit=limit + 1, cursor=cursor
        )
        return [self._response(context, product) for product in products]

    def get(self, context: RequestContext, product_id: UUID) -> ProductResponse:
        context.require(Permission.PRODUCT_READ)
        product = self._repository.get(
            organization_id=context.organization_id, record_id=product_id
        )
        if product is None:
            raise ApiProblem(
                404, "PRODUCT_NOT_FOUND", "Product not found", "The product was not found."
            )
        return self._response(context, product)

    @staticmethod
    def _response(context: RequestContext, product: Product) -> ProductResponse:
        return response(context, product)


class ProductCommandService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        audit_recorder: AuditRecorder | None = None,
        outbox_recorder: OutboxRecorder | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._audit_recorder = audit_recorder or AuditRecorder()
        self._outbox_recorder = outbox_recorder or OutboxRecorder()

    def create(self, context: RequestContext, data: dict[str, object]) -> ProductResponse:
        context.require(Permission.PRODUCT_WRITE)
        context.require(Permission.PROFIT_READ)
        with UnitOfWork(self._session_factory) as unit_of_work:
            product = Product(
                organization_id=context.organization_id,
                created_by=context.user_id,
                updated_by=context.user_id,
                **data,
            )
            unit_of_work.session.add(product)
            try:
                unit_of_work.session.flush()
            except IntegrityError as error:
                raise ApiProblem(
                    409,
                    "PRODUCT_SKU_EXISTS",
                    "Product already exists",
                    "SKU already exists in this organization.",
                ) from error
            self._audit_recorder.record(
                unit_of_work.session,
                context,
                action="product.created",
                target_type="product",
                target_id=product.id,
                after={"sku": product.sku, "name": product.name},
            )
            self._outbox_recorder.record(
                unit_of_work.session,
                context,
                DomainEvent(
                    "product.created.v1", "product", product.id, {"product_id": str(product.id)}
                ),
            )
            unit_of_work.commit()
            return response(context, product)
