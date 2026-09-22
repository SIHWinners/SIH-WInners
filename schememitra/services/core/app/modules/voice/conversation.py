"""Conversation state machine (spec §9.1): intake → clarify → confirm → done. Not free chat.

Questions come in small groups so one natural sentence can fill several fields; a
~6-turn conversation fills 15+ form fields. Replies are pre-localised i18n templates in
the person's language (no machine translation on the reply path). A hard cap of
MAX_TURNS hands whatever is still missing to the typed form."""

import unicodedata
from dataclasses import dataclass, field
from typing import Any

from app.core.i18n import money, t
from app.modules.routing.districts import BY_CODE
from app.modules.voice.lexicon import DISTRICT_NAMES
from app.modules.voice.slots import BOOLEAN_SLOTS, CONFIRM_THRESHOLD, MONEY_SLOTS, Slot, extract, field_mentioned, yes_no

MAX_TURNS = 12
GROUPS: list[list[str]] = [
    ["full_name", "age", "district_code"],
    ["gender", "social_category", "has_disability"],
    ["business_type", "project_cost_paise", "loan_needed_paise"],
    ["annual_family_income_paise", "education_level"],
    ["shg_member", "existing_loans"],
]
ASK_KEY = {
    "full_name": "voice.ask.name", "age": "voice.ask.age", "gender": "voice.ask.gender",
    "social_category": "voice.ask.social_category", "has_disability": "voice.ask.disability",
    "disability_pct": "intake.disability_pct", "state_code": "voice.ask.state", "district_code": "voice.ask.district",
    "annual_family_income_paise": "voice.ask.annual_income", "education_level": "voice.ask.education",
    "business_type": "voice.ask.business_type", "project_cost_paise": "voice.ask.project_cost",
    "loan_needed_paise": "voice.ask.loan_needed", "existing_loans": "voice.ask.existing_loans",
    "shg_member": "voice.ask.shg_member", "course_admitted": "intake.course_admitted",
}
OPTION_PREFIX = {"gender": "options.gender", "social_category": "options.social_category",
                 "education_level": "options.education", "business_type": "options.business_type"}


def required_slots(values: dict[str, Any]) -> list[str]:
    order: list[str] = []
    for group in GROUPS:
        for slot in group:
            order.append(slot)
            if slot == "has_disability" and values.get("has_disability") is True:
                order.append("disability_pct")
            if slot == "business_type" and values.get("business_type") == "education":
                order.append("course_admitted")
    return order


@dataclass
class ConversationState:
    lang: str
    state: str = "intake"  # intake | clarify | confirm | done
    slots: dict[str, dict[str, Any]] = field(default_factory=dict)  # name → {value, confidence, method}
    asked: list[str] = field(default_factory=list)
    clarify: dict[str, Any] | None = None  # {slot, value, confidence}
    user_turns: int = 0
    handoff: str | None = None  # rules | form

    @property
    def values(self) -> dict[str, Any]:
        return {k: v["value"] for k, v in self.slots.items()}

    def missing(self) -> list[str]:
        vals = self.values
        return [s for s in required_slots(vals) if s not in vals]

    def to_json(self) -> dict[str, Any]:
        return {"lang": self.lang, "state": self.state, "slots": self.slots, "asked": self.asked, "clarify": self.clarify,
                "user_turns": self.user_turns, "handoff": self.handoff}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ConversationState":
        return cls(**data)


@dataclass
class Reply:
    text: str
    changed: list[str]
    not_understood: bool = False


SCRIPT_OF = {"hi": "DEVANAGARI", "mr": "DEVANAGARI", "gu": "GUJARATI", "ta": "TAMIL", "ur": "ARABIC"}


def local_district_name(lang: str, code: str) -> str:
    """District name in the reader's script when we have it, else the English name."""
    script = SCRIPT_OF.get(lang)
    for alias in DISTRICT_NAMES.get(code, []) if script else []:
        if unicodedata.name(alias[0], "").startswith(script or "-"):
            return alias
    return BY_CODE[code].name


def display_value(lang: str, slot: str, value: Any) -> str:
    if slot in MONEY_SLOTS:
        return money(int(value))
    if slot in OPTION_PREFIX:
        return t(lang, f"{OPTION_PREFIX[slot]}.{value}")
    if slot in BOOLEAN_SLOTS:
        return t(lang, "common.yes" if value else "common.no")
    if slot == "district_code" and value in BY_CODE:
        return local_district_name(lang, value)
    if slot == "state_code":
        return t(lang, f"options.states.{value}")
    return str(value)


def greeting(conv: ConversationState) -> str:
    conv.asked = GROUPS[0][:]
    return t(conv.lang, "voice.greeting")


