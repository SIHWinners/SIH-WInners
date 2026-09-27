'use client';

import { db, type OutboxRow } from './local-db';

/**
 * Offline write queue (claim C13). A request that cannot reach the server is stored in
 * IndexedDB and retried with backoff when the connection returns. Every queued request
 * carries the draft's `client_uuid`, and the server treats that as an idempotency key, so
 * a retry after a half-delivered response can never create a second application.
 */
const MAX_ATTEMPTS = 8;
const BASE_DELAY_MS = 2_000;

export interface SyncState {
  pending: number;
  syncing: boolean;
  lastError: string | null;
}

type Listener = (state: SyncState) => void;
const listeners = new Set<Listener>();
let state: SyncState = { pending: 0, syncing: false, lastError: null };

function publish(patch: Partial<SyncState>) {
  state = { ...state, ...patch };
  listeners.forEach((listener) => listener(state));
}

export function subscribeToSync(listener: Listener): () => void {
  listeners.add(listener);
  listener(state);
  return () => listeners.delete(listener);
}

export async function refreshPendingCount(): Promise<number> {
  const pending = await db.outbox.count();
  publish({ pending });
  return pending;
}

/** Queues a write for later. Returns the queue id so callers can show "saved on this phone". */
export async function queueWrite(entry: Omit<OutboxRow, 'id' | 'attempts' | 'nextAttemptAt' | 'createdAt'>): Promise<number> {
  const id = await db.outbox.add({ ...entry, attempts: 0, nextAttemptAt: Date.now(), createdAt: Date.now() });
  await refreshPendingCount();
  return id as number;
}

/** Sends a write now, or queues it if the network is unreachable. */
export async function writeOrQueue(path: string, body: unknown, clientUuid: string): Promise<Response | null> {
  const payload = JSON.stringify(body);
  if (typeof navigator !== 'undefined' && !navigator.onLine) {
    await queueWrite({ clientUuid, method: 'POST', path, body: payload });
    return null;
  }
  try {
    const res = await fetch(`/api${path}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: payload });
    // 5xx means the server is there but unhappy: queue it rather than losing the answer.
    if (res.status >= 500) {
      await queueWrite({ clientUuid, method: 'POST', path, body: payload });
      return null;
    }
    return res;
  } catch {
    await queueWrite({ clientUuid, method: 'POST', path, body: payload });
    return null;
  }
}

let running = false;

/** Flushes what is queued. Safe to call often: only one pass runs at a time. */
export async function flushOutbox(): Promise<{ sent: number; left: number }> {
  if (running || (typeof navigator !== 'undefined' && !navigator.onLine)) {
    return { sent: 0, left: await refreshPendingCount() };
  }
  running = true;
  publish({ syncing: true });
  let sent = 0;
  try {
    const due = await db.outbox.where('nextAttemptAt').below(Date.now() + 1).sortBy('createdAt');
    for (const row of due) {
      try {
        const res = await fetch(`/api${row.path}`, {
          method: row.method,
          headers: { 'content-type': 'application/json' },
          body: row.body,
        });
        if (res.ok || (res.status >= 400 && res.status < 500 && res.status !== 408 && res.status !== 429)) {
          // Accepted, or refused for a reason retrying cannot fix (the UI shows it on next load).
          await db.outbox.delete(row.id!);
          sent += res.ok ? 1 : 0;
          if (!res.ok) publish({ lastError: `${row.path}: ${res.status}` });
          continue;
        }
        throw new Error(`HTTP ${res.status}`);
      } catch (err) {
        const attempts = row.attempts + 1;
        const message = err instanceof Error ? err.message : 'network';
        if (attempts >= MAX_ATTEMPTS) {
          await db.outbox.update(row.id!, { attempts, lastError: `gave up: ${message}` });
          publish({ lastError: `gave up after ${attempts} tries` });
        } else {
          await db.outbox.update(row.id!, {
            attempts,
            lastError: message,
            nextAttemptAt: Date.now() + BASE_DELAY_MS * 2 ** (attempts - 1),
          });
        }
      }
    }
  } finally {
    running = false;
    publish({ syncing: false });
  }
  return { sent, left: await refreshPendingCount() };
}

/** Starts background syncing: on reconnect, on tab focus, and on a slow timer. */
export function startSync(): () => void {
  const flush = () => void flushOutbox();
  flush();
  const timer = setInterval(flush, 30_000);
  window.addEventListener('online', flush);
  document.addEventListener('visibilitychange', () => document.visibilityState === 'visible' && flush());
  return () => {
    clearInterval(timer);
    window.removeEventListener('online', flush);
  };
}
