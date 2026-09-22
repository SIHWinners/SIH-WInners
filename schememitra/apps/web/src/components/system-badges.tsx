import { gatewayFetch } from '@/lib/session';

import { SandboxBadge } from './ui';

interface Adapter {
  name: string;
  mode: string;
  sandbox: boolean;
  breaker: string;
  chaos: boolean;
}

/** Officer-facing strip that labels every sandboxed or degraded dependency. Mocks are never hidden. */
export async function SystemBadges() {
  const res = await gatewayFetch('/v1/system/status').catch(() => null);
  if (!res?.ok) return <SandboxBadge label="CORE OFFLINE" />;
  const status = (await res.json()) as { adapters: Adapter[]; database: string };
  const sandboxed = status.adapters.filter((a) => a.sandbox);
  const degraded = status.adapters.filter((a) => a.chaos || a.breaker !== 'closed');
  return (
    <div className="flex flex-wrap items-center gap-1.5" aria-label="Adapter status">
      {sandboxed.length ? (
        <span title={sandboxed.map((a) => `${a.name}: ${a.mode}`).join('\n')}>
          <SandboxBadge label={`SANDBOX · ${sandboxed.length}`} />
        </span>
      ) : null}
      {degraded.map((a) => (
        <span key={a.name} className="rounded bg-danger-tint px-1.5 py-px text-[11px] font-bold text-danger-ink">
          {a.name} ↓
        </span>
      ))}
    </div>
  );
}
