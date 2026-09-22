'use client';

import type { SchemeResult } from '@sm/contracts/client';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';

import { ApplyShell, NextStepCard } from '@/components/apply/shell';
import { NearMissCard, SchemeCard } from '@/components/apply/rule-trace';
import { Icon } from '@/components/icons';
import { Button, ButtonLink, Notice, Skeleton } from '@/components/ui';
import { evaluateFacts } from '@/lib/evaluate';
import { useDraft } from '@/stores/draft';

export default function RulesPage() {
  const t = useTranslations();
  const router = useRouter();
  const draft = useDraft();
  const [refreshing, setRefreshing] = useState(false);
  const evaluation = draft.evaluation;

  // A provisional (offline) result is re-checked by the server as soon as we are back online.
  useEffect(() => {
    if (!draft.hydrated || !evaluation?.provisional) return;
    const recheck = async () => {
      if (!navigator.onLine) return;
      setRefreshing(true);
      try {
        draft.setEvaluation(await evaluateFacts(useDraft.getState().facts));
      } catch {
        /* keep the provisional result */
      } finally {
        setRefreshing(false);
      }
    };
    void recheck();
    window.addEventListener('online', recheck);
    return () => window.removeEventListener('online', recheck);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.hydrated, evaluation?.provisional]);

  const byCode = useMemo(
    () => Object.fromEntries((evaluation?.results ?? []).map((r) => [r.code, r])) as Record<string, SchemeResult>,
    [evaluation],
  );

  if (!draft.hydrated) {
    return (
      <ApplyShell step="rule_check" reachable={1}>
        <Skeleton className="h-64" />
      </ApplyShell>
    );
  }
  if (!evaluation) {
    return (
      <ApplyShell step="rule_check" reachable={0}>
        <Notice tone="warning">{t('next_card.speak_scan')}</Notice>
        <ButtonLink href="/apply" size="lg">
          {t('home.start_form')}
        </ButtonLink>
      </ApplyShell>
    );
  }

  const eligible = evaluation.eligible.map((c) => byCode[c]!).filter(Boolean);
  const nearMisses = evaluation.near_misses.map((c) => byCode[c]!).filter(Boolean);
  const others = evaluation.ineligible.filter((c) => !evaluation.near_misses.includes(c)).map((c) => byCode[c]!);
  const nextBest = evaluation.next_best ? byCode[evaluation.next_best] ?? null : null;

  function choose(code: string) {
    draft.chooseScheme(code);
    router.push('/apply/money');
  }

  return (
    <ApplyShell step="rule_check" reachable={draft.schemeCode ? 2 : 1}>
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-bold">{eligible.length ? t('rules.eligible_count', { count: eligible.length }) : t('rules.none_eligible')}</h1>
        <p className="flex items-start gap-2 text-sm text-muted">
          <Icon name="shield" size={18} className="mt-0.5 shrink-0" /> {t('rules.rule_based_note')}
        </p>
      </header>

      {evaluation.provisional ? (
        <Notice tone="warning" icon={refreshing ? 'refresh' : 'wifiOff'}>
          {t('common.provisional')}
        </Notice>
      ) : null}

      <section className="flex flex-col gap-4" aria-label={t('rules.title')}>
        {eligible.map((r, i) => (
          <SchemeCard key={r.code} result={r} best={i === 0} selected={draft.schemeCode === r.code} onChoose={() => choose(r.code)} />
        ))}
      </section>

      {nearMisses.length ? (
        <section className="flex flex-col gap-3">
          {nearMisses.map((r) => (
            <NearMissCard key={r.code} result={r} nextBest={nextBest} />
          ))}
        </section>
      ) : null}

      {others.length ? (
        <details className="sm-card p-4">
          <summary className="sm-tap flex cursor-pointer items-center font-semibold">
            {t('rules.not_eligible_title')} ({others.length})
          </summary>
          <div className="mt-3 flex flex-col gap-3">
            {others.map((r) => (
              <SchemeCard key={r.code} result={r} />
            ))}
          </div>
        </details>
      ) : null}

      <div className="flex gap-3">
        <Button variant="secondary" icon="chevronLeft" onClick={() => router.push('/apply')}>
          {t('common.edit')}
        </Button>
      </div>
      <NextStepCard step="rule_check" />
    </ApplyShell>
  );
}
