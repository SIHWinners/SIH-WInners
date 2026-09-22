import { jwtVerify } from 'jose';

export interface Principal {
  userId: string;
  role: 'citizen' | 'csc_operator' | 'partner_officer' | 'admin' | 'policy_viewer';
  partnerId: string | null;
}

/** Verifies Supabase-shaped HS256 tokens (same claims the core issues in dev). */
export async function verifyToken(token: string, secret: string): Promise<Principal | null> {
  try {
    const { payload } = await jwtVerify(token, new TextEncoder().encode(secret), {
      algorithms: ['HS256'],
      audience: 'authenticated',
    });
    const meta = (payload.app_metadata ?? {}) as Record<string, unknown>;
    if (typeof payload.sub !== 'string') return null;
    return {
      userId: payload.sub,
      role: (meta.app_role as Principal['role']) ?? 'citizen',
      partnerId: (meta.partner_id as string | null) ?? null,
    };
  } catch {
    return null;
  }
}

export function bearer(header: string | undefined): string | null {
  if (!header) return null;
  const [scheme, value] = header.split(' ');
  return scheme?.toLowerCase() === 'bearer' && value ? value : null;
}

// Routes that must carry a valid session. Everything else under /v1 is public
// (eligibility, EMI, partner search, tracking by ID) so citizens can explore before signing in.
const PROTECTED: Array<{ prefix: string; roles?: Principal['role'][] }> = [
  { prefix: '/v1/auth/me' },
  { prefix: '/v1/applications' },
  { prefix: '/v1/documents' },
  { prefix: '/v1/voice/readback' },
  { prefix: '/v1/partner/', roles: ['partner_officer', 'admin'] },
  { prefix: '/v1/csc/', roles: ['csc_operator', 'admin'] },
  { prefix: '/v1/admin/', roles: ['admin'] },
  { prefix: '/v1/insights/', roles: ['policy_viewer', 'admin'] },
];

export function routePolicy(path: string): { protected: boolean; roles?: Principal['role'][] } {
  const match = PROTECTED.find((p) => path.startsWith(p.prefix));
  return match ? { protected: true, roles: match.roles } : { protected: false };
}
