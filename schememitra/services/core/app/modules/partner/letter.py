"""Sanction letter, issued in the lender's name when the lender approves (C5 "to sanction letter",
C21). Bilingual like the loan file. Demo lenders are fictional and the letter says so."""

import io
from typing import Any

from fpdf.enums import XPos, YPos

from app.core.i18n import money, t
from app.modules.applications.pdf import BRAND, MUTED, LoanFile


class SanctionLetter(LoanFile):
    def __init__(self, lang: str, tracking_id: str, partner_name: str) -> None:
        self.partner_name = partner_name
        super().__init__(lang, tracking_id)

    def header(self) -> None:
        self.set_fill_color(*BRAND)
        self.rect(0, 0, 210, 14, style="F")
        self.set_xy(16, 4)
        self.set_text_color(255, 255, 255)
        self.set_font("sans", "B", 10)
        self.cell(0, 6, f"{self.partner_name} · {self.tracking_id}")
        self.set_text_color(16, 24, 40)
        self.set_y(20)


def render_sanction_letter(view: dict[str, Any], qr_png: bytes | None) -> bytes:
    lang = view["lang"]
    partner = view["partner"]
    terms = view["terms"]
    pdf = SanctionLetter(lang, view["tracking_id"], partner["name"])
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.set_font("sans", "B", 17)
    pdf.multi_cell(130, 9, pdf.bi("letter.title"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("sans", "", 9)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(130, 5, f"{partner['name']}\n{partner['address']}\nRef: {view['tracking_id']} · {view['decided_on']}",
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if qr_png:
        pdf.image(io.BytesIO(qr_png), x=166, y=20, w=28)
    pdf.set_text_color(16, 24, 40)
    if partner["is_demo"]:
        pdf.ln(2)
        pdf.set_font("sans", "B", 9)
        pdf.set_text_color(180, 35, 24)
        pdf.multi_cell(0, 5, pdf.bi("letter.demo"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(16, 24, 40)

    pdf.ln(4)
    pdf.set_font("sans", "", 10.5)
    pdf.multi_cell(0, 6, pdf.bi("letter.dear", name=view["applicant_name"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)
    pdf.multi_cell(0, 6, pdf.bi("letter.body", scheme=view["scheme_name"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.section(pdf.bi("letter.terms"))
    pdf.row(pdf.bi("letter.amount"), money(terms["amount_paise"]))
    pdf.row(pdf.bi("money.rate"), f"{terms['rate_bps'] / 100:.2f}%")
    pdf.row(pdf.bi("money.tenure"), t("en", "common.months", count=terms["tenure_months"]))
    pdf.row(pdf.bi("money.moratorium"), t("en", "common.months", count=terms["moratorium_months"]) if terms["moratorium_months"] else "—")
    pdf.row(pdf.bi("money.emi" if terms["frequency"] == "monthly" else "money.instalment"), money(terms["emi_paise"], show_paise=True))
    pdf.row(pdf.bi("money.total_payable"), money(terms["total_payable_paise"], show_paise=True))
    if view.get("note"):
        pdf.row(pdf.bi("letter.note"), view["note"])

    pdf.section(pdf.bi("letter.next_title"))
    pdf.set_font("sans", "", 10)
    pdf.multi_cell(0, 6, pdf.bi("letter.next", partner=partner["name"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(6)
    pdf.set_font("sans", "B", 10)
    pdf.multi_cell(0, 6, pdf.bi("letter.issued_by", partner=partner["name"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("sans", "", 8)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 4.5, f"{t('en', 'track.decision_by_lender')} · Officer ref {view['officer_ref']}",
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return bytes(pdf.output())
