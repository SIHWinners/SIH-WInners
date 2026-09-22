from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.modules.eligibility.schemas import ApplicantFacts


class PersonalIn(BaseModel):
    full_name: str | None = Field(default=None, max_length=120)
    father_name: str | None = Field(default=None, max_length=120)
    dob: date | None = None
    phone: str | None = Field(default=None, pattern=r"^[6-9]\d{9}$")


class LoanPlanIn(BaseModel):
    principal_paise: int = Field(gt=0, le=100_000_000_000)
    rate_bps: int = Field(ge=0, le=3000)
    tenure_months: int = Field(ge=1, le=360)
    moratorium_months: int = Field(default=0, ge=0, le=60)
    treatment: Literal["interest_capitalised", "interest_paid_monthly", "interest_waived"] = "interest_capitalised"
    frequency: Literal["monthly", "quarterly"] = "monthly"


class DraftIn(BaseModel):
    client_uuid: str = Field(min_length=8, max_length=64)
    lang: str = Field(default="en", max_length=8)
    personal: PersonalIn = PersonalIn()
    facts: ApplicantFacts
    scheme_code: str = Field(max_length=48)
    plan: LoanPlanIn
    partner_id: str
    submitted_via: Literal["app", "pwa", "sms", "csc"] = "pwa"

    @field_validator("lang")
    @classmethod
    def _lang(cls, v: str) -> str:
        from app.core.i18n import LOCALES

        return v if v in LOCALES else "en"


class TimelineItem(BaseModel):
    status: str
    at: str
    note_key: str | None = None
    params: dict[str, Any] = {}


class ApplicationOut(BaseModel):
    id: str
    tracking_id: str
    status: str
    scheme_code: str | None
    partner_id: str | None
    partner_name: str | None
    lang: str
    submitted_via: str
    completeness_score: int | None
    eligibility_status: str | None
    plan: dict[str, Any]
    finance: dict[str, Any]
    requested_documents: list[str]
    rejection_reason_code: str | None
    timeline: list[TimelineItem]
    documents: list[dict[str, Any]]
    consent_recorded: bool
    created_at: str
    submitted_at: str | None


class ReadinessOut(BaseModel):
    score: int
    ready: bool
    threshold: int
    components: dict[str, float]
    blockers: list[dict[str, Any]]
    fixes: list[dict[str, Any]]
    name_matches: dict[str, Any]
    required_documents: list[dict[str, Any]]


class ConsentIn(BaseModel):
    method: Literal["otp", "thumb", "voice"]
    language: str = Field(max_length=8)
    text_version: str = Field(default="2026-09-v1", max_length=32)
    scope: list[str] = ["profile", "documents", "share_partner"]
    evidence: dict[str, Any] = {}


class SubmitOut(BaseModel):
    tracking_id: str
    status: str
    qr_png_url: str
    loan_file_pdf_url: str
    qr_token: str


class TrackOut(BaseModel):
    tracking_id: str
    status: str
    scheme_code: str | None
    partner_name: str | None
    partner_type: str | None
    expected_days: int | None
    timeline: list[TimelineItem]
    next_step_key: str
    requested_documents: list[str]
    rejection_reason_code: str | None
    lang: str
