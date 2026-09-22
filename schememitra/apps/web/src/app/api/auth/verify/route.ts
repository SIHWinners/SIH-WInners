import { NextResponse, type NextRequest } from 'next/server';

import { GATEWAY_URL, ROLE_COOKIE, SESSION_COOKIE } from '@/lib/session';

export async function POST(req: NextRequest) {
  const body = await req.text();
  const upstream = await fetch(`${GATEWAY_URL}/v1/auth/otp/verify`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body,
    cache: 'no-store',
  }).catch(() => null);
  if (!upstream) {
    return NextResponse.json({ status: 503, user_message_key: 'errors.server_down' }, { status: 503 });
  }
  const data = await upstream.json();
  if (!upstream.ok) return NextResponse.json(data, { status: upstream.status });

  const res = NextResponse.json({ user: data.user });
  const secure = process.env.NODE_ENV === 'production' && process.env.INSECURE_COOKIES !== '1';
  res.cookies.set(SESSION_COOKIE, data.access_token, {
    httpOnly: true,
    sameSite: 'lax',
    secure,
    path: '/',
    maxAge: data.expires_in,
  });
  // Non-sensitive hint so client components can pick the right nav without a round trip.
  res.cookies.set(ROLE_COOKIE, data.user.role, { sameSite: 'lax', secure, path: '/', maxAge: data.expires_in });
  return res;
}
