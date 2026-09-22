"""Field extraction templates per document type: label proximity + regex over OCR lines.
Each field records the confidence of the line it came from; missing required fields lower the
document confidence so the readiness checker can ask for a retake or a DigiLocker pull."""

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.modules.documents.aadhaar import AADHAAR_RE, find_aadhaar, protect
from app.modules.documents.ocr import OcrResult

DOC_TYPES = ("aadhaar", "caste_certificate", "income_certificate", "disability_certificate", "bank_passbook",
             "marksheet", "project_quotation", "admission_letter", "shg_certificate")

LABEL = {
    "name": r"(?:^|\b)(?:name(?! of)|applicant|beneficiary|account holder|नाम|નામ|பெயர்)\s*[:\-]\s*(.+)",
    "father_name": r"(?:father'?s?\s*name|s/o|son of|पिता का नाम|પિતાનું નામ)\s*[:\-]?\s*(.+)",
    "dob": r"(?:dob|date of birth|जन्म तिथि|જન્મ તારીખ)\s*[:\-]?\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})",
    "issue_date": r"(?:date of issue|issued on|issue date|dated|जारी करने की तिथि)\s*[:\-]?\s*(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})",
    "income": r"(?:annual (?:family )?income|वार्षिक आय)[^\d₹]*(?:rs\.?|₹|inr)?\s*([\d,]{4,})",
    "total": r"(?:grand total|total amount|total|कुल)[^\d₹]*(?:rs\.?|₹|inr)?\s*([\d,]{4,}(?:\.\d{2})?)",
    "fee": r"(?:total (?:course )?fee|course fee|fees)[^\d₹]*(?:rs\.?|₹|inr)?\s*([\d,]{4,})",
    "udid": r"udid\s*(?:no\.?|number)?\s*[:\-]?\s*([a-z0-9]{16,20})",
    "account": r"(?:a/?c|account)\s*(?:no\.?|number)?\s*[:\-]?\s*(\d{9,18})",
    "ifsc": r"\b([a-z]{4}0[a-z0-9]{6})\b",
    "percent": r"(\d{2,3})\s*%",
    "institution": r"(?:institute|college|polytechnic|university)\s*[:\-]?\s*(.+)",
    "course": r"(?:course|programme|program)\s*[:\-]\s*(.+)",
    "shg": r"(?:self help group|shg)\s*(?:name)?\s*[:\-]\s*(.+)",
    "vendor": r"(?:vendor|supplier|dealer|firm)\s*[:\-]\s*(.+)",
}
CATEGORY_WORDS = [
    ("safai_karamchari", ("safai karamchari", "manual scavenger")),
    ("sc", ("scheduled caste", "अनुसूचित जाति")),
    ("st", ("scheduled tribe", "अनुसूचित जनजाति")),
    ("obc", ("other backward", "backward class", "अन्य पिछड़ा")),
]
REQUIRED = {
    "aadhaar": ["name", "aadhaar_last4"],
    "caste_certificate": ["name", "category", "issue_date"],
    "income_certificate": ["name", "annual_income_paise", "issue_date"],
    "disability_certificate": ["name", "disability_pct"],
    "bank_passbook": ["name", "account_last4"],
    "marksheet": ["name"],
    "project_quotation": ["total_paise"],
    "admission_letter": ["name", "course"],
    "shg_certificate": ["name"],
}


@dataclass
class Extraction:
    fields: dict[str, Any] = field(default_factory=dict)
    field_confidence: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    aadhaar_boxes: list[tuple[int, int, int, int]] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def _date(value: str) -> str | None:
    parts = re.split(r"[/\-.]", value)
    try:
        d, m, y = (int(p) for p in parts)
        return date(y, m, d).isoformat()
    except (ValueError, TypeError):
        return None


def _amount_paise(value: str) -> int:
    whole, _, frac = value.replace(",", "").partition(".")
    return int(whole) * 100 + int((frac + "00")[:2] if frac else 0)


def _clean_name(value: str) -> str:
    return re.split(r"\s{2,}|\||,|\bdob\b|\bdate\b", value, flags=re.IGNORECASE)[0].strip(" .:-")


def extract_fields(doc_type: str, ocr: OcrResult) -> Extraction:
    out = Extraction()

    def take(field_name: str, pattern_key: str, convert: Any = None) -> None:
        if field_name in out.fields:
            return
        for line in ocr.lines:
            m = re.search(LABEL[pattern_key], line.text, flags=re.IGNORECASE)
            if m:
                value = convert(m.group(1)) if convert else m.group(1).strip()
                if value in (None, ""):
                    continue
                out.fields[field_name] = value
                out.field_confidence[field_name] = round(line.confidence, 3)
                return

    take("name", "name", _clean_name)
    take("father_name", "father_name", _clean_name)
    take("dob", "dob", _date)
    take("issue_date", "issue_date", _date)

    if doc_type == "aadhaar":
        number = find_aadhaar(ocr.text)
        if number:
            out.fields.update(protect(number))  # never the full number
            out.field_confidence["aadhaar_last4"] = max((ln.confidence for ln in ocr.lines if number[-4:] in ln.text), default=0.0)
            out.aadhaar_boxes = [line.box for line in ocr.lines if AADHAAR_RE.search(line.text)]
        elif AADHAAR_RE.search(ocr.text):
            out.issues.append("aadhaar_invalid")
    elif doc_type in ("caste_certificate", "shg_certificate", "disability_certificate", "income_certificate"):
        lowered = ocr.text.lower()
        for category, words in CATEGORY_WORDS:
            if any(w.lower() in lowered for w in words):
                out.fields["category"] = category
                out.field_confidence["category"] = ocr.mean_confidence
                break
        take("annual_income_paise", "income", _amount_paise)
        take("udid", "udid", lambda v: v.upper())
        if doc_type == "disability_certificate":
            take("disability_pct", "percent", int)
        take("shg_name", "shg", _clean_name)
    elif doc_type == "bank_passbook":
        take("account_last4", "account", lambda v: v[-4:])
        take("ifsc", "ifsc", lambda v: v.upper())
    elif doc_type == "project_quotation":
        take("total_paise", "total", _amount_paise)
        take("vendor", "vendor", _clean_name)
    elif doc_type == "admission_letter":
        take("course", "course", _clean_name)
        take("institution", "institution", _clean_name)
        take("fee_paise", "fee", _amount_paise)

    required = REQUIRED.get(doc_type, [])
    found = [f for f in required if f in out.fields]
    base = sum(out.field_confidence.get(f, 0.0) for f in found) / len(found) if found else 0.0
    out.confidence = round(base * (len(found) / len(required) if required else 1.0), 3)
    return out
