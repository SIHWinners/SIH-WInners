"""Repayment maths (spec §9.5). Integer paise and basis points only.

Every fraction is computed as an exact rational number with Python integers and rounded
half-even to the paisa once, at the point a rupee amount is shown. With r = bps/120000
per month, (1 + r)^k = (120000 + bps)^k / 120000^k exactly, so:

  capitalised holiday   P' = P × A_m^m / B_m^m                     (A_m = 120000 + bps, B_m = 120000)
  EMI                   = P' × bps × A^n / (B × (A^n − B^n))       (B = 120000 monthly, 40000 quarterly)
  zero rate             = P' / n

The TypeScript twin (packages/contracts/src/finance.ts) does the same with BigInt; a golden
test replays 1,000 random cases through both and requires identical output to the paisa."""

from dataclasses import dataclass, field
from typing import Literal

Treatment = Literal["interest_capitalised", "interest_paid_monthly", "interest_waived"]
Frequency = Literal["monthly", "quarterly"]

MONTHLY_DEN = 120_000  # 12 months × 10,000 bps
QUARTERLY_DEN = 40_000  # 4 quarters × 10,000 bps


def round_half_even(num: int, den: int) -> int:
    if den <= 0:
        raise ValueError("denominator must be positive")
    sign = -1 if num < 0 else 1
    q, r = divmod(abs(num), den)
    twice = 2 * r
    if twice > den or (twice == den and q % 2 == 1):
        q += 1
    return sign * q


@dataclass(frozen=True)
class LoanInput:
    principal_paise: int
    rate_bps: int
    tenure_months: int  # repayment period after the payment holiday
    moratorium_months: int = 0
    treatment: Treatment = "interest_capitalised"
    frequency: Frequency = "monthly"
    subsidy_paise: int = 0

    def validate(self) -> None:
        if self.principal_paise <= 0:
            raise ValueError("principal must be positive")
        if not 0 <= self.rate_bps <= 3000:
            raise ValueError("rate must be between 0 and 30%")
        if not 1 <= self.tenure_months <= 360:
            raise ValueError("tenure must be 1–360 months")
        if not 0 <= self.moratorium_months <= 60:
            raise ValueError("moratorium must be 0–60 months")
        if not 0 <= self.subsidy_paise < self.principal_paise:
            raise ValueError("subsidy must be less than the principal")


@dataclass
class Row:
    period: int
    month: int
    kind: Literal["moratorium", "repayment"]
    opening_paise: int
    payment_paise: int
    interest_paise: int
    principal_paise: int
    closing_paise: int


@dataclass
class Schedule:
    principal_paise: int
    principal_after_moratorium_paise: int
    instalment_paise: int
    instalments: int
    period_months: int
    total_interest_paise: int
    total_payable_paise: int
    moratorium_interest_paise: int
    rows: list[Row] = field(default_factory=list)


