import Link from 'next/link';
import { getTranslations } from 'next-intl/server';
import type { ReactNode } from 'react';

import type { Role, SessionUser } from '@/lib/session';

import { Icon, type IconName } from './icons';
import { LogoMark } from './logo';
import { LogoutButton } from './logout-button';
import { SystemBadges } from './system-badges';

type NavItem = { href: string; key: string; icon: IconName };

const NAV: Record<Exclude<Role, 'citizen'>, NavItem[]> = {
  partner_officer: [
    { href: '/partner', key: 'queue', icon: 'list' },
    { href: '/partner/scan', key: 'scan', icon: 'qr' },
  ],
  csc_operator: [
    { href: '/csc', key: 'csc_today', icon: 'users' },
    { href: '/csc/new', key: 'csc_new', icon: 'user' },
  ],
  admin: [
    { href: '/admin', key: 'admin_overview', icon: 'home' },
    { href: '/admin/schemes', key: 'admin_schemes', icon: 'scale' },
    { href: '/admin/partners', key: 'admin_partners', icon: 'map' },
    { href: '/admin/system', key: 'admin_system', icon: 'settings' },
    { href: '/admin/sms', key: 'admin_sms', icon: 'message' },
    { href: '/partner', key: 'queue', icon: 'list' },
    { href: '/insights', key: 'insights', icon: 'chart' },
  ],
  policy_viewer: [{ href: '/insights', key: 'insights', icon: 'chart' }],
};

export async function OfficerShell({ user, title, actions, children }: { user: SessionUser; title: string; actions?: ReactNode; children: ReactNode }) {
  const t = await getTranslations('officer');
  const items = NAV[user.role as Exclude<Role, 'citizen'>] ?? [];
  return (
    <div className="flex min-h-dvh flex-col md:flex-row">
      <aside className="border-b border-border bg-surface md:w-60 md:shrink-0 md:border-b-0 md:border-e">
        <div className="flex h-14 items-center gap-2 px-4">
          <LogoMark size={26} />
          <span className="font-bold text-brand" lang="en">
            SchemeMitra
          </span>
          <span className="ms-auto rounded bg-brand-tint px-1.5 py-0.5 text-[11px] font-bold text-brand-ink">{t(`role.${user.role}`)}</span>
        </div>
        <nav aria-label={t('nav_label')} className="flex gap-1 overflow-x-auto px-2 pb-2 md:flex-col md:pb-4">
          {items.map((item) => (
            <Link
              key={item.href + item.key}
              href={item.href}
              className="flex min-h-10 shrink-0 items-center gap-2.5 rounded-md px-3 text-sm font-semibold text-muted hover:bg-brand-tint hover:text-brand-ink"
            >
              <Icon name={item.icon} size={18} />
              {t(`nav.${item.key}`)}
            </Link>
          ))}
        </nav>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex min-h-14 flex-wrap items-center gap-3 border-b border-border bg-surface px-4 py-2">
          <h1 className="text-lg font-bold">{title}</h1>
          <SystemBadges />
          <div className="ms-auto flex items-center gap-2">
            {actions}
            <span className="hidden text-sm text-muted sm:inline">{user.display_name ?? t(`role.${user.role}`)}</span>
            <LogoutButton label={t('sign_out')} />
          </div>
        </header>
        <main className="flex-1 p-4 md:p-6">{children}</main>
      </div>
    </div>
  );
}
