'use client';

import { useTranslations } from 'next-intl';
import { useCallback, useEffect, useState } from 'react';

import { NextStepCard } from '@/components/apply/shell';
import { Icon } from '@/components/icons';
import { Badge, ButtonLink, Card, cx, Notice } from '@/components/ui';

export interface TrackData {
  tracking_id: string;
  status: string;
  scheme_code: string | null;
  partner_name: string | null;
  partner_type: string | null;
  expected_days: number | null;
  timeline: Array<{ status: string; at: string; params: Record<string, unknown> }>;
  next_step_key: string;
  requested_documents: string[];
  rejection_reason_code: string | null;
}

const HAPPY_PATH = ['submitted', 'received_by_partner', 'under_review', 'sanctioned', 'disbursed'];

export function LiveTimeline({ initial }: { initial: TrackData }) {
  const t = useTranslations();
  const [data, setData] = useState(initial);
  const [live, setLive] = useState(false);

  const refetch = useCallback(async () => {
    const res = await fetch(`/api/v1/track/${initial.tracking_id}`, { cache: 'no-store' });
    if (res.ok) setData(await res.json());
  }, [initial.tracking_id]);

  // Status pushes over WebSocket; falls back to polling every 30 s when sockets are blocked.
  useEffect(() => {
    let socket: WebSocket | null = null;
    let poll: ReturnType<typeof setInterval> | null = null;
    let closed = false;
    const connect = () => {
      try {
        socket = new WebSocket(process.env.NEXT_PUBLIC_WS_URL ?? 'ws://localhost:8080/ws');
      } catch {
        return;
      }
      socket.onopen = () => socket?.send(JSON.stringify({ op: 'subscribe', channel: `track:${initial.tracking_id}` }));
      socket.onmessage = (msg) => {
        const frame = JSON.parse(msg.data as string) as { op?: string; event?: string };
        if (frame.op === 'subscribed') setLive(true);
        if (frame.event === 'status') void refetch();
      };
      socket.onclose = () => {
        setLive(false);
        if (!closed) setTimeout(connect, 5000);
      };
    };
    connect();
    poll = setInterval(() => void refetch(), 30_000);
    return () => {
      closed = true;
      socket?.close();
      if (poll) clearInterval(poll);
    };
  }, [initial.tracking_id, refetch]);

  const reached = new Map(data.timeline.map((e) => [e.status, e]));
  const rejected = data.status === 'rejected';
  const extras = data.timeline.filter((e) => !HAPPY_PATH.includes(e.status) && !['draft', 'ready'].includes(e.status));
  const currentIndex = HAPPY_PATH.indexOf(data.status);

  return (
    <div className="flex flex-col gap-5" data-testid="track-view">
      <header className="flex flex-col gap-1">
        <p className="text-sm text-muted">{t('send.tracking_id')}</p>
        <h1 className="tabular text-2xl font-bold tracking-wider text-brand">{data.tracking_id}</h1>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={rejected ? 'danger' : data.status === 'sanctioned' || data.status === 'disbursed' ? 'success' : 'brand'} data-testid="track-status">
            {t(`track.status.${data.status}` as never)}
          </Badge>
          {live ? (
            <span className="flex items-center gap-1 text-xs text-success-ink">
              <span className="size-2 animate-pulse rounded-full bg-success" aria-hidden /> Live
            </span>
          ) : null}
        </div>
        {data.partner_name ? (
          <p className="text-sm text-muted" lang="en">
            {data.partner_type ? `${t(`partner.types.${data.partner_type}` as never)} · ` : ''}
            {data.partner_name}
          </p>
        ) : null}
      </header>

      {data.status === 'documents_requested' ? (
        <Notice tone="warning" icon="doc" title={t('track.status.documents_requested')}>
          {t('track.requested_docs', { docs: data.requested_documents.map((d) => t(`docs.type.${d}` as never)).join(', ') })}
        </Notice>
      ) : null}
      {rejected && data.rejection_reason_code ? (
        <Notice tone="danger" icon="alert" title={t('track.status.rejected')}>
          {t('track.reject_reason', { reason: t(`reject_reason.${data.rejection_reason_code}` as never) })}
        </Notice>
      ) : null}

      <Card>
        <h2 className="mb-3 font-bold">{t('track.timeline')}</h2>
        <ol className="relative flex flex-col gap-0" role="list">
          {HAPPY_PATH.map((status, i) => {
            const entry = reached.get(status);
            const done = !!entry && (i < currentIndex || status === data.status);
            const current = status === data.status;
            const pending = !entry && !(rejected && i > 0);
            return (
              <li key={status} className="relative flex gap-3 pb-5 last:pb-0">
                {i < HAPPY_PATH.length - 1 ? (
                  <span className={cx('absolute start-[15px] top-8 h-[calc(100%-1.5rem)] w-0.5', done && !current ? 'bg-success' : 'bg-border')} aria-hidden />
                ) : null}
                <span
                  className={cx(
                    'z-10 grid size-8 shrink-0 place-items-center rounded-full border-2',
                    done ? 'border-success bg-success text-white' : current ? 'border-accent bg-accent-tint text-accent-ink' : 'border-border bg-surface text-muted',
                  )}
                >
                  {done ? <Icon name="check" size={16} strokeWidth={2.6} /> : <span className="text-xs font-bold">{i + 1}</span>}
                </span>
                <div className="pt-1">
                  <p className={cx('font-semibold', pending && 'text-muted')}>{t(`track.status.${status}` as never)}</p>
                  {entry ? <p className="tabular text-xs text-muted">{new Date(entry.at).toLocaleString()}</p> : null}
                </div>
              </li>
            );
          })}
        </ol>
        {extras.length ? (
          <ul className="mt-4 flex flex-col gap-1 border-t border-border pt-3 text-sm" role="list">
            {extras.map((e, i) => (
              <li key={i} className="flex justify-between gap-2">
                <span>{t(`track.status.${e.status}` as never)}</span>
                <span className="tabular text-xs text-muted">{new Date(e.at).toLocaleString()}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </Card>

      <aside className="flex flex-col gap-2 rounded-xl border border-brand/20 bg-brand-tint p-4 text-brand-ink" aria-live="polite">
        <p className="text-sm font-bold">{t('next_card.title')}</p>
        <p data-testid="track-next">{t(data.next_step_key as never)}</p>
        {data.expected_days && !['sanctioned', 'disbursed', 'rejected'].includes(data.status) ? (
          <p className="text-sm">{t('track.expected_days', { days: data.expected_days })}</p>
        ) : null}
      </aside>
      <p className="flex items-center gap-2 text-sm text-muted">
        <Icon name="scale" size={16} /> {t('track.decision_by_lender')}
      </p>
      <div className="grid gap-3 sm:grid-cols-2">
        <ButtonLink href="tel:18000000000" variant="secondary" icon="phone" block>
          {t('common.call_helpline')}
        </ButtonLink>
        <ButtonLink href="/apply/partner" variant="ghost" icon="pin" block>
          {t('common.visit_csc')}
        </ButtonLink>
      </div>
      {data.status === 'submitted' ? <NextStepCard step="submitted" extra={{ days: data.expected_days ?? 30 }} /> : null}
    </div>
  );
}