def instalments_for(tenure_months: int, frequency: Frequency) -> tuple[int, int]:
    """(number of instalments, months per instalment). Quarterly rounds the count up."""
    if frequency == "quarterly":
        return -(-tenure_months // 3), 3
    return tenure_months, 1


def emi_paise(principal_paise: int, rate_bps: int, instalments: int, frequency: Frequency = "monthly") -> int:
    if instalments <= 0:
        raise ValueError("instalments must be positive")
    if rate_bps == 0:
        return round_half_even(principal_paise, instalments)
    den = QUARTERLY_DEN if frequency == "quarterly" else MONTHLY_DEN
    a_n = (den + rate_bps) ** instalments
    b_n = den**instalments
    return round_half_even(principal_paise * rate_bps * a_n, den * (a_n - b_n))


def capitalised_balance(principal_paise: int, rate_bps: int, months: int) -> int:
    return round_half_even(principal_paise * (MONTHLY_DEN + rate_bps) ** months, MONTHLY_DEN**months)


def build_schedule(loan: LoanInput) -> Schedule:
    loan.validate()
    principal = loan.principal_paise - loan.subsidy_paise
    rows: list[Row] = []
    moratorium_interest = 0
    balance = principal

    for month in range(1, loan.moratorium_months + 1):
        if loan.treatment == "interest_capitalised":
            # Balance after k months is P·(1+r)^k rounded once, so accrued interest per row is
            # the difference of consecutive rounded balances and sums exactly to P' − P.
            closing = capitalised_balance(principal, loan.rate_bps, month)
            interest, payment = closing - balance, 0
        elif loan.treatment == "interest_paid_monthly":
            interest = round_half_even(principal * loan.rate_bps, MONTHLY_DEN)
            payment, closing = interest, balance
        else:
            interest, payment, closing = 0, 0, balance
        moratorium_interest += interest
        rows.append(Row(month, month, "moratorium", balance, payment, interest, 0, closing))
        balance = closing

    after_moratorium = balance
    count, step = instalments_for(loan.tenure_months, loan.frequency)
    instalment = emi_paise(after_moratorium, loan.rate_bps, count, loan.frequency)
    den = QUARTERLY_DEN if loan.frequency == "quarterly" else MONTHLY_DEN

    for period in range(1, count + 1):
        interest = round_half_even(balance * loan.rate_bps, den)
        if period == count:
            principal_part = balance  # last instalment absorbs all rounding
        else:
            principal_part = min(instalment - interest, balance)
        payment = principal_part + interest
        closing = balance - principal_part
        rows.append(Row(loan.moratorium_months + period, loan.moratorium_months + period * step, "repayment",
                        balance, payment, interest, principal_part, closing))
        balance = closing

    total_payable = sum(r.payment_paise for r in rows)
    paid_interest = sum(r.interest_paise for r in rows if r.kind == "repayment")
    return Schedule(
        principal_paise=principal,
        principal_after_moratorium_paise=after_moratorium,
        instalment_paise=instalment,
        instalments=count,
        period_months=step,
        total_interest_paise=paid_interest + moratorium_interest,
        total_payable_paise=total_payable,
        moratorium_interest_paise=moratorium_interest,
        rows=rows,
    )


@dataclass
class Split:
    project_cost_paise: int
    apex_paise: int
    partner_paise: int
    beneficiary_paise: int
    apex_bps: int
    partner_bps: int
    beneficiary_bps: int


def funding_split(project_cost_paise: int, apex_bps: int, partner_bps: int, beneficiary_bps: int) -> Split:
    if apex_bps + partner_bps + beneficiary_bps != 10_000:
        raise ValueError("shares must add up to 10000 bps")
    apex = round_half_even(project_cost_paise * apex_bps, 10_000)
    partner = round_half_even(project_cost_paise * partner_bps, 10_000)
    return Split(project_cost_paise, apex, partner, project_cost_paise - apex - partner,
                 apex_bps, partner_bps, beneficiary_bps)


@dataclass
class Affordability:
    affordable: bool
    ratio_bps: int
    max_ratio_bps: int
    monthly_income_paise: int
    suggest_tenure_months: int | None
    suggest_tenure_emi_paise: int | None
    suggest_principal_paise: int | None
    suggest_principal_emi_paise: int | None


def monthly_equivalent(instalment_paise: int, period_months: int) -> int:
    return round_half_even(instalment_paise, period_months)


def affordability(loan: LoanInput, schedule: Schedule, monthly_income_paise: int, max_ratio_bps: int = 4000,
                  max_tenure_months: int | None = None) -> Affordability:
    """EMI must stay within max_ratio of monthly income. When it doesn't, suggest the shortest
    longer tenure that fits and the largest principal (rounded down to ₹1,000) that fits."""
    monthly = monthly_equivalent(schedule.instalment_paise, schedule.period_months)
    ratio = round_half_even(monthly * 10_000, monthly_income_paise) if monthly_income_paise > 0 else 10_000_000
    ok = monthly_income_paise > 0 and monthly * 10_000 <= monthly_income_paise * max_ratio_bps
    result = Affordability(ok, ratio, max_ratio_bps, monthly_income_paise, None, None, None, None)
    if ok or monthly_income_paise <= 0:
        return result

    cap = monthly_income_paise * max_ratio_bps // 10_000
    step = 3 if loan.frequency == "quarterly" else 1
    for tenure in range(loan.tenure_months + step, (max_tenure_months or loan.tenure_months) + 1, step):
        trial = build_schedule(LoanInput(**{**loan.__dict__, "tenure_months": tenure}))
        if monthly_equivalent(trial.instalment_paise, trial.period_months) <= cap:
            result.suggest_tenure_months = tenure
            result.suggest_tenure_emi_paise = trial.instalment_paise
            break

    # Largest principal in ₹1,000 steps that fits, found by bisection on the exact schedule.
    lo, hi = 0, loan.principal_paise // 100_000
    while lo < hi:
        mid = (lo + hi + 1) // 2
        trial = build_schedule(LoanInput(**{**loan.__dict__, "principal_paise": mid * 100_000, "subsidy_paise": 0}))
        if monthly_equivalent(trial.instalment_paise, trial.period_months) <= cap:
            lo = mid
        else:
            hi = mid - 1
    if lo > 0:
        best = build_schedule(LoanInput(**{**loan.__dict__, "principal_paise": lo * 100_000, "subsidy_paise": 0}))
        result.suggest_principal_paise = lo * 100_000
        result.suggest_principal_emi_paise = best.instalment_paise
    return result
