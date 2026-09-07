from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.identity.enums import MembershipRole, MembershipStatus, OrganizationStatus, UserStatus


class IdentityCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    reason: str = Field(min_length=3, max_length=500)


class IdentityVersionCommand(IdentityCommand):
    expected_version: int = Field(ge=1)


class OrganizationUpdate(IdentityVersionCommand):
    name: str = Field(min_length=1, max_length=200)
    timezone: str = Field(min_length=1, max_length=64)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("Provide an installed IANA timezone name") from error
        return value


class MemberCreate(IdentityCommand):
    external_subject: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=200)
    role: MembershipRole


class MemberRoleChange(IdentityVersionCommand):
    role: MembershipRole


class OrganizationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version: int
    name: str
    timezone: str
    status: OrganizationStatus


class MemberResponse(BaseModel):
    id: UUID
    user_id: UUID
    version: int
    external_subject: str
    display_name: str
    user_status: UserStatus
    role: MembershipRole
    status: MembershipStatus
    created_at: datetime


class MemberListResponse(BaseModel):
    items: list[MemberResponse]
    has_more: bool
    next_cursor: UUID | None


class IdentityCommandResponse(BaseModel):
    id: UUID
