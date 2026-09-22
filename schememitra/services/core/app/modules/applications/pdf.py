"""Bank-ready loan file (spec §9.5, claim C18): bilingual (English + applicant's language),
2–4 pages, fonts subsetted, target < 400 KB. Rendered with fpdf2 + HarfBuzz shaping (ADR-002)
so conjuncts and matras in Indic scripts come out correctly."""

import io
from datetime import UTC, datetime
from typing import Any

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.config import CORE_DIR
from app.core.i18n import money, t
from app.modules.applications.sentences import render_sentence

FONTS = CORE_DIR / "assets" / "fonts"
SCRIPT_FONT = {
    "hi": "NotoSansDevanagari", "mr": "NotoSansDevanagari", "bn": "NotoSansBengali", "as": "NotoSansBengali",
    "gu": "NotoSansGujarati", "pa": "NotoSansGurmukhi", "ta": "NotoSansTamil", "te": "NotoSansTelugu",
    "kn": "NotoSansKannada", "ml": "NotoSansMalayalam", "or": "NotoSansOriya", "ur": "NotoNaskhArabic",
}
BRAND = (11, 61, 145)
MUTED = (71, 84, 103)


class LoanFile(FPDF):
    def __init__(self, lang: str, tracking_id: str) -> None:
        super().__init__(format="A4")
        self.lang, self.tracking_id = lang, tracking_id
        self.set_auto_page_break(True, margin=18)
        self.add_font("sans", "", str(FONTS / "NotoSans-Regular.ttf"))
        self.add_font("sans", "B", str(FONTS / "NotoSans-Bold.ttf"))
        fallbacks = []
        if lang in SCRIPT_FONT:
            self.add_font("local", "", str(FONTS / f"{SCRIPT_FONT[lang]}-Regular.ttf"))
            self.add_font("local", "B", str(FONTS / f"{SCRIPT_FONT[lang]}-Bold.ttf"))
            fallbacks.append("local")
        self.set_fallback_fonts(fallbacks)
        self.set_text_shaping(True)
        self.set_margins(16, 16, 16)

    def header(self) -> None:
        self.set_fill_color(*BRAND)
        self.rect(0, 0, 210, 14, style="F")
        self.set_xy(16, 4)
        self.set_text_color(255, 255, 255)
        self.set_font("sans", "B", 10)
        self.cell(0, 6, f"SchemeMitra · Loan file · {self.tracking_id}")
        self.set_text_color(16, 24, 40)
        self.set_y(20)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("sans", "", 7.5)
        self.set_text_color(*MUTED)
        free = t("en", "common.free_service")
        self.cell(0, 4, f"{free}  ·  Page {self.page_no()}/{{nb}}", align="C")

    def bi(self, key: str, **params: Any) -> str:
        english = t("en", key, **params)
        return english if self.lang == "en" else f"{english} / {t(self.lang, key, **params)}"

    def section(self, title: str) -> None:
        self.ln(2)
        self.set_font("sans", "B", 11.5)
        self.set_text_color(*BRAND)
        self.multi_cell(0, 7, title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(227, 231, 239)
        self.line(16, self.get_y(), 194, self.get_y())
        self.ln(1.5)
        self.set_text_color(16, 24, 40)

    def row(self, label: str, value: str) -> None:
        # Measure both columns first so a wrapped label never overlaps the next row.
        self.set_font("sans", "", 9)
        label_h = float(self.multi_cell(72, 5.2, label, dry_run=True, output="HEIGHT"))  # type: ignore[arg-type]
        self.set_font("sans", "B", 9.5)
        value_h = float(self.multi_cell(0, 5.2, value, dry_run=True, output="HEIGHT"))  # type: ignore[arg-type]
        height = max(label_h, value_h)
        if self.get_y() + height > self.page_break_trigger:
            self.add_page()
        y = self.get_y()
        self.set_font("sans", "", 9)
        self.set_text_color(*MUTED)
        self.multi_cell(72, 5.2, label, new_x=XPos.RIGHT, new_y=YPos.TOP)
        self.set_text_color(16, 24, 40)
        self.set_font("sans", "B", 9.5)
        self.multi_cell(0, 5.2, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_y(y + height + 0.8)


def render_loan_file(view: dict[str, Any], qr_png: bytes) -> bytes:
    lang = view["lang"]
    pdf = LoanFile(lang, view["tracking_id"])
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.set_font("sans", "B", 17)
    pdf.cell(0, 9, pdf.bi("send.submitted_title"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("sans", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(128, 5, f"{pdf.bi('send.tracking_id')}: {view['tracking_id']}\n"
                            f"Submitted: {view['submitted_at']} · Scheme rules v{view['scheme']['version']}",
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.image(io.BytesIO(qr_png), x=160, y=20, w=34)
    pdf.set_xy(156, 55)
    pdf.set_font("sans", "", 6.5)
    pdf.multi_cell(42, 3, t("en", "send.qr_note"), align="C")
    pdf.set_y(62)

    a = view["applicant"]
    pdf.section(pdf.bi("intake.title"))
    pdf.row(pdf.bi("intake.name"), a["full_name"] or "—")
    for key, value in (("intake.age", a.get("age")), ("intake.gender", a.get("gender_label")),
                       ("intake.social_category", a.get("category_label")), ("intake.district", a.get("district")),
                       ("intake.annual_income", money(a["income_paise"]) if a.get("income_paise") is not None else None),
                       ("intake.education", a.get("education_label")), ("intake.phone", a.get("phone_masked"))):
        if value not in (None, ""):
            pdf.row(pdf.bi(key), str(value))

    s = view["scheme"]
    pdf.section(f"{pdf.bi('rules.title')}: {s['name_en']}" + (f" / {s['name_local']}" if lang != "en" else ""))
    pdf.set_font("sans", "", 9)
    for row in s["trace"]:
        mark = {"pass": "PASS", "fail": "FAIL"}.get(row["result"], "MISSING")
        pdf.multi_cell(0, 5.2, f"[{mark}]  {render_sentence('en', row['sentence'])}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if lang != "en":
            pdf.set_text_color(*MUTED)
            pdf.multi_cell(0, 5.2, f"    {render_sentence(lang, row['sentence'])}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(16, 24, 40)
    pdf.set_text_color(*MUTED)
    pdf.set_font("sans", "", 7.5)
    pdf.multi_cell(0, 4, f"{t('en', 'rules.rule_based_note')} Source: {s['source_url']}"
                         + (" (values marked for verification)" if s["needs_verification"] else ""),
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_text_color(16, 24, 40)

    p = view["plan"]
    pdf.section(pdf.bi("money.title"))
    pdf.row(pdf.bi("intake.project_cost"), money(a["project_cost_paise"]) if a.get("project_cost_paise") else "—")
    pdf.row(pdf.bi("money.amount"), money(p["principal_paise"]))
    pdf.row(pdf.bi("money.rate"), f"{p['rate_bps'] / 100:.2f}%")
    pdf.row(pdf.bi("money.tenure"), t("en", "common.months", count=p["tenure_months"]))
    pdf.row(pdf.bi("money.moratorium"), t("en", "common.months", count=p["moratorium_months"]) if p["moratorium_months"] else "—")
    pdf.row(pdf.bi("money.emi" if p["frequency"] == "monthly" else "money.instalment"), money(p["emi_paise"], show_paise=True))
    pdf.row(pdf.bi("money.total_interest"), money(p["total_interest_paise"], show_paise=True))
    pdf.row(pdf.bi("money.total_payable"), money(p["total_payable_paise"], show_paise=True))
    split = view["split"]
    pdf.row(pdf.bi("money.split_apex", corp=s["apex_corp"]), f"{money(split['apex_paise'])} ({split['apex_bps'] / 100:.0f}%)")
    pdf.row(pdf.bi("money.split_partner"), f"{money(split['partner_paise'])} ({split['partner_bps'] / 100:.0f}%)")
    pdf.row(pdf.bi("money.split_you"), f"{money(split['beneficiary_paise'])} ({split['beneficiary_bps'] / 100:.0f}%)")

    partner = view["partner"]
    pdf.section(pdf.bi("partner.chosen"))
    pdf.row(t("en", f"partner.types.{partner['type']}"), f"{partner['name']}\n{partner['address']}")

    pdf.section(pdf.bi("docs.title"))
    pdf.set_font("sans", "", 8.5)
    for doc in view["documents"]:
        status = "verified" if doc["verified"] else doc["status"]
        pdf.multi_cell(0, 5, f"• {pdf.bi(f'docs.type.{doc['type']}')} — {doc['source']} · {status} · "
                             f"confidence {doc['confidence']:.2f} · sha256 {doc['sha256'][:16]}…",
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    readiness = view["readiness"]
    pdf.multi_cell(0, 5, pdf.bi("docs.readiness_score", score=readiness["score"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    for doc_type, match in readiness.get("name_matches", {}).items():
        reasons = ", ".join(t("en", f"name_match.reason.{r}") for r in match["reasons"])
        pdf.multi_cell(0, 5, f"  Name check ({doc_type}): {match['score'] * 100:.0f}% — {reasons}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    c = view["consent"]
    pdf.section(pdf.bi("consent.notice_version", version=c["text_version"]))
    pdf.set_font("sans", "", 8.5)
    pdf.multi_cell(0, 5, f"{pdf.bi('consent.purpose_apply')}\nMethod: {c['method']} · Granted: {c['granted_at']} · "
                         f"Language: {c['language']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(3)
    pdf.set_font("sans", "B", 9)
    pdf.set_text_color(*BRAND)
    pdf.multi_cell(0, 5, f"{pdf.bi('track.decision_by_lender')}\n{pdf.bi('common.free_service')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("sans", "", 7)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 4, f"Generated {datetime.now(UTC).isoformat(timespec='seconds')} · content hash {view['content_hash'][:24]}…",
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return bytes(pdf.output())
