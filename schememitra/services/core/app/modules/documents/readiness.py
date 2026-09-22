"""Pre-submission file check (spec §9.2, claim C16). Catches what banks reject files for — a
missing paper, an unreadable photo, an expired income certificate, a name that does not match,
a quotation that disagrees with the project cost — before the citizen sends anything.

score = 50·presence + 20·legibility + 10·validity + 20·consistency (0–100)"""

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from app.modules.documents.names import match_names

LEGIBLE_MIN_CONFIDENCE = 0.6
AMOUNT_TOLERANCE_BPS = 500  # quotation may differ from declared project cost by up to 5%


@dataclass
class DocView:
    type: str
    fields: dict[str, Any]
    confidence: float
    quality_issues: list[str]
    source: str
    verified: bool = False


@dataclass
class Applicant:
    full_name: str | None
    father_name: str | None = None
    dob: str | None = None
    project_cost_paise: int | None = None


@dataclass
class Finding:
    code: str
    doc: str | None
    key: str
    params: dict[str, Any] = field(default_factory=dict)
    blocking: bool = True


def _months_between(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month) - (1 if end.day < start.day else 0)


def check_readiness(
    required: list[dict[str, Any]], documents: dict[str, DocView], applicant: Applicant, threshold: int,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    findings: list[Finding] = []
    needed = [r for r in required if r["required"]]
    present = [r for r in needed if r["type"] in documents]
    for r in needed:
        if r["type"] not in documents:
            findings.append(Finding("missing", r["type"], "docs.fix.upload", {"doc": r["type"]}))

    legible = 0
    for r in present:
        doc = documents[r["type"]]
        if doc.quality_issues or doc.confidence < LEGIBLE_MIN_CONFIDENCE:
            findings.append(Finding("illegible", r["type"], "docs.fix.retake", {"doc": r["type"]}))
        else:
            legible += 1
        if "aadhaar_invalid" in doc.quality_issues:
            findings.append(Finding("aadhaar_invalid", r["type"], "docs.fix.aadhaar_invalid", {"doc": r["type"]}))

    dated = [r for r in present if r.get("validity_months")]
    valid = 0
    for r in dated:
        issued = documents[r["type"]].fields.get("issue_date")
        if issued and _months_between(date.fromisoformat(issued), today) >= r["validity_months"]:
            findings.append(Finding("expired", r["type"], "docs.fix.expired", {"doc": r["type"], "months": r["validity_months"]}))
        else:
            valid += 1

    consistency_checks = 0
    consistent = 0
    reference = applicant.full_name
    aadhaar_last4 = next((d.fields.get("aadhaar_last4") for d in documents.values() if d.fields.get("aadhaar_last4")), None)
    known_fathers = [applicant.father_name] + [d.fields.get("father_name") for d in documents.values()]
    father_hint = next((f for f in known_fathers if f), None)
    name_matches: dict[str, Any] = {}
    for doc_type, doc in documents.items():
        doc_name = doc.fields.get("name")
        if reference and doc_name:
            consistency_checks += 1
            result = match_names(
                doc_name, reference, dob_left=doc.fields.get("dob"), dob_right=applicant.dob,
                aadhaar_last4_left=doc.fields.get("aadhaar_last4"), aadhaar_last4_right=aadhaar_last4,
                father_left=doc.fields.get("father_name"), father_right=father_hint if father_hint != doc.fields.get("father_name") else applicant.father_name,
            )
            name_matches[doc_type] = {"score": result.score, "matched": result.matched, "reasons": result.reasons,
                                      "document_name": result.left, "declared_name": result.right}
            if result.matched:
                consistent += 1
            else:
                findings.append(Finding("name_mismatch", doc_type, "docs.fix.name_mismatch", {"doc": doc_type}))
        if applicant.dob and doc.fields.get("dob"):
            consistency_checks += 1
            if doc.fields["dob"] == applicant.dob:
                consistent += 1
            else:
                findings.append(Finding("dob_mismatch", doc_type, "docs.fix.dob_mismatch", {"doc": doc_type}))

    quotation = documents.get("project_quotation")
    if quotation and applicant.project_cost_paise and quotation.fields.get("total_paise"):
        consistency_checks += 1
        total = quotation.fields["total_paise"]
        if abs(total - applicant.project_cost_paise) * 10_000 <= applicant.project_cost_paise * AMOUNT_TOLERANCE_BPS:
            consistent += 1
        else:
            findings.append(Finding("amount_mismatch", "project_quotation", "docs.fix.amount_mismatch",
                                    {"doc_amount": total, "project_cost": applicant.project_cost_paise}))

    presence = len(present) / len(needed) if needed else 1.0
    legibility = legible / len(present) if present else 0.0
    validity = valid / len(dated) if dated else (1.0 if present else 0.0)
    consistency = consistent / consistency_checks if consistency_checks else (1.0 if present else 0.0)
    score = round(50 * presence + 20 * legibility + 10 * validity + 20 * consistency)
    blockers = [f for f in findings if f.blocking]
    ready = score >= threshold and not any(f.code == "missing" for f in blockers)
    return {
        "score": score,
        "ready": ready,
        "threshold": threshold,
        "components": {"presence": round(presence, 3), "legibility": round(legibility, 3),
                       "validity": round(validity, 3), "consistency": round(consistency, 3)},
        "blockers": [f.__dict__ for f in blockers],
        "fixes": [{"key": f.key, "params": f.params, "doc": f.doc} for f in findings],
        "name_matches": name_matches,
    }
