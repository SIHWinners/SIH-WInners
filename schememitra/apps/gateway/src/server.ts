import compress from '@fastify/compress';
import cors from '@fastify/cors';
import helmet from '@fastify/helmet';
import proxy from '@fastify/http-proxy';
import rateLimit from '@fastify/rate-limit';
import websocket from '@fastify/websocket';
import Fastify, { type FastifyInstance, type FastifyRequest } from 'fastify';
import { timingSafeEqual } from 'node:crypto';

import { bearer, routePolicy, verifyToken, type Principal } from './auth.js';
import type { GatewayConfig } from './config.js';
import { Hub, type HubEvent } from './hub.js';
import { normaliseInbound } from './sms.js';

declare module 'fastify' {
  interface FastifyRequest {
    principal: Principal | null;
  }
}

const PII_PATHS = ['req.headers.authorization', 'req.body.phone', 'req.body.code', 'req.body.from'];

function safeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  return ab.length === bb.length && timingSafeEqual(ab, bb);
}

function phoneKey(req: FastifyRequest): string {
  const body = req.body as { phone?: string } | undefined;
  const digits = (body?.phone ?? '').replace(/\D/g, '').slice(-10);
  return digits ? `phone:${digits}` : `ip:${req.ip}`;
}

export async function buildServer(cfg: GatewayConfig, hub = new Hub()): Promise<FastifyInstance> {
  const app = Fastify({
    logger: cfg.env === 'test' ? false : { level: 'info', redact: { paths: PII_PATHS, censor: '[REDACTED]' } },
    trustProxy: true,
    bodyLimit: 12 * 1024 * 1024,
  });

  await app.register(helmet, {
    contentSecurityPolicy: { directives: { defaultSrc: ["'none'"], frameAncestors: ["'none'"] } },
    hsts: { maxAge: 31536000, includeSubDomains: true },
    crossOriginResourcePolicy: { policy: 'same-site' },
  });
  await app.register(cors, { origin: cfg.corsOrigins, credentials: true });
  await app.register(compress, { encodings: ['br', 'gzip'], threshold: 800 });
  await app.register(rateLimit, {
    hook: 'preHandler', // after auth, so signed-in users are limited per user, not per shared IP
    max: cfg.rateLimitPerMinute,
    timeWindow: '1 minute',
    keyGenerator: (req) => (req.principal ? `user:${req.principal.userId}` : `ip:${req.ip}`),
    errorResponseBuilder: (_req, ctx) => ({
      type: 'https://schememitra.dev/problems/errors-rate_limited',
      title: 'Too many requests',
      status: 429,
      user_message_key: 'errors.rate_limited',
      retry_after_s: Math.ceil(ctx.ttl / 1000),
    }),
  });
  await app.register(websocket);

  app.decorateRequest('principal', null);

  // Verify the session once at the edge; the core verifies again (defence in depth).
  app.addHook('onRequest', async (req, reply) => {
    const token = bearer(req.headers.authorization);
    req.principal = token ? await verifyToken(token, cfg.jwtSecret) : null;
    const path = req.url.split('?')[0] ?? '';
    const policy = routePolicy(path);
    if (!policy.protected) return;
    if (!req.principal) {
      return reply.code(401).type('application/problem+json').send({
        title: 'Sign-in required', status: 401, user_message_key: 'errors.unauthorized',
      });
    }
    if (policy.roles && !policy.roles.includes(req.principal.role)) {
      return reply.code(403).type('application/problem+json').send({
        title: 'Forbidden', status: 403, user_message_key: 'errors.forbidden',
      });
    }
  });

  app.get('/healthz', async () => ({ status: 'ok', service: 'gateway' }));

  app.get('/readyz', async (_req, reply) => {
    try {
      const res = await fetch(`${cfg.coreUrl}/healthz`, { signal: AbortSignal.timeout(2000) });
      return reply.code(res.ok ? 200 : 503).send({ status: res.ok ? 'ready' : 'core-unhealthy' });
    } catch {
      return reply.code(503).send({ status: 'core-unreachable' });
    }
  });

  // Core → gateway status events, fanned out to WebSocket subscribers.
  app.post('/internal/events', async (req, reply) => {
    const secret = String(req.headers['x-internal-secret'] ?? '');
    if (!safeEqual(secret, cfg.internalSecret)) return reply.code(403).send({ status: 403 });
    const evt = req.body as HubEvent;
    return { delivered: hub.publish(evt) };
  });

  app.get('/internal/hub', async (req, reply) => {
    if (req.principal?.role !== 'admin') return reply.code(403).send({ status: 403 });
    return hub.stats();
  });

  // Client protocol: {"op":"subscribe","channel":"track:SM-GJ-26-K7Q2MX9","token":"..."}.
  app.get('/ws', { websocket: true }, (socket) => {
    socket.on('message', async (raw: Buffer) => {
      let msg: { op?: string; channel?: string; token?: string };
      try {
        msg = JSON.parse(raw.toString());
      } catch {
        return;
      }
      if (msg.op === 'ping') {
        socket.send(JSON.stringify({ op: 'pong' }));
        return;
      }
      if (msg.op !== 'subscribe' || !msg.channel) return;
      const principal = msg.token ? await verifyToken(msg.token, cfg.jwtSecret) : null;
      if (!hub.canSubscribe(msg.channel, principal)) {
        socket.send(JSON.stringify({ op: 'error', channel: msg.channel, reason: 'forbidden' }));
        return;
      }
      hub.subscribe(msg.channel, socket);
      socket.send(JSON.stringify({ op: 'subscribed', channel: msg.channel }));
    });
  });

  // SMS provider webhook: normalise vendor payloads, then hand to the core.
  app.post(
    '/v1/sms/inbound',
    { config: { rateLimit: { max: 120, timeWindow: '1 minute' } } },
    async (req, reply) => {
      const sms = normaliseInbound(req.body);
      if (!sms) return reply.code(422).send({ status: 422, user_message_key: 'errors.validation' });
      const res = await fetch(`${cfg.coreUrl}/v1/sms/inbound`, {
        method: 'POST',
        headers: { 'content-type': 'application/json', 'x-internal-secret': cfg.internalSecret },
        body: JSON.stringify(sms),
        signal: AbortSignal.timeout(8000),
      });
      return reply.code(res.status).type('application/json').send(await res.text());
    },
  );

  // BFF: one round trip for the citizen tracking screen on 2G (status + adapter health).
  app.get('/bff/track/:tid', async (req, reply) => {
    const { tid } = req.params as { tid: string };
    const [track, status] = await Promise.allSettled([
      fetch(`${cfg.coreUrl}/v1/track/${encodeURIComponent(tid)}`, { signal: AbortSignal.timeout(4000) }),
      fetch(`${cfg.coreUrl}/v1/system/status`, { signal: AbortSignal.timeout(4000) }),
    ]);
    if (track.status !== 'fulfilled' || !track.value.ok) {
      const code = track.status === 'fulfilled' ? track.value.status : 502;
      return reply.code(code).send({ status: code, user_message_key: 'errors.track_not_found' });
    }
    const body = (await track.value.json()) as Record<string, unknown>;
    type Adapter = { name: string; breaker: string };
    const sys =
      status.status === 'fulfilled' && status.value.ok
        ? ((await status.value.json()) as { adapters: Adapter[] })
        : null;
    const degraded = (sys?.adapters ?? []).filter((a) => a.breaker !== 'closed').map((a) => a.name);
    return { ...body, degraded };
  });

  // OTP routes are forwarded explicitly (not streamed) so the limiter can key on the phone
  // number: stops brute force and SMS pumping from rotating IPs.
  for (const step of ['request', 'verify'] as const) {
    app.post(
      `/v1/auth/otp/${step}`,
      { config: { rateLimit: { max: cfg.otpLimitPerHour, timeWindow: '1 hour', keyGenerator: phoneKey } } },
      async (req, reply) => {
        const res = await fetch(`${cfg.coreUrl}/v1/auth/otp/${step}`, {
          method: 'POST',
          headers: { 'content-type': 'application/json', 'x-forwarded-for': req.ip },
          body: JSON.stringify(req.body ?? {}),
          signal: AbortSignal.timeout(8000),
        });
        return reply
          .code(res.status)
          .type(res.headers.get('content-type') ?? 'application/json')
          .send(await res.text());
      },
    );
  }

  await app.register(proxy, {
    upstream: cfg.coreUrl,
    prefix: '/v1',
    rewritePrefix: '/v1',
    http: { requestOptions: { timeout: 60_000 } },
    replyOptions: {
      rewriteRequestHeaders: (req, headers) => ({
        ...headers,
        'x-forwarded-for': req.ip,
        'x-gateway': 'schememitra',
      }),
    },
  });

  return app;
}
