from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.catalog.models import ProductSupplierLink
from app.catalog.supplier_schemas import (
    SupplierLinkCreate,
    SupplierLinkListResponse,
    SupplierLinkRecord,
    SupplierLinkResponse,
    SupplierLinkUpdate,
)
from app.catalog.supplier_services import SupplierLinkQuery, SupplierLinkService
from app.crm.schemas import ActivityResponse

router = APIRouter(
    prefix="/api/v1/products/{product_id}/supplier-links",
    tags=["product-suppliers"],
    responses=PROBLEM_RESPONSES,
)
Database = Annotated[Session, Depends(get_database_session)]
Factory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
Reader = Annotated[
    RequestContext,
    Depends(require_permissions(Permission.PRODUCT_SUPPLIER_READ, Permission.PROFIT_READ)),
]
Writer = Annotated[
    RequestContext,
    Depends(require_permissions(Permission.PRODUCT_SUPPLIER_WRITE, Permission.PROFIT_READ)),
]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]


class SupplierHistoryResponse(BaseModel):
    items: list[ActivityResponse]
    has_more: bool


def serialize_links(
    context: RequestContext, session: Session, rows: Sequence[ProductSupplierLink]
) -> list[SupplierLinkResponse]:
    names = SupplierLinkQuery(session).supplier_names(context, rows)
    return [
        SupplierLinkResponse(
            **SupplierLinkRecord.model_validate(row).model_dump(),
            supplier_name=names[row.supplier_id],
        )
        for row in rows
    ]


@router.get("", response_model=SupplierLinkListResponse)
def list_links(
    product_id: UUID,
    context: Reader,
    session: Database,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> SupplierLinkListResponse:
    rows = SupplierLinkQuery(session).list(context, product_id, cursor=cursor, limit=limit)
    items = serialize_links(context, session, rows[:limit])
    more = len(rows) > limit
    return SupplierLinkListResponse(
        items=items, has_more=more, next_cursor=items[-1].id if more else None
    )


@router.get("/activities", response_model=SupplierHistoryResponse)
def history(
    product_id: UUID,
    context: Reader,
    session: Database,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> SupplierHistoryResponse:
    rows = SupplierLinkQuery(session).history(context, product_id, offset=offset, limit=limit)
    return SupplierHistoryResponse(
        items=[ActivityResponse.model_validate(row) for row in rows[:limit]],
        has_more=len(rows) > limit,
    )


@router.get("/{link_id}", response_model=SupplierLinkResponse)
def read_link(
    product_id: UUID, link_id: UUID, context: Reader, session: Database
) -> SupplierLinkResponse:
    row = SupplierLinkQuery(session).get(context, product_id, link_id)
    return serialize_links(context, session, [row])[0]


@router.post("", response_model=SupplierLinkResponse, status_code=201)
def create_link(
    product_id: UUID,
    request: SupplierLinkCreate,
    context: Writer,
    factory: Factory,
    session: Database,
    idempotency_key: Key,
) -> SupplierLinkResponse:
    row = SupplierLinkService(factory).write(
        context, product_id, request.model_dump(), key=idempotency_key
    )
    return serialize_links(context, session, [row])[0]


@router.put("/{link_id}", response_model=SupplierLinkResponse)
def update_link(
    product_id: UUID,
    link_id: UUID,
    request: SupplierLinkUpdate,
    context: Writer,
    factory: Factory,
    session: Database,
    idempotency_key: Key,
) -> SupplierLinkResponse:
    row = SupplierLinkService(factory).write(
        context, product_id, request.model_dump(), key=idempotency_key, link_id=link_id
    )
    return serialize_links(context, session, [row])[0]
