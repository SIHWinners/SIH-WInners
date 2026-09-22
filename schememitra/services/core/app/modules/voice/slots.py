"""Rule-based slot extractor (spec §9.1). Deterministic, offline, and always runs first;
the LLM extractor only fills slots this one could not, and never overrides a number the
amount parser found.

Each slot carries value, confidence and the clause it came from. Anything under
CONFIRM_THRESHOLD makes the conversation ask a targeted clarification question."""

import re
import unicodedata
from dataclasses import asdict, dataclass
from functools import cache
from typing import Any

from rapidfuzz import fuzz, process

from app.modules.routing.districts import BY_CODE
from app.modules.voice import lexicon as lx
from app.modules.voice.numbers import NumberMatch, find_numbers
from app.modules.voice.text import clauses, is_latin, key, normalise, tokenize

CONFIRM_THRESHOLD = 0.75
LAKH = 100_000

# Slot names match ApplicantFacts / Personal so the web form can apply them directly.
SLOTS = ["full_name", "age", "gender", "social_category", "has_disability", "disability_pct", "state_code",
         "district_code", "pincode", "annual_family_income_paise", "education_level", "business_type",
         "project_cost_paise", "loan_needed_paise", "course_admitted", "shg_member", "existing_loans"]
BOOLEAN_SLOTS = {"has_disability", "shg_member", "existing_loans", "course_admitted"}
MONEY_SLOTS = {"annual_family_income_paise", "project_cost_paise", "loan_needed_paise"}


@dataclass
class Slot:
    value: Any
    confidence: float
    source: str  # the clause it came from (text only, never audio)
    method: str = "rules"  # rules | llm | context

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@cache
def _compiled(words: tuple[str, ...]) -> re.Pattern[str]:
    parts = []
    for w in sorted({normalise(x) for x in words}, key=len, reverse=True):
        esc = re.escape(w)
        if is_latin(w):
            parts.append(rf"(?<![a-z]){esc}(?![a-z])")
        elif len(w) <= 3:
            parts.append(rf"(?<!\S){esc}(?!\S)")
        else:
            parts.append(rf"(?<!\S){esc}")  # Indic words take suffixes: "જાતિમાંથી"
    return re.compile("|".join(parts))


def has_any(text: str, words: list[str]) -> bool:
    return bool(_compiled(tuple(words)).search(text))


def find_any(text: str, words: list[str]) -> re.Match[str] | None:
    return _compiled(tuple(words)).search(text)


def _tokens(text: str) -> list[str]:
    return [t.text for t in tokenize(text)[1]]


def is_negated(clause: str) -> bool:
    no = {key(normalise(w)) for w in lx.NO}
    return any(key(tok) in no for tok in _tokens(clause))


def yes_no(text: str) -> bool | None:
    """A bare yes / no reply ("haan ji", "ના", "sahi hai")."""
    toks = [key(t) for t in _tokens(text)]
    yes = {key(normalise(w)) for w in lx.YES}
    no = {key(normalise(w)) for w in lx.NO}
    has_yes = any(t in yes for t in toks)
    has_no = any(t in no for t in toks)
    if has_no and not has_yes:
        return False
    if has_yes and not has_no:
        return True
    return None


def _first_category(text: str, table: dict[str, list[str]]) -> str | None:
    best: tuple[int, str] | None = None
    for value, words in table.items():
        m = find_any(text, words)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), value)
    return best[1] if best else None


# --- name ---------------------------------------------------------------------------------

def _clean_name(raw: str) -> str | None:
    stop = {key(normalise(w)) for w in lx.NAME_STOP} | {key(normalise(w)) for w in lx.FILLERS}
    words = [w for w in re.split(r"\s+", raw.strip(" .,:;-")) if w]
    while words and key(normalise(words[-1])) in stop:
        words.pop()
    while words and key(normalise(words[0])) in stop:
        words.pop(0)
    if not 1 <= len(words) <= 5 or any(ch.isdigit() for w in words for ch in w):
        return None
    name = " ".join(words)
    return name.title() if is_latin(normalise(name)) else name


