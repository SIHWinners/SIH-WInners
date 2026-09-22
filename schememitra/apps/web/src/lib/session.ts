import 'server-only';

import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

export const SESSION_COOKIE = 'sm_session';
export const ROLE_COOKIE = 'sm_role';
export const GATEWAY_URL = process.env.GATEWAY_URL ?? 'http://127.0.0.1:8080';

export type Role = 'citizen' | 'csc_operator' | 'partner_officer' | 'admin' | 'policy_viewer';

export interface SessionUser {
  id: string;
  role: Role;
  partner_id: string | null;
  csc_id: string | null;
  display_name: string | null;
  preferred_lang: string;
}

/** The JWT never reaches browser JavaScript: it lives in an httpOnly cookie and is attached
 * to gateway calls by the Next.js server (XSS cannot exfiltrate it). */
export async function sessionToken(): Promise<string | null> {
  return (await cookies()).get(SESSION_COOKIE)?.value ?? null;
}

export async function gatewayFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const token = await sessionToken();
  const headers = new Headers(init.headers);
  if (token) headers.set('authorization', `Bearer ${token}`);
  return fetch(`${GATEWAY_URL}${path}`, { ...init, headers, cache: 'no-store' });
}

export async function currentUser(): Promise<SessionUser | null> {
  if (!(await sessionToken())) return null;
  const res = await gatewayFetch('/v1/auth/me').catch(() => null);
  if (!res || !res.ok) return null;
  return (await res.json()) as SessionUser;
}

export async function requireRole(...roles: Role[]): Promise<SessionUser> {
  const user = await currentUser();
  if (!user) redirect('/login');
  if (!roles.includes(user.role)) redirect(homeFor(user.role));
  return user;
}

export function homeFor(role: Role): string {
  return {
    citizen: '/apply',
    csc_operator: '/csc',
    partner_officer: '/partner',
    admin: '/admin',
    policy_viewer: '/insights',
  }[role];
}
