/**
 * Offline eligibility — TypeScript twin of services/core/app/modules/eligibility/engine.py.
 * Evaluates the compiled rule bundle from GET /v1/rules/bundle with zero network. Results
 * computed here are shown as "provisional" and re-checked by the server when online.
 */

/* eslint-disable @typescript-eslint/no-explicit-any */
export type Json = any;

export class RuleError extends Error {}

const truthy = (v: Json): boolean => (Array.isArray(v) ? v.length > 0 : Boolean(v));

function getVar(data: Json, path: Json, fallback: Json = null): Json {
  if (path === null || path === undefined || path === '') return data;
  let node = data;
  for (const part of String(path).split('.')) {
    if (node !== null && typeof node === 'object' && !Array.isArray(node) && part in node) node = node[part];
    else if (Array.isArray(node) && /^\d+$/.test(part) && Number(part) < node.length) node = node[Number(part)];
    else return fallback;
  }
  return (node === null || node === undefined) && fallback !== null ? fallback : node ?? null;
}

const isNum = (v: Json) => typeof v === 'number' && Number.isFinite(v);

function num(v: Json): number {
  if (!isNum(v)) throw new TypeError('not a number');
  return v;
}

function deepEqual(a: Json, b: Json): boolean {
  if (a === b) return true;
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((x, i) => deepEqual(x, b[i]));
  return false;
}

function compare(op: string, args: Json[]): boolean {
  if (args.some((a) => a === null || a === undefined)) return false;
  if (!args.every(isNum)) return false;
  const [a, b, c] = args as number[];
  if (op === '<') return args.length === 3 ? a! < b! && b! < c! : a! < b!;
  if (op === '<=') return args.length === 3 ? a! <= b! && b! <= c! : a! <= b!;
  if (op === '>') return a! > b!;
  return a! >= b!;
}

export function evaluateLogic(logic: Json, data: Json, params: Record<string, Json> = {}): Json {
  if (Array.isArray(logic)) return logic.map((item) => evaluateLogic(item, data, params));
  if (logic === null || typeof logic !== 'object') return logic;
  const keys = Object.keys(logic);
  if (keys.length !== 1) throw new RuleError('a logic node must have exactly one operator');
  const op = keys[0]!;
  const raw = logic[op];
  const args: Json[] = Array.isArray(raw) ? raw : [raw];

  if (op === 'and') {
    let result: Json = true;
    for (const arg of args) {
      result = evaluateLogic(arg, data, params);
      if (!truthy(result)) return result;
    }
    return result;
  }
  if (op === 'or') {
    let result: Json = false;
    for (const arg of args) {
      result = evaluateLogic(arg, data, params);
      if (truthy(result)) return result;
    }
    return result;
  }
  if (op === 'if') {
    for (let i = 0; i + 1 < args.length; i += 2) {
      if (truthy(evaluateLogic(args[i], data, params))) return evaluateLogic(args[i + 1], data, params);
    }
    return args.length % 2 === 1 ? evaluateLogic(args[args.length - 1], data, params) : null;
  }

  const values = args.map((a) => evaluateLogic(a, data, params));
  switch (op) {
    case 'var':
      return getVar(data, values[0], values.length > 1 ? values[1] : null);
    case 'param':
      if (!(values[0] in params)) throw new RuleError(`unknown param ${values[0]}`);
      return params[values[0]];
    case 'missing':
      return values.filter((key) => getVar(data, key) === null);
    case '==':
    case '===':
      return deepEqual(values[0], values[1]);
    case '!=':
    case '!==':
      return !deepEqual(values[0], values[1]);
    case '<':
    case '<=':
    case '>':
    case '>=':
      if ((op === '>' || op === '>=') && values.length !== 2) throw new RuleError(`${op} takes exactly two arguments`);
      if (values.length !== 2 && values.length !== 3) throw new RuleError(`${op} takes two or three arguments`);
      return compare(op, values);
    case '!':
      return !truthy(values[0]);
    case '!!':
      return truthy(values[0]);
    case 'in': {
      const [needle, haystack] = values;
      if (needle === null || needle === undefined || haystack === null || haystack === undefined) return false;
      if (typeof haystack === 'string') return haystack.includes(String(needle));
      return Array.isArray(haystack) && haystack.some((h: Json) => deepEqual(h, needle));
    }
    case '+':
    case '*':
    case 'min':
    case 'max': {
      if (values.some((v) => v === null || v === undefined)) return null;
      const nums = values.map(num);
      if (op === '+') return nums.reduce((s, n) => s + n, 0);
      if (op === '*') return nums.reduce((s, n) => s * n, 1);
      return op === 'min' ? Math.min(...nums) : Math.max(...nums);
    }
    case '-':
    case '/': {
      if (values.some((v) => v === null || v === undefined)) return null;
      if (op === '-') return values.length === 1 ? -num(values[0]) : num(values[0]) - num(values[1]);
      return Math.floor(num(values[0]) / num(values[1]));
    }
    default:
      throw new RuleError(`operator ${op} is not allowed`);
  }
}