def extract_name(text: str, expecting: str | None) -> Slot | None:
    nfc = unicodedata.normalize("NFC", text)
    for clause in re.split(r"[,;।!?\n]|\s(?:and|aur|और|અને)\s", nfc):
        lowered = normalise(clause)
        m = find_any(lowered, lx.NAME_MARKERS)
        if m:
            # Offsets line up because markers carry no nukta; fall back to the normalised tail.
            tail = clause[m.end():] if normalise(clause[: m.end()]) == lowered[: m.end()] else lowered[m.end():]
            tail = re.sub(r"^\s*(is|hai|है|છે|ہے)\s+", "", tail)
            if name := _clean_name(tail):
                return Slot(name, 0.92, clause.strip())
    if expecting == "full_name":
        only = nfc.split(",")[0]
        if not find_numbers(only) and yes_no(only) is not False and (name := _clean_name(only)):
            return Slot(name, 0.8, only.strip(), "context")
    return None


# --- location -----------------------------------------------------------------------------

@cache
def _aliases() -> list[tuple[str, str]]:
    return sorted(((normalise(a), c) for a, c in lx.district_aliases().items()), key=lambda x: -len(x[0]))


def extract_district(text: str) -> Slot | None:
    norm = normalise(text)
    for alias, code in _aliases():
        if has_any(norm, [alias]):
            return Slot(code, 0.95, alias)
    # Fuzzy match for romanised spellings ("Dahood", "Barmar"): confirm before using.
    latin = [t for t in _tokens(text) if is_latin(t) and len(t) >= 5]
    choices = {a: c for a, c in _aliases() if is_latin(a)}
    for tok in latin:
        hit = process.extractOne(tok, list(choices), scorer=fuzz.ratio, score_cutoff=80)
        if hit:
            return Slot(choices[hit[0]], 0.6, tok)
    return None


def extract_state(text: str) -> Slot | None:
    norm = normalise(text)
    for code, words in lx.STATES.items():
        if has_any(norm, words):
            return Slot(code, 0.95, code)
    return None


# --- numbers in context ---------------------------------------------------------------------

def _money_slot_for(clause: str, number: NumberMatch, expecting: str | None) -> tuple[str, float] | None:
    norm = normalise(clause)
    before = norm[: number.char_start] if number.char_start <= len(norm) else norm
    candidates = []
    for slot, words in (("annual_family_income_paise", lx.INCOME), ("loan_needed_paise", lx.LOAN),
                        ("project_cost_paise", lx.COST)):
        hits = list(_compiled(tuple(words)).finditer(norm))
        if hits:
            # prefer the keyword closest before the number, else any in the clause
            prior = [h.start() for h in hits if h.start() <= len(before)]
            candidates.append((max(prior) if prior else -1, slot))
    if candidates:
        with_prior = [c for c in candidates if c[0] >= 0]
        slot = max(with_prior)[1] if with_prior else candidates[0][1]
        return slot, number.confidence
    if expecting in MONEY_SLOTS:
        return expecting, min(number.confidence, 0.85)
    return None


def extract_numbers(text: str, lang: str, expecting: str | None) -> dict[str, Slot]:
    out: dict[str, Slot] = {}
    for clause in clauses(text):
        norm = normalise(clause)
        numbers = find_numbers(clause, lang)
        for n in numbers:
            moneyish = n.unit >= 1000 or n.currency or (n.value >= 1000 and not n.words)
            if n.ordinal:
                continue
            if not n.words and n.unit == 1 and n.value.denominator == 1 and 100000 <= n.value <= 999999 \
                    and len(str(int(n.value))) == 6 and not n.currency and not has_any(norm, lx.INCOME + lx.COST + lx.LOAN):
                out["pincode"] = Slot(str(int(n.value)), 0.9, clause)
                continue
            if moneyish:
                target = _money_slot_for(clause, n, expecting)
                if target:
                    slot, conf = target
                    rupees = n.value
                    if slot == "annual_family_income_paise" and has_any(norm, lx.MONTHLY):
                        rupees, conf = rupees * 12, min(conf, 0.8)
                    if rupees.denominator == 1 or (rupees * 100).denominator == 1:
                        out[slot] = Slot(int(rupees * 100), conf, clause)
                continue
            if n.value.denominator != 1:
                continue
            value = int(n.value)
            if has_any(norm, lx.PERCENT) and has_any(norm, lx.DISABILITY) or (has_any(norm, lx.PERCENT) and expecting == "disability_pct"):
                if 1 <= value <= 100:
                    out["disability_pct"] = Slot(value, n.confidence, clause)
                continue
            if has_any(norm, lx.EDUCATION_WORDS) and 0 <= value <= 12:
                out["education_level"] = Slot(_class_to_level(value), 0.9, clause)
                continue
            if 14 <= value <= 99 and (has_any(norm, lx.AGE) or expecting == "age"):
                out["age"] = Slot(value, n.confidence if has_any(norm, lx.AGE) else 0.8, clause)
            elif expecting == "disability_pct" and 1 <= value <= 100:
                out["disability_pct"] = Slot(value, 0.8, clause)
    return out


