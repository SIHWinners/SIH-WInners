'use client';

import { encodeApply, type SmsFacts } from '@sm/contracts/sms';
import { useLocale, useTranslations } from 'next-intl';
import { useMemo } from 'react';

import { Icon } from '@/components/icons';
import { Card } from '@/components/ui';
import { useDraft } from '@/stores/draft';

const SHORTCODE = process.env.NEXT_PUBLIC_SMS_SHORTCODE ?? '9000000000';

/**
 * No data connection and none coming (claim C13). The answers already on the phone are packed
 * into the SMS wire format and handed to the phone's own messaging app, so the citizen sends
 * them over the GSM network for the price of one SMS. Papers and consent follow later, from
 * the app or a CSC — an SMS never submits an application on its own.
 */
export function SmsFallback() {
  const t = useTranslations();
  const locale = useLocale();
  const draft = useDraft();

  const parts = useMemo(() => {
    const f = draft.facts;
    const facts: SmsFacts = {
      full_name: draft.personal.full_name,
      age: f.age ?? undefined,
      gender: f.gender ?? undefined,
      social_category: f.social_category ?? undefined,
      state_code: f.state_code ?? undefined,
      district_code: f.district_code ?? undefined,
      pincode: f.pincode ?? undefined,
      annual_family_income_rupees: f.annual_family_income_paise ? Math.round(f.annual_family_income_paise / 100) : undefined,
      education_level: f.education_level ?? undefined,
      business_type: f.business_type ?? undefined,
      project_cost_rupees: f.project_cost_paise ? Math.round(f.project_cost_paise / 100) : undefined,
      loan_needed_rupees: f.loan_needed_paise ? Math.round(f.loan_needed_paise / 100) : undefined,
      shg_member: f.shg_member ?? undefined,
      existing_loans: f.existing_loans ?? undefined,
      has_disability: f.has_disability ?? undefined,
      phone: draft.personal.phone,
      lang: locale,
    };
    try {
      return encodeApply(facts);
    } catch {
      return [];
    }
  }, [draft.facts, draft.personal.full_name, draft.personal.phone, locale]);

  if (parts.length === 0) return null;
  const href = `sms:${SHORTCODE}?body=${encodeURIComponent(parts.join('\n'))}`;

  return (
    <Card className="flex flex-col gap-3 border-warning" data-testid="sms-fallback">
      <h2 className="flex items-center gap-2 text-lg font-bold">
        <Icon name="message" size={20} /> {t('offline.send_by_sms')}
      </h2>
      <p className="text-muted">{t('offline.sms_explain', { parts: parts.length })}</p>
      <a
        href={href}
        className="sm-tap inline-flex min-h-14 items-center justify-center gap-2 rounded-lg bg-brand px-6 text-lg font-semibold text-on-brand"
        data-testid="sms-fallback-send"
      >
        <Icon name="send" size={22} /> {t('offline.send_by_sms')}
      </a>
      <p className="text-sm text-muted">{t('offline.sms_sent_wait')}</p>
      <details className="text-xs text-muted">
        <summary className="cursor-pointer font-semibold text-brand">{t('common.help')}</summary>
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap break-all font-mono" data-testid="sms-fallback-body">
          {parts.join('\n')}
        </pre>
      </details>
    </Card>
  );
}
