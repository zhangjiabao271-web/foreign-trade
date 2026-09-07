from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.errors import ApiProblem
from app.auth.permissions import Permission
from app.catalog.models import Product, ProductSupplierLink
from app.catalog.supplier_schemas import SupplierLinkCreate, SupplierLinkUpdate
from app.companies.models import Company
from app.companies.repositories import CompanyRepository
from app.core.unit_of_work import UnitOfWork
from app.platform.idempotency import begin_command, complete_command
from app.platform.records import AuditRecorder, DomainEvent, OutboxRecorder
from app.work.models import Activity


class SupplierLinkRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def supplier_names(self, organization_id: UUID, ids: list[UUID]) -> dict[UUID, str]:
        return dict(
            self.session.execute(
                select(Company.id, Company.name).where(
                    Company.organization_id == organization_id, Company.id.in_(ids)
                )
            )
            .tuples()
            .all()
        )

    def product(self, organization_id: UUID, product_id: UUID, *, lock: bool = False) -> Product:
        statement = select(Product).where(
            Product.organization_id == organization_id,
            Product.id == product_id,
            Product.deleted_at.is_(None),
        )
        if lock:
            statement = statement.with_for_update()
        row = self.session.scalar(statement)
        if row is None:
            raise ApiProblem(
                404, "PRODUCT_NOT_FOUND", "Product not found", "The product was not found."
            )
        return row

    def get(
        self, organization_id: UUID, product_id: UUID, link_id: UUID, *, lock: bool = False
    ) -> ProductSupplierLink:
        statement = select(ProductSupplierLink).where(
            ProductSupplierLink.organization_id == organization_id,
            ProductSupplierLink.product_id == product_id,
            ProductSupplierLink.id == link_id,
            ProductSupplierLink.deleted_at.is_(None),
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        row = self.session.scalar(statement)
        if row is None:
            raise ApiProblem(
                404,
                "SUPPLIER_LINK_NOT_FOUND",
                "Supplier link not found",
                "The supplier link was not found for this product.",
            )
        return row

    def list(
        self, organization_id: UUID, product_id: UUID, *, cursor: UUID | None, limit: int
    ) -> Sequence[ProductSupplierLink]:
        statement = select(ProductSupplierLink).where(
            ProductSupplierLink.organization_id == organization_id,
            ProductSupplierLink.product_id == product_id,
            ProductSupplierLink.deleted_at.is_(None),
        )
        if cursor:
            anchor = self.get(organization_id, product_id, cursor)
            statement = statement.where(
                tuple_(ProductSupplierLink.created_at, ProductSupplierLink.id)
                < (anchor.created_at, anchor.id)
            )
        return self.session.scalars(
            statement.order_by(
                ProductSupplierLink.created_at.desc(), ProductSupplierLink.id.desc()
            ).limit(limit + 1)
        ).all()

    def history(
        self, organization_id: UUID, product_id: UUID, *, offset: int, limit: int
    ) -> Sequence[Activity]:
        return self.session.scalars(
            select(Activity)
            .where(
                Activity.organization_id == organization_id,
                Activity.subject_type == "product",
                Activity.subject_id == product_id,
                Activity.deleted_at.is_(None),
            )
            .order_by(Activity.occurred_at.desc(), Activity.id.desc())
            .offset(offset)
            .limit(limit + 1)
        ).all()


class SupplierLinkQuery:
    def __init__(self, session: Session) -> None:
        self.repository = SupplierLinkRepository(session)

    def supplier_names(
        self, context: RequestContext, rows: Sequence[ProductSupplierLink]
    ) -> dict[UUID, str]:
        context.require(Permission.PRODUCT_SUPPLIER_READ)
        context.require(Permission.PROFIT_READ)
        return self.repository.supplier_names(
            context.organization_id, [row.supplier_id for row in rows]
        )

    def get(self, context: RequestContext, product_id: UUID, link_id: UUID) -> ProductSupplierLink:
        context.require(Permission.PRODUCT_SUPPLIER_READ)
        context.require(Permission.PROFIT_READ)
        self.repository.product(context.organization_id, product_id)
        return self.repository.get(context.organization_id, product_id, link_id)

    def list(
        self, context: RequestContext, product_id: UUID, *, cursor: UUID | None, limit: int
    ) -> Sequence[ProductSupplierLink]:
        context.require(Permission.PRODUCT_SUPPLIER_READ)
        context.require(Permission.PROFIT_READ)
        self.repository.product(context.organization_id, product_id)
        return self.repository.list(context.organization_id, product_id, cursor=cursor, limit=limit)

    def history(
        self, context: RequestContext, product_id: UUID, *, offset: int, limit: int
    ) -> Sequence[Activity]:
        context.require(Permission.PRODUCT_SUPPLIER_READ)
        context.require(Permission.PROFIT_READ)
        self.repository.product(context.organization_id, product_id)
        return self.repository.history(
            context.organization_id, product_id, offset=offset, limit=limit
        )


class SupplierLinkService:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    def write(
        self,
        context: RequestContext,
        product_id: UUID,
        data: dict[str, object],
        *,
        key: str,
        link_id: UUID | None = None,
    ) -> ProductSupplierLink:
        context.require(Permission.PRODUCT_SUPPLIER_WRITE)
        context.require(Permission.PROFIT_READ)
        request = (
            SupplierLinkCreate.model_validate(data)
            if link_id is None
            else SupplierLinkUpdate.model_validate(data)
        )
        action = "product_supplier.created" if link_id is None else "product_supplier.updated"
        try:
            with UnitOfWork(self.factory) as uow:
                session = uow.session
                command = begin_command(
                    session,
                    context,
                    scope=action,
                    key=key,
                    payload={
                        "product_id": str(product_id),
                        "link_id": str(link_id) if link_id else None,
                        **request.model_dump(mode="json"),
                    },
                )
                repository = SupplierLinkRepository(session)
                if command.resource_id is not None:
                    repository.product(context.organization_id, product_id)
                    result = repository.get(
                        context.organization_id, product_id, command.resource_id
                    )
                    uow.commit()
                    return result
                if isinstance(request, SupplierLinkCreate):
                    supplier_id = request.supplier_id
                else:
                    assert link_id is not None
                    supplier_id = repository.get(
                        context.organization_id, product_id, link_id
                    ).supplier_id
                # Same company-first lock order as procurement; references cannot move on update.
                companies = CompanyRepository(session)
                if (
                    companies.get_for_update(
                        organization_id=context.organization_id, company_id=supplier_id
                    )
                    is None
                ):
                    raise ApiProblem(
                        404,
                        "COMPANY_NOT_FOUND",
                        "Supplier not found",
                        "The supplier company was not found.",
                    )
                repository.product(context.organization_id, product_id, lock=True)
                if (
                    companies.find_role(
                        organization_id=context.organization_id,
                        company_id=supplier_id,
                        role="SUPPLIER",
                    )
                    is None
                ):
                    raise ApiProblem(
                        409,
                        "SUPPLIER_ROLE_REQUIRED",
                        "Supplier role required",
                        "Add the supplier role to the existing company first.",
                    )
                fields = request.model_dump(exclude={"supplier_id", "expected_version", "reason"})
                before = None
                reason = None
                if isinstance(request, SupplierLinkCreate):
                    result = ProductSupplierLink(
                        organization_id=context.organization_id,
                        product_id=product_id,
                        supplier_id=supplier_id,
                        created_by=context.user_id,
                        updated_by=context.user_id,
                        **fields,
                    )
                    session.add(result)
                else:
                    assert link_id is not None
                    result = repository.get(context.organization_id, product_id, link_id, lock=True)
                    if result.version != request.expected_version:
                        raise ApiProblem(
                            409,
                            "VERSION_CONFLICT",
                            "Version conflict",
                            "Refresh the supplier link before submitting.",
                        )
                    before = self._snapshot(result)
                    for field, value in fields.items():
                        setattr(result, field, value)
                    result.updated_by = context.user_id
                    reason = request.reason
                session.flush()
                session.add(
                    Activity(
                        organization_id=context.organization_id,
                        created_by=context.user_id,
                        updated_by=context.user_id,
                        subject_type="product",
                        subject_id=product_id,
                        activity_type=action,
                        summary=reason or "建立产品供应商参考记录",
                        details={
                            "supplier_link_id": str(result.id),
                            "supplier_id": str(supplier_id),
                        },
                        correlation_id=context.request_id,
                    )
                )
                AuditRecorder().record(
                    session,
                    context,
                    action=action,
                    target_type="product_supplier",
                    target_id=result.id,
                    before=before,
                    after=self._snapshot(result),
                    reason=reason,
                )
                OutboxRecorder().record(
                    session,
                    context,
                    DomainEvent(
                        f"{action}.v1",
                        "product_supplier",
                        result.id,
                        {
                            "product_id": str(product_id),
                            "supplier_id": str(supplier_id),
                            "supplier_link_id": str(result.id),
                        },
                    ),
                )
                complete_command(command, result.id, "product_supplier")
                uow.commit()
                return result
        except IntegrityError as error:
            if (
                getattr(getattr(error.orig, "diag", None), "constraint_name", None)
                == "uq_product_supplier_links_org_product_supplier_active"
            ):
                raise ApiProblem(
                    409,
                    "SUPPLIER_LINK_EXISTS",
                    "Supplier link already exists",
                    "Update the existing product supplier reference instead.",
                ) from error
            raise

    @staticmethod
    def _snapshot(row: ProductSupplierLink) -> dict[str, object]:
        return {
            "product_id": str(row.product_id),
            "supplier_id": str(row.supplier_id),
            "supplier_sku": row.supplier_sku,
            "unit_price": str(row.unit_price),
            "currency": row.currency,
            "lead_time_days": row.lead_time_days,
            "quoted_on": row.quoted_on.isoformat(),
            "valid_until": row.valid_until.isoformat() if row.valid_until else None,
            "quotation_reference": row.quotation_reference,
        }
