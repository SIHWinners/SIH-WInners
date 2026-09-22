'use client';

import type { components } from '@sm/contracts/client';
import { buildSchedule } from '@sm/contracts/finance';
import { useLocale, useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { DocumentsPanel } from '@/components/apply/documents-panel';
import { ReadbackCard } from '@/components/apply/readback-card';
import { ApplyShell, NextStepCard } from '@/components/apply/shell';
import { Icon } from '@/components/icons';
import { Button, ButtonLink, Card, cx, Notice, Skeleton } from '@/components/ui';
import { api, ApiError, unwrap } from '@/lib/api';
import { formatPaise, localName, useMoneyWords } from '@/lib/format';
import { clientRole, demoPersonaFor } from '@/lib/session-client';
import { useDraft } from '@/stores/draft';

type Readiness = components['schemas']['ReadinessOut'];

export default function SendPage() {
  const t = useTranslations();
  const locale = useLocale();
  const router = useRouter();
  const draft = useDraft();
  const words = useMoneyWords();
  const [role, setRole] = useState<string | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [agreed, setAgreed] = useState(false);
  const [confirmedReadback, setConfirmedReadback] = useState(false);
  const [voiceEvidence, setVoiceEvidence] = useState<Record<string, unknown> | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => setRole(clientRole()), []);
  const result = draft.evaluation?.results.find((r) => r.code === draft.schemeCode) ?? null;
  const ready = draft.hydrated && result && draft.plan && draft.partner;

  // Save the draft on the server (idempotent on client_uuid) as soon as we can.
  useEffect(() => {
    if (!ready || !role) return;
    const s = useDraft.getState();
    unwrap(
      api.POST('/v1/applications', {
        body: {
          client_uuid: s.clientUuid,
          lang: locale,
          personal: { full_name: s.personal.full_name, father_name: s.personal.father_name, phone: s.personal.phone },
          facts: s.facts as never,
          scheme_code: s.schemeCode!,
          plan: s.plan!,
          partner_id: s.partner!.id,
          submitted_via: role === 'csc_operator' ? 'csc' : 'pwa',
        },
      }),
    )
      .then((app) => {
        s.setApplication(app.id, app.tracking_id);
        if (!['draft', 'ready'].includes(app.status)) router.replace(`/track/${app.tracking_id}`);
      })
      .catch((err) => setSyncError(err instanceof ApiError ? err.problem.user_message_key : 'errors.generic'));
  }, [ready, role, locale, router]);

  const refreshReadiness = useCallback(() => {
    const id = useDraft.getState().applicationId;
    if (!id) return;
    unwrap(api.POST('/v1/applications/{application_id}/readiness', { params: { path: { application_id: id } } }))
      .then(setReadiness)
      .catch(() => undefined);
  }, []);
  useEffect(refreshReadiness, [draft.applicationId, refreshReadiness]);

  const summary = useMemo(() => {
    if (!result || !draft.plan || !draft.partner) return '';
    return t('send.readback_summary', {
      name: draft.personal.full_name ?? '—',
      scheme: localName(result.name, locale),
      amount: words(draft.plan.principal_paise),
      emi: words(buildSchedule(draft.plan).instalment_paise),
      tenure: draft.plan.tenure_months,
      moratorium: draft.plan.moratorium_months,
      partner: draft.partner.name.replace(' (demo)', ''),
    });
  }, [result, draft.plan, draft.partner, draft.personal.full_name, locale, t, words]);

  async function submit() {
    const id = draft.applicationId;
    if (!id) return;
    setSubmitting(true);
    setSubmitError(null);
    try {
      await unwrap(
        api.POST('/v1/applications/{application_id}/consent', {
          params: { path: { application_id: id } },
          body: {
            method: voiceEvidence ? 'voice' : 'otp',
            language: locale,
            evidence: { otp_verified: true, readback_text: summary, ...(voiceEvidence ?? {}) },
          },
        }),
      );
      const out = await unwrap(api.POST('/v1/applications/{application_id}/submit', { params: { path: { application_id: id } } }));
      draft.setApplication(id, out.tracking_id);
      router.push('/apply/done');
    } catch (err) {
      setSubmitError(err instanceof ApiError ? err.problem.user_message_key : 'errors.generic');
      refreshReadiness();
    } finally {
      setSubmitting(false);
    }
  }

  if (!draft.hydrated) {
    return (
      <ApplyShell step="send_track" reachable={4}>
        <Skeleton className="h-64" />
      </ApplyShell>
    );
  }
  if (!ready) {
    return (
      <ApplyShell step="send_track" reachable={3}>
        <Notice tone="warning">{t('next_card.partner_pick')}</Notice>
        <ButtonLink href="/apply/partner">{t('steps.partner_pick')}</ButtonLink>
      </ApplyShell>
    );
  }

  const signedIn = role === 'citizen' || role === 'csc_operator' || role === 'admin';
  const canSubmit = signedIn && readiness?.ready && agreed && confirmedReadback;

  return (
    <ApplyShell
      step="send_track"
      reachable={4}
      footer={
        signedIn ? (
          <Button size="lg" block icon="send" loading={submitting} disabled={!canSubmit} onClick={submit} data-testid="submit-application">
            {submitting ? t('send.submitting') : t('send.submit')}
          </Button>
        ) : undefined
      }
    >
      <h1 className="text-2xl font-bold">{t('send.review_title')}</h1>

      {!signedIn ? (
        <Card className="flex flex-col gap-3">
          <p className="flex items-start gap-2">
            <Icon name="lock" size={20} className="mt-0.5 shrink-0" /> {t('send.sign_in_needed')}
          </p>
          <ButtonLink href={`/login?next=/apply/send${draft.personal.phone ? `&phone=${draft.personal.phone}` : ''}`} size="lg" icon="message">
            {t('auth.send_otp')}
          </ButtonLink>
        </Card>
      ) : null}

      {syncError ? <Notice tone="danger">{t(syncError as never)}</Notice> : null}

      {signedIn && draft.applicationId ? (
        <>
          <DocumentsPanel
            applicationId={draft.applicationId}
            required={result.documents_required as never}
            demoPersona={demoPersonaFor(draft.personal.phone)}
            onChange={refreshReadiness}
          />
          <ReadinessCard readiness={readiness} />
        </>
      ) : signedIn ? (
        <Skeleton className="h-40" />
      ) : null}

      <ReadbackCard
        applicationId={signedIn ? draft.applicationId : null}
        summary={summary}
        confirmed={confirmedReadback}
        onConfirmed={(evidence) => {
          setVoiceEvidence(evidence);
          setConfirmedReadback(true);
        }}
        onChange={() => router.push('/apply')}
      />

      <Card className="flex flex-col gap-3">
        <h2 className="text-lg font-bold">{t('send.consent_title')}</h2>
        <p>{t('send.consent_short')}</p>
        <details className="text-sm text-muted">
          <summary className="cursor-pointer font-semibold text-brand">{t('common.help')}</summary>
          <p className="mt-2">{t('send.consent_details')}</p>
        </details>
        <label className="sm-tap flex cursor-pointer items-center gap-3 rounded-lg border border-border-strong px-3">
          <input type="checkbox" className="size-6 accent-[var(--sm-brand)]" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} data-testid="consent-agree" />
          <span className="font-semibold">{t('send.consent_agree')}</span>
        </label>
        <p className="flex items-center gap-2 text-sm font-semibold text-success-ink">
          <Icon name="check" size={16} /> {t('common.free_service')}
        </p>
      </Card>

      {submitError ? <Notice tone="danger" icon="alert">{t(submitError as never)}</Notice> : null}
      <NextStepCard step="send_track" />
    </ApplyShell>
  );
}

