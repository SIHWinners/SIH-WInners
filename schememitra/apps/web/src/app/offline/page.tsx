import { getTranslations } from 'next-intl/server';

import { CitizenHeader } from '@/components/citizen-header';
import { Icon } from '@/components/icons';
import { ButtonLink, Card } from '@/components/ui';

export const metadata = { title: 'Offline' };

/** Shown when a page is opened with no connection and nothing cached. Everything already
 * answered stays on the phone, so the message is "carry on", not "start again". */
export default async function OfflinePage() {
  const t = await getTranslations();
  return (
    <>
      <CitizenHeader />
      <main className="mx-auto flex max-w-xl flex-col gap-4 px-4 py-8">
        <Card className="flex flex-col gap-3">
          <h1 className="flex items-center gap-2 text-2xl font-bold">
            <Icon name="wifiOff" size={26} /> {t('common.offline_banner')}
          </h1>
          <p className="text-muted">{t('offline.saved')} · {t('offline.will_sync')}</p>
          <ButtonLink href="/apply" size="lg" icon="chevronRight">
            {t('common.continue')}
          </ButtonLink>
        </Card>
      </main>
    </>
  );
}
