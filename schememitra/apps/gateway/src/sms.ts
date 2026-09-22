import { z } from 'zod';

/** Normalises inbound SMS webhooks from different providers into one shape for the core. */
const Msg91 = z.object({ mobile: z.string(), message: z.string(), keyword: z.string().optional() });
const Twilio = z.object({ From: z.string(), Body: z.string() });
const Console = z.object({ from: z.string(), text: z.string() });

export interface InboundSms {
  from: string;
  text: string;
  provider: 'msg91' | 'twilio' | 'console';
}

export function normaliseInbound(body: unknown): InboundSms | null {
  const c = Console.safeParse(body);
  if (c.success) return { from: c.data.from, text: c.data.text, provider: 'console' };
  const t = Twilio.safeParse(body);
  if (t.success) return { from: t.data.From, text: t.data.Body, provider: 'twilio' };
  const m = Msg91.safeParse(body);
  if (m.success) return { from: m.data.mobile, text: m.data.message, provider: 'msg91' };
  return null;
}
