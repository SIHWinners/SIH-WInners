"""Relational model (spec §8). Money is integer paise, rates are basis points.
PII columns use EncryptedText; lookup happens through keyed hashes, never plaintext."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import (
    Base,
    EncryptedText,
    IdMixin,
    PortableJSON,
    SoftDeleteMixin,
    TimestampMixin,
    UTCDateTime,
    utcnow,
)

ROLES = ("citizen", "csc_operator", "partner_officer", "admin", "policy_viewer")
PARTNER_TYPES = ("SCA", "PSB", "RRB", "NBFC_MFI")
APPLICATION_STATUSES = (
    "draft", "ready", "submitted", "received_by_partner", "documents_requested", "resubmitted",
    "under_review", "sanctioned", "rejected", "disbursed",
)


class User(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    role: Mapped[str] = mapped_column(String(24), index=True)
    phone_hash: Mapped[str] = mapped_column(String(64), unique=True)
    phone_enc: Mapped[str | None] = mapped_column(EncryptedText)
    display_name: Mapped[str | None] = mapped_column(String(80))  # officers/operators only, not citizens
    preferred_lang: Mapped[str] = mapped_column(String(8), default="en")
    partner_id: Mapped[UUID | None] = mapped_column(ForeignKey("partners.id"))
    csc_id: Mapped[str | None] = mapped_column(String(32))


class OtpChallenge(IdMixin, Base):
    __tablename__ = "otp_challenges"
    phone_hash: Mapped[str] = mapped_column(String(64), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    locked_until: Mapped[datetime | None] = mapped_column(UTCDateTime)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Consent(IdMixin, TimestampMixin, Base):
    __tablename__ = "consents"
    applicant_id: Mapped[UUID | None] = mapped_column(ForeignKey("applicants.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(String(64))
    scope: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    language: Mapped[str] = mapped_column(String(8))
    method: Mapped[str] = mapped_column(String(16))  # otp | thumb | voice
    text_version: Mapped[str] = mapped_column(String(32))
    evidence: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)  # text only, never audio
    captured_by_operator_id: Mapped[UUID | None] = mapped_column(Uuid)
    granted_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    withdrawn_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Applicant(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "applicants"
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    created_by_operator_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    full_name_enc: Mapped[str | None] = mapped_column(EncryptedText)
    father_name_enc: Mapped[str | None] = mapped_column(EncryptedText)
    name_normalized: Mapped[str | None] = mapped_column(String(160))
    name_phonetic: Mapped[str | None] = mapped_column(String(160))
    dob_enc: Mapped[str | None] = mapped_column(EncryptedText)
    phone_enc: Mapped[str | None] = mapped_column(EncryptedText)
    address_enc: Mapped[str | None] = mapped_column(EncryptedText)
    aadhaar_last4: Mapped[str | None] = mapped_column(String(4))
    aadhaar_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    gender: Mapped[str | None] = mapped_column(String(12))
    social_category: Mapped[str | None] = mapped_column(String(24))
    disability_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    disability_pct: Mapped[int | None] = mapped_column(Integer)
    state_code: Mapped[str | None] = mapped_column(String(2))
    district_code: Mapped[str | None] = mapped_column(String(8))
    pincode: Mapped[str | None] = mapped_column(String(6))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    annual_family_income_paise: Mapped[int | None] = mapped_column(BigInteger)
    education_level: Mapped[str | None] = mapped_column(String(24))
    occupation: Mapped[str | None] = mapped_column(String(48))
    profile: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)  # other rule-relevant slots
    consent_id: Mapped[UUID | None] = mapped_column(Uuid)


class Scheme(IdMixin, TimestampMixin, Base):
    __tablename__ = "schemes"
    code: Mapped[str] = mapped_column(String(48), unique=True)
    apex_corp: Mapped[str] = mapped_column(String(16))
    name_i18n: Mapped[dict[str, Any]] = mapped_column(PortableJSON)
    loan_type: Mapped[str] = mapped_column(String(24))
    rule_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    versions: Mapped[list["SchemeRuleVersion"]] = relationship(back_populates="scheme", lazy="raise")


class SchemeRuleVersion(IdMixin, TimestampMixin, Base):
    __tablename__ = "scheme_rule_versions"
    __table_args__ = (UniqueConstraint("scheme_id", "version"),)
    scheme_id: Mapped[UUID] = mapped_column(ForeignKey("schemes.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    rules: Mapped[dict[str, Any]] = mapped_column(PortableJSON)
    params: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    source_url: Mapped[str] = mapped_column(String(300))
    verified_on: Mapped[date | None] = mapped_column(Date)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    author: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), default="published")  # draft | published | retired
    approved_by: Mapped[str | None] = mapped_column(String(80))
    scheme: Mapped[Scheme] = relationship(back_populates="versions", lazy="raise")


class Partner(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "partners"
    name: Mapped[str] = mapped_column(String(160))
    type: Mapped[str] = mapped_column(String(12), index=True)
    state_code: Mapped[str] = mapped_column(String(2), index=True)
    district_code: Mapped[str] = mapped_column(String(8))
    district_name: Mapped[str] = mapped_column(String(64))
    address: Mapped[str] = mapped_column(String(240))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    service_radius_km: Mapped[int] = mapped_column(Integer, default=40)
    schemes_supported: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    categories_supported: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    languages: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    documents_needed: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    open_hours: Mapped[str] = mapped_column(String(64), default="Mon–Fri 10:00–16:00")
    contact: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=True)


class PartnerMetric(Base):
    __tablename__ = "partner_metrics"
    partner_id: Mapped[UUID] = mapped_column(ForeignKey("partners.id", ondelete="CASCADE"), primary_key=True)
    period: Mapped[str] = mapped_column(String(7), primary_key=True)  # YYYY-MM
    recovery_rate: Mapped[float] = mapped_column(Float)  # ratio, not money
    npa_pct: Mapped[float] = mapped_column(Float)
    avg_sanction_days: Mapped[float] = mapped_column(Float)
    funds_allocated_paise: Mapped[int] = mapped_column(BigInteger)
    funds_disbursed_paise: Mapped[int] = mapped_column(BigInteger)
    pending_applications: Mapped[int] = mapped_column(Integer)


class Application(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "applications"
    tracking_id: Mapped[str] = mapped_column(String(20), unique=True)
    applicant_id: Mapped[UUID] = mapped_column(ForeignKey("applicants.id", ondelete="CASCADE"), index=True)
    scheme_id: Mapped[UUID | None] = mapped_column(ForeignKey("schemes.id"))
    rule_version_id: Mapped[UUID | None] = mapped_column(Uuid)
    partner_id: Mapped[UUID | None] = mapped_column(ForeignKey("partners.id"), index=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, index=True)
    requested_amount_paise: Mapped[int | None] = mapped_column(BigInteger)
    project_cost_paise: Mapped[int | None] = mapped_column(BigInteger)
    tenure_months: Mapped[int | None] = mapped_column(Integer)
    moratorium_months: Mapped[int | None] = mapped_column(Integer)
    interest_rate_bps: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    status_history: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    eligibility_trace: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    ranking_explanation: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    finance_summary: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    completeness_score: Mapped[int | None] = mapped_column(Integer)
    submitted_via: Mapped[str] = mapped_column(String(8), default="pwa")  # app | pwa | sms | csc
    lang: Mapped[str] = mapped_column(String(8), default="en")
    rejection_reason_code: Mapped[str | None] = mapped_column(String(32))
    requested_documents: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    content_hash: Mapped[str | None] = mapped_column(String(64))
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    client_uuid: Mapped[str | None] = mapped_column(String(64), unique=True)

    __table_args__ = (Index("ix_applications_status_open", "status"),)


class Document(IdMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    application_id: Mapped[UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    source: Mapped[str] = mapped_column(String(16))  # camera | digilocker | upload
    storage_key: Mapped[str | None] = mapped_column(String(160))
    sha256: Mapped[str] = mapped_column(String(64))
    ocr_json: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    confidence: Mapped[float | None] = mapped_column(Float)
    quality: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_notes: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)
    purge_after: Mapped[datetime | None] = mapped_column(UTCDateTime)
    purged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class Conversation(IdMixin, TimestampMixin, Base):
    __tablename__ = "conversations"
    application_id: Mapped[UUID | None] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    user_id: Mapped[UUID | None] = mapped_column(Uuid)
    lang: Mapped[str] = mapped_column(String(8))
    state: Mapped[str] = mapped_column(String(16), default="intake")
    turns: Mapped[list[Any]] = mapped_column(PortableJSON, default=list)  # text only, no audio retained
    extracted_slots: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    pending_slot: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Notification(IdMixin, TimestampMixin, Base):
    __tablename__ = "notifications"
    application_id: Mapped[UUID | None] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    channel: Mapped[str] = mapped_column(String(8))  # sms | push | ivr
    to_hash: Mapped[str | None] = mapped_column(String(64))
    to_masked: Mapped[str | None] = mapped_column(String(16))
    template_id: Mapped[str] = mapped_column(String(48))
    lang: Mapped[str] = mapped_column(String(8), default="en")
    payload: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    body: Mapped[str] = mapped_column(Text, default="")
    segments: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    provider: Mapped[str] = mapped_column(String(16), default="console")
    provider_msg_id: Mapped[str | None] = mapped_column(String(64))


class OfflineSubmission(IdMixin, Base):
    __tablename__ = "offline_submissions"
    device_id: Mapped[str | None] = mapped_column(String(64))
    client_uuid: Mapped[str] = mapped_column(String(64), unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    received_via: Mapped[str] = mapped_column(String(8))  # data | sms
    application_id: Mapped[UUID | None] = mapped_column(Uuid)
    response: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class SmsInboundPart(IdMixin, Base):
    __tablename__ = "sms_inbound_parts"
    __table_args__ = (UniqueConstraint("sender_hash", "message_ref", "part_no"),)
    sender_hash: Mapped[str] = mapped_column(String(64), index=True)
    message_ref: Mapped[str] = mapped_column(String(8))
    part_no: Mapped[int] = mapped_column(Integer)
    part_total: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(80))
    actor_role: Mapped[str] = mapped_column(String(24))
    action: Mapped[str] = mapped_column(String(64))
    entity: Mapped[str] = mapped_column(String(80), index=True)
    diff: Mapped[dict[str, Any]] = mapped_column(PortableJSON, default=dict)
    at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event: Mapped[str] = mapped_column(String(40))
    step: Mapped[str | None] = mapped_column(String(24))
    lang: Mapped[str | None] = mapped_column(String(8))
    state_code: Mapped[str | None] = mapped_column(String(2))
    district_code: Mapped[str | None] = mapped_column(String(8))
    scheme_code: Mapped[str | None] = mapped_column(String(48))
    partner_type: Mapped[str | None] = mapped_column(String(12))
    social_category: Mapped[str | None] = mapped_column(String(24))
    gender: Mapped[str | None] = mapped_column(String(12))
    bucketed_age: Mapped[str | None] = mapped_column(String(8))
    bucketed_income: Mapped[str | None] = mapped_column(String(12))
    reason_code: Mapped[str | None] = mapped_column(String(32))
    value: Mapped[float | None] = mapped_column(Float)  # e.g. days-to-sanction; never money or identifiers
    ts: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


class FeatureFlag(Base):
    __tablename__ = "feature_flags"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(PortableJSON)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)
    updated_by: Mapped[str | None] = mapped_column(String(80))
