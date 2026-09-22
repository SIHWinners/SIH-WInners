'use client';

import { groupIndian } from '@sm/i18n';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useEffect, useMemo, useRef, useState } from 'react';

import { Icon } from '@/components/icons';
import { Button, Card, cx, Notice, Skeleton } from '@/components/ui';
import { api, ApiError, unwrap } from '@/lib/api';
import { evaluateFacts } from '@/lib/evaluate';
import { useMoneyWords } from '@/lib/format';
import { useDraft } from '@/stores/draft';

import { answerOf, isAnswered, visibleQuestions, type Question } from './questions';
import { ApplyShell, ListenButton, NextStepCard } from './shell';

interface District {
  code: string;
  name: string;
  state_code: string;
  lat: number;
  lng: number;
  pincode: string;
}

export function IntakeFlow() {
  const t = useTranslations();
  const router = useRouter();
  const draft = useDraft();
  const questions = useMemo(() => visibleQuestions(draft.facts), [draft.facts]);
  const index = Math.min(draft.intakeIndex, questions.length - 1);
  const q = questions[index]!;
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const filled = questions.filter((x) => isAnswered(x, draft.facts, draft.personal)).length;

  useEffect(() => {
    headingRef.current?.focus();
  }, [index]);

  if (!draft.hydrated) {
    return (
      <ApplyShell step="speak_scan" reachable={0}>
        <Skeleton className="h-40" />
      </ApplyShell>
    );
  }

  const answered = isAnswered(q, draft.facts, draft.personal);

  async function next() {
    if (!answered && !q.optional) {
      setError('common.required');
      return;
    }
    setError(null);
    if (index < questions.length - 1) {
      draft.setIntakeIndex(index + 1);
      return;
    }
    setBusy(true);
    try {
      draft.setEvaluation(await evaluateFacts(useDraft.getState().facts));
      router.push('/apply/rules');
    } catch (err) {
      setError(err instanceof ApiError ? err.problem.user_message_key : 'errors.generic');
    } finally {
      setBusy(false);
    }
  }

  const label = t(q.labelKey as never);
  return (
    <ApplyShell
      step="speak_scan"
      reachable={draft.evaluation ? 4 : 0}
      footer={
        <>
          <Button variant="secondary" size="lg" icon="chevronLeft" disabled={index === 0} onClick={() => draft.setIntakeIndex(index - 1)}>
            <span className="sr-only sm:not-sr-only">{t('common.back')}</span>
          </Button>
          <Button size="lg" block iconRight="chevronRight" loading={busy} onClick={next} data-testid="intake-next">
            {q.optional && !answered ? t('common.skip') : t('common.continue')}
          </Button>
        </>
      }
    >
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted">{t('intake.fields_filled', { filled, total: questions.length })}</p>
        <Button variant="ghost" size="sm" icon="mic" onClick={() => router.push('/apply/voice')}>
          {t('home.start_voice')}
        </Button>
      </div>

      <Card className="sm-enter flex flex-col gap-5" key={q.id}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 ref={headingRef} tabIndex={-1} className="text-2xl font-bold leading-snug outline-none" id={`q-${q.id}`}>
              {label}
            </h1>
            {q.hintKey ? <p className="mt-1 text-muted">{t(q.hintKey as never)}</p> : null}
          </div>
          <ListenButton text={q.hintKey ? `${label} ${t(q.hintKey as never)}` : label} />
        </div>
        <QuestionInput q={q} onSubmit={next} />
        {error ? (
          <Notice tone="danger" icon="alert">
            {t(error as never)}
          </Notice>
        ) : null}
      </Card>

      <NextStepCard step="speak_scan" />
    </ApplyShell>
  );
}

