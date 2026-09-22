/**
 * Repayment maths — TypeScript twin of services/core/app/modules/finance/calc.py.
 * Exact rational arithmetic with BigInt, rounded half-even to the paisa, so the offline
 * calculator on a phone gives the same rupee figures as the server. The golden test replays
 * 1,000 server-generated cases and requires identical output.
 */

export type Treatment = 'interest_capitalised' | 'interest_paid_monthly' | 'interest_waived';
export type Frequency = 'monthly' | 'quarterly';

const MONTHLY_DEN = 120_000n;
const QUARTERLY_DEN = 40_000n;

export function roundHalfEven(num: bigint, den: bigint): bigint {
  if (den <= 0n) throw new RangeError('denominator must be positive');
  const negative = num < 0n;
  const abs = negative ? -num : num;
  let q = abs / den;
  const twice = 2n * (abs % den);
  if (twice > den || (twice === den && q % 2n === 1n)) q += 1n;
  return negative ? -q : q;
}

export interface LoanInput {
  principal_paise: number;
  rate_bps: number;
  tenure_months: number;
  moratorium_months?: number;
  treatment?: Treatment;
  frequency?: Frequency;
  subsidy_paise?: number;
}

export interface ScheduleRow {
  period: number;
  month: number;
  kind: 'moratorium' | 'repayment';
  opening_paise: number;
  payment_paise: number;
  interest_paise: number;
  principal_paise: number;
  closing_paise: number;
}

export interface Schedule {
  principal_paise: number;
  principal_after_moratorium_paise: number;
  instalment_paise: number;
  instalments: number;
  period_months: number;
  total_interest_paise: number;
  total_payable_paise: number;
  moratorium_interest_paise: number;
  rows: ScheduleRow[];
}

function validate(loan: Required<LoanInput>): void {
  if (loan.principal_paise <= 0) throw new RangeError('principal must be positive');
  if (loan.rate_bps < 0 || loan.rate_bps > 3000) throw new RangeError('rate must be between 0 and 30%');
  if (loan.tenure_months < 1 || loan.tenure_months > 360) throw new RangeError('tenure must be 1–360 months');
  if (loan.moratorium_months < 0 || loan.moratorium_months > 60) throw new RangeError('moratorium must be 0–60 months');
  if (loan.subsidy_paise < 0 || loan.subsidy_paise >= loan.principal_paise)
    throw new RangeError('subsidy must be less than the principal');
  for (const v of [loan.principal_paise, loan.rate_bps, loan.tenure_months, loan.moratorium_months, loan.subsidy_paise])
    if (!Number.isSafeInteger(v)) throw new RangeError('amounts must be integer paise / bps / months');
}

export function instalmentsFor(tenureMonths: number, frequency: Frequency): [number, number] {
  return frequency === 'quarterly' ? [Math.ceil(tenureMonths / 3), 3] : [tenureMonths, 1];
}

export function emiPaise(principal: bigint, rateBps: number, instalments: number, frequency: Frequency = 'monthly'): bigint {
  if (instalments <= 0) throw new RangeError('instalments must be positive');
  if (rateBps === 0) return roundHalfEven(principal, BigInt(instalments));
  const den = frequency === 'quarterly' ? QUARTERLY_DEN : MONTHLY_DEN;
  const rate = BigInt(rateBps);
  const aN = (den + rate) ** BigInt(instalments);
  const bN = den ** BigInt(instalments);
  return roundHalfEven(principal * rate * aN, den * (aN - bN));
}

export function capitalisedBalance(principal: bigint, rateBps: number, months: number): bigint {
  const m = BigInt(months);
  return roundHalfEven(principal * (MONTHLY_DEN + BigInt(rateBps)) ** m, MONTHLY_DEN ** m);
}

export function buildSchedule(input: LoanInput): Schedule {
  const loan: Required<LoanInput> = {
    moratorium_months: 0,
    treatment: 'interest_capitalised',
    frequency: 'monthly',
    subsidy_paise: 0,
    ...input,
  };
  validate(loan);
  const principal = BigInt(loan.principal_paise - loan.subsidy_paise);
  const rows: ScheduleRow[] = [];
  let moratoriumInterest = 0n;
  let balance = principal;

  for (let month = 1; month <= loan.moratorium_months; month++) {
    let interest: bigint;
    let payment: bigint;
    let closing: bigint;
    if (loan.treatment === 'interest_capitalised') {
      closing = capitalisedBalance(principal, loan.rate_bps, month);
      interest = closing - balance;
      payment = 0n;
    } else if (loan.treatment === 'interest_paid_monthly') {
      interest = roundHalfEven(principal * BigInt(loan.rate_bps), MONTHLY_DEN);
      payment = interest;
      closing = balance;
    } else {
      interest = 0n;
      payment = 0n;
      closing = balance;
    }
    moratoriumInterest += interest;
    rows.push(row(month, month, 'moratorium', balance, payment, interest, 0n, closing));
    balance = closing;
  }

  const afterMoratorium = balance;
  const [count, step] = instalmentsFor(loan.tenure_months, loan.frequency);
  const instalment = emiPaise(afterMoratorium, loan.rate_bps, count, loan.frequency);
  const den = loan.frequency === 'quarterly' ? QUARTERLY_DEN : MONTHLY_DEN;

  for (let period = 1; period <= count; period++) {
    const interest = roundHalfEven(balance * BigInt(loan.rate_bps), den);
    let principalPart = period === count ? balance : instalment - interest;
    if (principalPart > balance) principalPart = balance;
    const closing = balance - principalPart;
    rows.push(
      row(loan.moratorium_months + period, loan.moratorium_months + period * step, 'repayment', balance,
        principalPart + interest, interest, principalPart, closing),
    );
    balance = closing;
  }

  const totalPayable = rows.reduce((s, r) => s + r.payment_paise, 0);
  const paidInterest = rows.filter((r) => r.kind === 'repayment').reduce((s, r) => s + r.interest_paise, 0);
  return {
    principal_paise: Number(principal),
    principal_after_moratorium_paise: Number(afterMoratorium),
    instalment_paise: Number(instalment),
    instalments: count,
    period_months: step,
    total_interest_paise: paidInterest + Number(moratoriumInterest),
    total_payable_paise: totalPayable,
    moratorium_interest_paise: Number(moratoriumInterest),
    rows,
  };
}

