from typing import Any, Literal

from pydantic import BaseModel, Field

SocialCategory = Literal["sc", "st", "obc", "safai_karamchari", "minority", "general"]
Gender = Literal["female", "male", "other"]


class ApplicantFacts(BaseModel):
    """Only rule-relevant facts (DPDP data minimisation). Money in paise."""

    age: int | None = Field(default=None, ge=0, le=120)
    gender: Gender | None = None
    social_category: SocialCategory | None = None
    has_disability: bool | None = None
    disability_pct: int | None = Field(default=None, ge=0, le=100)
    state_code: str | None = Field(default=None, min_length=2, max_length=2)
    district_code: str | None = Field(default=None, max_length=8)
    pincode: str | None = Field(default=None, pattern=r"^\d{6}$")
    annual_family_income_paise: int | None = Field(default=None, ge=0, le=10_000_000_000)
    education_level: str | None = Field(default=None, max_length=24)
    occupation: str | None = Field(default=None, max_length=48)
    business_type: str | None = Field(default=None, max_length=32)
    project_cost_paise: int | None = Field(default=None, ge=0, le=100_000_000_000)
    loan_needed_paise: int | None = Field(default=None, ge=0, le=100_000_000_000)
    existing_loans: bool | None = None
    shg_member: bool | None = None
    course_admitted: bool | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)

    def facts(self) -> dict[str, Any]:
        data = self.model_dump()
        # Someone without a disability certificate has 0% benchmark disability, not "unknown".
        if data["disability_pct"] is None and data["has_disability"] is False:
            data["disability_pct"] = 0
        if data["state_code"]:
            data["state_code"] = data["state_code"].upper()
        return data


class TypedValue(BaseModel):
    type: str
    value: Any = None


class Sentence(BaseModel):
    key: str
    params: dict[str, TypedValue] = {}


class TraceRow(BaseModel):
    id: str
    kind: str
    result: Literal["pass", "fail", "unknown"]
    inputs: dict[str, Any]
    logic: dict[str, Any]
    sentence: Sentence
    change: Sentence | None = None


class FundingPattern(BaseModel):
    apex_bps: int
    partner_bps: int
    beneficiary_bps: int


class Offer(BaseModel):
    rate_bps: int
    max_loan_paise: int
    suggested_principal_paise: int | None
    default_tenure_months: int
    max_tenure_months: int
    moratorium_default_months: int
    moratorium_max_months: int
    moratorium_treatment: str
    repayment_frequency: str
    funding_pattern: FundingPattern
    processing_days: int


class SchemeResult(BaseModel):
    code: str
    name: dict[str, str]
    apex_corp: str
    loan_type: str
    version: int
    rule_version_id: str | None
    source_url: str
    verified_on: str | None
    needs_verification: bool
    status: Literal["eligible", "ineligible", "needs_info"]
    trace: list[TraceRow]
    failed: list[str]
    missing: list[str]
    near_miss: TraceRow | None
    documents_required: list[dict[str, Any]]
    channel_partner_types: list[str]
    offer: Offer
    rank: "RankInfo | None" = None


class RankReason(BaseModel):
    feature: str
    key: str
    params: dict[str, Any] = {}
    weight: float


class RankInfo(BaseModel):
    """Order among eligible schemes only. `method` is `model` (XGBoost + TreeSHAP) or `heuristic` (§13 fallback)."""

    position: int
    score: float
    method: Literal["model", "heuristic"]
    reasons: list[RankReason]
    features: dict[str, float]


class EvaluateRequest(BaseModel):
    applicant: ApplicantFacts
    scheme_codes: list[str] | None = None


class EvaluateResponse(BaseModel):
    rules_etag: str
    eligible: list[str]
    ineligible: list[str]
    needs_info: list[str]
    near_misses: list[str]
    next_best: str | None
    ranking_method: Literal["model", "heuristic", "none"] | None = None
    results: list[SchemeResult]


class RankRequest(BaseModel):
    applicant: ApplicantFacts
    scheme_codes: list[str] | None = None


class RankedScheme(BaseModel):
    code: str
    position: int
    score: float
    reasons: list[RankReason]


class RankResponse(BaseModel):
    method: Literal["model", "heuristic", "none"]
    ranked: list[RankedScheme]