function ReadinessCard({ readiness }: { readiness: Readiness | null }) {
  const t = useTranslations();
  if (!readiness) return <Skeleton className="h-28" />;
  const tone = readiness.ready ? 'success' : readiness.score >= 50 ? 'warning' : 'danger';
  const renderParams = (params: Record<string, unknown>) =>
    Object.fromEntries(
      Object.entries(params).map(([k, v]) => [
        k,
        k === 'doc' ? t(`docs.type.${String(v)}` as never) : k.endsWith('amount') || k === 'project_cost' ? formatPaise(Number(v)) : String(v),
      ]),
    );
  return (
    <Card className="flex flex-col gap-3" data-testid="readiness">
      <div className="flex items-center gap-4">
        <div
          className={cx('grid size-20 shrink-0 place-items-center rounded-full border-8 text-xl font-bold tabular',
            tone === 'success' ? 'border-success text-success-ink' : tone === 'warning' ? 'border-warning text-warning-ink' : 'border-danger text-danger-ink')}
          aria-hidden
        >
          {readiness.score}
        </div>
        <div>
          <h2 className="text-lg font-bold">{t('docs.readiness_title')}</h2>
          <p className="font-semibold">{t('docs.readiness_score', { score: readiness.score })}</p>
          <p className="text-sm text-muted">{readiness.ready ? t('docs.readiness_ok') : t('docs.readiness_block')}</p>
        </div>
      </div>
      {readiness.fixes.length ? (
        <ul className="flex flex-col gap-1.5" role="list">
          {readiness.fixes.map((fix, i) => (
            <li key={i} className="flex items-start gap-2 text-sm">
              <Icon name="alert" size={16} className="mt-0.5 shrink-0 text-warning-ink" />
              {t(fix.key as never, renderParams(fix.params as Record<string, unknown>) as never)}
            </li>
          ))}
        </ul>
      ) : null}
      {Object.entries(readiness.name_matches).map(([docType, match]) => {
        const m = match as { score: number; matched: boolean; reasons: string[]; document_name: string };
        return (
          <p key={docType} className="flex flex-wrap items-center gap-2 text-sm text-muted">
            <Icon name={m.matched ? 'check' : 'alert'} size={16} className={m.matched ? 'text-success-ink' : 'text-warning-ink'} />
            {t(`docs.type.${docType}` as never)}: {t('name_match.score', { score: Math.round(m.score * 100) })} ·{' '}
            {m.reasons.map((r) => t(`name_match.reason.${r}` as never)).join(', ')}
          </p>
        );
      })}
    </Card>
  );
}
