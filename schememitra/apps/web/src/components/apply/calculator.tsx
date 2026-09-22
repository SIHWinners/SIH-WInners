'use client';

import type { SchemeResult } from '@sm/contracts/client';
import { affordability, buildSchedule, fundingSplit, type Schedule, type Treatment } from '@sm/contracts/finance';
import { useTranslations } from 'next-intl';
import { useMemo, useState } from 'react';

import { Icon } from '@/components/icons';
import { Button, Card, cx, Notice } from '@/components/ui';
import { formatPaise, pct, useMoneyWords } from '@/lib/format';
import type { LoanPlan } from '@/stores/draft';

import { ListenButton } from './shell';

const DECK_MIN_RATE = 650;
const DECK_MAX_RATE = 1500;
const MORATORIUM_STEPS = [0, 3, 6, 9, 12, 18, 24, 36, 48, 60];

export function defaultPlan(result: SchemeResult, loanNeeded?: number | null): LoanPlan {
  const { offer } = result;
  return {
    principal_paise: Math.min(loanNeeded ?? offer.suggested_principal_paise ?? offer.max_loan_paise, offer.max_loan_paise),
    rate_bps: offer.rate_bps,
    tenure_months: offer.default_tenure_months,
    moratorium_months: offer.moratorium_default_months,
    treatment: offer.moratorium_treatment as Treatment,
    frequency: offer.repayment_frequency === 'quarterly' ? 'quarterly' : 'monthly',
  };
}

