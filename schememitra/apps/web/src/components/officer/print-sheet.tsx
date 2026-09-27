'use client';

import type { components } from '@sm/contracts/client';
import { useTranslations } from 'next-intl';
import { useEffect } from 'react';

type Item = components['schemas']['CscItem'];

/**
 * Printable slips for the counter (claim C15). One slip per applicant: tracking ID, the
 * lender it went to, and how to check the status by SMS — so someone who leaves the centre
 * with no smartphone still has everything they need on paper.
 */
export function PrintSheet({ items, title }: { items: Item[]; title: string }) {
  const t = useTranslations();

  useEffect(() => {
    const timer = setTimeout(() => window.print(), 500);
    return () => clearTimeout(timer);
  }, []);

  return (
    <main className="mx-auto max-w-3xl p-6 print:p-0">
      <style>{`@media print { .no-print { display: none } .slip { break-inside: avoid; page-break-inside: avoid } }`}</style>
      <div className="no-print mb-4 flex items-center justify-between">
        <h1 className="text-xl font-bold">{title}</h1>
        <button type="button" onClick={() => window.print()} className="sm-tap rounded-md bg-brand px-4 text-on-brand" data-testid="print-now">
          {t('officer.csc.print')}
        </button>
      </div>
      <div className="flex flex-col gap-3">
        {items.map((item) => (
          <section key={item.id} className="slip rounded-lg border border-border p-4" data-testid={`slip-${item.tracking_id}`}>
            <header className="flex items-baseline justify-between">
              <h2 className="text-lg font-bold" lang="en">SchemeMitra</h2>
              <p className="font-mono text-lg font-bold">{item.tracking_id}</p>
            </header>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <dt className="text-muted">{t('intake.name')}</dt>
              <dd className="font-semibold">{item.applicant_name}</dd>
              <dt className="text-muted">{t('officer.queue.col_scheme')}</dt>
              <dd>{item.scheme_name ?? '—'}</dd>
              <dt className="text-muted">{t('partner.chosen')}</dt>
              <dd>{item.partner_name ?? '—'}</dd>
              <dt className="text-muted">{t('officer.queue.col_status')}</dt>
              <dd>{t(`track.status.${item.status}` as never)}</dd>
            </dl>
            <p className="mt-2 text-sm">{t('officer.csc.slip_sms', { tid: item.tracking_id ?? '' })}</p>
            <p className="text-xs text-muted">{t('common.free_service')}</p>
          </section>
        ))}
      </div>
    </main>
  );
}