def summary(conv: ConversationState) -> str:
    v = conv.values
    lang = conv.lang
    return t(lang, "voice.summary",
             name=v.get("full_name", "—"), age=v.get("age", "—"),
             district=display_value(lang, "district_code", v["district_code"]) if "district_code" in v else "—",
             work=display_value(lang, "business_type", v["business_type"]) if "business_type" in v else "—",
             loan=display_value(lang, "loan_needed_paise", v["loan_needed_paise"]) if "loan_needed_paise" in v else "—",
             cost=display_value(lang, "project_cost_paise", v["project_cost_paise"]) if "project_cost_paise" in v else "—",
             income=display_value(lang, "annual_family_income_paise", v["annual_family_income_paise"])
             if "annual_family_income_paise" in v else "—")


def _accept(conv: ConversationState, name: str, slot: Slot, confidence: float | None = None) -> None:
    conv.slots[name] = {"value": slot.value, "confidence": round(confidence or slot.confidence, 2), "method": slot.method}


def _next_prompt(conv: ConversationState, prefix: list[str]) -> str:
    lang = conv.lang
    missing = conv.missing()
    if not missing:
        conv.state, conv.asked = "confirm", []
        return " ".join([*prefix, summary(conv), t(lang, "voice.confirm_all")])
    if conv.user_turns >= MAX_TURNS:
        conv.state, conv.handoff, conv.asked = "done", "form", []
        return " ".join([*prefix, t(lang, "voice.finish_on_form")])
    group = next(g for g in GROUPS if any(s in missing for s in g))
    extra = [s for s in missing if s in ("disability_pct", "course_admitted")]
    conv.asked = extra[:1] if extra else [s for s in group if s in missing]
    conv.state = "intake"
    return " ".join([*prefix, *(t(lang, ASK_KEY[s]) for s in conv.asked)])


def step(conv: ConversationState, text: str, llm_slots: dict[str, Slot] | None = None) -> Reply:
    lang = conv.lang
    conv.user_turns += 1
    expecting = conv.asked[0] if conv.asked else None

    if conv.state == "confirm":
        target = field_mentioned(text)
        answer = yes_no(text)
        if answer is True and target is None:
            conv.state, conv.handoff = "done", "rules"
            return Reply(t(lang, "voice.done"), [])
        if target:
            found = extract(text, lang, target)
            if target in found and found[target].confidence >= CONFIRM_THRESHOLD:
                _accept(conv, target, found[target])
                return Reply(" ".join([t(lang, "voice.ack"), summary(conv), t(lang, "voice.confirm_all")]), [target])
            conv.slots.pop(target, None)
            conv.state, conv.asked = "intake", [target]
            return Reply(t(lang, ASK_KEY.get(target, "voice.not_understood")), [target])
        if answer is False:
            return Reply(t(lang, "voice.correct_which"), [])
        return Reply(" ".join([t(lang, "voice.not_understood"), t(lang, "voice.confirm_all")]), [], True)

    if conv.state == "clarify" and conv.clarify:
        slot_name = conv.clarify["slot"]
        answer = yes_no(text)
        found = extract(text, lang, slot_name)
        if slot_name in found and found[slot_name].value != conv.clarify["value"] and found[slot_name].confidence >= CONFIRM_THRESHOLD:
            _accept(conv, slot_name, found[slot_name])
        elif answer is True:
            conv.slots[slot_name] = {"value": conv.clarify["value"], "confidence": 0.9, "method": "confirmed"}
        elif answer is False:
            conv.clarify = None
            conv.state, conv.asked = "intake", [slot_name]
            return Reply(t(lang, ASK_KEY[slot_name]), [])
        else:
            return Reply(" ".join([t(lang, "voice.not_understood"), _clarify_text(conv)]), [], True)
        conv.clarify = None
        return Reply(_next_prompt(conv, [t(lang, "voice.ack")]), [slot_name])

    found = extract(text, lang, expecting)
    for name, slot in (llm_slots or {}).items():
        found.setdefault(name, slot)
    changed: list[str] = []
    low: tuple[str, Slot] | None = None
    for name, slot in found.items():
        if slot.confidence >= CONFIRM_THRESHOLD:
            _accept(conv, name, slot)
            changed.append(name)
        elif name not in conv.slots and low is None and name in ASK_KEY:
            low = (name, slot)
    if low:
        conv.state = "clarify"
        conv.clarify = {"slot": low[0], "value": low[1].value, "confidence": low[1].confidence}
        prefix = [t(lang, "voice.ack")] if changed else []
        return Reply(" ".join([*prefix, _clarify_text(conv)]), changed)
    if not changed:
        return Reply(" ".join([t(lang, "voice.not_understood"), *(t(lang, ASK_KEY[s]) for s in conv.asked)]), [], True)
    return Reply(_next_prompt(conv, [t(lang, "voice.ack")]), changed)


def _clarify_text(conv: ConversationState) -> str:
    assert conv.clarify
    slot = conv.clarify["slot"]
    return t(conv.lang, "voice.clarify", field=t(conv.lang, f"voice.field.{slot}"),
             value=display_value(conv.lang, slot, conv.clarify["value"]))
