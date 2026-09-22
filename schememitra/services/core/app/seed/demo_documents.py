"""Fictional demo documents for the personas, rendered as images so the whole document flow
(upload → quality → OCR → fields → readiness → DigiLocker fallback → name match) can be shown
without anyone's real papers. Every image carries a "DEMO — NOT VALID" banner.

Writes var/demo_docs/<persona>/<doc_type>.png, a SANDBOX OCR manifest keyed by SHA-256, and
clean DigiLocker copies under var/demo_docs/<persona>/digilocker/."""

import hashlib
import io
import json
import random
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CORE_DIR
from app.modules.documents.aadhaar import verhoeff_digit
from app.modules.documents.extract import extract_fields
from app.modules.documents.ocr import DEMO_DOCS_DIR, OcrLine, OcrResult

FONTS = CORE_DIR / "assets" / "fonts"
W, H = 1240, 877

IDENTITY: dict[str, dict[str, Any]] = {
    "savitaben": {"name": "Savitaben Rathwa", "doc_name": "Smt. Savitaben Rathwa", "father": "Ramsinh Rathwa",
                  "dob": "14/03/1992", "gender": "Female", "district": "Dahod", "state": "Gujarat", "base": "53428716093",
                  "category": "Scheduled Caste", "income": "1,20,000", "account": "30219877451203", "ifsc": "SGKB0DAH001",
                  "docs": ["aadhaar", "caste_certificate", "income_certificate", "bank_passbook", "shg_certificate"],
                  "script_line": ("NotoSansGujarati", "નામ: સવિતાબેન રાઠવા")},
    "ramesh": {"name": "RAMESH KANARAM MEGHWAL", "doc_name": "Shri Ramesh S/O Late Kanaram", "father": "Late Kanaram",
               "dob": "02/07/1985", "gender": "Male", "district": "Barmer", "state": "Rajasthan", "base": "45391876204",
               "category": "Scheduled Caste", "income": "1,80,000", "account": "61230045578912", "ifsc": "TGBK0BAR017",
               "quotation": ("Shree Balaji Sewing Machines (demo)", "4,50,000"),
               "docs": ["aadhaar", "caste_certificate", "income_certificate", "bank_passbook", "project_quotation"],
               "faded": {"caste_certificate"}, "digilocker": {"caste_certificate", "income_certificate"},
               "script_line": ("NotoSansDevanagari", "नाम: श्री रमेश पुत्र स्व. कानाराम")},
    "kavya": {"name": "Kavya Selvam", "doc_name": "Kum. Kavya Selvam", "father": "Selvam Murugan", "dob": "20/01/2007",
              "gender": "Female", "district": "Madurai", "state": "Tamil Nadu", "base": "62017384519",
              "category": "Other Backward Class", "income": "1,50,000", "account": "40128833001276", "ifsc": "VGBK0MDU004",
              "course": ("Diploma in Electronics (3 years)", "Madurai Government Polytechnic (demo)", "2,40,000"),
              "docs": ["aadhaar", "caste_certificate", "income_certificate", "admission_letter", "marksheet", "bank_passbook"],
              "digilocker": {"caste_certificate", "marksheet"},
              "script_line": ("NotoSansTamil", "பெயர்: காவ்யா செல்வம்")},
    "imran": {"name": "Imran Qureshi", "doc_name": "Mr. Imran Qureshi", "father": "Salim Qureshi", "dob": "05/11/1994",
              "gender": "Male", "district": "Lucknow", "state": "Uttar Pradesh", "base": "78302945167",
              "category": "Other Backward Class", "income": "1,40,000", "account": "50117766230981", "ifsc": "GGBK0LKO002",
              "disability": ("60", "UP0920199400012345"), "quotation": ("Awadh E-Rickshaw Motors (demo)", "1,80,000"),
              "docs": ["aadhaar", "disability_certificate", "income_certificate", "bank_passbook", "project_quotation"],
              "digilocker": {"disability_certificate"},
              "script_line": ("NotoSansDevanagari", "नाम: इमरान कुरैशी")},
    "edge": {"name": "Suresh Jatav", "doc_name": "Shri Suresh Jatav", "father": "Mohanlal Jatav", "dob": "05/05/1990",
             "gender": "Male", "district": "Jaipur", "state": "Rajasthan", "base": "29847163502",
             "category": "Scheduled Caste", "income": "5,00,001", "account": "70112233445566", "ifsc": "JNBK0JAI009",
             "quotation": ("Pink City Traders (demo)", "3,50,000"),
             "docs": ["aadhaar", "bank_passbook", "project_quotation", "income_certificate"],
             "script_line": ("NotoSansDevanagari", "नाम: सुरेश जाटव")},
}

TITLES = {
    "aadhaar": "UNIQUE IDENTIFICATION (SAMPLE LAYOUT)", "caste_certificate": "CASTE CERTIFICATE",
    "income_certificate": "INCOME CERTIFICATE", "disability_certificate": "CERTIFICATE OF DISABILITY (UDID)",
    "bank_passbook": "SAVINGS ACCOUNT PASSBOOK", "project_quotation": "QUOTATION", "admission_letter": "PROVISIONAL ADMISSION LETTER",
    "marksheet": "HIGHER SECONDARY MARKSHEET", "shg_certificate": "SHG MEMBERSHIP LETTER",
}


def _font(name: str, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"{name}-{'Bold' if bold else 'Regular'}.ttf"), size)