export function Calculator({
  result,
  plan,
  onChange,
  annualIncomePaise,
  projectCostPaise,
}: {
  result: SchemeResult;
  plan: LoanPlan;
  onChange: (p: LoanPlan) => void;
  annualIncomePaise?: number | null;
  projectCostPaise?: number | null;
}) {
  const t = useTranslations();
  const words = useMoneyWords();
  const { offer } = result;
  const [saved, setSaved] = useState<LoanPlan[]>([]);

  const minRate = Math.min(DECK_MIN_RATE, offer.rate_bps); // ADR-014
  const maxRate = Math.max(DECK_MAX_RATE, offer.rate_bps);
  const tenureOptions = useMemo(() => {
    const out = new Set<number>();
    for (let m = 6; m <= offer.max_tenure_months; m += m < 24 ? 6 : 12) out.add(m);
    out.add(offer.max_tenure_months);
    out.add(plan.tenure_months);
    return [...out].sort((a, b) => a - b);
  }, [offer.max_tenure_months, plan.tenure_months]);
  const moratoriumOptions = MORATORIUM_STEPS.filter((m) => m <= offer.moratorium_max_months);

  const schedule = useMemo(() => buildSchedule(plan), [plan]);
  const monthlyIncome = annualIncomePaise ? Math.floor(annualIncomePaise / 12) : 0;
  const afford = useMemo(
    () => (monthlyIncome ? affordability(plan, schedule, monthlyIncome, 4000, offer.max_tenure_months) : null),
    [plan, schedule, monthlyIncome, offer.max_tenure_months],
  );
  const cost = projectCostPaise && projectCostPaise >= plan.principal_paise ? projectCostPaise : plan.principal_paise;
  const split = fundingSplit(cost, offer.funding_pattern.apex_bps, offer.funding_pattern.partner_bps, offer.funding_pattern.beneficiary_bps);
  const set = (patch: Partial<LoanPlan>) => onChange({ ...plan, ...patch });
  const emiLabel = plan.frequency === 'quarterly' ? t('money.instalment') : t('money.emi');

  const spoken = `${emiLabel}: ${words(schedule.instalment_paise)}. ${t('money.total_payable')}: ${words(schedule.total_payable_paise)}.`;

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-muted">{emiLabel}</p>
            <p className="tabular text-4xl font-bold text-brand" data-testid="emi-value">
              {formatPaise(schedule.instalment_paise)}
            </p>
            <p className="text-sm text-muted">
              {t('common.months', { count: schedule.instalments * schedule.period_months })} · {pct(plan.rate_bps)}
              {plan.moratorium_months ? ` · ${t('money.moratorium')}: ${t('common.months', { count: plan.moratorium_months })}` : ''}
            </p>
          </div>
          <ListenButton text={spoken} />
        </div>

        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          <Stat label={t('money.total_interest')} value={formatPaise(schedule.total_interest_paise)} />
          <Stat label={t('money.total_payable')} value={formatPaise(schedule.total_payable_paise)} />
          {plan.moratorium_months ? <Stat label={t('money.principal_after_holiday')} value={formatPaise(schedule.principal_after_moratorium_paise)} /> : null}
        </dl>

        {afford ? (
          afford.affordable ? (
            <Notice tone="success" icon="check">
              {t('money.affordability_ok')}
            </Notice>
          ) : (
            <Notice tone="warning" icon="alert" title={t('money.affordability_warn', { pct: afford.max_ratio_bps / 100 })}>
              <div className="mt-2 flex flex-wrap gap-2">
                {afford.suggest_tenure_months ? (
                  <Button size="sm" variant="secondary" onClick={() => set({ tenure_months: afford.suggest_tenure_months! })}>
                    {t('money.suggest_longer', { months: afford.suggest_tenure_months, emi: formatPaise(afford.suggest_tenure_emi_paise!) })}
                  </Button>
                ) : null}
                {afford.suggest_principal_paise ? (
                  <Button size="sm" variant="secondary" onClick={() => set({ principal_paise: afford.suggest_principal_paise! })}>
                    {t('money.suggest_lower', { amount: formatPaise(afford.suggest_principal_paise), emi: formatPaise(afford.suggest_principal_emi_paise!) })}
                  </Button>
                ) : null}
              </div>
            </Notice>
          )
        ) : null}
        <p className="flex items-center gap-1.5 text-xs text-muted">
          <Icon name="lock" size={14} /> {t('money.offline_calc')}
        </p>
      </Card>

      <Card className="flex flex-col gap-5">
        <Range
          id="amount"
          label={t('money.amount')}
          value={Math.round(plan.principal_paise / 100)}
          min={1000}
          max={Math.round(offer.max_loan_paise / 100)}
          step={1000}
          display={formatPaise(plan.principal_paise)}
          onChange={(v) => set({ principal_paise: v * 100 })}
        />
        <Range
          id="rate"
          label={t('money.rate')}
          value={plan.rate_bps}
          min={minRate}
          max={maxRate}
          step={25}
          display={pct(plan.rate_bps)}
          onChange={(v) => set({ rate_bps: v })}
        />
        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            id="tenure"
            label={t('money.tenure')}
            value={plan.tenure_months}
            options={tenureOptions.map((m) => ({ value: m, label: t('common.months', { count: m }) }))}
            onChange={(v) => set({ tenure_months: Number(v) })}
          />
          <Select
            id="moratorium"
            label={t('money.moratorium')}
            value={plan.moratorium_months}
            options={moratoriumOptions.map((m) => ({ value: m, label: m ? t('common.months', { count: m }) : t('money.moratorium_none') }))}
            onChange={(v) => set({ moratorium_months: Number(v) })}
          />
          {plan.moratorium_months ? (
            <Select
              id="treatment"
              label={t('money.treatment')}
              value={plan.treatment}
              options={(['interest_capitalised', 'interest_paid_monthly', 'interest_waived'] as const).map((v) => ({
                value: v,
                label: t(`options.moratorium_treatment.${v}`),
              }))}
              onChange={(v) => set({ treatment: v as Treatment })}
            />
          ) : null}
          <Select
            id="frequency"
            label={t('money.frequency')}
            value={plan.frequency}
            options={[
              { value: 'monthly', label: t('money.monthly') },
              { value: 'quarterly', label: t('money.quarterly') },
            ]}
            onChange={(v) => set({ frequency: v as LoanPlan['frequency'] })}
          />
        </div>
      </Card>

      <SplitCard split={split} corp={result.apex_corp} />
      <ScheduleCard schedule={schedule} />

      <Card className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-bold">{t('money.compare')}</h2>
          <Button size="sm" variant="secondary" icon="refresh" disabled={saved.length >= 3} onClick={() => setSaved((s) => [...s, plan].slice(-3))}>
            {t('money.add_option')}
          </Button>
        </div>
        {saved.length ? <CompareTable plans={saved} onPick={onChange} /> : null}
      </Card>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-surface-alt px-3 py-2">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="tabular font-bold">{value}</dd>
    </div>
  );
}

function Range({ id, label, value, min, max, step, display, onChange }: {
  id: string; label: string; value: number; min: number; max: number; step: number; display: string; onChange: (v: number) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between">
        <label htmlFor={id} className="font-semibold">
          {label}
        </label>
        <output htmlFor={id} className="tabular text-lg font-bold text-brand">
          {display}
        </output>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={Math.min(Math.max(value, min), max)}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-10 w-full accent-[var(--sm-brand)]"
      />
    </div>
  );
}

