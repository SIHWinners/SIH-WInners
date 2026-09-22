'use client';

import { isValidTrackingId, normalizeTrackingId } from '@sm/contracts/tracking';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';

import { CitizenHeader } from '@/components/citizen-header';
import { Button, Card, Field, Notice } from '@/components/ui';

export default function TrackLookupPage() {
  const t = useTranslations('track');
  const router = useRouter();
  const [value, setValue] = useState('');
  const [error, setError] = useState(false);

  useEffect(() => {
    try {
      const last = JSON.parse(localStorage.getItem('sm_last_tracking') ?? 'null') as { trackingId?: string } | null;
      if (last?.trackingId) setValue(last.trackingId);
    } catch {
      /* ignore */
    }
  }, []);

  return (
    <>
      <CitizenHeader />
      <main className="mx-auto flex max-w-md flex-col gap-5 px-4 py-8">
        <h1 className="text-2xl font-bold">{t('title')}</h1>
        <Card>
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              // The check character catches typos before any network call (works offline too).
              if (!isValidTrackingId(value)) {
                setError(true);
                return;
              }
              router.push(`/track/${normalizeTrackingId(value)}`);
            }}
          >
            <Field
              label={t('enter_id')}
              hint={t('id_example')}
              value={value}
              autoCapitalize="characters"
              spellCheck={false}
              onChange={(e) => {
                setValue(e.target.value);
                setError(false);
              }}
              error={error ? t('invalid_id') : undefined}
              className="tabular"
            />
            <Button type="submit" size="lg" icon="clock">
              {t('find')}
            </Button>
          </form>
        </Card>
        {error ? <Notice tone="warning">{t('invalid_id')}</Notice> : null}
      </main>
    </>
  );
}
