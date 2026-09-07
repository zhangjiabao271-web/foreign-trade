from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.companies.enums import CompanyRoleType


class CompanyRoleRequest(BaseModel):
    role: CompanyRoleType


class CompanyRoleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    company_id: UUID
    role: CompanyRoleType
    version: int


class CompanyFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=240)
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    website: str | None = Field(default=None, max_length=500, pattern=r"^https?://[^\s]+$")


class CompanyCreate(CompanyFields):
    roles: list[CompanyRoleType] = Field(min_length=1, max_length=4)

    @field_validator("roles")
    @classmethod
    def unique_roles(cls, value: list[CompanyRoleType]) -> list[CompanyRoleType]:
        if len(value) != len(set(value)):
            raise ValueError("Select each role once")
        return value


class CompanyUpdate(CompanyFields):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class CompanyResponse(CompanyFields):
    model_config = ConfigDict(from_attributes=True)
    country_code: str | None = None
    website: str | None = None
    id: UUID
    version: int
    created_at: datetime
    roles: list[CompanyRoleType] = Field(default_factory=list)


class CompanyListResponse(BaseModel):
    items: list[CompanyResponse]
    has_more: bool
    next_cursor: UUID | None


class ContactFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    full_name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    phone: str | None = Field(default=None, max_length=80)
    job_title: str | None = Field(default=None, max_length=160)


class ContactUpdate(ContactFields):
    expected_version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class ContactResponse(ContactFields):
    model_config = ConfigDict(from_attributes=True)
    email: str | None = None
    id: UUID
    company_id: UUID
    version: int
    created_at: datetime


class ContactListResponse(BaseModel):
    items: list[ContactResponse]
    has_more: bool
    next_cursor: UUID | None
