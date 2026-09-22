'use client';

import type { ExcludedPartner, NearbyResponse, PartnerCard } from '@sm/contracts/client';
import { languages } from '@sm/i18n';
import dynamic from 'next/dynamic';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useState } from 'react';

import { ApplyShell, NextStepCard } from '@/components/apply/shell';
import { Icon } from '@/components/icons';
import { Badge, Button, ButtonLink, Card, cx, Notice, Skeleton } from '@/components/ui';
import { api, ApiError, unwrap } from '@/lib/api';
import { useDraft } from '@/stores/draft';

const PartnerMap = dynamic(() => import('@/components/apply/partner-map'), {
  ssr: false,
  loading: () => <Skeleton className="h-80" />,
});

const NATIVE = Object.fromEntries(languages.map((l) => [l.code, l.native]));

export default function PartnerPage() {
  const t = useTranslations();
  const router = useRouter();
  const draft = useDraft();
  const [view, setView] = useState<'list' | 'map'>('list');
  const [tilesFailed, setTilesFailed] = useState(false);
  const [radius, setRadius] = useState(40);
  const [data, setData] = useState<NearbyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [center, setCenter] = useState<{ lat: number; lng: number } | null>(null);

  useEffect(() => {
    if (draft.hydrated && !center && draft.facts.lat != null && draft.facts.lng != null) {
      setCenter({ lat: draft.facts.lat, lng: draft.facts.lng });
    }
  }, [draft.hydrated, draft.facts.lat, draft.facts.lng, center]);

  useEffect(() => {
    if (!center || !draft.schemeCode) return;
    let cancelled = false;
    setError(null);
    unwrap(
      api.GET('/v1/partners/nearby', {
        params: {
          query: {
            lat: center.lat,
            lng: center.lng,
            scheme: draft.schemeCode,
            category: draft.facts.social_category ?? undefined,
            radius_km: radius,
            loan_paise: draft.plan?.principal_paise,
          },
        },
      }),
    )
      .then((res) => !cancelled && setData(res))
      .catch((err) => !cancelled && setError(err instanceof ApiError ? err.problem.user_message_key : 'errors.generic'));
    return () => {
      cancelled = true;
    };
  }, [center, radius, draft.schemeCode, draft.facts.social_category, draft.plan?.principal_paise]);

  const choose = useCallback(
    (p: PartnerCard) => {
      draft.choosePartner(p);
    },
    [draft],
  );

  function useMyLocation() {
    navigator.geolocation?.getCurrentPosition(
      (pos) => setCenter({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
      () => undefined,
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 600000 },
    );
  }

  if (draft.hydrated && !draft.schemeCode) {
    return (
      <ApplyShell step="partner_pick" reachable={1}>
        <Notice tone="warning">{t('next_card.rule_check')}</Notice>
        <ButtonLink href="/apply/rules">{t('steps.rule_check')}</ButtonLink>
      </ApplyShell>
    );
  }

  return (
    <ApplyShell
      step="partner_pick"
      reachable={draft.partner ? 4 : 3}
      footer={
        <>
          <Button variant="secondary" size="lg" icon="chevronLeft" onClick={() => router.push('/apply/money')}>
            <span className="sr-only sm:not-sr-only">{t('common.back')}</span>
          </Button>
          <Button size="lg" block iconRight="chevronRight" disabled={!draft.partner} onClick={() => router.push('/apply/send')} data-testid="partner-next">
            {t('common.continue')}
          </Button>
        </>
      }
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">{t('partner.title')}</h1>
        <div className="flex gap-2">
          <div role="tablist" className="flex rounded-lg border border-border-strong p-0.5">
            {(['list', 'map'] as const).map((v) => (
              <button
                key={v}
                role="tab"
                aria-selected={view === v}
                disabled={v === 'map' && tilesFailed}
                onClick={() => setView(v)}
                className={cx('flex h-10 items-center gap-1.5 rounded-md px-3 text-sm font-semibold', view === v ? 'bg-brand text-on-brand' : 'text-brand')}
              >
                <Icon name={v === 'list' ? 'list' : 'map'} size={18} /> {t(v === 'list' ? 'partner.list_view' : 'partner.map_view')}
              </button>
            ))}
          </div>
          <Button size="sm" variant="ghost" icon="pin" onClick={useMyLocation} aria-label="GPS" />
        </div>
      </header>

      {tilesFailed ? <Notice tone="warning">{t('partner.map_unavailable')}</Notice> : null}
      {error ? <Notice tone="danger">{t(error as never)}</Notice> : null}
      {!data && !error ? <Skeleton className="h-48" /> : null}

      {data && view === 'map' && center && !tilesFailed ? (
        <PartnerMap
          center={center}
          partners={data.partners}
          excluded={data.excluded}
          selectedId={draft.partner?.id ?? null}
          onSelect={choose}
          onTilesFailed={() => {
            setTilesFailed(true);
            setView('list');
          }}
        />
      ) : null}

      {data ? (
        <>
          {data.partners.length === 0 ? (
            <Notice tone="warning" title={t('partner.no_results', { km: radius })}>
              <Button size="sm" variant="secondary" className="mt-2" onClick={() => setRadius((r) => Math.min(r * 2, 300))}>
                {t('partner.widen')}
              </Button>
            </Notice>
          ) : null}
          <ul className="flex flex-col gap-3" role="list" data-testid="partner-list">
            {data.partners.map((p) => (
              <PartnerItem key={p.id} partner={p} selected={draft.partner?.id === p.id} onChoose={() => choose(p)} />
            ))}
          </ul>
          {data.excluded.length ? (
            <section aria-labelledby="skipped" className="flex flex-col gap-2">
              <h2 id="skipped" className="font-bold">
                {t('partner.skipped_title')}
              </h2>
              <p className="text-sm text-muted">{t('partner.skipped_why')}</p>
              <ul className="flex flex-col gap-2" role="list" data-testid="partner-skipped">
                {data.excluded.map((p) => (
                  <SkippedItem key={p.id} partner={p} />
                ))}
              </ul>
            </section>
          ) : null}
        </>
      ) : null}
      <NextStepCard step="partner_pick" />
    </ApplyShell>
  );
}

function PartnerItem({ partner, selected, onChoose }: { partner: PartnerCard; selected: boolean; onChoose: () => void }) {
  const t = useTranslations();
  const tone = partner.health_score >= 80 ? 'success' : partner.health_score >= 65 ? 'brand' : 'warning';
  return (
    <Card as="li" className={cx('flex flex-col gap-3', selected && 'border-brand ring-2 ring-brand/30')}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="mb-1 flex flex-wrap gap-1.5">
            <Badge tone="brand">{t(`partner.types.${partner.type}` as never)}</Badge>
            <Badge tone={tone} icon="shield">
              {t('partner.health', { score: partner.health_score })}
            </Badge>
          </div>
          <h3 className="font-bold leading-snug" lang="en">
            {partner.name}
          </h3>
          <p className="text-sm text-muted" lang="en">
            {partner.address}
          </p>
        </div>
        <span className="tabular shrink-0 rounded-lg bg-surface-alt px-2 py-1 text-sm font-bold">{t('partner.distance', { km: partner.distance_km })}</span>
      </div>
      <dl className="grid gap-1 text-sm sm:grid-cols-2">
        <div>
          <dt className="inline font-semibold">{t('partner.languages')}: </dt>
          <dd className="inline">{partner.languages.map((l) => NATIVE[l] ?? l).join(', ')}</dd>
        </div>
        <div>
          <dt className="inline font-semibold">{t('partner.open_hours')}: </dt>
          <dd className="inline" lang="en">{partner.open_hours}</dd>
        </div>
        <div className="sm:col-span-2">
          <dt className="inline font-semibold">{t('partner.documents_needed')}: </dt>
          <dd className="inline">{partner.documents_needed.map((d) => t(`docs.type.${d}` as never)).join(', ')}</dd>
        </div>
        {partner.avg_sanction_days ? (
          <div className="sm:col-span-2">
            <dd className="inline text-muted">{t('track.expected_days', { days: partner.avg_sanction_days })}</dd>
          </div>
        ) : null}
      </dl>
      <Button variant={selected ? 'success' : 'primary'} icon={selected ? 'check' : 'pin'} onClick={onChoose} data-testid={`choose-partner-${partner.id}`}>
        {selected ? t('partner.chosen') : t('partner.choose')}
      </Button>
    </Card>
  );
}

function SkippedItem({ partner }: { partner: ExcludedPartner }) {
  const t = useTranslations();
  return (
    <li className="flex items-start gap-3 rounded-lg border border-dashed border-border-strong bg-surface-alt p-3 text-muted">
      <Icon name="x" size={20} className="mt-0.5 shrink-0 text-danger-ink" />
      <div>
        <p className="font-semibold" lang="en">
          {partner.name} · {t('partner.distance', { km: partner.distance_km })}
        </p>
        <p className="text-sm font-semibold text-danger-ink" data-reason={partner.reason}>
          {t(`partner.skip.${partner.reason}` as never)}
        </p>
      </div>
    </li>
  );
}
