'use client';

import type { components } from '@sm/contracts/client';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

import { Icon } from '@/components/icons';
import { Badge, Button, Card, cx, Notice, SandboxBadge } from '@/components/ui';
import { api, ApiError, unwrap } from '@/lib/api';
import { formatPaise, useSentence } from '@/lib/format';

type Review = components['schemas']['ReviewOut'];
type Action = components['schemas']['DecisionIn']['action'];
type ReviewDocument = components['schemas']['ReviewDocument'];

const ACTION_ICON: Record<Action, 'check' | 'x' | 'doc' | 'eye' | 'rupee'> = {
  receive: 'check', start_review: 'eye', request_documents: 'doc', approve: 'check', reject: 'x', disburse: 'rupee',
};
const SHORTCUT: Record<string, Action> = { a: 'approve', r: 'reject', d: 'request_documents' };

/**
 * Split view: the papers on the left, what the rules and the citizen said on the right.
 * The decision bar only ever offers transitions the server allows for this officer (C21).
 */
export function ReviewWorkspace({ review: initial }: { review: Review }) {
  const t = useTranslations();
  const sentence = useSentence();
  const router = useRouter();
  const [review, setReview] = useState(initial);
  const [docIndex, setDocIndex] = useState(0);
  const [pending, setPending] = useState<Action | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);

  // The generated OpenAPI types model free-form JSON as unknown; narrow it once here.
  const applicant = review.applicant as Record<string, string | number | null>;
  const plan = review.finance.plan as Record<string, number>;
  const consent = review.consent as
    | { method: string; language: string; granted_at: string; evidence?: Record<string, unknown> }
    | null;
  const readiness = review.readiness as { ready: boolean; score: number; required_documents?: { type: string }[] };
  const scheme = review.scheme as { name_en: string; trace: { result: string; sentence: { key: string } }[] };
  const documents = review.documents;
  const doc: ReviewDocument | undefined = documents[Math.min(docIndex, documents.length - 1)];
  const app = review.application;

  const decide = useCallback(
    async (action: Action, extra: Partial<components['schemas']['DecisionIn']> = {}) => {
      setBusy(true);
      setError(null);
      try {
        const out = await unwrap(
          api.POST('/v1/partner/applications/{application_id}/decision', {
            params: { path: { application_id: app.id } },
            body: { action, ...extra },
          }),
        );
        setReview(out as Review);
        setPending(null);
        setDone(t('officer.actions.done'));
        router.refresh();
      } catch (err) {
        setError(err instanceof ApiError ? err.problem.user_message_key : 'errors.network');
      } finally {
        setBusy(false);
      }
    },
    [app.id, router, t],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (event.metaKey || event.ctrlKey || target?.matches('input, textarea, select')) return;
      const key = event.key.toLowerCase();
      if (key === 'j') setDocIndex((i) => Math.min(i + 1, documents.length - 1));
      if (key === 'k') setDocIndex((i) => Math.max(i - 1, 0));
      const action = SHORTCUT[key];
      if (action && review.allowed_actions.includes(action)) setPending(action);
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [documents.length, review.allowed_actions]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone="brand">{t(`track.status.${app.status}` as never)}</Badge>
        <Badge tone={review.integrity.unchanged_since_submit ? 'success' : 'warning'} icon="shield" data-testid="review-integrity">
          {review.integrity.unchanged_since_submit ? t('officer.review.hash_ok') : t('officer.review.hash_changed')}
        </Badge>
        <Badge tone={readiness.ready ? 'success' : 'warning'}>
          {t('officer.review.readiness', { score: readiness.score })}
        </Badge>
        {review.sanction_letter_url ? (
          <a
            href={review.sanction_letter_url}
            target="_blank"
            rel="noreferrer"
            className="sm-tap inline-flex items-center gap-1.5 rounded-md border border-border-strong px-3 text-sm font-semibold text-brand hover:bg-brand-tint"
          >
            <Icon name="download" size={16} /> {t('officer.review.letter')}
          </a>
        ) : null}
        <p className="ms-auto hidden text-xs text-muted lg:block">{t('officer.review.shortcuts')}</p>
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
        <Card className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-lg font-bold">{t('officer.review.documents')}</h2>
            <div className="ms-auto flex gap-1">
              <Button size="sm" variant="ghost" icon="chevronLeft" onClick={() => setDocIndex((i) => Math.max(i - 1, 0))} aria-label="K" />
              <Button size="sm" variant="ghost" icon="chevronRight" onClick={() => setDocIndex((i) => Math.min(i + 1, documents.length - 1))} aria-label="J" />
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5" role="tablist" aria-label={t('officer.review.documents')}>
            {documents.map((d, i) => (
              <button
                key={d.document_id}
                role="tab"
                aria-selected={i === docIndex}
                onClick={() => setDocIndex(i)}
                className={cx('sm-tap rounded-full border px-3 text-xs font-semibold',
                  i === docIndex ? 'border-brand bg-brand text-on-brand' : 'border-border-strong text-muted hover:bg-brand-tint')}
                data-testid={`review-doc-tab-${d.type}`}
              >
                {t(`docs.type.${d.type}` as never)} {d.verified ? '✓' : ''}
              </button>
            ))}
          </div>
          {doc ? (
            <div className="flex flex-col gap-3" data-testid="review-document">
              <div className="grid place-items-center rounded-lg border border-border bg-surface-alt p-2">
                {doc.has_image ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={`/api/v1/documents/${doc.document_id}/image`} alt={t(`docs.type.${doc.type}` as never)} className="max-h-[52vh] w-auto rounded" />
                ) : (
                  <p className="p-8 text-muted">{t('officer.review.no_image')}</p>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <Badge tone={doc.verified ? 'success' : doc.status === 'ok' ? 'neutral' : 'warning'}>
                  {doc.source} · {Math.round(doc.confidence * 100)}%
                </Badge>
                {doc.sandbox ? <SandboxBadge label="SANDBOX OCR" /> : null}
                {doc.name_match ? (
                  <Badge tone={doc.name_match.matched ? 'success' : 'warning'}>
                    {t('officer.review.name_match', { score: Math.round((doc.name_match.score as number) * 100) })}
                  </Badge>
                ) : null}
              </div>
              <div>
                <h3 className="text-sm font-bold text-muted">{t('officer.review.fields')}</h3>
                <dl className="mt-1 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                  {Object.entries(doc.fields).map(([key, value]) => (
                    <div key={key} className="contents">
                      <dt className="text-muted">{key}</dt>
                      <dd className="font-semibold">{String(value)}</dd>
                    </div>
                  ))}
                </dl>
              </div>
            </div>
          ) : null}
        </Card>

        <div className="flex flex-col gap-4">
          <Card className="flex flex-col gap-2">
            <h2 className="text-lg font-bold">{t('officer.review.applicant')}</h2>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <Row label={t('intake.name')} value={applicant.full_name} />
              <Row label={t('intake.age')} value={applicant.age} />
              <Row label={t('intake.gender')} value={applicant.gender_label} />
              <Row label={t('intake.social_category')} value={applicant.category_label} />
              <Row label={t('intake.district')} value={applicant.district} />
              <Row label={t('intake.annual_income')} value={applicant.income_paise ? formatPaise(Number(applicant.income_paise)) : '—'} />
              <Row label={t('intake.education')} value={applicant.education_label} />
              <Row label={t('intake.phone')} value={applicant.phone_masked} />
            </dl>
          </Card>

          <Card className="flex flex-col gap-2">
            <h2 className="text-lg font-bold">{t('officer.review.eligibility')}</h2>
            <p className="text-sm font-semibold">{scheme.name_en}</p>
            <ul className="flex flex-col gap-1 text-sm" role="list">
              {scheme.trace.map((row, i) => (
                <li key={i} className="flex items-start gap-2">
                  <Icon name={row.result === 'pass' ? 'check' : row.result === 'fail' ? 'x' : 'alert'} size={15}
                    className={cx('mt-0.5 shrink-0', row.result === 'pass' ? 'text-success-ink' : row.result === 'fail' ? 'text-danger-ink' : 'text-warning-ink')} />
                  <span className="text-muted">{sentence(row.sentence)}</span>
                </li>
              ))}
            </ul>
            <p className="text-xs text-muted">{t('rules.rule_based_note')}</p>
          </Card>

          <Card className="flex flex-col gap-2">
            <h2 className="text-lg font-bold">{t('officer.review.money')}</h2>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <Row label={t('money.amount')} value={formatPaise(plan.principal_paise!)} />
              <Row label={t('money.rate')} value={`${plan.rate_bps! / 100}%`} />
              <Row label={t('money.tenure')} value={t('common.months', { count: plan.tenure_months! })} />
              <Row label={t('money.emi')} value={formatPaise(plan.emi_paise!)} />
            </dl>
          </Card>

          <Card className="flex flex-col gap-2">
            <h2 className="text-lg font-bold">{t('officer.review.consent')}</h2>
            {consent ? (
              <div className="text-sm text-muted">
                <p>{consent.method} · {consent.language} · {consent.granted_at}</p>
                {consent.evidence?.voice_confirmation ? (
                  <p className="mt-1 font-semibold text-text">
                    {t('officer.review.consent_voice')}: “{String(consent.evidence.voice_confirmation)}”
                  </p>
                ) : null}
              </div>
            ) : (
              <p className="text-sm text-muted">—</p>
            )}
          </Card>

          <Card className="flex flex-col gap-2">
            <h2 className="text-lg font-bold">{t('officer.review.audit')}</h2>
            <ol className="flex flex-col gap-1 text-xs text-muted" role="list" data-testid="review-audit">
              {review.audit.map((entry, i) => (
                <li key={i} className="flex flex-wrap gap-2">
                  <span className="tabular">{entry.at.replace('T', ' ')}</span>
                  <span className="font-semibold text-text">{entry.action}</span>
                  <span>{entry.actor_role}</span>
                  <span className="font-mono">{entry.hash}</span>
                </li>
              ))}
            </ol>
          </Card>
        </div>
      </div>

      <Card className="sticky bottom-0 flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-bold">{t('officer.actions.title')}</h2>
          <p className="text-xs text-muted">{t('officer.review.lender_only_note')}</p>
        </div>
        {review.allowed_actions.length === 0 ? (
          <p className="text-sm text-muted">{t('officer.actions.none')}</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {review.allowed_actions.map((action) => (
              <Button
                key={action}
                icon={ACTION_ICON[action]}
                variant={action === 'approve' ? 'success' : action === 'reject' ? 'danger' : 'secondary'}
                onClick={() => setPending(action)}
                data-testid={`action-${action}`}
              >
                {t(`officer.actions.${action}`)}
              </Button>
            ))}
          </div>
        )}
        {pending ? (
          <DecisionForm
            action={pending}
            review={review}
            busy={busy}
            onCancel={() => setPending(null)}
            onSubmit={(extra) => void decide(pending, extra)}
          />
        ) : null}
        {error ? <Notice tone="danger" icon="alert">{t(error as never)}</Notice> : null}
        {done && !pending ? <p className="text-sm font-semibold text-success-ink" role="status" data-testid="decision-done">{done}</p> : null}
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="contents">
      <dt className="text-muted">{label}</dt>
      <dd className="font-semibold">{value == null || value === '' ? '—' : String(value)}</dd>
    </div>
  );
}

