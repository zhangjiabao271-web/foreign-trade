from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.context import RequestContext
from app.auth.dependencies import get_database_session, require_permissions
from app.auth.errors import PROBLEM_RESPONSES
from app.auth.permissions import Permission
from app.platform.repositories import AsyncJobRepository
from app.platform.schemas import AsyncJobListResponse, AsyncJobResponse
from app.platform.services import AsyncJobQueryService

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"], responses=PROBLEM_RESPONSES)
JobReader = Annotated[
    RequestContext,
    Depends(require_permissions(Permission.JOB_READ)),
]
DatabaseSession = Annotated[Session, Depends(get_database_session)]


@router.get("", response_model=AsyncJobListResponse)
def list_jobs(context: JobReader, session: DatabaseSession) -> AsyncJobListResponse:
    service = AsyncJobQueryService(AsyncJobRepository(session))
    jobs = service.list(context)
    return AsyncJobListResponse(
        items=[AsyncJobResponse.model_validate(job) for job in jobs],
        count=service.count(context),
    )


@router.get("/{job_id}", response_model=AsyncJobResponse)
def read_job(job_id: UUID, context: JobReader, session: DatabaseSession) -> AsyncJobResponse:
    service = AsyncJobQueryService(AsyncJobRepository(session))
    return AsyncJobResponse.model_validate(service.get(context, job_id))
