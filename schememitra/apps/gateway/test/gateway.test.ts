import Fastify, { type FastifyInstance } from 'fastify';
import { SignJWT } from 'jose';
import type { AddressInfo } from 'node:net';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import WebSocket from 'ws';

import { routePolicy } from '../src/auth.js';
import { loadConfig } from '../src/config.js';
import { buildServer } from '../src/server.js';
import { normaliseInbound } from '../src/sms.js';

const secret = 'test-secret-0123456789abcdef0123456789';
let core: FastifyInstance;
let gw: FastifyInstance;
let gwUrl: string;

async function token(role: string, partnerId: string | null = null): Promise<string> {
  return new SignJWT({ app_metadata: { app_role: role, partner_id: partnerId } })
    .setProtectedHeader({ alg: 'HS256' })
    .setSubject('00000000-0000-7000-8000-000000000001')
    .setAudience('authenticated')
    .setExpirationTime('1h')
    .sign(new TextEncoder().encode(secret));
}

beforeAll(async () => {
  core = Fastify();
  core.get('/healthz', async () => ({ status: 'ok' }));
  core.post('/v1/auth/otp/request', async (req) => ({ echoed: req.body }));
  core.get('/v1/eligibility/ping', async () => ({ pong: true }));
  core.get('/v1/admin/flags', async () => ({ flags: {} }));
  core.get('/v1/track/:tid', async (req) => ({
    tracking_id: (req.params as { tid: string }).tid,
    status: 'submitted',
  }));
  core.get('/v1/system/status', async () => ({ adapters: [{ name: 'sms', breaker: 'open' }] }));
  core.post('/v1/sms/inbound', async (req) => ({ got: req.body }));
  await core.listen({ port: 0, host: '127.0.0.1' });
  const corePort = (core.server.address() as AddressInfo).port;

  const cfg = {
    ...loadConfig({}),
    env: 'test',
    jwtSecret: secret,
    internalSecret: 'int',
    coreUrl: `http://127.0.0.1:${corePort}`,
    otpLimitPerHour: 3,
  };
  gw = await buildServer(cfg);
  await gw.listen({ port: 0, host: '127.0.0.1' });
  gwUrl = `127.0.0.1:${(gw.server.address() as AddressInfo).port}`;
});

afterAll(async () => {
  await gw.close();
  await core.close();
});

describe('route policy', () => {
  it('protects role-scoped prefixes and leaves public ones open', () => {
    expect(routePolicy('/v1/admin/flags')).toEqual({ protected: true, roles: ['admin'] });
    expect(routePolicy('/v1/eligibility/evaluate').protected).toBe(false);
    expect(routePolicy('/v1/partner/scan').roles).toContain('partner_officer');
  });
});

describe('gateway', () => {
  it('proxies public routes to the core with security headers', async () => {
    const res = await gw.inject({ method: 'GET', url: '/v1/eligibility/ping' });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toEqual({ pong: true });
    expect(res.headers['strict-transport-security']).toContain('max-age');
  });

  it('rejects missing or wrong-role tokens on protected routes', async () => {
    expect((await gw.inject({ method: 'GET', url: '/v1/admin/flags' })).statusCode).toBe(401);
    const citizen = await token('citizen');
    const denied = await gw.inject({
      method: 'GET',
      url: '/v1/admin/flags',
      headers: { authorization: `Bearer ${citizen}` },
    });
    expect(denied.statusCode).toBe(403);
    const admin = await token('admin');
    const ok = await gw.inject({
      method: 'GET',
      url: '/v1/admin/flags',
      headers: { authorization: `Bearer ${admin}` },
    });
    expect(ok.statusCode).toBe(200);
  });

  it('rate-limits OTP requests per phone number', async () => {
    const send = (phone: string) =>
      gw.inject({ method: 'POST', url: '/v1/auth/otp/request', payload: { phone } });
    for (let i = 0; i < 3; i++) expect((await send('9876500009')).statusCode).toBe(200);
    const limited = await send('9876500009');
    expect(limited.statusCode).toBe(429);
    expect(limited.json().user_message_key).toBe('errors.rate_limited');
    expect((await send('9876500010')).statusCode).toBe(200);
  });

  it('normalises SMS provider payloads before handing to the core', async () => {
    expect(normaliseInbound({ From: '+919876500001', Body: 'STATUS SM-GJ-26-K7Q2MX9' })?.provider).toBe(
      'twilio',
    );
    expect(normaliseInbound({ nope: 1 })).toBeNull();
    const res = await gw.inject({
      method: 'POST',
      url: '/v1/sms/inbound',
      payload: { mobile: '9876500001', message: 'hi' },
    });
    expect(res.json().got).toEqual({ from: '9876500001', text: 'hi', provider: 'msg91' });
  });

  it('aggregates tracking status with degraded adapters for the BFF', async () => {
    const res = await gw.inject({ method: 'GET', url: '/bff/track/SM-GJ-26-K7Q2MX9' });
    expect(res.json()).toMatchObject({ status: 'submitted', degraded: ['sms'] });
  });

  it('pushes internal events to authorised WebSocket subscribers', async () => {
    const ws = new WebSocket(`ws://${gwUrl}/ws`);
    const frames: Array<Record<string, unknown>> = [];
    ws.on('message', (d) => frames.push(JSON.parse(d.toString())));
    await new Promise((r) => ws.once('open', r));
    ws.send(JSON.stringify({ op: 'subscribe', channel: 'partner:p1' }));
    ws.send(JSON.stringify({ op: 'subscribe', channel: 'track:SM-GJ-26-K7Q2MX9' }));
    await new Promise((r) => setTimeout(r, 150));
    expect(frames).toContainEqual({ op: 'error', channel: 'partner:p1', reason: 'forbidden' });

    const denied = await gw.inject({
      method: 'POST',
      url: '/internal/events',
      payload: {},
      headers: { 'x-internal-secret': 'bad' },
    });
    expect(denied.statusCode).toBe(403);
    const pub = await gw.inject({
      method: 'POST',
      url: '/internal/events',
      headers: { 'x-internal-secret': 'int' },
      payload: { channel: 'track:SM-GJ-26-K7Q2MX9', event: 'status', data: { status: 'sanctioned' } },
    });
    expect(pub.json()).toEqual({ delivered: 1 });
    await new Promise((r) => setTimeout(r, 150));
    expect(frames.at(-1)).toMatchObject({ event: 'status', data: { status: 'sanctioned' } });
    ws.close();
  });
});
