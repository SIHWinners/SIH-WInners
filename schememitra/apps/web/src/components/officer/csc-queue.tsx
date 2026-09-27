'use client';

import type { components } from '@sm/contracts/client';
import { useTranslations } from 'next-intl';
import Link from 'next/link';

import { Icon } from '@/components/icons';
import { Badge, Card } from '@/components/ui';
import { formatPaise } from '@/lib/format';

type Queue = components['schemas']['CscQueueOut'];
type Item = components['schemas']['CscItem'];

/** The operator's day: who they helped, where each file stands, and what is missing. */
export function CscQueue({ initial }: { initial: Queue }) {
  const t = useTranslations();
  const counts = initial.counts ?? {};

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap gap-2">
        {(['all', 'draft', 'sent', 'decided'] as const).map((key) => (
          <Badge key={key} tone={key === 'decided' ? 'success' : key === 'draft' ? 'warning' : 'brand'}>
            {t(`officer.csc.count_${key}`)} <span className="tabular">{counts[key] ?? 0}</span>
          </Badge>
        ))}
      </div>

      {initial.items.length === 0 ? (
        <Card className="text-muted" data-testid="csc-empty">{t('officer.csc.empty')}</Card>
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full min-w-[44rem] border-collapse text-sm" data-testid="csc-table">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-muted">
                <th scope="col" className="px-3 py-2 text-start">{t('officer.queue.col_applicant')}</th>
                <th scope="col" className="px-3 py-2 text-start">{t('officer.queue.col_scheme')}</th>
                <th scope="col" className="px-3 py-2 text-end">{t('officer.queue.col_amount')}</th>
                <th scope="col" className="px-3 py-2 text-start">{t('officer.queue.col_status')}</th>
                <th scope="col" className="px-3 py-2 text-start">{t('officer.csc.consent')}</th>
                <th scope="col" className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {initial.items.map((item: Item) => (
                <tr key={item.id} className="border-b border-border last:border-0" data-testid={`csc-row-${item.tracking_id}`}>
                  <td className="px-3 py-2">
                    <span className="font-semibold">{item.applicant_name}</span>
                    <span className="block text-xs text-muted">
                      {item.tracking_id} · {item.phone_masked ?? '—'} · {item.lang.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-3 py-2">{item.scheme_name ?? '—'}</td>
                  <td className="px-3 py-2 text-end tabular">{item.amount_paise ? formatPaise(item.amount_paise) : '—'}</td>
                  <td className="px-3 py-2">
                    <Badge tone={item.status === 'sanctioned' ? 'success' : item.status === 'rejected' ? 'danger' : 'brand'}>
                      {t(`track.status.${item.status}` as never)}
                    </Badge>
                  </td>
                  <td className="px-3 py-2">
                    {item.consent_method ? (
                      <span className="inline-flex items-center gap-1 text-success-ink">
                        <Icon name="check" size={14} /> {t(`officer.csc.consent_${item.consent_method}` as never)}
                      </span>
                    ) : (
                      <span className="text-warning-ink">{t('officer.csc.consent_missing')}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-end">
                    {item.tracking_id ? (
                      <Link href={`/track/${item.tracking_id}`} className="font-semibold text-brand hover:underline">
                        {t('officer.queue.open')}
                      </Link>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
