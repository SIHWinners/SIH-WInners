import Dexie, { type Table } from 'dexie';

export interface KvRow {
  key: string;
  value: string;
  updatedAt: number;
}

/** Offline mutation queued while the network is down. `clientUuid` is the idempotency key. */
export interface OutboxRow {
  id?: number;
  clientUuid: string;
  method: 'POST' | 'PUT';
  path: string;
  body: string;
  attempts: number;
  nextAttemptAt: number;
  createdAt: number;
  lastError?: string;
}

class LocalDb extends Dexie {
  kv!: Table<KvRow, string>;
  outbox!: Table<OutboxRow, number>;

  constructor() {
    super('schememitra');
    this.version(1).stores({ kv: 'key, updatedAt', outbox: '++id, clientUuid, nextAttemptAt' });
  }
}

export const db = new LocalDb();
