'use client';

/** Non-sensitive role hint cookie set alongside the httpOnly session (see /api/auth/verify). */
export function clientRole(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(/(?:^|;\s*)sm_role=([^;]+)/);
  return match ? decodeURIComponent(match[1]!) : null;
}

// Fictional demo personas (seeded). Used only to offer "use demo document" in DEMO mode.
const DEMO_PERSONA_BY_PHONE: Record<string, string> = {
  '9000000001': 'savitaben',
  '9000000002': 'ramesh',
  '9000000003': 'kavya',
  '9000000004': 'imran',
  '9000000005': 'edge',
};

export function demoPersonaFor(phone: string | undefined | null): string | null {
  return phone ? (DEMO_PERSONA_BY_PHONE[phone] ?? null) : null;
}
