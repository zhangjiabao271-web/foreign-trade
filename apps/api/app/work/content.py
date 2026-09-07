"""Detached Work projections and exact-version human release checks."""

import hashlib
import json
from copy import deepcopy

from app.auth.context import RequestContext
from app.auth.permissions import Permission
from app.work.models import Activity, Task
from app.work.schemas import ActivityResponse, TaskResponse


def content_digest(row: Task | Activity, *, version: int | None = None) -> str:
    facts = {
        "kind": "task" if isinstance(row, Task) else "activity",
        "id": str(row.id),
        "organization_id": str(row.organization_id),
        "subject_type": row.subject_type,
        "subject_id": str(row.subject_id),
        "version": row.version if version is None else version,
        "text": row.title if isinstance(row, Task) else row.summary,
        "details": row.details,
    }
    return hashlib.sha256(
        json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def is_released(row: Task | Activity) -> bool:
    return (
        row.reviewed_by is not None
        and row.reviewed_at is not None
        and row.released_digest == content_digest(row)
    )


def task_response(context: RequestContext, row: Task) -> TaskResponse:
    released = is_released(row)
    visible = Permission.PROFIT_READ in context.permissions or released
    response = TaskResponse.model_validate(row)
    return response.model_copy(
        update={
            "title": row.title if visible else None,
            "details": deepcopy(row.details) if visible else {},
            "content_visible": visible,
            "released": released,
        }
    )


def activity_response(context: RequestContext, row: Activity) -> ActivityResponse:
    released = is_released(row)
    visible = Permission.PROFIT_READ in context.permissions or released
    response = ActivityResponse.model_validate(row)
    return response.model_copy(
        update={
            "summary": row.summary if visible else None,
            "details": deepcopy(row.details) if visible else {},
            "content_visible": visible,
            "released": released,
        }
    )
