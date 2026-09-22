'use client';

import type { components } from '@sm/contracts/client';
import { useTranslations } from 'next-intl';
import { useEffect, useRef, useState } from 'react';

import { Icon } from '@/components/icons';
import { Badge, Button, Card, cx, Notice, SandboxBadge } from '@/components/ui';
import { api, ApiError, unwrap } from '@/lib/api';
import { compressPhoto } from '@/lib/image';
import { useDraft } from '@/stores/draft';

type DocumentOut = components['schemas']['DocumentOut'];
type Required = { type: string; required: boolean; validity_months?: number };

const DIGILOCKER_TYPES = new Set(['caste_certificate', 'income_certificate', 'disability_certificate', 'marksheet']);

async function uploadBlob(applicationId: string, docType: string, blob: Blob, source: 'camera' | 'upload'): Promise<DocumentOut> {
  const form = new FormData();
  form.set('application_id', applicationId);
  form.set('doc_type', docType);
  form.set('source', source);
  form.set('file', blob, `${docType}.${blob.type === 'image/png' ? 'png' : 'jpg'}`);
  const res = await fetch('/api/v1/documents', { method: 'POST', body: form });
  const body = await res.json();
  if (!res.ok) throw new ApiError({ ...body, status: res.status, user_message_key: body.user_message_key ?? 'errors.generic' });
  return body as DocumentOut;
}

export function DocumentsPanel({
  applicationId,
  required,
  demoPersona,
  onChange,
}: {
  applicationId: string;
  required: Required[];
  demoPersona: string | null;
  onChange: () => void;
}) {
  const t = useTranslations();
  const draft = useDraft();
  const [results, setResults] = useState<Record<string, DocumentOut>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<{ type: string; key: string } | null>(null);
  const [digilockerFor, setDigilockerFor] = useState<string | null>(null);

  // Restore server-side document state when the page is reopened.
  useEffect(() => {
    unwrap(api.GET('/v1/applications/{application_id}', { params: { path: { application_id: applicationId } } }))
      .then((app) => setResults(Object.fromEntries(app.documents.map((d) => [d.type, d as DocumentOut]))))
      .catch(() => undefined);
  }, [applicationId]);

  async function run(docType: string, task: () => Promise<DocumentOut>) {
    setBusy(docType);
    setError(null);
    draft.setDocument(docType, { status: 'checking' });
    try {
      const out = await task();
      setResults((r) => ({ ...r, [docType]: out }));
      draft.setDocument(docType, { documentId: out.document_id, status: out.status as never, confidence: out.confidence, issues: out.issues });
      onChange();
    } catch (err) {
      setError({ type: docType, key: err instanceof ApiError ? err.problem.user_message_key : 'errors.generic' });
      draft.setDocument(docType, { status: 'failed' });
    } finally {
      setBusy(null);
    }
  }

  const fromFile = (docType: string, file: File, source: 'camera' | 'upload') =>
    run(docType, async () => uploadBlob(applicationId, docType, await compressPhoto(file), source));

  const fromDemo = (docType: string) =>
    run(docType, async () => {
      // Demo papers are uploaded untouched so the SANDBOX OCR can recognise them by hash.
      const res = await fetch(`/api/v1/demo/documents/${demoPersona}/${docType}`);
      if (!res.ok) throw new ApiError({ status: res.status, user_message_key: 'errors.not_found' });
      return uploadBlob(applicationId, docType, await res.blob(), 'upload');
    });

  const fromDigiLocker = (docType: string) =>
    run(docType, async () => {
      const { consent_token } = await unwrap(api.POST('/v1/documents/digilocker/consent', { body: { code: 'sandbox' } })) as { consent_token: string };
      return unwrap(
        api.POST('/v1/documents/digilocker/pull', { body: { application_id: applicationId, doc_type: docType, consent_token } }),
      ) as Promise<DocumentOut>;
    });

  return (
    <Card className="flex flex-col gap-3">
      <div>
        <h2 className="text-lg font-bold">{t('docs.title')}</h2>
        <p className="text-sm text-muted">{t('docs.subtitle')}</p>
      </div>
      <ul className="flex flex-col gap-3" role="list" data-testid="documents">
        {required.map((req) => (
          <DocumentRow
            key={req.type}
            req={req}
            result={results[req.type]}
            busy={busy === req.type}
            error={error?.type === req.type ? error.key : null}
            demoAvailable={!!demoPersona}
            onFile={(file, source) => fromFile(req.type, file, source)}
            onDemo={() => fromDemo(req.type)}
            onDigiLocker={() => setDigilockerFor(req.type)}
          />
        ))}
      </ul>
      {digilockerFor ? (
        <DigiLockerConsent
          docType={digilockerFor}
          onCancel={() => setDigilockerFor(null)}
          onAllow={() => {
            const type = digilockerFor;
            setDigilockerFor(null);
            void fromDigiLocker(type);
          }}
        />
      ) : null}
    </Card>
  );
}

