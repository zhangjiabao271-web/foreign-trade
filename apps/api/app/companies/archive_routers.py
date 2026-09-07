from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.companies.archive import CompanyArchiveQuery, CompanyArchiveService
from app.companies.enums import CompanyRoleType
from app.companies.schemas import (
    CompanyCreate,
    CompanyListResponse,
    CompanyResponse,
    CompanyUpdate,
    ContactFields,
    ContactListResponse,
    ContactResponse,
    ContactUpdate,
)
from app.crm.schemas import ActivityResponse

router = APIRouter(prefix="/api/v1/companies", tags=["companies"], responses=PROBLEM_RESPONSES)
Database = Annotated[Session, Depends(get_database_session)]
Factory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
Reader = Annotated[RequestContext, Depends(require_permissions(Permission.COMPANY_READ))]
Writer = Annotated[RequestContext, Depends(require_permissions(Permission.COMPANY_WRITE))]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]


class CompanyHistoryResponse(BaseModel):
    items: list[ActivityResponse]
    has_more: bool


@router.get("", response_model=CompanyListResponse)
def list_companies(
    context: Reader,
    session: Database,
    query: Annotated[str | None, Query(max_length=240)] = None,
    role: CompanyRoleType | None = None,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> CompanyListResponse:
    rows, roles = CompanyArchiveQuery(session).list(
        context, query=query, role=role, cursor=cursor, limit=limit
    )
    items = [
        CompanyResponse.model_validate(row).model_copy(update={"roles": roles[row.id]})
        for row in rows[:limit]
    ]
    more = len(rows) > limit
    return CompanyListResponse(
        items=items, has_more=more, next_cursor=items[-1].id if more else None
    )


@router.get("/{company_id}", response_model=CompanyResponse)
def read_company(company_id: UUID, context: Reader, session: Database) -> CompanyResponse:
    row, roles = CompanyArchiveQuery(session).get(context, company_id)
    return CompanyResponse.model_validate(row).model_copy(update={"roles": roles})


@router.post("", response_model=CompanyResponse, status_code=201)
def create_company(
    request: CompanyCreate,
    context: Writer,
    factory: Factory,
    session: Database,
    idempotency_key: Key,
) -> CompanyResponse:
    row = CompanyArchiveService(factory).write_company(
        context, request.model_dump(), key=idempotency_key
    )
    return read_company(row.id, context, session)


@router.put("/{company_id}", response_model=CompanyResponse)
def update_company(
    company_id: UUID,
    request: CompanyUpdate,
    context: Writer,
    factory: Factory,
    session: Database,
    idempotency_key: Key,
) -> CompanyResponse:
    row = CompanyArchiveService(factory).write_company(
        context, request.model_dump(), key=idempotency_key, company_id=company_id
    )
    return read_company(row.id, context, session)


@router.get("/{company_id}/contacts", response_model=ContactListResponse)
def list_contacts(
    company_id: UUID,
    context: Reader,
    session: Database,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> ContactListResponse:
    rows = CompanyArchiveQuery(session).contacts(context, company_id, cursor=cursor, limit=limit)
    items = [ContactResponse.model_validate(row) for row in rows[:limit]]
    more = len(rows) > limit
    return ContactListResponse(
        items=items, has_more=more, next_cursor=items[-1].id if more else None
    )


@router.get("/{company_id}/contacts/{contact_id}", response_model=ContactResponse)
def read_contact(
    company_id: UUID, contact_id: UUID, context: Reader, session: Database
) -> ContactResponse:
    return ContactResponse.model_validate(
        CompanyArchiveQuery(session).contact(context, company_id, contact_id)
    )


@router.post("/{company_id}/contacts", response_model=ContactResponse, status_code=201)
def create_contact(
    company_id: UUID,
    request: ContactFields,
    context: Writer,
    factory: Factory,
    idempotency_key: Key,
) -> ContactResponse:
    return ContactResponse.model_validate(
        CompanyArchiveService(factory).write_contact(
            context, company_id, request.model_dump(), key=idempotency_key
        )
    )


@router.put("/{company_id}/contacts/{contact_id}", response_model=ContactResponse)
def update_contact(
    company_id: UUID,
    contact_id: UUID,
    request: ContactUpdate,
    context: Writer,
    factory: Factory,
    idempotency_key: Key,
) -> ContactResponse:
    return ContactResponse.model_validate(
        CompanyArchiveService(factory).write_contact(
            context, company_id, request.model_dump(), key=idempotency_key, contact_id=contact_id
        )
    )


@router.get("/{company_id}/activities", response_model=CompanyHistoryResponse)
def company_history(
    company_id: UUID,
    context: Reader,
    session: Database,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> CompanyHistoryResponse:
    rows = CompanyArchiveQuery(session).history(context, company_id, offset=offset, limit=limit)
    return CompanyHistoryResponse(
        items=[ActivityResponse.model_validate(row) for row in rows[:limit]],
        has_more=len(rows) > limit,
    )
