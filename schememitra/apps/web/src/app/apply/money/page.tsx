'use client';

import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

import { Calculator, defaultPlan } from '@/components/apply/calculator';
import { ApplyShell, NextStepCard } from '@/components/apply/shell';
import { Button, ButtonLink, Notice, Skeleton } from '@/components/ui';
import { localName } from '@/lib/format';
import { useDraft } from '@/stores/draft';

export default function MoneyPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const draft = useDraft();
  const result = draft.evaluation?.results.find((r) => r.code === draft.schemeCode) ?? null;

  useEffect(() => {
    if (draft.hydrated && result && !draft.plan) draft.setPlan(defaultPlan(result, draft.facts.loan_needed_paise));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.hydrated, result]);

  if (!draft.hydrated) {
    return (
      <ApplyShell step="money_maths" reachable={2}>
        <Skeleton className="h-72" />
      </ApplyShell>
    );
  }
  if (!result) {
    return (
      <ApplyShell step="money_maths" reachable={1}>
        <Notice tone="warning">{t('next_card.rule_check')}</Notice>
        <ButtonLink href="/apply/rules" size="lg">
          {t('steps.rule_check')}
        </ButtonLink>
      </ApplyShell>
    );
  }

  return (
    <ApplyShell
      step="money_maths"
      reachable={draft.partner ? 3 : 2}
      footer={
        <>
          <Button variant="secondary" size="lg" icon="chevronLeft" onClick={() => router.push('/apply/rules')}>
            <span className="sr-only sm:not-sr-only">{t('common.back')}</span>
          </Button>
          <Button size="lg" block iconRight="chevronRight" disabled={!draft.plan} onClick={() => router.push('/apply/partner')} data-testid="money-next">
            {t('common.continue')}
          </Button>
        </>
      }
    >
      <header>
        <p className="text-sm font-semibold text-muted">{localName(result.name, locale)}</p>
        <h1 className="text-2xl font-bold">{t('money.title')}</h1>
      </header>
      {draft.plan ? (
        <Calculator
          result={result}
          plan={draft.plan}
          onChange={draft.setPlan}
          annualIncomePaise={draft.facts.annual_family_income_paise}
          projectCostPaise={draft.facts.project_cost_paise}
        />
      ) : (
        <Skeleton className="h-72" />
      )}
      <NextStepCard step="money_maths" />
    </ApplyShell>
  );
}
