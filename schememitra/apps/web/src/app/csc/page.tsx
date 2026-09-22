import { getTranslations } from 'next-intl/server';

import { OfficerShell } from '@/components/officer-shell';
import { requireRole } from '@/lib/session';

export default async function Page() {
  const user = await requireRole('csc_operator');
  const t = await getTranslations('officer');
  return (
    <OfficerShell user={user} title={t('nav.csc_today')}>
      <p className="text-muted">{t('role.' + user.role)}</p>
    </OfficerShell>
  );
}
