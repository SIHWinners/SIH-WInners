import { getTranslations } from 'next-intl/server';

import { ScanPanel } from '@/components/officer/scan-panel';
import { OfficerShell } from '@/components/officer-shell';
import { requireRole } from '@/lib/session';

export const metadata = { title: 'Scan QR' };

export default async function Page() {
  const user = await requireRole('partner_officer', 'admin');
  const t = await getTranslations('officer');
  return (
    <OfficerShell user={user} title={t('scan.title')}>
      <ScanPanel />
    </OfficerShell>
  );
}
