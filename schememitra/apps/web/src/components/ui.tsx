import Link from 'next/link';
import { forwardRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode } from 'react';

import { Icon, type IconName } from './icons';

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'success';
type Size = 'sm' | 'md' | 'lg';

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-brand text-on-brand hover:bg-brand-ink border border-transparent',
  secondary: 'bg-surface text-brand border border-border-strong hover:bg-brand-tint',
  ghost: 'bg-transparent text-brand border border-transparent hover:bg-brand-tint',
  danger: 'bg-danger text-white border border-transparent hover:bg-danger-ink',
  success: 'bg-success text-white border border-transparent hover:bg-success-ink',
};

const SIZES: Record<Size, string> = {
  sm: 'h-9 px-3 text-sm gap-1.5 rounded-md',
  md: 'min-h-12 px-4 text-base gap-2 rounded-md',
  lg: 'min-h-14 px-6 text-lg gap-2.5 rounded-lg font-semibold',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: IconName;
  iconRight?: IconName;
  loading?: boolean;
  block?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'primary', size = 'md', icon, iconRight, loading, block, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cx(
        'inline-flex select-none items-center justify-center font-semibold transition-colors duration-150',
        'disabled:cursor-not-allowed disabled:opacity-55',
        VARIANTS[variant],
        SIZES[size],
        block && 'w-full',
        className,
      )}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? (
        <span className="size-4 animate-spin rounded-full border-2 border-current border-r-transparent" aria-hidden />
      ) : icon ? (
        <Icon name={icon} size={size === 'lg' ? 22 : 18} />
      ) : null}
      {children}
      {iconRight ? <Icon name={iconRight} size={size === 'lg' ? 22 : 18} /> : null}
    </button>
  );
});

export function ButtonLink({
  href,
  variant = 'primary',
  size = 'md',
  icon,
  block,
  className,
  children,
}: {
  href: string;
  variant?: Variant;
  size?: Size;
  icon?: IconName;
  block?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      className={cx(
        'inline-flex items-center justify-center font-semibold transition-colors duration-150',
        VARIANTS[variant],
        SIZES[size],
        block && 'w-full',
        className,
      )}
    >
      {icon ? <Icon name={icon} size={size === 'lg' ? 22 : 18} /> : null}
      {children}
    </Link>
  );
}

export function Card({
  children,
  className,
  as: Tag = 'section',
  ...rest
}: { children: ReactNode; className?: string; as?: 'section' | 'div' | 'article' | 'li' } & Record<string, unknown>) {
  return (
    <Tag className={cx('sm-card p-4 sm:p-5', className)} {...rest}>
      {children}
    </Tag>
  );
}

type Tone = 'neutral' | 'brand' | 'success' | 'warning' | 'danger' | 'accent';
const TONES: Record<Tone, string> = {
  neutral: 'bg-surface-alt text-muted',
  brand: 'bg-brand-tint text-brand-ink',
  success: 'bg-success-tint text-success-ink',
  warning: 'bg-warning-tint text-warning-ink',
  danger: 'bg-danger-tint text-danger-ink',
  accent: 'bg-accent-tint text-accent-ink',
};

export function Badge({
  tone = 'neutral',
  icon,
  children,
  className,
  ...rest
}: { tone?: Tone; icon?: IconName; children: ReactNode; className?: string } & Record<`data-${string}`, string>) {
  return (
    <span className={cx('inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold', TONES[tone], className)} {...rest}>
      {icon ? <Icon name={icon} size={14} /> : null}
      {children}
    </span>
  );
}

/** Visible label on every mock/sandbox path — the product never hides a stand-in. */
export function SandboxBadge({ label = 'SANDBOX' }: { label?: string }) {
  return (
    <span className="inline-flex items-center rounded border border-dashed border-warning px-1.5 py-px text-[11px] font-bold tracking-wide text-warning-ink">
      {label}
    </span>
  );
}

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string;
  leading?: ReactNode;
}

export const Field = forwardRef<HTMLInputElement, FieldProps>(function Field(
  { label, hint, error, id, leading, className, ...rest },
  ref,
) {
  const inputId = id ?? `f-${label.replace(/\W+/g, '-').toLowerCase()}`;
  const describedBy = [hint && `${inputId}-hint`, error && `${inputId}-err`].filter(Boolean).join(' ') || undefined;
  return (
    <div className={cx('flex flex-col gap-1.5', className)}>
      <label htmlFor={inputId} className="text-sm font-semibold">
        {label}
      </label>
      <div
        className={cx(
          'flex min-h-12 items-center gap-2 rounded-md border bg-surface px-3 focus-within:border-brand',
          error ? 'border-danger' : 'border-border-strong',
        )}
      >
        {leading}
        <input
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy}
          className="h-11 w-full min-w-0 bg-transparent text-base outline-none placeholder:text-muted"
          {...rest}
        />
      </div>
      {hint ? (
        <p id={`${inputId}-hint`} className="text-sm text-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={`${inputId}-err`} role="alert" className="flex items-center gap-1 text-sm text-danger-ink">
          <Icon name="alert" size={16} /> {error}
        </p>
      ) : null}
    </div>
  );
});

export function Notice({ tone = 'brand', icon = 'info', title, children }: { tone?: Tone; icon?: IconName; title?: string; children: ReactNode }) {
  return (
    <div className={cx('flex gap-3 rounded-lg p-3.5', TONES[tone])} role={tone === 'danger' ? 'alert' : 'status'}>
      <Icon name={icon} size={20} className="mt-0.5 shrink-0" />
      <div className="text-sm leading-relaxed">
        {title ? <p className="font-semibold">{title}</p> : null}
        {children}
      </div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx('sm-skeleton', className)} aria-hidden />;
}
