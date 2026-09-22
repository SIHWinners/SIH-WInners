'use client';

import { useRouter } from 'next/navigation';

import { Icon } from './icons';

export function LogoutButton({ label }: { label: string }) {
  const router = useRouter();
  return (
    <button
      type="button"
      className="inline-flex h-9 items-center gap-1.5 rounded-md px-2.5 text-sm font-semibold text-muted hover:bg-surface-alt"
      onClick={async () => {
        await fetch('/api/auth/logout', { method: 'POST' });
        router.replace('/login');
        router.refresh();
      }}
    >
      <Icon name="logout" size={18} />
      <span className="sr-only sm:not-sr-only">{label}</span>
    </button>
  );
}
