"""Deterministic eligibility engine (spec §9.3, ADR-005).

Two layers:
1. `evaluate_logic` — a small, whitelisted JSON-Logic interpreter. No I/O, no randomness,
   no floating-point money. The TypeScript twin in packages/contracts/src/rules.ts is
   tested against the same fixture file so both give identical answers.
2. `evaluate_scheme` — runs every compiled condition of one scheme against applicant facts
   and returns a trace: condition, inputs, pass/fail/unknown, and a sentence key + typed
   params that each client renders in the user's language.

AI never touches this module. Eligibility is rules only."""

from dataclasses import dataclass, field
from typing import Any

Json = Any


class RuleError(ValueError):
    """Malformed rule logic (unknown operator, wrong arity). Raised at load time."""


_MISSING = object()


def _truthy(value: Json) -> bool:
    # JSON-Logic truthiness: empty arrays are falsy, like the reference implementation.
    if isinstance(value, list):
        return len(value) > 0
    return bool(value)


def _get_var(data: dict[str, Any], path: Json, default: Json = None) -> Json:
    if path is None or path == "":
        return data
    node: Any = data
    for part in str(path).split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        elif isinstance(node, list) and part.isdigit() and int(part) < len(node):
            node = node[int(part)]
        else:
            return default
    return default if node is None and default is not None else node


def _num(value: Json) -> int | float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("not a number")
    return value


def _compare(op: str, args: list[Json]) -> bool:
    # Comparisons with a missing (None) operand are False rather than errors, so a missing
    # answer can never accidentally satisfy a limit. The trace marks such rows "unknown".
    if any(a is None for a in args):
        return False
    try:
        nums = [_num(a) for a in args]
    except TypeError:
        return False
    if op == "<":
        return all(x < y for x, y in zip(nums, nums[1:], strict=False))
    if op == "<=":
        return all(x <= y for x, y in zip(nums, nums[1:], strict=False))
    if op == ">":
        return nums[0] > nums[1]
    return nums[0] >= nums[1]


def evaluate_logic(logic: Json, data: dict[str, Any], params: dict[str, Any] | None = None) -> Json:
    params = params or {}
    if isinstance(logic, list):
        return [evaluate_logic(item, data, params) for item in logic]
    if not isinstance(logic, dict):
        return logic
    if len(logic) != 1:
        raise RuleError("a logic node must have exactly one operator")
    op, raw = next(iter(logic.items()))
    args = raw if isinstance(raw, list) else [raw]

    # Operators that control evaluation order are handled before evaluating arguments.
    if op == "and":
        result: Json = True
        for arg in args:
            result = evaluate_logic(arg, data, params)
            if not _truthy(result):
                return result
        return result
    if op == "or":
        result = False
        for arg in args:
            result = evaluate_logic(arg, data, params)
            if _truthy(result):
                return result
        return result
    if op == "if":
        for i in range(0, len(args) - 1, 2):
            if _truthy(evaluate_logic(args[i], data, params)):
                return evaluate_logic(args[i + 1], data, params)
        return evaluate_logic(args[-1], data, params) if len(args) % 2 == 1 else None

    values = [evaluate_logic(arg, data, params) for arg in args]

    if op == "var":
        return _get_var(data, values[0] if values else None, values[1] if len(values) > 1 else None)
    if op == "param":
        if values[0] not in params:
            raise RuleError(f"unknown param {values[0]!r}")
        return params[values[0]]
    if op == "missing":
        return [key for key in values if _get_var(data, key) is None]
    if op in ("==", "==="):
        return values[0] == values[1]
    if op in ("!=", "!=="):
        return values[0] != values[1]
    if op in ("<", "<=", ">", ">="):
        if op in (">", ">=") and len(values) != 2:
            raise RuleError(f"{op} takes exactly two arguments")
        if len(values) not in (2, 3):
            raise RuleError(f"{op} takes two or three arguments")
        return _compare(op, values)
    if op == "!":
        return not _truthy(values[0])
    if op == "!!":
        return _truthy(values[0])
    if op == "in":
        needle, haystack = values[0], values[1]
        if needle is None or haystack is None:
            return False
        if isinstance(haystack, str):
            return str(needle) in haystack
        return needle in haystack
    if op in ("+", "*", "min", "max"):
        if any(v is None for v in values):
            return None
        nums = [_num(v) for v in values]
        if op == "+":
            return sum(nums)
        if op == "*":
            product: int | float = 1
            for n in nums:
                product *= n
            return product
        return min(nums) if op == "min" else max(nums)
    if op in ("-", "/"):
        if any(v is None for v in values):
            return None
        if op == "-":
            return -_num(values[0]) if len(values) == 1 else _num(values[0]) - _num(values[1])
        # Integer division keeps paise arithmetic exact; rules never need fractions.
        return _num(values[0]) // _num(values[1])
    raise RuleError(f"operator {op!r} is not allowed")


def validate_logic(logic: Json, params: dict[str, Any]) -> None:
    """Dry-run against empty facts to surface unknown operators/params at load time."""
    evaluate_logic(logic, {}, params)


@dataclass
class Condition:
    id: str
    kind: str
    logic: Json
    fields: list[str]
    pass_key: str
    fail_key: str
    sentence: dict[str, dict[str, Any]] = field(default_factory=dict)
    change_key: str | None = None
    change: dict[str, dict[str, Any]] = field(default_factory=dict)


def _sentence_params(spec: dict[str, dict[str, Any]], facts: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    """Typed params, e.g. {"limit": {"type": "money", "paise": 50000000}}. Clients format them."""
    out: dict[str, Any] = {}
    for name, src in spec.items():
        raw = _get_var(facts, src["var"]) if "var" in src else params.get(src.get("param", ""))
        out[name] = {"type": src.get("type", "text"), "value": raw}
    return out


def evaluate_condition(cond: Condition, facts: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    inputs = {name: _get_var(facts, name) for name in cond.fields}
    missing = [name for name, value in inputs.items() if value is None]
    if missing:
        return {
            "id": cond.id, "kind": cond.kind, "result": "unknown", "inputs": inputs, "logic": cond.logic,
            "sentence": {"key": "rules.c.missing_value", "params": {"field": {"type": "field", "value": missing[0]}}},
            "change": None,
        }
    passed = _truthy(evaluate_logic(cond.logic, facts, params))
    sentence = {
        "key": cond.pass_key if passed else cond.fail_key,
        "params": _sentence_params(cond.sentence, facts, params),
    }
    change = None
    if not passed and cond.change_key:
        change = {"key": cond.change_key, "params": _sentence_params(cond.change, facts, params)}
    return {"id": cond.id, "kind": cond.kind, "result": "pass" if passed else "fail", "inputs": inputs,
            "logic": cond.logic, "sentence": sentence, "change": change}


def evaluate_scheme(conditions: list[Condition], facts: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    trace = [evaluate_condition(c, facts, params) for c in conditions]
    failed = [row for row in trace if row["result"] == "fail"]
    unknown = [row for row in trace if row["result"] == "unknown"]
    if failed:
        status = "ineligible"
    elif unknown:
        status = "needs_info"
    else:
        status = "eligible"
    near_miss = failed[0] if len(failed) == 1 and failed[0]["change"] is not None and not unknown else None
    return {
        "status": status,
        "trace": trace,
        "failed": [row["id"] for row in failed],
        "missing": sorted({f for row in unknown for f, v in row["inputs"].items() if v is None}),
        "near_miss": near_miss,
    }
