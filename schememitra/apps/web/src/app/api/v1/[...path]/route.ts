import { NextResponse, type NextRequest } from 'next/server';

import { GATEWAY_URL, SESSION_COOKIE } from '@/lib/session';

// Same-origin proxy to the gateway. Browser code calls /api/v1/...; this handler attaches
// the session token from the httpOnly cookie and streams the response back.
const HOP_BY_HOP = new Set(['connection', 'keep-alive', 'transfer-encoding', 'upgrade', 'host', 'cookie']);

async function forward(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const target = `${GATEWAY_URL}/v1/${path.map(encodeURIComponent).join('/')}${req.nextUrl.search}`;
  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value);
  });
  const token = req.cookies.get(SESSION_COOKIE)?.value;
  if (token) headers.set('authorization', `Bearer ${token}`);
  headers.set('x-forwarded-for', req.headers.get('x-forwarded-for') ?? '127.0.0.1');

  const hasBody = !['GET', 'HEAD'].includes(req.method);
  try {
    const upstream = await fetch(target, {
      method: req.method,
      headers,
      body: hasBody ? req.body : undefined,
      // Node's fetch needs this to stream a request body.
      ...(hasBody ? { duplex: 'half' } : {}),
      cache: 'no-store',
    } as RequestInit);
    const out = new Headers();
    upstream.headers.forEach((value, key) => {
      // fetch() already decompressed the body, so the upstream encoding and length no longer apply.
      const k = key.toLowerCase();
      if (!HOP_BY_HOP.has(k) && k !== 'content-encoding' && k !== 'content-length') out.set(key, value);
    });
    return new NextResponse(upstream.body, { status: upstream.status, headers: out });
  } catch {
    return NextResponse.json(
      { status: 503, title: 'Service unavailable', user_message_key: 'errors.server_down' },
      { status: 503, headers: { 'content-type': 'application/problem+json' } },
    );
  }
}

export { forward as DELETE, forward as GET, forward as PATCH, forward as POST, forward as PUT };
