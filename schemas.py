"""Validation at both boundaries: HTTP requests and model-generated data."""

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator

from validation import DocumentType, Status

Name = Annotated[str, Field(min_length=1, max_length=200)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ExtractedDocuments(StrictModel):
    identity_verification: StrictBool = Field(alias="Identity Verification")
    tax_form: StrictBool = Field(alias="Tax Form")
    corporate_registration: StrictBool = Field(alias="Corporate Registration")
    beneficial_ownership: StrictBool = Field(alias="Beneficial Ownership")


class ClientExtraction(StrictModel):
    company_name: Name
    contact_name: Name | None
    account_type: Literal["Institutional"]
    state: Annotated[str, Field(min_length=1, max_length=100)] | None
    expected_monthly_volume: Annotated[float, Field(ge=0, allow_inf_nan=False, strict=True)] | None
    documents: ExtractedDocuments


class NoteRequest(StrictModel):
    note: str = Field(min_length=20, max_length=10000)


class DocumentRequest(StrictModel):
    document_type: DocumentType


class ORMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class DocumentResponse(ORMResponse):
    id: int
    document_type: DocumentType
    received: bool


class TimestampResponse(ORMResponse):
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def mark_sqlite_time_as_utc(cls, value: datetime) -> datetime:
        # SQLite returns naive datetimes; this project writes only UTC.
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class ClientResponse(TimestampResponse):
    id: int
    company_name: str
    contact_name: str | None
    account_type: str
    state: str | None
    expected_monthly_volume: float | None
    status: Status
    documents: list[DocumentResponse]
    missing_documents: list[DocumentType]
    summary: str
    summary_source: Literal["mock", "openai", "rules"]


class EventResponse(TimestampResponse):
    id: int
    client_id: int
    event_type: str
    description: str


class HealthResponse(BaseModel):
    status: Literal["ok"]
    llm_mode: Literal["mock", "openai"]
