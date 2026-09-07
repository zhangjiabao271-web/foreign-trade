from dataclasses import dataclass
from uuid import UUID

from app.auth.errors import ApiProblem
from app.auth.permissions import Permission


@dataclass(frozen=True, slots=True)
class RequestContext:
    user_id: UUID
    organization_id: UUID
    permissions: frozenset[Permission]
    request_id: UUID

    def require(self, *required: Permission) -> None:
        missing = [
            permission.value for permission in required if permission not in self.permissions
        ]
        if missing:
            raise ApiProblem(
                status=403,
                code="PERMISSION_DENIED",
                title="Permission denied",
                detail=f"Missing required permission: {', '.join(missing)}.",
            )