function DecisionForm({
  action,
  review,
  busy,
  onCancel,
  onSubmit,
}: {
  action: Action;
  review: Review;
  busy: boolean;
  onCancel: () => void;
  onSubmit: (extra: Partial<components['schemas']['DecisionIn']>) => void;
}) {
  const t = useTranslations();
  const plan = review.finance.plan as Record<string, number>;
  const [reason, setReason] = useState(review.reject_reasons[0] ?? 'other');
  const [note, setNote] = useState('');
  const [docs, setDocs] = useState<string[]>([]);
  const [amount, setAmount] = useState(Math.round((plan.principal_paise ?? 0) / 100));
  const [rate, setRate] = useState((plan.rate_bps ?? 0) / 100);
  const [tenure, setTenure] = useState(plan.tenure_months ?? 36);
  const [moratorium, setMoratorium] = useState(plan.moratorium_months ?? 0);
  const requestable = (review.readiness as { required_documents?: { type: string }[] }).required_documents?.map((d) => d.type)
    ?? review.documents.map((d) => d.type);

  return (
    <form
      className="flex flex-col gap-3 rounded-lg border border-border-strong p-3"
      data-testid="decision-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(
          action === 'reject'
            ? { reason_code: reason, note: note || undefined }
            : action === 'request_documents'
              ? { documents: docs, note: note || undefined }
              : action === 'approve'
                ? {
                    note: note || undefined,
                    sanction: { amount_paise: Math.round(amount * 100), rate_bps: Math.round(rate * 100), tenure_months: tenure, moratorium_months: moratorium },
                  }
                : { note: note || undefined },
        );
      }}
    >
      <p className="font-semibold">{t(`officer.actions.${action}`)}</p>

      {action === 'reject' ? (
        <label className="flex flex-col gap-1 text-sm">
          {t('officer.actions.reason')}
          <select value={reason} onChange={(e) => setReason(e.target.value)} className="sm-tap rounded-md border border-border-strong bg-surface px-2" data-testid="reject-reason">
            {review.reject_reasons.map((code) => (
              <option key={code} value={code}>{t(`reject_reason.${code}` as never)}</option>
            ))}
          </select>
        </label>
      ) : null}

      {action === 'request_documents' ? (
        <fieldset className="flex flex-col gap-1.5 text-sm">
          <legend className="mb-1">{t('officer.actions.which_documents')}</legend>
          <div className="flex flex-wrap gap-2">
            {requestable.map((type) => (
              <label key={type} className="sm-tap flex items-center gap-2 rounded-md border border-border-strong px-2">
                <input
                  type="checkbox"
                  className="size-4"
                  checked={docs.includes(type)}
                  onChange={(e) => setDocs((prev) => (e.target.checked ? [...prev, type] : prev.filter((d) => d !== type)))}
                  data-testid={`request-doc-${type}`}
                />
                {t(`docs.type.${type}` as never)}
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}

      {action === 'approve' ? (
        <div className="grid gap-2 sm:grid-cols-2">
          <NumberField label={t('officer.actions.sanction_amount')} value={amount} onChange={setAmount} testId="sanction-amount" step={100} />
          <NumberField label={t('officer.actions.rate')} value={rate} onChange={setRate} testId="sanction-rate" step={0.25} />
          <NumberField label={t('officer.actions.tenure')} value={tenure} onChange={setTenure} testId="sanction-tenure" step={1} />
          <NumberField label={t('officer.actions.moratorium')} value={moratorium} onChange={setMoratorium} testId="sanction-moratorium" step={1} />
        </div>
      ) : null}

      <label className="flex flex-col gap-1 text-sm">
        {t('officer.actions.note')}
        <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} className="sm-tap rounded-md border border-border-strong bg-surface px-2" data-testid="decision-note" />
      </label>

      <div className="flex gap-2">
        <Button type="submit" loading={busy} disabled={action === 'request_documents' && docs.length === 0} data-testid="decision-confirm">
          {t('officer.actions.confirm')}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>{t('officer.actions.cancel')}</Button>
      </div>
    </form>
  );
}

function NumberField({ label, value, onChange, testId, step }: { label: string; value: number; onChange: (v: number) => void; testId: string; step: number }) {
  return (
    <label className="flex flex-col gap-1 text-sm">
      {label}
      <input
        type="number"
        inputMode="decimal"
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="sm-tap rounded-md border border-border-strong bg-surface px-2 tabular"
        data-testid={testId}
      />
    </label>
  );
}
