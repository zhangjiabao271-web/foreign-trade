from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.platform.operations_queries import OperationsQuery
from app.platform.operations_schemas import OperationsResponse

router = APIRouter(prefix="/api/v1/operations", tags=["operations"], responses=PROBLEM_RESPONSES)


@router.get("", response_model=OperationsResponse)
def read_operations(
    context: Annotated[RequestContext, Depends(require_permissions(Permission.OPERATIONS_MONITOR))],
    session: Annotated[Session, Depends(get_database_session)],
    response: Response,
) -> OperationsResponse:
    response.headers["Cache-Control"] = "no-store"
    return OperationsQuery(session).read(context)
