"""LLM slot extractor (LLM_MODE=ollama | openai_compat). Used last: only for slots the
rule-based extractor left empty, never for eligibility, and its values are capped below
the auto-accept confidence so the person confirms them.

Privacy: phone/Aadhaar-like digit runs and the person's name are redacted before any
prompt leaves the process, and `full_name` is never taken from the model."""

import json
import re
from typing import Any

import httpx

from app.config import get_settings
from app.core.resilience import guarded, registry
from app.modules.voice.slots import Slot

MAX_LLM_CONFIDENCE = 0.7  # below CONFIRM_THRESHOLD: every LLM value is read back for a yes/no

ENUMS: dict[str, list[Any]] = {
    "gender": ["female", "male", "other"],
    "social_category": ["sc", "st", "obc", "safai_karamchari", "minority", "general"],
    "education_level": ["none", "primary", "secondary", "higher_secondary", "diploma", "graduate", "postgraduate"],
    "business_type": ["dairy", "tailoring", "e_rickshaw", "retail_shop", "handicraft", "agriculture", "services",
                      "sanitation_enterprise", "education"],
}
INTS = {"age": (14, 99), "annual_income_rupees": (0, 100_000_000), "project_cost_rupees": (0, 1_000_000_000),
        "loan_needed_rupees": (0, 1_000_000_000), "disability_pct": (0, 100)}
BOOLS = ["has_disability", "shg_member", "existing_loans"]


def _slot_schema() -> dict[str, Any]:
    props: dict[str, Any] = {}
    for name, values in ENUMS.items():
        props[name] = {"type": ["string", "null"], "enum": [*values, None]}
    for name in INTS:
        props[name] = {"type": ["integer", "null"]}
    for name in BOOLS:
        props[name] = {"type": ["boolean", "null"]}
    props["district"] = {"type": ["string", "null"]}
    return {
        "type": "object",
        "properties": {name: {"type": "object", "properties": {"value": schema, "confidence": {"type": "number"}},
                              "required": ["value", "confidence"]} for name, schema in props.items()},
        "additionalProperties": False,
    }


SYSTEM = ("You extract facts for an Indian government loan-scheme application from one spoken sentence. "
          "Return JSON only, matching the schema. Use null when a fact is not clearly stated. Never guess "
          "social category or gender from names. Amounts are in rupees as integers (1 lakh = 100000). "
          "confidence is 0..1.")


def redact(text: str, name: str | None) -> str:
    out = re.sub(r"\d[\d\s-]{6,}\d", "<NUMBER>", text)
    if name:
        for part in name.split():
            if len(part) > 2:
                out = out.replace(part, "<NAME>")
    return out


def _parse(content: str, source: str) -> dict[str, Slot]:
    data = json.loads(content)
    out: dict[str, Slot] = {}
    if not isinstance(data, dict):
        return out
    for name, item in data.items():
        if not isinstance(item, dict) or item.get("value") is None:
            continue
        value, conf = item["value"], min(float(item.get("confidence") or 0), MAX_LLM_CONFIDENCE)
        if name in ENUMS and value in ENUMS[name]:
            out[name] = Slot(value, conf, source, "llm")
        elif name in INTS and isinstance(value, int) and INTS[name][0] <= value <= INTS[name][1]:
            target = {"annual_income_rupees": "annual_family_income_paise", "project_cost_rupees": "project_cost_paise",
                      "loan_needed_rupees": "loan_needed_paise"}.get(name) or str(name)
            out[target] = Slot(value * 100 if target.endswith("_paise") else value, conf, source, "llm")
        elif name in BOOLS and isinstance(value, bool):
            out[name] = Slot(value, conf, source, "llm")
    return out


async def _call(prompt: str) -> str:
    s = get_settings()
    headers = {"Authorization": f"Bearer {s.llm_api_key}"} if s.llm_api_key else {}
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
    async with httpx.AsyncClient(timeout=s.llm_timeout_s) as client:
        if s.llm_mode == "ollama":
            resp = await client.post(f"{s.llm_base_url.rstrip('/')}/api/chat", json={
                "model": s.llm_model, "messages": messages, "stream": False, "format": _slot_schema(),
                "options": {"temperature": 0}})
            resp.raise_for_status()
            return str(resp.json()["message"]["content"])
        resp = await client.post(f"{s.llm_base_url.rstrip('/')}/chat/completions", headers=headers, json={
            "model": s.llm_model, "messages": messages, "temperature": 0,
            "response_format": {"type": "json_schema", "json_schema": {"name": "slots", "schema": _slot_schema()}}})
        resp.raise_for_status()
        return str(resp.json()["choices"][0]["message"]["content"])


async def extract(text: str, lang: str, known_name: str | None, missing: list[str]) -> dict[str, Slot]:
    if get_settings().llm_mode == "off" or not missing:
        registry.last_path.setdefault("llm", "off")
        return {}
    prompt = f"Language: {lang}\nStill needed: {', '.join(missing)}\nSentence: {redact(text, known_name)}"

    async def primary() -> dict[str, Slot]:
        return _parse(await _call(prompt), text)

    async def fallback() -> dict[str, Slot]:
        return {}  # rule-based slots and the form UI carry on

    result, _ = await guarded("llm", primary, fallback, timeout_s=get_settings().llm_timeout_s, attempts=1)
    return {k: v for k, v in result.items() if k in missing and k != "full_name"}
