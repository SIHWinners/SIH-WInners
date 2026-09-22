import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { affordability, buildSchedule, emiPaise, fundingSplit, roundHalfEven, type LoanInput } from '../src/finance';
import { evaluateLogic, evaluateScheme, normaliseFacts, RuleError, type BundleCondition } from '../src/rules';

const fixtures = join(dirname(fileURLToPath(import.meta.url)), '..', 'fixtures');
const load = (name: string) => JSON.parse(readFileSync(join(fixtures, name), 'utf8'));

describe('rules twin', () => {
  const { cases, errors } = load('jsonlogic-cases.json');

  const labelled = cases.map((c: { logic: unknown }) => [JSON.stringify(c.logic).slice(0, 60), c]) as Array<[string, unknown]>;
  it.each(labelled)('%s', (_label, c) => {
    const tc = c as { logic: unknown; data: unknown; params?: Record<string, unknown>; expect: unknown };
    expect(evaluateLogic(tc.logic, tc.data, tc.params)).toEqual(tc.expect);
  });

  it('rejects the same malformed logic as Python', () => {
    for (const e of errors) expect(() => evaluateLogic(e.logic, {}, {})).toThrow(RuleError);
  });

  it('matches the engine near-miss semantics', () => {
    const conditions: BundleCondition[] = [
      {
        id: 'income', kind: 'income_max', logic: { '<=': [{ var: 'annual_family_income_paise' }, { param: 'income_limit_paise' }] },
        fields: ['annual_family_income_paise'], pass_key: 'rules.c.income_within', fail_key: 'rules.c.income_exceeds',
        sentence: { value: { var: 'annual_family_income_paise', type: 'money' }, limit: { param: 'income_limit_paise', type: 'money' } },
        change_key: 'rules.change.income_below', change: { limit: { param: 'income_limit_paise', type: 'money' } },
      },
    ];
    const params = { income_limit_paise: 50_000_000 };
    expect(evaluateScheme(conditions, { annual_family_income_paise: 50_000_000 }, params).status).toBe('eligible');
    const over = evaluateScheme(conditions, { annual_family_income_paise: 50_000_100 }, params);
    expect(over.near_miss?.change).toEqual({ key: 'rules.change.income_below', params: { limit: { type: 'money', value: 50_000_000 } } });
    expect(evaluateScheme(conditions, {}, params)).toMatchObject({ status: 'needs_info', missing: ['annual_family_income_paise'] });
    expect(normaliseFacts({ has_disability: false, state_code: 'gj' })).toMatchObject({ disability_pct: 0, state_code: 'GJ' });
  });
});

describe('finance twin', () => {
  it('rounds half to even', () => {
    expect(roundHalfEven(5n, 2n)).toBe(2n);
    expect(roundHalfEven(7n, 2n)).toBe(4n);
    expect(roundHalfEven(-7n, 2n)).toBe(-4n);
    expect(() => roundHalfEven(1n, 0n)).toThrow();
  });

  it('computes the textbook EMI', () => {
    expect(emiPaise(10_000_000n, 1200, 12)).toBe(888_488n);
  });

  it('reproduces 1,000 server-generated cases to the paisa', () => {
    const { cases } = load('finance-golden.json');
    expect(cases).toHaveLength(1000);
    for (const c of cases) {
      const s = buildSchedule(c.input as LoanInput);
      expect({
        emi: s.instalment_paise, after_moratorium: s.principal_after_moratorium_paise, total_interest: s.total_interest_paise,
        total_payable: s.total_payable_paise, rows: s.rows.length, last_payment: s.rows.at(-1)!.payment_paise,
      }).toEqual(c.expect);
    }
  });

  it('splits funding and suggests affordable options', () => {
    const split = fundingSplit(45_000_001, 9000, 500, 500);
    expect(split.apex_paise + split.partner_paise + split.beneficiary_paise).toBe(45_000_001);
    expect(() => fundingSplit(100, 9000, 500, 400)).toThrow();
    const loan: LoanInput = { principal_paise: 40_000_000, rate_bps: 800, tenure_months: 24, moratorium_months: 6 };
    const a = affordability(loan, buildSchedule(loan), 2_000_000, 4000, 84);
    expect(a.affordable).toBe(false);
    expect(a.suggest_tenure_months).not.toBeNull();
    expect(a.suggest_principal_paise! % 100_000).toBe(0);
  });

  it('validates inputs like the server', () => {
    expect(() => buildSchedule({ principal_paise: 0, rate_bps: 100, tenure_months: 12 })).toThrow();
    expect(() => buildSchedule({ principal_paise: 100, rate_bps: 100, tenure_months: 12, subsidy_paise: 100 })).toThrow();
  });
});
