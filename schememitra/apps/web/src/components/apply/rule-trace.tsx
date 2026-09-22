'use client';

import type { SchemeResult, TraceRow } from '@sm/contracts/client';
import { useLocale, useTranslations } from 'next-intl';

import { Icon } from '@/components/icons';
import { Badge, Button, Card, cx } from '@/components/ui';
import { formatPaise, localName, pct, useSentence } from '@/lib/format';

const RESULT_STYLE: Record<TraceRow['result'], { icon: 'check' | 'x' | 'info'; cls: string; labelKey: string }> = {
  pass: { icon: 'check', cls: 'text-success-ink bg-success-tint', labelKey: 'rules.pass' },
  fail: { icon: 'x', cls: 'text-danger-ink bg-danger-tint', labelKey: 'rules.fail' },
  unknown: { icon: 'info', cls: 'text-warning-ink bg-warning-tint', labelKey: 'rules.unknown' },
};

/** C8: every rule, the applicant's value, pass/fail and a plain sentence in the user's language. */
export function RuleTrace({ rows }: { rows: TraceRow[] }) {
  const t = useTranslations();
  const sentence = useSentence();
  return (
    <ul className="flex flex-col gap-2" role="list" data-testid="rule-trace">
      {rows.map((row) => {
        const style = RESULT_STYLE[row.result];
        return (
          <li key={row.id} className="flex items-start gap-3 rounded-lg border border-border p-3">
            <span className={cx('grid size-8 shrink-0 place-items-center rounded-full', style.cls)} title={t(style.labelKey as never)}>
              <Icon name={style.icon} size={18} />
              <span className="sr-only">{t(style.labelKey as never)}</span>
            </span>
            <div className="min-w-0">
              <p className="text-base">{sentence(row.sentence)}</p>
              {row.change ? (
                <p className="mt-1 text-sm text-muted">{t('rules.near_miss_change', { change: sentence(row.change) })}</p>
              ) : null}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function SchemeCard({
  result,
  best,
  selected,
  onChoose,
  reasons,
}: {
  result: SchemeResult;
  best?: boolean;
  selected?: boolean;
  onChoose?: () => void;
  reasons?: string[];
}) {
  const t = useTranslations();
  const locale = useLocale();
  const { offer } = result;
  return (
    <Card as="article" className={cx('flex flex-col gap-4', selected && 'border-brand ring-2 ring-brand/30')} data-testid={`scheme-${result.code}`}>
      <header className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="mb-1 flex flex-wrap gap-1.5">
            {best ? (
              <Badge tone="accent" icon="sparkle">
                {t('rules.best_match')}
              </Badge>
            ) : null}
            <Badge tone="brand">{t(`options.loan_type.${result.loan_type}` as never)}</Badge>
            <Badge>{result.apex_corp}</Badge>
          </div>
          <h3 className="text-lg font-bold leading-snug">{localName(result.name, locale)}</h3>
        </div>
      </header>

      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Fact label={t('money.rate')} value={pct(offer.rate_bps)} />
        <Fact label={t('money.amount')} value={`≤ ${formatPaise(offer.max_loan_paise)}`} />
        <Fact label={t('money.moratorium')} value={offer.moratorium_default_months ? t('common.months', { count: offer.moratorium_default_months }) : t('money.moratorium_none')} />
        <Fact label={t('money.split_apex', { corp: result.apex_corp })} value={pct(offer.funding_pattern.apex_bps)} />
      </dl>

      {reasons?.length ? (
        <div>
          <p className="mb-1 text-sm font-bold text-muted">{t('rules.reasons_title')}</p>
          <ul className="flex flex-col gap-1 text-sm" role="list">
            {reasons.map((r) => (
              <li key={r} className="flex items-center gap-2">
                <Icon name="check" size={16} className="text-success-ink" /> {t(`rules.reason.${r}` as never)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <details className="group rounded-lg bg-surface-alt px-3 py-2">
        <summary className="sm-tap flex cursor-pointer list-none items-center justify-between font-semibold text-brand">
          {t('rules.why')}
          <Icon name="chevronDown" size={20} className="transition-transform group-open:rotate-180" />
        </summary>
        <div className="pb-2 pt-1">
          <RuleTrace rows={result.trace} />
          <p className="mt-2 text-xs text-muted">
            {t('rules.rule_version', { version: result.version, date: result.verified_on ?? '—' })} ·{' '}
            <a href={result.source_url} target="_blank" rel="noreferrer noopener" className="underline" lang="en">
              {new URL(result.source_url).hostname}
            </a>
          </p>
        </div>
      </details>

      {onChoose ? (
        <Button size="lg" variant={selected ? 'success' : 'primary'} icon={selected ? 'check' : undefined} onClick={onChoose} block data-testid={`choose-${result.code}`}>
          {selected ? t('partner.chosen') : t('common.continue')}
        </Button>
      ) : null}
    </Card>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-surface-alt px-3 py-2">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="tabular text-base font-bold">{value}</dd>
    </div>
  );
}

export function NearMissCard({ result, nextBest }: { result: SchemeResult; nextBest: SchemeResult | null }) {
  const t = useTranslations();
  const locale = useLocale();
  const sentence = useSentence();
  const miss = result.near_miss!;
  return (
    <Card className="flex flex-col gap-2 border-warning bg-warning-tint/40" data-testid={`near-miss-${result.code}`}>
      <p className="flex items-center gap-2 font-bold text-warning-ink">
        <Icon name="alert" size={20} /> {localName(result.name, locale)}
      </p>
      <p>{t('rules.near_miss', { rule: sentence(miss.sentence) })}</p>
      {miss.change ? <p className="font-semibold">{t('rules.near_miss_change', { change: sentence(miss.change) })}</p> : null}
      {nextBest ? (
        <p className="text-brand-ink">
          {t('rules.next_best', { scheme: localName(nextBest.name, locale) })}
        </p>
      ) : null}
    </Card>
  );
}
