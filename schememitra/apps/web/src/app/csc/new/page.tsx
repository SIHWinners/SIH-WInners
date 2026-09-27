import { getTranslations } from 'next-intl/server';

import { NewApplicant } from '@/components/officer/new-applicant';
import { OfficerShell } from '@/components/officer-shell';
import { requireRole } from '@/lib/session';

export const metadata = { title: 'New applicant' };

export default async function Page() {
  const user = await requireRole('csc_operator', 'admin');
  const t = await getTranslations('officer');
  return (
    <OfficerShell user={user} title={t('nav.csc_new')}>
      <NewApplicant />
    </OfficerShell>
  );
}
