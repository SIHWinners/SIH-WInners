'use client';

import type { components } from '@sm/contracts/client';
import { useTranslations } from 'next-intl';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import { Icon } from '@/components/icons';
import { Badge, Button, Card, cx } from '@/components/ui';
import { formatPaise } from '@/lib/format';

type Queue = components['schemas']['QueueOut'];
type Item = components['schemas']['QueueItem'];

const TABS = ['new', 'in_review', 'decided', 'all'] as const;
const STATUS_TONE: Record<string, 'brand' | 'warning' | 'success' | 'danger' | 'neutral'> = {
  submitted: 'brand', resubmitted: 'brand', received_by_partner: 'neutral', under_review: 'warning',
  documents_requested: 'warning', sanctioned: 'success', disbursed: 'success', rejected: 'danger',
};

/** Lender queue. Refreshes when the gateway pushes an update for this lender's channel. */
export function PartnerQueue({ initial, group, query }: { initial: Queue; group: string; query: string }) {
  const t = useTranslations();
  const router = useRouter();
  const params = useSearchParams();
  const [search, setSearch] = useState(query);
  const [live, setLive] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let closed = false;
    (async () => {
      const res = await fetch('/api/v1/auth/me');
      if (!res.ok) return;
      const me = await res.json();
      if (!me.partner_id || closed) return;
      const url = new URL(`/ws?channel=partner:${me.partner_id}`, window.location.origin);
      url.protocol = url.protocol.replace('http', 'ws');
      socket = new WebSocket(url);
      socket.onopen = () => setLive(true);
      socket.onclose = () => setLive(false);
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload?.data?.tracking_id) setFlash(payload.data.tracking_id);
        } catch {
          /* ignore malformed frames */
        }
        router.refresh();
      };
    })();
    return () => {
      closed = true;
      socket?.close();
    };
  }, [router]);

  function go(next: { group?: string; q?: string }) {
    const url = new URLSearchParams(params.toString());
    if (next.group) url.set('group', next.group);
    if (next.q !== undefined) {
      if (next.q) url.set('q', next.q);
      else url.delete('q');
    }
    router.push(`/partner?${url}`);
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <div role="tablist" aria-label={t('officer.queue.title')} className="flex flex-wrap gap-1.5">
          {TABS.map((tab) => (
            <button
              key={tab}
              role="tab"
              aria-selected={group === tab}
              onClick={() => go({ group: tab })}
              className={cx(
                'sm-tap rounded-full border px-3.5 text-sm font-semibold',
                group === tab ? 'border-brand bg-brand text-on-brand' : 'border-border-strong text-muted hover:bg-brand-tint',
              )}
              data-testid={`queue-tab-${tab}`}
            >
              {t(`officer.queue.tabs.${tab}`)} <span className="tabular">{initial.counts?.[tab] ?? 0}</span>
            </button>
          ))}
        </div>
        <form
          className="ms-auto flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            go({ q: search.trim() });
          }}
        >
          <label htmlFor="queue-search" className="sr-only">{t('officer.queue.search')}</label>
          <input
            id="queue-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('officer.queue.search')}
            className="sm-tap min-w-52 rounded-md border border-border-strong bg-surface px-3 text-sm"
            data-testid="queue-search"
          />
          <Button type="submit" size="sm" variant="secondary">{t('common.search')}</Button>
        </form>
      </div>

      <p className="flex items-center gap-2 text-sm text-muted">
        {initial.partner_name ? t('officer.queue.lender', { name: initial.partner_name }) : null}
        {live ? (
          <span className="inline-flex items-center gap-1.5 text-success-ink">
            <span className="size-2 animate-pulse rounded-full bg-success" aria-hidden /> {t('officer.queue.live')}
          </span>
        ) : null}
        {flash ? <Badge tone="success" icon="bolt" data-testid="queue-flash">{t('officer.queue.new_arrival', { tid: flash })}</Badge> : null}
      </p>

      {initial.items.length === 0 ? (
        <Card className="text-muted">{t('officer.queue.empty')}</Card>
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full min-w-[46rem] border-collapse text-sm" data-testid="queue-table">
            <thead>
              <tr className="border-b border-border text-start text-xs uppercase tracking-wide text-muted">
                <th scope="col" className="px-3 py-2 text-start">{t('officer.queue.col_applicant')}</th>
                <th scope="col" className="px-3 py-2 text-start">{t('officer.queue.col_scheme')}</th>
                <th scope="col" className="px-3 py-2 text-end">{t('officer.queue.col_amount')}</th>
                <th scope="col" className="px-3 py-2 text-start">{t('officer.queue.col_status')}</th>
                <th scope="col" className="px-3 py-2 text-end">{t('officer.queue.col_age')}</th>
                <th scope="col" className="px-3 py-2 text-end">{t('officer.queue.col_readiness')}</th>
                <th scope="col" className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {initial.items.map((item: Item) => (
                <tr key={item.id} className="border-b border-border last:border-0 hover:bg-brand-tint/40" data-testid={`queue-row-${item.tracking_id}`}>
                  <td className="px-3 py-2">
                    <span className="font-semibold">{item.applicant_name}</span>
                    <span className="block text-xs text-muted">
                      {item.tracking_id} · {item.district ?? '—'} · {item.submitted_via.toUpperCase()}
                    </span>
                  </td>
                  <td className="px-3 py-2">{item.scheme_name ?? '—'}</td>
                  <td className="px-3 py-2 text-end tabular">{item.amount_paise ? formatPaise(item.amount_paise) : '—'}</td>
                  <td className="px-3 py-2">
                    <Badge tone={STATUS_TONE[item.status] ?? 'neutral'}>{t(`track.status.${item.status}` as never)}</Badge>
                  </td>
                  <td className="px-3 py-2 text-end tabular">
                    {item.age_hours != null ? t('officer.queue.hours', { hours: Math.round(item.age_hours) }) : '—'}
                    {item.overdue ? <Badge tone="danger" className="ms-1">{t('officer.queue.overdue')}</Badge> : null}
                  </td>
                  <td className="px-3 py-2 text-end tabular">{item.readiness_score != null ? `${item.readiness_score}%` : '—'}</td>
                  <td className="px-3 py-2 text-end">
                    <Link
                      href={`/partner/applications/${item.id}`}
                      className="inline-flex items-center gap-1 font-semibold text-brand hover:underline"
                      data-testid={`queue-open-${item.tracking_id}`}
                    >
                      {t('officer.queue.open')} <Icon name="chevronRight" size={16} />
                    </Link>
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
