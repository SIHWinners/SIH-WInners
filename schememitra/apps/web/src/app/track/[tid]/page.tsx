import { getTranslations } from 'next-intl/server';

import { CitizenHeader } from '@/components/citizen-header';
import { ButtonLink, Notice } from '@/components/ui';
import { GATEWAY_URL } from '@/lib/session';

import { LiveTimeline, type TrackData } from './live-timeline';

export const metadata = { title: 'Track' };

export default async function TrackPage({ params }: { params: Promise<{ tid: string }> }) {
  const { tid } = await params;
  const t = await getTranslations();
  const res = await fetch(`${GATEWAY_URL}/v1/track/${encodeURIComponent(tid)}`, { cache: 'no-store' }).catch(() => null);
  const body = res ? await res.json().catch(() => null) : null;

  return (
    <>
      <CitizenHeader />
      <main className="mx-auto flex max-w-2xl flex-col gap-5 px-4 py-6">
        {res?.ok && body ? (
          <LiveTimeline initial={body as TrackData} />
        ) : (
          <>
            <Notice tone="warning" icon="alert">
              {t((body?.user_message_key ?? (res ? 'errors.track_not_found' : 'errors.server_down')) as never)}
            </Notice>
            <ButtonLink href="/track" variant="secondary">
              {t('track.enter_id')}
            </ButtonLink>
          </>
        )}
      </main>
    </>
  );
}
