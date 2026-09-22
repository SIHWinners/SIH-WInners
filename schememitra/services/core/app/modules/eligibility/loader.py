"""Scheme rule files: load, validate (JSON Schema + dry-run compile), and serve as a
versioned rule set. Published versions live in `scheme_rule_versions`; YAML files in
services/core/rules are the seed source and the review-friendly format."""

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import CORE_DIR
from app.db.models import Scheme, SchemeRuleVersion
from app.modules.eligibility.engine import Condition, RuleError, validate_logic
from app.modules.eligibility.kinds import compile_condition

RULES_DIR = CORE_DIR / "rules"


@lru_cache
def _validator() -> Draft202012Validator:
    schema = json.loads((RULES_DIR / "schema" / "scheme-rule.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


class RuleValidationError(ValueError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


def validate_document(doc: dict[str, Any]) -> list[Condition]:
    """Schema-check a rule document and compile its conditions. Raises with every problem found."""
    problems = [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in _validator().iter_errors(doc)]
    if problems:
        raise RuleValidationError(problems)
    conditions: list[Condition] = []
    params = doc["params"]
    for spec in doc["eligibility"]:
        try:
            cond = compile_condition(spec)
            validate_logic(cond.logic, params)
            for meta in (*cond.sentence.values(), *cond.change.values()):
                if "param" in meta and meta["param"] not in params:
                    raise RuleError(f"sentence references unknown param {meta['param']!r}")
            conditions.append(cond)
        except (RuleError, KeyError, ValueError) as err:
            problems.append(f"eligibility/{spec.get('id', '?')}: {err}")
    fp = doc["funding_pattern"]
    if fp["apex_bps"] + fp["partner_bps"] + fp["beneficiary_bps"] != 10000:
        problems.append("funding_pattern: shares must add up to 10000 bps (100%)")
    if doc["moratorium"]["default_months"] > doc["moratorium"]["max_months"]:
        problems.append("moratorium: default_months exceeds max_months")
    if problems:
        raise RuleValidationError(problems)
    return conditions


def parse_yaml(text: str) -> dict[str, Any]:
    doc = yaml.safe_load(text)
    if not isinstance(doc, dict):
        raise RuleValidationError(["document must be a mapping"])
    # YAML turns ISO dates into date objects; the schema and JSON storage want strings.
    for key in ("verified_on", "effective_from"):
        if isinstance(doc.get(key), date):
            doc[key] = doc[key].isoformat()
    return doc


def load_rule_files(directory: Path = RULES_DIR) -> list[dict[str, Any]]:
    docs = []
    for path in sorted(directory.glob("*.yaml")):
        doc = parse_yaml(path.read_text(encoding="utf-8"))
        validate_document(doc)
        docs.append(doc)
    return docs


@dataclass
class SchemeRules:
    code: str
    doc: dict[str, Any]
    conditions: list[Condition]
    version: int
    rule_version_id: str | None = None
    scheme_id: str | None = None

    @property
    def params(self) -> dict[str, Any]:
        return self.doc["params"]

    def rate_bps_for(self, principal_paise: int, gender: str | None = None) -> int:
        slabs = sorted(self.doc["interest"]["slabs"], key=lambda s: s["upto_paise"])
        rate = next((s["rate_bps"] for s in slabs if principal_paise <= s["upto_paise"]), slabs[-1]["rate_bps"])
        if gender == "female":
            rate -= self.doc["interest"].get("women_rebate_bps", 0)
        return rate

    def to_bundle(self) -> dict[str, Any]:
        d = self.doc
        return {
            "code": self.code, "version": self.version, "apex_corp": d["apex_corp"], "loan_type": d["loan_type"],
            "name": d["name"], "source_url": d["source_url"], "verified_on": d.get("verified_on"),
            "needs_verification": d["needs_verification"], "params": d["params"],
            "conditions": [
                {"id": c.id, "kind": c.kind, "logic": c.logic, "fields": c.fields, "pass_key": c.pass_key,
                 "fail_key": c.fail_key, "sentence": c.sentence, "change_key": c.change_key, "change": c.change}
                for c in self.conditions
            ],
            "documents_required": d["documents_required"], "loan_limits": d["loan_limits"],
            "funding_pattern": d["funding_pattern"], "interest": d["interest"], "moratorium": d["moratorium"],
            "repayment": d["repayment"], "channel_partner_types": d["channel_partner_types"],
            "processing_days": d.get("processing_days", 30),
        }


@dataclass
class RuleSet:
    schemes: dict[str, SchemeRules]

    def bundle(self) -> dict[str, Any]:
        schemes = [s.to_bundle() for s in sorted(self.schemes.values(), key=lambda s: s.code)]
        canonical = json.dumps(schemes, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return {"etag": hashlib.sha256(canonical.encode()).hexdigest()[:32], "schemes": schemes}


_cache: RuleSet | None = None


def invalidate_ruleset() -> None:
    global _cache
    _cache = None


async def get_ruleset(session: AsyncSession) -> RuleSet:
    """Published rule versions from the database, cached in-process until a publish."""
    global _cache
    if _cache is not None:
        return _cache
    rows = (
        await session.execute(
            select(Scheme, SchemeRuleVersion)
            .join(SchemeRuleVersion, SchemeRuleVersion.id == Scheme.rule_version_id)
            .where(Scheme.active.is_(True))
        )
    ).all()
    schemes: dict[str, SchemeRules] = {}
    for scheme, version in rows:
        doc = version.rules
        schemes[scheme.code] = SchemeRules(
            code=scheme.code, doc=doc, conditions=validate_document(doc), version=version.version,
            rule_version_id=str(version.id), scheme_id=str(scheme.id),
        )
    if not schemes:
        # Fresh database without seed: fall back to the reviewed YAML files.
        for doc in load_rule_files():
            schemes[doc["scheme_code"]] = SchemeRules(doc["scheme_code"], doc, validate_document(doc), doc["version"])
    _cache = RuleSet(schemes)
    return _cache