function Select({ id, label, value, options, onChange }: {
  id: string; label: string; value: string | number; options: Array<{ value: string | number; label: string }>; onChange: (v: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-semibold">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-12 rounded-md border border-border-strong bg-surface px-3 text-base"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function SplitCard({ split, corp }: { split: ReturnType<typeof fundingSplit>; corp: string }) {
  const t = useTranslations('money');
  const parts = [
    { key: 'apex', label: t('split_apex', { corp }), paise: split.apex_paise, bps: split.apex_bps, cls: 'bg-brand' },
    { key: 'partner', label: t('split_partner'), paise: split.partner_paise, bps: split.partner_bps, cls: 'bg-accent' },
    { key: 'you', label: t('split_you'), paise: split.beneficiary_paise, bps: split.beneficiary_bps, cls: 'bg-success' },
  ].filter((p) => p.bps > 0);
  return (
    <Card className="flex flex-col gap-3" data-testid="funding-split">
      <h2 className="font-bold">{t('split_title')}</h2>
      <div className="flex h-4 overflow-hidden rounded-full" aria-hidden>
        {parts.map((p) => (
          <span key={p.key} className={p.cls} style={{ width: `${p.bps / 100}%` }} />
        ))}
      </div>
      <ul className="flex flex-col gap-1.5" role="list">
        {parts.map((p) => (
          <li key={p.key} className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-2">
              <span className={cx('size-3 rounded-full', p.cls)} aria-hidden /> {p.label}
            </span>
            <span className="tabular font-semibold">
              {formatPaise(p.paise)} <span className="text-sm text-muted">({pct(p.bps)})</span>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function ScheduleCard({ schedule }: { schedule: Schedule }) {
  const t = useTranslations('money');
  const rows = schedule.rows;
  const maxPayment = Math.max(1, ...rows.map((r) => r.payment_paise), ...rows.map((r) => r.interest_paise));
  const width = 320;
  const height = 110;
  const barW = width / rows.length;
  return (
    <Card className="flex flex-col gap-3">
      <h2 className="font-bold">{t('schedule')}</h2>
      <svg viewBox={`0 0 ${width} ${height}`} className="h-28 w-full" role="img" aria-label={`${t('schedule')}: ${rows.length}`}>
        {rows.map((r, i) => {
          const principalH = (r.principal_paise / maxPayment) * (height - 4);
          const interestH = (r.interest_paise / maxPayment) * (height - 4);
          return (
            <g key={r.period}>
              <rect x={i * barW} y={height - principalH - interestH} width={Math.max(barW - 0.6, 0.6)} height={interestH} fill="var(--sm-accent)" />
              <rect x={i * barW} y={height - principalH} width={Math.max(barW - 0.6, 0.6)} height={principalH} fill={r.kind === 'moratorium' ? 'var(--sm-border-strong)' : 'var(--sm-brand)'} />
            </g>
          );
        })}
      </svg>
      <p className="flex flex-wrap gap-4 text-xs text-muted">
        <span className="flex items-center gap-1"><span className="size-2.5 rounded-sm bg-brand" aria-hidden /> {t('schedule_principal')}</span>
        <span className="flex items-center gap-1"><span className="size-2.5 rounded-sm bg-accent" aria-hidden /> {t('schedule_interest')}</span>
      </p>
      <details>
        <summary className="sm-tap flex cursor-pointer items-center font-semibold text-brand">{t('schedule')}</summary>
        <div className="mt-2 max-h-80 overflow-auto">
          <table className="tabular w-full text-sm">
            <thead className="sticky top-0 bg-surface text-start text-muted">
              <tr>
                <th className="py-1 text-start">{t('schedule_month')}</th>
                <th className="py-1 text-end">{t('schedule_payment')}</th>
                <th className="py-1 text-end">{t('schedule_interest')}</th>
                <th className="py-1 text-end">{t('schedule_principal')}</th>
                <th className="py-1 text-end">{t('schedule_balance')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.period} className={cx('border-t border-border', r.kind === 'moratorium' && 'text-muted')}>
                  <td className="py-1">{r.month}</td>
                  <td className="py-1 text-end">{formatPaise(r.payment_paise)}</td>
                  <td className="py-1 text-end">{formatPaise(r.interest_paise)}</td>
                  <td className="py-1 text-end">{formatPaise(r.principal_paise)}</td>
                  <td className="py-1 text-end">{formatPaise(r.closing_paise)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Card>
  );
}

function CompareTable({ plans, onPick }: { plans: LoanPlan[]; onPick: (p: LoanPlan) => void }) {
  const t = useTranslations();
  const schedules = plans.map((p) => buildSchedule(p));
  return (
    <div className="overflow-x-auto">
      <table className="tabular w-full text-sm">
        <thead>
          <tr className="text-muted">
            <th />
            {plans.map((_, i) => (
              <th key={i} className="px-2 py-1 text-end">
                {t('money.option', { n: i + 1 })}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {[
            [t('money.amount'), plans.map((p) => formatPaise(p.principal_paise))],
            [t('money.rate'), plans.map((p) => pct(p.rate_bps))],
            [t('money.tenure'), plans.map((p) => t('common.months', { count: p.tenure_months }))],
            [t('money.emi'), schedules.map((s) => formatPaise(s.instalment_paise))],
            [t('money.total_payable'), schedules.map((s) => formatPaise(s.total_payable_paise))],
          ].map(([label, values]) => (
            <tr key={label as string} className="border-t border-border">
              <th className="py-1.5 text-start font-semibold">{label}</th>
              {(values as string[]).map((v, i) => (
                <td key={i} className="px-2 py-1.5 text-end">
                  {v}
                </td>
              ))}
            </tr>
          ))}
          <tr>
            <td />
            {plans.map((p, i) => (
              <td key={i} className="px-2 pt-2 text-end">
                <Button size="sm" variant="ghost" onClick={() => onPick(p)}>
                  {t('common.confirm')}
                </Button>
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