def _lines_for(persona: str, doc_type: str) -> list[str]:
    p = IDENTITY[persona]
    issued = "Date of Issue: 10/05/2026"
    common_issuer = f"Office of the Tehsildar, {p['district']} (fictional)"
    if doc_type == "aadhaar":
        number = p["base"] + verhoeff_digit(p["base"])
        return [f"Name: {p['name'].title()}", f"DOB: {p['dob']}", f"Gender: {p['gender']}",
                f"{number[:4]} {number[4:8]} {number[8:]}"]
    if doc_type == "caste_certificate":
        return [common_issuer, f"Name: {p['doc_name']}", f"Father's Name: {p['father']}",
                f"belongs to the {p['category']} community of {p['state']}", f"District: {p['district']}", issued]
    if doc_type == "income_certificate":
        return [common_issuer, f"Name: {p['doc_name']}", f"Father's Name: {p['father']}",
                f"Annual Family Income: Rs {p['income']}", issued]
    if doc_type == "disability_certificate":
        pct, udid = p["disability"]
        return ["Chief Medical Officer, District Hospital (fictional)", f"Name: {p['doc_name']}", f"DOB: {p['dob']}",
                f"Locomotor disability: {pct} %", f"UDID No: {udid}", issued]
    if doc_type == "bank_passbook":
        return [f"Account Holder: {p['name']}", f"A/c No: {p['account']}", f"IFSC: {p['ifsc']}",
                f"Branch: {p['district']} (demo)"]
    if doc_type == "project_quotation":
        vendor, total = p["quotation"]
        return [f"Vendor: {vendor}", f"To: {p['name'].title()}", "Items as per attached list", f"Grand Total: Rs {total}",
                "Dated: 01/08/2026"]
    if doc_type == "admission_letter":
        course, college, fee = p["course"]
        return [f"Institute: {college}", f"Name: {p['name']}", f"Course: {course}", f"Total Course Fee: Rs {fee}",
                "Dated: 20/07/2026"]
    if doc_type == "marksheet":
        return ["State Board of Higher Secondary Education (fictional)", f"Name: {p['name']}", f"DOB: {p['dob']}",
                "Result: PASS — First Class"]
    return [f"Self Help Group Name: Jyoti Mahila Mandal, {p['district']} (demo)", f"Name: {p['doc_name']}",
            "Member since: 2021", issued]


def _render(persona: str, doc_type: str, *, faded: bool, rng: random.Random) -> tuple[bytes, list[dict[str, Any]]]:
    img = Image.new("RGB", (W, H), (250, 248, 240))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, W, 64), fill=(180, 35, 24))
    draw.text((32, 14), "DEMO DOCUMENT — FICTIONAL — NOT VALID FOR ANY USE", font=_font("NotoSans", 28, True), fill="white")
    draw.text((60, 100), TITLES[doc_type], font=_font("NotoSans", 40, True), fill=(20, 30, 60))
    lines = []
    y = 190
    body = _font("NotoSans", 32)
    for text in _lines_for(persona, doc_type):
        box = draw.textbbox((60, y), text, font=body)
        draw.text((60, y), text, font=body, fill=(15, 15, 15))
        confidence = round(rng.uniform(0.32, 0.5) if faded else rng.uniform(0.91, 0.99), 3)
        lines.append({"text": text, "confidence": confidence, "box": list(box)})
        y += 64
    font_name, script_text = IDENTITY[persona]["script_line"]
    if doc_type in ("caste_certificate", "income_certificate"):
        draw.text((60, y + 10), script_text, font=_font(font_name, 30), fill=(40, 40, 40))
    draw.ellipse((W - 250, H - 250, W - 70, H - 70), outline=(30, 60, 140), width=5)
    draw.text((W - 225, H - 175), "SEAL (demo)", font=_font("NotoSans", 26, True), fill=(30, 60, 140))

    if faded:
        img = ImageEnhance.Contrast(img).enhance(0.35)
        img = ImageEnhance.Brightness(img).enhance(1.12).filter(ImageFilter.GaussianBlur(2.6))
        torn = ImageDraw.Draw(img)
        torn.polygon([(W, 0), (W - 260, 0), (W - 120, 120), (W - 200, 240), (W, 330)], fill=(60, 60, 60))
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue(), lines


async def seed_demo_documents(_: AsyncSession) -> str:
    rng = random.Random(2026)
    manifest: dict[str, Any] = {}
    count = 0
    for persona, p in IDENTITY.items():
        folder = DEMO_DOCS_DIR / persona
        (folder / "digilocker").mkdir(parents=True, exist_ok=True)
        for doc_type in p["docs"]:
            faded = doc_type in p.get("faded", set())
            data, lines = _render(persona, doc_type, faded=faded, rng=rng)
            (folder / f"{doc_type}.png").write_bytes(data)
            manifest[hashlib.sha256(data).hexdigest()] = {"persona": persona, "doc_type": doc_type, "lines": lines}
            count += 1
            if doc_type in p.get("digilocker", set()):
                clean, clean_lines = _render(persona, doc_type, faded=False, rng=rng)
                for line in clean_lines:
                    line["confidence"] = 1.0  # issuer-signed digital copy
                ocr = OcrResult([OcrLine(ln["text"], ln["confidence"], tuple(ln["box"])) for ln in clean_lines], "digilocker", True)
                record = {"fields": extract_fields(doc_type, ocr).fields, "lines": clean_lines,
                          "issuer": f"{p['district']} District Administration (sandbox)",
                          "uri": f"in.gov.sandbox-{persona}-{doc_type}"}
                (folder / "digilocker" / f"{doc_type}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
                (folder / "digilocker" / f"{doc_type}.png").write_bytes(clean)
    Path(DEMO_DOCS_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return f"{count} demo documents rendered"
