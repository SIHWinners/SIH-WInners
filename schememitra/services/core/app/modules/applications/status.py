"""Application status machine (spec §9.7). The app prepares and routes; only the partner moves
a file to sanctioned / rejected / disbursed (claim C21)."""

CITIZEN_SIDE = {"citizen", "csc_operator"}
PARTNER_SIDE = {"partner_officer"}

# from → {to: roles allowed}
TRANSITIONS: dict[str, dict[str, set[str]]] = {
    "draft": {"ready": CITIZEN_SIDE | {"system"}, "submitted": CITIZEN_SIDE},
    "ready": {"draft": CITIZEN_SIDE | {"system"}, "submitted": CITIZEN_SIDE},
    "submitted": {"received_by_partner": PARTNER_SIDE},
    "received_by_partner": {"documents_requested": PARTNER_SIDE, "under_review": PARTNER_SIDE, "rejected": PARTNER_SIDE},
    "documents_requested": {"resubmitted": CITIZEN_SIDE, "rejected": PARTNER_SIDE},
    "resubmitted": {"under_review": PARTNER_SIDE, "documents_requested": PARTNER_SIDE, "rejected": PARTNER_SIDE},
    "under_review": {"sanctioned": PARTNER_SIDE, "rejected": PARTNER_SIDE, "documents_requested": PARTNER_SIDE},
    "sanctioned": {"disbursed": PARTNER_SIDE},
    "rejected": {},
    "disbursed": {},
}

TIMELINE = ["submitted", "received_by_partner", "under_review", "sanctioned", "disbursed"]
TERMINAL = {"rejected", "disbursed"}
REJECT_REASONS = ("income_proof_invalid", "category_proof_invalid", "project_not_viable", "existing_default",
                  "duplicate_application", "funds_exhausted", "other")
# SMS template per status change; statuses without one fall back to the generic status template.
SMS_TEMPLATE = {"submitted": "sms.submitted", "documents_requested": "sms.documents_requested",
                "sanctioned": "sms.sanctioned", "rejected": "sms.rejected", "disbursed": "sms.disbursed"}


# Lending decisions belong to the lender alone (C21): not even a SchemeMitra admin can make them.
LENDER_DECISIONS = {"sanctioned", "rejected", "disbursed"}


def can_transition(current: str, target: str, role: str) -> bool:
    allowed = TRANSITIONS.get(current, {}).get(target)
    if allowed is None:
        return False
    if role == "admin":
        return target not in LENDER_DECISIONS
    return role in allowed
