import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

import { decode, decodeFacts, encodeApply, encodeFacts, gsm7Safe, MAX_PARTS, parsePart, PART_CHARS, type SmsFacts } from '../src/sms-codec';

interface Case {
  name: string;
  ref?: string;
  facts?: SmsFacts;
  wire: string[];
  decoded?: SmsFacts;
  parts?: number;
  expect?: { kind: string; tracking_id?: string; reason?: string };
}

const cases: Case[] = JSON.parse(readFileSync(join(__dirname, '..', 'fixtures', 'sms-cases.json'), 'utf8'));

describe('SMS codec twin (shared fixture with the Python server)', () => {
  for (const c of cases.filter((x) => x.facts)) {
    it(`encodes ${c.name} exactly as the server does`, () => {
      // Same payload and checksum; only the random ref differs, so compare with the fixture's ref.
      const payload = encodeFacts(c.facts!);
      const fromFixture = c.wire.map((w) => parsePart(w)!);
      expect(fromFixture.map((p) => p.body).join('')).toBe(payload);
      expect(c.wire.every((w) => w.length <= PART_CHARS)).toBe(true);
      expect(c.wire.length).toBeLessThanOrEqual(MAX_PARTS);
    });

    it(`decodes ${c.name} to the same facts the server sees`, () => {
      const decoded = decode(c.wire);
      expect(decoded.kind).toBe('apply');
      if (decoded.kind === 'apply') expect(decoded.facts).toEqual(c.decoded);
    });
  }

  for (const c of cases.filter((x) => x.expect)) {
    it(`agrees on ${c.name}`, () => {
      const decoded = decode(c.wire);
      expect(decoded.kind).toBe(c.expect!.kind);
      if (c.expect!.tracking_id && decoded.kind === 'status') expect(decoded.trackingId).toBe(c.expect!.tracking_id);
      if (c.expect!.reason && decoded.kind === 'unknown') expect(decoded.reason).toBe(c.expect!.reason);
    });
  }
});

describe('SMS codec', () => {
  it('round-trips an application through its own encoder', () => {
    const facts: SmsFacts = {
      full_name: 'Ramesh Kanaram Meghwal', age: 41, gender: 'male', social_category: 'sc', state_code: 'RJ',
      district_code: 'RJ-BAR', pincode: '344001', annual_family_income_rupees: 180000, education_level: 'secondary',
      business_type: 'tailoring', project_cost_rupees: 450000, loan_needed_rupees: 400000, shg_member: false,
      existing_loans: false, phone: '9000000002', lang: 'hi',
    };
    const wire = encodeApply(facts);
    expect(wire.length).toBeLessThanOrEqual(MAX_PARTS);
    const decoded = decode(wire);
    expect(decoded).toMatchObject({ kind: 'apply', facts });
  });

  it('reports missing parts instead of applying half an application', () => {
    const long = { ...{ full_name: 'A'.repeat(200) } } as SmsFacts;
    const wire = encodeApply(long);
    expect(wire.length).toBeGreaterThan(1);
    const partial = decode([wire[0]!]);
    expect(partial).toMatchObject({ kind: 'partial', received: [1], total: wire.length });
  });

  it('rejects a corrupted message', () => {
    const wire = encodeApply({ age: 30, loan_needed_rupees: 50000 });
    const mangled = wire[0]!.replace('a=30', 'a=99');
    expect(decode([mangled])).toMatchObject({ kind: 'unknown', reason: 'checksum' });
  });

  it('refuses to fabricate: characters an SMS cannot carry are dropped, not transliterated', () => {
    expect(gsm7Safe('સવિતાબેન રાઠવા')).toBe('');
    expect(gsm7Safe('Savitaben Rathwa')).toBe('Savitaben Rathwa');
    // The three characters the wire format uses as separators are neutralised in values.
    expect(gsm7Safe('A;B*C=D')).toBe('A B C D');
  });

  it('ignores unknown keys from a newer sender', () => {
    expect(decodeFacts('a=41;zz=future;l=400000')).toEqual({ age: 41, loan_needed_rupees: 400000 });
  });

  it('never splits into more than three messages', () => {
    expect(() => encodeApply({ full_name: 'X'.repeat(600) })).toThrow(/three|3/i);
  });
});
