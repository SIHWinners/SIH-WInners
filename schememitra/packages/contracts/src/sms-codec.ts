/**
 * SMS codec (spec §9.8, claim C13). When there is no data connection, a whole application
 * fits in at most three plain SMS. The wire format is deliberately boring so a feature phone,
 * a CSC operator or a bank's SMS gateway can all produce it:
 *
 *     SM1*<ref><part><total>*<payload>*<crc>
 *
 * - `SM1` is the format version, so we can change the payload later without guessing.
 * - `ref` is two base-36 characters that tie the parts of one message together.
 * - `payload` is `key=value;key=value`, keys are 1–2 characters (see FIELDS).
 * - `crc` is CRC-16/CCITT of the *joined* payload in base 36, so a mangled or partly
 *   delivered message is rejected instead of being half-applied.
 *
 * Every character is in the GSM-7 basic alphabet — including the `*` separators, which is why
 * they are not the more obvious `|` (that lives in GSM-7's extension table and would silently
 * double the cost of every message). One part is 160 characters, never UCS-2, never more than
 * three parts.
 */

export const SMS_VERSION = 'SM1';
export const MAX_PARTS = 3;
export const PART_CHARS = 160;
/** GSM 03.38 basic set, minus characters our own framing uses. */
const GSM7 = /^[A-Za-z0-9 @£$¥èéùìòÇØøÅåÆæßÉÑÜäöñüà!"#¤%&'()*+,\-./:;<=>?¡¿§_]*$/;

export interface SmsFacts {
  full_name?: string;
  age?: number;
  gender?: 'female' | 'male' | 'other';
  social_category?: 'sc' | 'st' | 'obc' | 'safai_karamchari' | 'minority' | 'general';
  state_code?: string;
  district_code?: string;
  pincode?: string;
  annual_family_income_rupees?: number;
  education_level?: string;
  business_type?: string;
  project_cost_rupees?: number;
  loan_needed_rupees?: number;
  shg_member?: boolean;
  existing_loans?: boolean;
  has_disability?: boolean;
  phone?: string;
  lang?: string;
}

/** Short wire key → field. Keep these stable: old phones may send an old message. */
export const FIELDS = {
  n: 'full_name', a: 'age', g: 'gender', c: 'social_category', s: 'state_code', d: 'district_code',
  p: 'pincode', i: 'annual_family_income_rupees', e: 'education_level', w: 'business_type',
  k: 'project_cost_rupees', l: 'loan_needed_rupees', sh: 'shg_member', x: 'existing_loans',
  dis: 'has_disability', ph: 'phone', lg: 'lang',
} as const satisfies Record<string, keyof SmsFacts>;

const GENDER = { female: 'f', male: 'm', other: 'o' } as const;
const CATEGORY = { sc: 'sc', st: 'st', obc: 'ob', safai_karamchari: 'sk', minority: 'mi', general: 'ge' } as const;
const WIRE_TO_GENDER = Object.fromEntries(Object.entries(GENDER).map(([k, v]) => [v, k]));
const WIRE_TO_CATEGORY = Object.fromEntries(Object.entries(CATEGORY).map(([k, v]) => [v, k]));

export function crc16(text: string): number {
  let crc = 0xffff;
  for (const char of text) {
    crc ^= char.charCodeAt(0) << 8;
    for (let bit = 0; bit < 8; bit++) crc = crc & 0x8000 ? ((crc << 1) ^ 0x1021) & 0xffff : (crc << 1) & 0xffff;
  }
  return crc;
}

const checksum = (payload: string): string => crc16(payload).toString(36).toUpperCase().padStart(4, '0');

/** Strips what GSM-7 cannot carry: a name in Gujarati travels as its Latin spelling or not at all. */
export function gsm7Safe(value: string): string {
  return [...value].filter((c) => GSM7.test(c)).join('').replace(/[;*=]/g, ' ').trim();
}

export function encodeFacts(facts: SmsFacts): string {
  const parts: string[] = [];
  for (const [key, field] of Object.entries(FIELDS) as [string, keyof SmsFacts][]) {
    const value = facts[field];
    if (value === undefined || value === null || value === '') continue;
    let wire: string;
    if (field === 'gender') wire = GENDER[value as keyof typeof GENDER];
    else if (field === 'social_category') wire = CATEGORY[value as keyof typeof CATEGORY];
    else if (typeof value === 'boolean') wire = value ? '1' : '0';
    else wire = gsm7Safe(String(value));
    if (wire) parts.push(`${key}=${wire}`);
  }
  return parts.join(';');
}

/** Splits an application into at most three sendable SMS bodies. */
export function encodeApply(facts: SmsFacts): string[] {
  const payload = encodeFacts(facts);
  const crc = checksum(payload);
  const ref = Math.floor(Math.random() * 1296).toString(36).toUpperCase().padStart(2, '0');
  const overhead = `${SMS_VERSION}*${ref}13*${crc}*`.length + 1;
  const room = PART_CHARS - overhead;
  const chunks: string[] = [];
  for (let i = 0; i < payload.length; i += room) chunks.push(payload.slice(i, i + room));
  if (chunks.length > MAX_PARTS) throw new Error(`application does not fit in ${MAX_PARTS} SMS`);
  return chunks.map((chunk, i) => `${SMS_VERSION}*${ref}${i + 1}${chunks.length}*${chunk}*${crc}`);
}

export type Decoded =
  | { kind: 'apply'; facts: SmsFacts; ref: string; parts: number }
  | { kind: 'status'; trackingId: string }
  | { kind: 'help' }
  | { kind: 'partial'; ref: string; received: number[]; total: number }
  | { kind: 'unknown'; reason: 'checksum' | 'format' | 'version' };

export interface Part {
  ref: string;
  part: number;
  total: number;
  body: string;
  crc: string;
}

export function parsePart(text: string): Part | null {
  const m = /^SM1\*([0-9A-Z]{2})([1-3])([1-3])\*(.*)\*([0-9A-Z]{4})$/.exec(text.trim());
  if (!m) return null;
  return { ref: m[1]!, part: Number(m[2]), total: Number(m[3]), body: m[4]!, crc: m[5]! };
}

export function decodeFacts(payload: string): SmsFacts {
  const facts: SmsFacts = {};
  const byKey = FIELDS as Record<string, keyof SmsFacts>;
  for (const pair of payload.split(';')) {
    const at = pair.indexOf('=');
    if (at < 1) continue;
    const field = byKey[pair.slice(0, at).trim()];
    const raw = pair.slice(at + 1).trim();
    if (!field || raw === '') continue;
    if (field === 'gender') facts.gender = WIRE_TO_GENDER[raw] as SmsFacts['gender'];
    else if (field === 'social_category') facts.social_category = WIRE_TO_CATEGORY[raw] as SmsFacts['social_category'];
    else if (field === 'shg_member' || field === 'existing_loans' || field === 'has_disability') facts[field] = raw === '1';
    else if (['age', 'annual_family_income_rupees', 'project_cost_rupees', 'loan_needed_rupees'].includes(field)) {
      const n = Number(raw);
      if (Number.isFinite(n)) (facts as Record<string, unknown>)[field] = Math.trunc(n);
    } else (facts as Record<string, unknown>)[field] = raw;
  }
  return facts;
}

/** Decodes one complete message. `parts` must be the bodies of a single ref, in order. */
export function decode(texts: string[]): Decoded {
  const first = texts[0]?.trim() ?? '';
  if (/^\s*help\b/i.test(first)) return { kind: 'help' };
  const status = /^\s*status\s+([A-Za-z0-9-]+)\s*$/i.exec(first);
  if (status) return { kind: 'status', trackingId: status[1]!.toUpperCase() };
  if (/^SM\d\*/.test(first) && !first.startsWith(`${SMS_VERSION}*`)) return { kind: 'unknown', reason: 'version' };

  const parsed = texts.map(parsePart);
  if (parsed.some((p) => p === null)) return { kind: 'unknown', reason: 'format' };
  const parts = (parsed as Part[]).sort((a, b) => a.part - b.part);
  const total = parts[0]!.total;
  const seen = parts.map((p) => p.part);
  if (seen.length < total || new Set(seen).size < total) {
    return { kind: 'partial', ref: parts[0]!.ref, received: [...new Set(seen)].sort(), total };
  }
  const payload = parts.map((p) => p.body).join('');
  if (checksum(payload) !== parts[0]!.crc) return { kind: 'unknown', reason: 'checksum' };
  return { kind: 'apply', facts: decodeFacts(payload), ref: parts[0]!.ref, parts: total };
}