function QuestionInput({ q, onSubmit }: { q: Question; onSubmit: () => void }) {
  const t = useTranslations();
  const draft = useDraft();
  const value = answerOf(q, draft.facts, draft.personal);

  const set = (v: unknown) => {
    if (q.target.scope === 'personal') draft.setPersonal({ [q.target.key]: v as string });
    else draft.setFact(q.target.key, v as never);
  };
  const submitOnEnter = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      onSubmit();
    }
  };
  const inputClass =
    'h-14 w-full rounded-lg border border-border-strong bg-surface px-4 text-xl outline-none focus:border-brand';

  switch (q.kind) {
    case 'choice':
    case 'yesno': {
      const options = q.kind === 'yesno' ? ['yes', 'no'] : [...(q.options ?? [])];
      const current = q.kind === 'yesno' ? (value === true ? 'yes' : value === false ? 'no' : undefined) : value;
      return (
        <div role="radiogroup" aria-labelledby={`q-${q.id}`} className="grid gap-2 sm:grid-cols-2">
          {options.map((opt) => {
            const selected = current === opt;
            return (
              <button
                key={opt}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => set(q.kind === 'yesno' ? opt === 'yes' : opt)}
                className={cx(
                  'sm-tap flex min-h-14 items-center justify-between gap-3 rounded-lg border px-4 text-start text-lg font-semibold transition-colors',
                  selected ? 'border-brand bg-brand-tint text-brand-ink' : 'border-border-strong hover:border-brand',
                )}
              >
                {q.kind === 'yesno' ? t(`common.${opt}` as never) : t(`${q.optionPrefix}.${opt}` as never)}
                {selected ? <Icon name="check" size={22} /> : null}
              </button>
            );
          })}
        </div>
      );
    }
    case 'money':
      return <MoneyInput id={q.id} value={value as number | undefined} onChange={set} onEnter={submitOnEnter} />;
    case 'number':
      return (
        <input
          aria-labelledby={`q-${q.id}`}
          className={cx(inputClass, 'tabular')}
          inputMode="numeric"
          value={value === undefined || value === null ? '' : String(value)}
          onChange={(e) => {
            const digits = e.target.value.replace(/\D/g, '').slice(0, 3);
            set(digits === '' ? undefined : Math.min(Number(digits), q.max ?? 999));
          }}
          onKeyDown={submitOnEnter}
          autoFocus
        />
      );
    case 'pincode':
      return (
        <input
          aria-labelledby={`q-${q.id}`}
          className={cx(inputClass, 'tabular tracking-widest')}
          inputMode="numeric"
          maxLength={6}
          value={(value as string) ?? ''}
          onChange={(e) => set(e.target.value.replace(/\D/g, '').slice(0, 6) || undefined)}
          onKeyDown={submitOnEnter}
          autoFocus
        />
      );
    case 'tel':
      return (
        <div className="flex items-center gap-2">
          <span className="text-xl text-muted">+91</span>
          <input
            aria-labelledby={`q-${q.id}`}
            className={cx(inputClass, 'tabular')}
            inputMode="tel"
            autoComplete="tel-national"
            maxLength={10}
            value={(value as string) ?? ''}
            onChange={(e) => set(e.target.value.replace(/\D/g, '').slice(0, 10) || undefined)}
            onKeyDown={submitOnEnter}
          />
        </div>
      );
    case 'district':
      return <DistrictPicker questionId={q.id} />;
    default:
      return (
        <input
          aria-labelledby={`q-${q.id}`}
          className={inputClass}
          value={(value as string) ?? ''}
          maxLength={120}
          autoComplete="name"
          onChange={(e) => set(e.target.value || undefined)}
          onKeyDown={submitOnEnter}
          autoFocus
        />
      );
  }
}

function MoneyInput({ id, value, onChange, onEnter }: { id: string; value: number | undefined; onChange: (v: number | undefined) => void; onEnter: (e: React.KeyboardEvent) => void }) {
  const t = useTranslations('intake');
  const words = useMoneyWords();
  const rupees = value === undefined ? '' : groupIndian(Math.floor(value / 100));
  return (
    <div className="flex flex-col gap-2">
      <div className="flex h-14 items-center gap-2 rounded-lg border border-border-strong bg-surface px-4 focus-within:border-brand">
        <span className="text-2xl text-muted" aria-hidden>
          ₹
        </span>
        <input
          aria-labelledby={`q-${id}`}
          className="tabular h-full w-full bg-transparent text-2xl font-semibold outline-none"
          inputMode="numeric"
          value={rupees}
          onChange={(e) => {
            const digits = e.target.value.replace(/\D/g, '').slice(0, 9);
            onChange(digits === '' ? undefined : Number(digits) * 100);
          }}
          onKeyDown={onEnter}
          autoFocus
        />
      </div>
      {value ? (
        <p className="text-lg font-semibold text-brand-ink" aria-live="polite">
          {t('amount_in_words', { words: words(value) })}
        </p>
      ) : null}
    </div>
  );
}

function DistrictPicker({ questionId }: { questionId: string }) {
  const t = useTranslations();
  const draft = useDraft();
  const state = draft.facts.state_code;
  const [districts, setDistricts] = useState<District[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const cacheKey = `districts-${state ?? 'all'}`;
      const { db } = await import('@/lib/local-db');
      const cached = await db.kv.get(cacheKey);
      if (cached && !cancelled) setDistricts(JSON.parse(cached.value));
      try {
        const data = (await unwrap(api.GET('/v1/geo/districts', { params: { query: { state: state ?? undefined } } }))) as District[];
        if (cancelled) return;
        setDistricts(data);
        await db.kv.put({ key: cacheKey, value: JSON.stringify(data), updatedAt: Date.now() });
      } catch {
        if (!cached && !cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [state]);

  if (!districts) return failed ? <Notice tone="warning">{t('errors.offline')}</Notice> : <Skeleton className="h-28" />;
  return (
    <div role="radiogroup" aria-labelledby={`q-${questionId}`} className="grid gap-2 sm:grid-cols-2">
      {districts.map((d) => {
        const selected = draft.facts.district_code === d.code;
        return (
          <button
            key={d.code}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() =>
              draft.setFacts({ district_code: d.code, lat: d.lat, lng: d.lng, pincode: draft.facts.pincode ?? d.pincode })
            }
            className={cx(
              'sm-tap flex min-h-12 items-center justify-between rounded-lg border px-4 text-start font-semibold',
              selected ? 'border-brand bg-brand-tint text-brand-ink' : 'border-border-strong hover:border-brand',
            )}
            lang="en"
          >
            {d.name}
            {selected ? <Icon name="check" size={20} /> : null}
          </button>
        );
      })}
    </div>
  );
}
