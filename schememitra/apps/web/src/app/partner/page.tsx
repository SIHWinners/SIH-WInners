import { getTranslations } from 'next-intl/server';

import { PartnerQueue } from '@/components/officer/partner-queue';
import { OfficerShell } from '@/components/officer-shell';
import { ButtonLink } from '@/components/ui';
import { gatewayFetch, requireRole } from '@/lib/session';

export const metadata = { title: 'Applications' };

export default async function Page({ searchParams }: { searchParams: Promise<{ group?: string; q?: string }> }) {
  const user = await requireRole('partner_officer', 'admin');
  const t = await getTranslations('officer');
  const { group = 'new', q } = await searchParams;
  const params = new URLSearchParams({ group, ...(q ? { q } : {}) });
  const res = await gatewayFetch(`/v1/partner/queue?${params}`);
  const data = res.ok ? await res.json() : { items: [], counts: {}, partner_name: null };

  return (
    <OfficerShell
      user={user}
      title={t('queue.title')}
      actions={
        <ButtonLink href="/partner/scan" size="sm" icon="qr">
          {t('nav.scan')}
        </ButtonLink>
      }
    >
      <PartnerQueue initial={data} group={group} query={q ?? ''} />
    </OfficerShell>
  );
}