function row(period: number, month: number, kind: ScheduleRow['kind'], opening: bigint, payment: bigint,
  interest: bigint, principal: bigint, closing: bigint): ScheduleRow {
  return {
    period,
    month,
    kind,
    opening_paise: Number(opening),
    payment_paise: Number(payment),
    interest_paise: Number(interest),
    principal_paise: Number(principal),
    closing_paise: Number(closing),
  };
}

export interface Split {
  project_cost_paise: number;
  apex_paise: number;
  partner_paise: number;
  beneficiary_paise: number;
  apex_bps: number;
  partner_bps: number;
  beneficiary_bps: number;
}

export function fundingSplit(projectCostPaise: number, apexBps: number, partnerBps: number, beneficiaryBps: number): Split {
  if (apexBps + partnerBps + beneficiaryBps !== 10_000) throw new RangeError('shares must add up to 10000 bps');
  const cost = BigInt(projectCostPaise);
  const apex = roundHalfEven(cost * BigInt(apexBps), 10_000n);
  const partner = roundHalfEven(cost * BigInt(partnerBps), 10_000n);
  return {
    project_cost_paise: projectCostPaise,
    apex_paise: Number(apex),
    partner_paise: Number(partner),
    beneficiary_paise: Number(cost - apex - partner),
    apex_bps: apexBps,
    partner_bps: partnerBps,
    beneficiary_bps: beneficiaryBps,
  };
}

export interface Affordability {
  affordable: boolean;
  ratio_bps: number;
  max_ratio_bps: number;
  monthly_income_paise: number;
  suggest_tenure_months: number | null;
  suggest_tenure_emi_paise: number | null;
  suggest_principal_paise: number | null;
  suggest_principal_emi_paise: number | null;
}

const monthlyEquivalent = (instalment: number, periodMonths: number) =>
  Number(roundHalfEven(BigInt(instalment), BigInt(periodMonths)));

export function affordability(input: LoanInput, schedule: Schedule, monthlyIncomePaise: number, maxRatioBps = 4000,
  maxTenureMonths?: number): Affordability {
  const monthly = monthlyEquivalent(schedule.instalment_paise, schedule.period_months);
  const ratio = monthlyIncomePaise > 0 ? Number(roundHalfEven(BigInt(monthly) * 10_000n, BigInt(monthlyIncomePaise))) : 10_000_000;
  const ok = monthlyIncomePaise > 0 && monthly * 10_000 <= monthlyIncomePaise * maxRatioBps;
  const result: Affordability = {
    affordable: ok, ratio_bps: ratio, max_ratio_bps: maxRatioBps, monthly_income_paise: monthlyIncomePaise,
    suggest_tenure_months: null, suggest_tenure_emi_paise: null, suggest_principal_paise: null, suggest_principal_emi_paise: null,
  };
  if (ok || monthlyIncomePaise <= 0) return result;

  const cap = Math.floor((monthlyIncomePaise * maxRatioBps) / 10_000);
  const step = input.frequency === 'quarterly' ? 3 : 1;
  for (let tenure = input.tenure_months + step; tenure <= (maxTenureMonths ?? input.tenure_months); tenure += step) {
    const trial = buildSchedule({ ...input, tenure_months: tenure });
    if (monthlyEquivalent(trial.instalment_paise, trial.period_months) <= cap) {
      result.suggest_tenure_months = tenure;
      result.suggest_tenure_emi_paise = trial.instalment_paise;
      break;
    }
  }
  let lo = 0;
  let hi = Math.floor(input.principal_paise / 100_000);
  while (lo < hi) {
    const mid = Math.floor((lo + hi + 1) / 2);
    const trial = buildSchedule({ ...input, principal_paise: mid * 100_000, subsidy_paise: 0 });
    if (monthlyEquivalent(trial.instalment_paise, trial.period_months) <= cap) lo = mid;
    else hi = mid - 1;
  }
  if (lo > 0) {
    const best = buildSchedule({ ...input, principal_paise: lo * 100_000, subsidy_paise: 0 });
    result.suggest_principal_paise = lo * 100_000;
    result.suggest_principal_emi_paise = best.instalment_paise;
  }
  return result;
}