def _class_to_level(klass: int) -> str:
    if klass == 0:
        return "none"
    if klass <= 5:
        return "primary"
    if klass <= 10:
        return "secondary"
    return "higher_secondary"


def extract_education(text: str) -> Slot | None:
    norm = normalise(text)
    for level in ("postgraduate", "graduate", "diploma", "none"):
        if has_any(norm, lx.EDUCATION_LEVEL[level]):
            return Slot(level, 0.9, level)
    if has_any(norm, lx.EDUCATION_WORDS):
        for n, words in sorted(lx.ORDINALS.items(), reverse=True):
            if has_any(norm, words):
                return Slot(_class_to_level(n), 0.9, words[0])
        if m := re.search(r"\b(\d{1,2})(?:st|nd|rd|th)\b", norm):
            return Slot(_class_to_level(min(int(m.group(1)), 12)), 0.9, m.group(0))
    return None


# --- main entry -----------------------------------------------------------------------------

def extract(text: str, lang: str, expecting: str | None = None) -> dict[str, Slot]:
    """Slots found in one utterance. `expecting` is the slot the last question asked for."""
    out: dict[str, Slot] = {}
    if not text.strip():
        return out
    norm = normalise(text)

    if name := extract_name(text, expecting):
        out["full_name"] = name
    out.update(extract_numbers(text, lang, expecting))

    for clause in clauses(text):
        negated = is_negated(clause)
        if (g := _first_category(clause, lx.GENDER)) and "gender" not in out:
            out["gender"] = Slot(g, 0.95, clause)
        if (c := _first_category(clause, lx.SOCIAL_CATEGORY)) and "social_category" not in out and not negated:
            out["social_category"] = Slot(c, 0.9 if c != "general" else 0.75, clause)
        if has_any(clause, lx.DISABILITY) and "has_disability" not in out:
            out["has_disability"] = Slot(not negated, 0.9, clause)
            if negated:
                out["disability_pct"] = Slot(0, 0.9, clause)
        if has_any(clause, lx.SHG):
            out["shg_member"] = Slot(not negated, 0.9, clause)
        loan_here = has_any(clause, lx.LOAN)
        amounts_here = any(n.unit >= 1000 or n.currency for n in find_numbers(clause, lang))
        if loan_here and not amounts_here and (negated or has_any(clause, lx.EXISTING)):
            out["existing_loans"] = Slot(not negated, 0.9, clause)
        if has_any(clause, lx.ADMISSION):
            out["course_admitted"] = Slot(not negated, 0.85, clause)
        if (b := _first_category(clause, lx.BUSINESS)) and "business_type" not in out:
            out["business_type"] = Slot(b, 0.9, clause)

    if "education_level" not in out and (edu := extract_education(text)):
        out["education_level"] = edu
    if d := extract_district(text):
        out["district_code"] = d
        out["state_code"] = Slot(BY_CODE[d.value].state_code, d.confidence, d.source)
    elif s := extract_state(text):
        out["state_code"] = s

    # A bare yes/no answers whichever yes/no question was asked.
    if expecting in BOOLEAN_SLOTS and expecting not in out and (yn := yes_no(norm)) is not None:
        out[expecting] = Slot(yn, 0.9, text.strip(), "context")
        if expecting == "has_disability" and yn is False:
            out["disability_pct"] = Slot(0, 0.9, text.strip(), "context")
    if expecting == "social_category" and "social_category" not in out and yes_no(norm) is False:
        out["social_category"] = Slot("general", 0.7, text.strip(), "context")
    return out


def field_mentioned(text: str) -> str | None:
    """Which answer the person wants to change ("umar galat hai" → age)."""
    norm = normalise(text)
    best: tuple[int, str] | None = None
    for slot, words in lx.FIELD_WORDS.items():
        m = find_any(norm, words)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), slot)
    return best[1] if best else None
