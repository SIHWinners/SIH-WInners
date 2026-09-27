'use client';

import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useState } from 'react';

import { Icon } from '@/components/icons';
import { Button, Card, Notice } from '@/components/ui';
import { useDraft } from '@/stores/draft';

const STEPS = ['sit', 'explain', 'consent', 'phone'] as const;

/**
 * Starting a new applicant at a CSC counter. The previous applicant's answers are cleared
 * first — a shared counter must never carry one person's details into the next person's file
 * (claim C12) — and the operator confirms the spoken consent script before starting.
 */
export function NewApplicant() {
  const t = useTranslations();
  const router = useRouter();
  const reset = useDraft((s) => s.reset);
  const [done, setDone] = useState<string[]>([]);

  const ready = STEPS.every((step) => done.includes(step));

  return (
    <div className="flex max-w-2xl flex-col gap-4">
      <Notice tone="warning" icon="info">{t('officer.csc.assisted_note')}</Notice>
      <Card className="flex flex-col gap-3">
        <h2 className="text-lg font-bold">{t('officer.csc.checklist')}</h2>
        <ul className="flex flex-col gap-2" role="list">
          {STEPS.map((step) => (
            <li key={step}>
              <label className="sm-tap flex cursor-pointer items-center gap-3 rounded-lg border border-border-strong px-3">
                <input
                  type="checkbox"
                  className="size-5"
                  checked={done.includes(step)}
                  onChange={(e) => setDone((prev) => (e.target.checked ? [...prev, step] : prev.filter((s) => s !== step)))}
                  data-testid={`csc-check-${step}`}
                />
                <span>{t(`officer.csc.check_${step}` as never)}</span>
              </label>
            </li>
          ))}
        </ul>
      </Card>
      <Button
        size="lg"
        icon="user"
        disabled={!ready}
        data-testid="csc-start-applicant"
        onClick={() => {
          reset(); // a fresh file: nothing from the last person at this counter carries over
          router.push('/apply');
        }}
      >
        {t('officer.csc.start')} <Icon name="chevronRight" size={20} />
      </Button>
    </div>
  );
}
