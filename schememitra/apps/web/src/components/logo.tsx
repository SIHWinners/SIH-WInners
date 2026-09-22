import { brandMarkPaths } from '@sm/ui/brand';

/** SchemeMitra mark: a citizen's path and a lender's path meeting and continuing as one. */
export function LogoMark({ size = 32 }: { size?: number }) {
  const { viewBox, left, right, node } = brandMarkPaths;
  return (
    <svg width={size} height={size} viewBox={viewBox} aria-hidden focusable="false">
      <rect width="48" height="48" rx="12" fill="var(--sm-brand)" />
      <path d={left} fill="none" stroke="var(--sm-on-brand)" strokeWidth="4" strokeLinecap="round" />
      <path d={right} fill="none" stroke="var(--sm-accent)" strokeWidth="4" strokeLinecap="round" />
      <circle cx={node.cx} cy={node.cy} r={node.r} fill="var(--sm-accent)" />
    </svg>
  );
}

export function Wordmark({ size = 28 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-2">
      <LogoMark size={size} />
      <span className="hidden text-lg font-bold tracking-tight text-brand min-[420px]:inline" lang="en">
        Scheme<span className="text-brand-ink">Mitra</span>
      </span>
    </span>
  );
}
