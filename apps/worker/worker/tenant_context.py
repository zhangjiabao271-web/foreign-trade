from typing import NotRequired, TypedDict
from uuid import UUID


class TenantTaskContext(TypedDict):
    organization_id: str
    request_id: str
    actor_user_id: NotRequired[str | None]


def validate_tenant_task_context(context: TenantTaskContext) -> TenantTaskContext:
    UUID(context["organization_id"])
    UUID(context["request_id"])
    actor_user_id = context.get("actor_user_id")
    if actor_user_id is not None:
        UUID(actor_user_id)
    return context
