from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.catalog.schemas import normalize_currency
from app.documents.enums import DocumentType
from app.export.enums import CustomsStatus, TaxRefundStatus


class CustomsCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    shipment_id: UUID
    declared_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    currency_code: str
    required_document_types: list[DocumentType] = Field(
        default_factory=lambda: [DocumentType.COMMERCIAL_INVOICE, DocumentType.PACKING_LIST],
        min_length=1,
        max_length=20,
    )
    follow_up_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("currency_code")
    @classmethod
    def currency(cls, value: str) -> str:
        return normalize_currency(value)

    @field_validator("required_document_types")
    @classmethod
    def unique_checklist(cls, values: list[DocumentType]) -> list[DocumentType]:
        if len(set(values)) != len(values):
            raise ValueError("Checklist types must be unique")
        return values


class RefundCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    customs_declaration_id: UUID
    expected_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    required_document_types: list[DocumentType] = Field(
        default_factory=lambda: [DocumentType.COMMERCIAL_INVOICE, DocumentType.BILL_OF_LADING],
        min_length=1,
        max_length=20,
    )
    follow_up_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("required_document_types")
    @classmethod
    def unique_checklist(cls, values: list[DocumentType]) -> list[DocumentType]:
        return CustomsCreate.unique_checklist(values)


class CaseCommand(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, min_length=3, max_length=1000)


class ManualSubmission(CaseCommand):
    external_reference: str = Field(min_length=1, max_length=160)
    occurred_on: date


class CustomsClear(CaseCommand):
    occurred_on: date


class RefundReceived(CaseCommand):
    occurred_on: date
    refunded_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=4)


class CaseReject(CaseCommand):
    reason: str = Field(min_length=3, max_length=1000)


class FollowUpSchedule(CaseCommand):
    follow_up_date: date | None
    reason: str = Field(min_length=3, max_length=1000)


class CaseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    content_visible: bool = False
    released: bool = False
    id: UUID
    currency_code: str
    required_document_types: list[DocumentType]
    missing_document_types: list[DocumentType] = Field(default_factory=list)
    external_reference: str | None
    submitted_on: date | None
    follow_up_date: date | None
    notes: str | None
    rejection_reason: str | None
    version: int
    created_at: datetime


class CustomsResponse(CaseResponse):
    declaration_number: str
    shipment_id: UUID
    status: CustomsStatus
    declared_amount: Decimal
    cleared_on: date | None


class RefundResponse(CaseResponse):
    case_number: str
    customs_declaration_id: UUID
    status: TaxRefundStatus
    expected_amount: Decimal
    refunded_amount: Decimal
    refunded_on: date | None


class CustomsListResponse(BaseModel):
    items: list[CustomsResponse]
    next_cursor: str | None
    has_more: bool


class RefundListResponse(BaseModel):
    items: list[RefundResponse]
    next_cursor: str | None
    has_more: bool
