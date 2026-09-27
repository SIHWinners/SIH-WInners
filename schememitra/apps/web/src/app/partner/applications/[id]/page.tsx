import { notFound } from 'next/navigation';
import { getTranslations } from 'next-intl/server';

import { ReviewWorkspace } from '@/components/officer/review-workspace';
import { OfficerShell } from '@/components/officer-shell';
import { gatewayFetch, requireRole } from '@/lib/session';

export const metadata = { title: 'Review file' };

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const user = await requireRole('partner_officer', 'admin');
  const t = await getTranslations('officer');
  const { id } = await params;
  const res = await gatewayFetch(`/v1/partner/applications/${id}`);
  if (!res.ok) notFound();
  const review = await res.json();
  return (
    <OfficerShell user={user} title={`${t('review.title')} · ${review.application.tracking_id}`}>
      <ReviewWorkspace review={review} />
    </OfficerShell>
  );
}