function DocumentRow({
  req, result, busy, error, demoAvailable, onFile, onDemo, onDigiLocker,
}: {
  req: Required;
  result?: DocumentOut;
  busy: boolean;
  error: string | null;
  demoAvailable: boolean;
  onFile: (file: File, source: 'camera' | 'upload') => void;
  onDemo: () => void;
  onDigiLocker: () => void;
}) {
  const t = useTranslations();
  const camera = useRef<HTMLInputElement>(null);
  const gallery = useRef<HTMLInputElement>(null);
  const label = t(`docs.type.${req.type}` as never);
  const ok = result && result.status === 'ok';
  const needsFix = result && result.status !== 'ok';

  return (
    <li className={cx('rounded-lg border p-3', ok ? 'border-success/50' : needsFix ? 'border-warning' : 'border-border')} data-testid={`doc-${req.type}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-2 font-semibold">
          <Icon name={ok ? 'check' : 'doc'} size={20} className={ok ? 'text-success-ink' : 'text-muted'} />
          {label}
          {!req.required ? <span className="text-xs font-normal text-muted">({t('docs.optional')})</span> : null}
        </p>
        {result ? (
          <span className="flex items-center gap-1.5">
            {result.source === 'digilocker' ? <Badge tone="success" icon="shield">{t('docs.digilocker_fetched')}</Badge> : null}
            {ok ? <Badge tone="success">{result.verified ? t('docs.verified') : t('docs.uploaded')}</Badge> : null}
            {result.sandbox ? <SandboxBadge /> : null}
          </span>
        ) : null}
      </div>

      {needsFix ? (
        <div className="mt-2 flex flex-col gap-1 text-sm text-warning-ink" role="status">
          {(result.issues.length ? result.issues : ['docs.low_confidence']).map((issue) => (
            <p key={issue} className="flex items-center gap-1.5">
              <Icon name="alert" size={16} /> {t((issue.startsWith('docs.') ? issue : `docs.${issue}`) as never)}
            </p>
          ))}
        </div>
      ) : null}
      {req.type === 'aadhaar' && result ? <p className="mt-1 text-xs text-muted">{t('docs.aadhaar_masked')}</p> : null}
      {error ? <Notice tone="danger" icon="alert">{t(error as never)}</Notice> : null}

      <div className="mt-3 flex flex-wrap gap-2">
        <input ref={camera} type="file" accept="image/*" capture="environment" hidden onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0], 'camera')} />
        <input ref={gallery} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={(e) => e.target.files?.[0] && onFile(e.target.files[0], 'upload')} />
        <Button size="sm" icon="camera" loading={busy} onClick={() => camera.current?.click()} variant={ok ? 'secondary' : 'primary'}>
          {result ? t('docs.retake') : t('docs.capture')}
        </Button>
        <Button size="sm" variant="secondary" icon="upload" disabled={busy} onClick={() => gallery.current?.click()}>
          {t('docs.upload')}
        </Button>
        {(result?.suggest_digilocker || (!ok && DIGILOCKER_TYPES.has(req.type) && result)) ? (
          <Button size="sm" variant="success" icon="shield" disabled={busy} onClick={onDigiLocker} data-testid={`digilocker-${req.type}`}>
            {t('docs.fetch_digilocker')}
          </Button>
        ) : null}
        {demoAvailable && !ok ? (
          <Button size="sm" variant="ghost" icon="sparkle" disabled={busy} onClick={onDemo} data-testid={`demo-doc-${req.type}`}>
            {t('docs.use_demo')}
          </Button>
        ) : null}
      </div>
    </li>
  );
}

function DigiLockerConsent({ docType, onAllow, onCancel }: { docType: string; onAllow: () => void; onCancel: () => void }) {
  const t = useTranslations();
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
  }, []);
  return (
    <dialog ref={ref} onClose={onCancel} className="m-auto w-[min(26rem,calc(100vw-2rem))] rounded-xl border border-border bg-surface p-5 text-text backdrop:bg-black/40" aria-labelledby="dl-title">
      <div className="flex flex-col gap-3">
        <div className="flex items-center justify-between">
          <h2 id="dl-title" className="flex items-center gap-2 text-lg font-bold">
            <Icon name="shield" size={22} className="text-success-ink" /> DigiLocker
          </h2>
          <SandboxBadge />
        </div>
        <p>{t('docs.digilocker_consent', { doc: t(`docs.type.${docType}` as never) })}</p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" onClick={onCancel}>{t('common.cancel')}</Button>
          <Button variant="success" icon="check" onClick={onAllow} data-testid="digilocker-allow">{t('docs.allow')}</Button>
        </div>
      </div>
    </dialog>
  );
}
