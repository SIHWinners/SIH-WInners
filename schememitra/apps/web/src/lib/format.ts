'use client';

import { amountInWords, formatPaise, unitWordsFrom, type Messages } from '@sm/i18n';
import { useMessages, useTranslations } from 'next-intl';
import { useCallback } from 'react';

type Typed = { type: string; value?: unknown };
type SentenceRef = { key: string; params?: Record<string, Typed> };

const FIELD_QUESTION: Record<string, string> = {
  annual_family_income_paise: 'intake.annual_income',
  project_cost_paise: 'intake.project_cost',
  loan_needed_paise: 'intake.loan_needed',
  social_category: 'intake.social_category',
  disability_pct: 'intake.disability_pct',
  shg_member: 'intake.shg_member',
  course_admitted: 'intake.course_admitted',
  state_code: 'intake.state',
  gender: 'intake.gender',
  age: 'intake.age',
};

/** Renders engine sentences ({key, typed params}) in the active language. */
export function useSentence() {
  const t = useTranslations();
  return useCallback(
    (ref: SentenceRef | null | undefined): string => {
      if (!ref) return '';
      const params: Record<string, string> = {};
      for (const [name, p] of Object.entries(ref.params ?? {})) params[name] = renderValue(p, t);
      return t(ref.key as never, params as never);
    },
    [t],
  );
}

function renderValue(p: Typed, t: ReturnType<typeof useTranslations>): string {
  const v = p.value;
  switch (p.type) {
    case 'money':
      return typeof v === 'number' ? formatPaise(v) : '—';
    case 'category':
      return t(`options.social_category.${String(v)}` as never);
    case 'categories':
      return (Array.isArray(v) ? v : []).map((c) => t(`options.social_category.${String(c)}` as never)).join(', ');
    case 'field':
      return t((FIELD_QUESTION[String(v)] ?? 'common.not_answered') as never);
    default:
      return v === null || v === undefined ? '—' : String(v);
  }
}

export function useMoneyWords() {
  const messages = useMessages() as Messages;
  return useCallback((paise: number) => amountInWords(paise, unitWordsFrom(messages)), [messages]);
}

export function localName(name: Record<string, string>, locale: string): string {
  return name[locale] ?? name.en ?? Object.values(name)[0] ?? '';
}

export const pct = (bps: number) => `${(bps / 100).toLocaleString('en-IN', { maximumFractionDigits: 2 })}%`;
export { formatPaise };
