'use client';

import { useTranslations } from 'next-intl';
import { useEffect } from 'react';

import { ApplyShell, NextStepCard } from '@/components/apply/shell';
import { Icon } from '@/components/icons';
import { ButtonLink, Card, Skeleton } from '@/components/ui';
import { useDraft } from '@/stores/draft';

export default function DonePage() {
  const t = useTranslations();
  const draft = useDraft();

  // The draft has done its job; keep the tracking ID, clear the answers from this shared phone.
  useEffect(() => {
    if (draft.hydrated && draft.trackingId) {
      const { trackingId, applicationId } = draft;
      try {
        localStorage.setItem('sm_last_tracking', JSON.stringify({ trackingId, applicationId }));
      } catch {
        /* private mode */
      }
    }
  }, [draft]);

  if (!draft.hydrated) {
    return (
      <ApplyShell step="send_track" reachable={4}>
        <Skeleton className="h-64" />
      </ApplyShell>
    );
  }

  const tid = draft.trackingId;
  return (
    <ApplyShell step="send_track" reachable={4}>
      <Card className="sm-enter flex flex-col items-center gap-4 text-center">
        <span className="grid size-16 place-items-center rounded-full bg-success text-white">
          <Icon name="check" size={36} strokeWidth={2.6} />
        </span>
        <h1 className="text-2xl font-bold">{t('send.submitted_title')}</h1>
        <div>
          <p className="text-sm text-muted">{t('send.tracking_id')}</p>
          <p className="tabular text-3xl font-bold tracking-wider text-brand" data-testid="tracking-id">
            {tid}
          </p>
        </div>
        <p className="flex items-center gap-2 text-sm">
          <Icon name="message" size={18} /> {t('send.sms_sent')}
        </p>
        {draft.applicationId ? (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element -- authenticated QR stream */}
            <img src={`/api/v1/applications/${draft.applicationId}/qr.png`} alt="QR" width={200} height={200} className="rounded-lg border border-border" />
            <p className="text-sm text-muted">{t('send.qr_note')}</p>
            <ButtonLink href={`/api/v1/applications/${draft.applicationId}/loan-file.pdf`} variant="secondary" icon="download">
              {t('send.download_loan_file')}
            </ButtonLink>
          </>
        ) : null}
      </Card>
      <div className="grid gap-3 sm:grid-cols-2">
        {tid ? (
          <ButtonLink href={`/track/${tid}`} size="lg" icon="clock" block>
            {t('track.title')}
          </ButtonLink>
        ) : null}
        <ButtonLink href="/" size="lg" variant="secondary" icon="home" block>
          {t('common.done')}
        </ButtonLink>
      </div>
      <NextStepCard step="submitted" extra={{ days: draft.partner?.avg_sanction_days ?? 30 }} />
    </ApplyShell>
  );
}
