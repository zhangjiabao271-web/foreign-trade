from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.catalog.repositories import ProductRepository
from app.catalog.schemas import ProductCreate, ProductListResponse, ProductResponse
from app.catalog.services import ProductCommandService, ProductQueryService

router = APIRouter(prefix="/api/v1/products", tags=["products"], responses=PROBLEM_RESPONSES)
DatabaseSession = Annotated[Session, Depends(get_database_session)]
SessionFactory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
ProductReader = Annotated[RequestContext, Depends(require_permissions(Permission.PRODUCT_READ))]
ProductWriter = Annotated[
    RequestContext, Depends(require_permissions(Permission.PRODUCT_WRITE, Permission.PROFIT_READ))
]


@router.get("", response_model=ProductListResponse)
def list_products(
    context: ProductReader,
    session: DatabaseSession,
    query: Annotated[str | None, Query(max_length=240)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: UUID | None = None,
) -> ProductListResponse:
    products = ProductQueryService(ProductRepository(session)).list(
        context, query=query, limit=limit, cursor=cursor
    )
    has_more = len(products) > limit
    page = products[:limit]
    return ProductListResponse(
        items=list(page),
        count=len(page),
        has_more=has_more,
        next_cursor=page[-1].id if has_more else None,
    )


@router.post("", response_model=ProductResponse, status_code=201)
def create_product(
    request: ProductCreate, context: ProductWriter, factory: SessionFactory
) -> ProductResponse:
    product = ProductCommandService(factory).create(context, request.model_dump())
    return ProductResponse.model_validate(product)


@router.get("/{product_id}", response_model=ProductResponse)
def read_product(
    product_id: UUID, context: ProductReader, session: DatabaseSession
) -> ProductResponse:
    product = ProductQueryService(ProductRepository(session)).get(context, product_id)
    return product
