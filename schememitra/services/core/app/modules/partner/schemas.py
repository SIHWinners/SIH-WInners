from typing import Any, Literal

from pydantic import BaseModel, Field

from app.modules.applications.schemas import ApplicationOut

Action = Literal["receive", "start_review", "request_documents", "approve", "reject", "disburse"]
ACTION_TARGET: dict[str, str] = {"receive": "received_by_partner", "start_review": "under_review",
                                 "request_documents": "documents_requested", "approve": "sanctioned", "reject": "rejected",
                                 "disburse": "disbursed"}


class QueueItem(BaseModel):
    id: str
    tracking_id: str | None
    status: str
    applicant_name: str
    district: str | None
    scheme_code: str | None
    scheme_name: str | None
    amount_paise: int | None
    submitted_at: str | None
    age_hours: float | None
    readiness_score: int | None
    name_match_min: float | None
    submitted_via: str
    lang: str
    overdue: bool


class QueueOut(BaseModel):
    items: list[QueueItem]
    counts: dict[str, int]
    partner_name: str | None


class ScanIn(BaseModel):
    jws: str = Field(min_length=20, max_length=2000)


class ScanOut(BaseModel):
    application_id: str
    tracking_id: str
    status: str
    signature_valid: bool
    file_unchanged: bool
    issued_at: str
    received_now: bool


class SanctionTerms(BaseModel):
    amount_paise: int = Field(gt=0, le=10_000_000_000)
    rate_bps: int = Field(ge=0, le=3600)
    tenure_months: int = Field(ge=3, le=240)
    moratorium_months: int = Field(default=0, ge=0, le=60)


class DecisionIn(BaseModel):
    action: Action
    reason_code: str | None = None
    note: str | None = Field(default=None, max_length=500)
    documents: list[str] = []
    sanction: SanctionTerms | None = None


class ReviewDocument(BaseModel):
    document_id: str
    type: str
    source: str
    status: str
    verified: bool
    confidence: float
    sandbox: bool
    fields: dict[str, Any]
    issues: list[str]
    has_image: bool
    name_match: dict[str, Any] | None = None


class AuditEntry(BaseModel):
    at: str
    actor_role: str
    action: str
    diff: dict[str, Any]
    hash: str


class ReviewOut(BaseModel):
    application: ApplicationOut
    applicant: dict[str, Any]
    scheme: dict[str, Any]
    finance: dict[str, Any]
    documents: list[ReviewDocument]
    readiness: dict[str, Any]
    consent: dict[str, Any] | None
    audit: list[AuditEntry]
    allowed_actions: list[Action]
    reject_reasons: list[str]
    integrity: dict[str, Any]
    sanction_letter_url: str | None
