import { getTranslations } from 'next-intl/server';

import { PrintSheet } from '@/components/officer/print-sheet';
import { gatewayFetch, requireRole } from '@/lib/session';

export const metadata = { title: 'Print slips' };

/** A counter-friendly page: one slip per applicant with the tracking ID and next step,
 * printed on the CSC's own printer and handed over. */
export default async function Page() {
  await requireRole('csc_operator', 'admin');
  const t = await getTranslations('officer');
  const res = await gatewayFetch('/v1/csc/queue?days=1');
  const data = res.ok ? await res.json() : { items: [] };
  return <PrintSheet items={data.items} title={t('csc.slips_title')} />;
}
