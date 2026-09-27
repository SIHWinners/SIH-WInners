import { getTranslations } from 'next-intl/server';

import { CscQueue } from '@/components/officer/csc-queue';
import { OfficerShell } from '@/components/officer-shell';
import { ButtonLink } from '@/components/ui';
import { gatewayFetch, requireRole } from '@/lib/session';

export const metadata = { title: "Today's applicants" };

export default async function Page() {
  const user = await requireRole('csc_operator', 'admin');
  const t = await getTranslations('officer');
  const res = await gatewayFetch('/v1/csc/queue?days=1');
  const data = res.ok ? await res.json() : { items: [], counts: {}, operator: null };
  return (
    <OfficerShell
      user={user}
      title={t('nav.csc_today')}
      actions={
        <>
          <ButtonLink href="/csc/print" size="sm" variant="secondary" icon="download">
            {t('csc.print')}
          </ButtonLink>
          <ButtonLink href="/apply" size="sm" icon="user">
            {t('nav.csc_new')}
          </ButtonLink>
        </>
      }
    >
      <CscQueue initial={data} />
    </OfficerShell>
  );
}
