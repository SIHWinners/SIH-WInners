import { getTranslations } from 'next-intl/server';

import { OfficerShell } from '@/components/officer-shell';
import { requireRole } from '@/lib/session';

export default async function Page() {
  const user = await requireRole('partner_officer');
  const t = await getTranslations('officer');
  return (
    <OfficerShell user={user} title={t('nav.queue')}>
      <p className="text-muted">{t('role.' + user.role)}</p>
    </OfficerShell>
  );
}