export interface TypedValue {
  type: string;
  value: Json;
}
export interface SentenceRef {
  key: string;
  params: Record<string, TypedValue>;
}
export interface BundleCondition {
  id: string;
  kind: string;
  logic: Json;
  fields: string[];
  pass_key: string;
  fail_key: string;
  sentence: Record<string, { var?: string; param?: string; type: string }>;
  change_key: string | null;
  change: Record<string, { var?: string; param?: string; type: string }>;
}
export interface TraceRow {
  id: string;
  kind: string;
  result: 'pass' | 'fail' | 'unknown';
  inputs: Record<string, Json>;
  logic: Json;
  sentence: SentenceRef;
  change: SentenceRef | null;
}
export interface SchemeOutcome {
  status: 'eligible' | 'ineligible' | 'needs_info';
  trace: TraceRow[];
  failed: string[];
  missing: string[];
  near_miss: TraceRow | null;
}

function sentenceParams(spec: BundleCondition['sentence'], facts: Json, params: Record<string, Json>) {
  const out: Record<string, TypedValue> = {};
  for (const [name, src] of Object.entries(spec)) {
    const raw = src.var !== undefined ? getVar(facts, src.var) : (params[src.param ?? ''] ?? null);
    out[name] = { type: src.type ?? 'text', value: raw };
  }
  return out;
}

export function evaluateCondition(cond: BundleCondition, facts: Json, params: Record<string, Json>): TraceRow {
  const inputs = Object.fromEntries(cond.fields.map((f) => [f, getVar(facts, f)]));
  const missing = Object.entries(inputs).filter(([, v]) => v === null).map(([k]) => k);
  if (missing.length) {
    return {
      id: cond.id, kind: cond.kind, result: 'unknown', inputs, logic: cond.logic,
      sentence: { key: 'rules.c.missing_value', params: { field: { type: 'field', value: missing[0] } } },
      change: null,
    };
  }
  const passed = truthy(evaluateLogic(cond.logic, facts, params));
  return {
    id: cond.id, kind: cond.kind, result: passed ? 'pass' : 'fail', inputs, logic: cond.logic,
    sentence: { key: passed ? cond.pass_key : cond.fail_key, params: sentenceParams(cond.sentence, facts, params) },
    change: !passed && cond.change_key ? { key: cond.change_key, params: sentenceParams(cond.change, facts, params) } : null,
  };
}

export function evaluateScheme(conditions: BundleCondition[], facts: Json, params: Record<string, Json>): SchemeOutcome {
  const trace = conditions.map((c) => evaluateCondition(c, facts, params));
  const failed = trace.filter((r) => r.result === 'fail');
  const unknown = trace.filter((r) => r.result === 'unknown');
  const status = failed.length ? 'ineligible' : unknown.length ? 'needs_info' : 'eligible';
  const nearMiss = failed.length === 1 && failed[0]!.change !== null && unknown.length === 0 ? failed[0]! : null;
  const missing = [...new Set(unknown.flatMap((r) => Object.entries(r.inputs).filter(([, v]) => v === null).map(([k]) => k)))].sort();
  return { status, trace, failed: failed.map((r) => r.id), missing, near_miss: nearMiss };
}

/** Mirrors ApplicantFacts.facts() on the server. */
export function normaliseFacts(applicant: Record<string, Json>): Record<string, Json> {
  const data = { ...applicant };
  if ((data.disability_pct === null || data.disability_pct === undefined) && data.has_disability === false) data.disability_pct = 0;
  if (typeof data.state_code === 'string') data.state_code = data.state_code.toUpperCase();
  return data;
}
