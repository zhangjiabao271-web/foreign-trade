from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session, sessionmaker

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, get_session_factory, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.sales.contract_schemas import (
    ContractCommand,
    ContractCreate,
    ContractListResponse,
    ContractResponse,
    ContractSign,
    ContractUpdate,
)
from app.sales.contract_services import ContractQuery, ContractService

router = APIRouter(
    prefix="/api/v1/sales-orders/{order_id}/contracts",
    tags=["sales-contracts"],
    responses=PROBLEM_RESPONSES,
)
DatabaseSession = Annotated[Session, Depends(get_database_session)]
Factory = Annotated[sessionmaker[Session], Depends(get_session_factory)]
Reader = Annotated[RequestContext, Depends(require_permissions(Permission.CONTRACT_READ))]
Writer = Annotated[RequestContext, Depends(require_permissions(Permission.CONTRACT_WRITE))]
Signer = Annotated[RequestContext, Depends(require_permissions(Permission.CONTRACT_SIGN))]
Key = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=160)]


@router.get("", response_model=ContractListResponse)
def list_contracts(
    order_id: UUID,
    context: Reader,
    session: DatabaseSession,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ContractListResponse:
    rows = ContractQuery(session).list(context, order_id, cursor=cursor, limit=limit)
    page = rows[:limit]
    return ContractListResponse(
        items=[ContractResponse.model_validate(row) for row in page],
        has_more=len(rows) > limit,
        next_cursor=page[-1].id if len(rows) > limit else None,
    )


@router.get("/{contract_id}", response_model=ContractResponse)
def read_contract(
    order_id: UUID, contract_id: UUID, context: Reader, session: DatabaseSession
) -> ContractResponse:
    return ContractResponse.model_validate(
        ContractQuery(session).get(context, order_id, contract_id)
    )


@router.post("", response_model=ContractResponse, status_code=201)
def create_contract(
    order_id: UUID, request: ContractCreate, context: Writer, factory: Factory, key: Key
) -> ContractResponse:
    return ContractResponse.model_validate(
        ContractService(factory).execute(
            context, order_id, action="created", data=request.model_dump(), key=key
        )
    )


@router.put("/{contract_id}", response_model=ContractResponse)
def update_contract(
    order_id: UUID,
    contract_id: UUID,
    request: ContractUpdate,
    context: Writer,
    factory: Factory,
    key: Key,
) -> ContractResponse:
    return ContractResponse.model_validate(
        ContractService(factory).execute(
            context,
            order_id,
            contract_id=contract_id,
            action="updated",
            data=request.model_dump(exclude_unset=True),
            key=key,
        )
    )


@router.post("/{contract_id}/record-signature", response_model=ContractResponse)
def sign_contract(
    order_id: UUID,
    contract_id: UUID,
    request: ContractSign,
    context: Signer,
    factory: Factory,
    key: Key,
) -> ContractResponse:
    return ContractResponse.model_validate(
        ContractService(factory).execute(
            context,
            order_id,
            contract_id=contract_id,
            action="signed",
            data=request.model_dump(),
            key=key,
        )
    )


@router.post("/{contract_id}/void", response_model=ContractResponse)
def void_contract(
    order_id: UUID,
    contract_id: UUID,
    request: ContractCommand,
    context: Writer,
    factory: Factory,
    key: Key,
) -> ContractResponse:
    return ContractResponse.model_validate(
        ContractService(factory).execute(
            context,
            order_id,
            contract_id=contract_id,
            action="voided",
            data=request.model_dump(),
            key=key,
        )
    )
