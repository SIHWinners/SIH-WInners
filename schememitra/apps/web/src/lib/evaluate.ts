'use client';

import type { ApplicantFacts, EvaluateResponse } from '@sm/contracts/client';
import { evaluateBundle, type RulesBundle } from '@sm/contracts/offline';

import { api, ApiError, unwrap } from './api';

const BUNDLE_KEY = 'rules-bundle';

async function cachedBundle(): Promise<RulesBundle | null> {
  const { db } = await import('./local-db');
  const row = await db.kv.get(BUNDLE_KEY);
  return row ? (JSON.parse(row.value) as RulesBundle) : null;
}

/** Refreshes the offline rule bundle using its ETag, so a 304 costs a few hundred bytes on 2G. */
export async function refreshRulesBundle(): Promise<void> {
  try {
    const current = await cachedBundle();
    const res = await fetch('/api/v1/rules/bundle', {
      headers: current ? { 'if-none-match': `"${current.etag}"` } : {},
    });
    if (res.status === 200) {
      const { db } = await import('./local-db');
      await db.kv.put({ key: BUNDLE_KEY, value: await res.text(), updatedAt: Date.now() });
    }
  } catch {
    /* offline: keep the last bundle */
  }
}

/**
 * Server evaluation when online; the same rules evaluated on the device when not.
 * Offline results are provisional and re-checked automatically when the network returns.
 */
export async function evaluateFacts(facts: Partial<ApplicantFacts>): Promise<EvaluateResponse & { provisional: boolean; at: number }> {
  try {
    const data = await unwrap(api.POST('/v1/eligibility/evaluate', { body: { applicant: facts as ApplicantFacts } }));
    void refreshRulesBundle();
    return { ...data, provisional: false, at: Date.now() };
  } catch (err) {
    if (err instanceof ApiError && err.problem.status !== 0 && err.problem.status < 500) throw err;
    const bundle = await cachedBundle();
    if (!bundle) throw err;
    return { ...(evaluateBundle(bundle, facts) as unknown as EvaluateResponse), provisional: true, at: Date.now() };
  }
}
