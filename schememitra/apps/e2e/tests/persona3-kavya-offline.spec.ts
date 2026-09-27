import { expect, test } from '@playwright/test';

import { answer, setLocale } from './helpers';

// Persona 3 — Kavya Selvam, Madurai (fictional). Tamil, and the village has no data signal.
// Claims: C13 (offline + SMS), C14 (works on a dead 2G cell), C5.
// The offline half needs the service worker, which `next dev` deliberately does not register,
// so those steps run against a production build (`node scripts/make.mjs demo`).

const KAVYA = '9000000003';

test('Kavya fills the form with no signal and sends it by SMS', async ({ page, context }) => {
  const built = await page.request.get('/sw.js').then((r) => r.ok()).catch(() => false);
  test.skip(!built, 'needs the production build (service worker): run `node scripts/make.mjs demo`');

  await setLocale(page, 'ta');
  await page.goto('/');
  // Warm the shell and the offline rule bundle, the way a first visit at the CSC or a bus stop would.
  await page.goto('/apply');
  // Wait for the service worker to install and take control; until it does, a reload still
  // needs the network. A real first visit is the same: install, then it works offline.
  await page.waitForFunction(async () => Boolean((await navigator.serviceWorker.ready).active), undefined, { timeout: 30_000 });
  await page.reload();
  await page.waitForFunction(() => Boolean(navigator.serviceWorker.controller), undefined, { timeout: 30_000 });
  // The app stores the rule bundle (and the district list) in IndexedDB on load.
  await page.waitForFunction(
    () =>
      new Promise<boolean>((resolve) => {
        const open = indexedDB.open('schememitra');
        open.onsuccess = () => {
          const database = open.result;
          if (!database.objectStoreNames.contains('kv')) return resolve(false);
          const row = database.transaction('kv').objectStore('kv').get('rules-bundle');
          row.onsuccess = () => resolve(Boolean(row.result));
          row.onerror = () => resolve(false);
        };
        open.onerror = () => resolve(false);
      }),
    undefined,
    { timeout: 30_000 },
  );

  // The signal drops.
  await context.setOffline(true);
  await page.reload();
  await expect(page.getByTestId('offline-status')).toContainText('இணையம் இல்லை');

  await answer(page, { text: 'Kavya Selvam' });
  await answer(page, { text: '19' });
  await answer(page, { choice: 'பெண்' });
  await answer(page, { choice: 'பிற்படுத்தப்பட்ட வகுப்பு (OBC)' });
  await answer(page, { choice: 'இல்லை' });
  await answer(page, { choice: 'தமிழ்நாடு' });
  await answer(page, { choice: 'Madurai' });  // district names come from the reference data, in English
  await answer(page, { text: '625001' });
  await answer(page, { text: '150000' });
  await answer(page, { choice: '12-ஆம் வகுப்பு' });
  await answer(page, { choice: 'கல்வி / படிப்புக் கட்டணம்' });
  await answer(page, { choice: 'ஆம்' });
  await answer(page, { text: '240000' });
  await answer(page, { text: '200000' });
  await answer(page, { choice: 'இல்லை' });
  await answer(page, { choice: 'இல்லை' });
  await answer(page, { text: KAVYA });

  // Eligibility was worked out on the phone from the cached rule bundle, and says so.
  await expect(page).toHaveURL(/\/apply\/rules/);
  await expect(page.getByTestId('scheme-NBCFDC_EDUCATION_LOAN')).toBeVisible();
  await expect(page.getByText(/தற்காலிகம்/).first()).toBeVisible();

  await page.getByTestId('choose-NBCFDC_EDUCATION_LOAN').click();
  await expect(page).toHaveURL(/\/apply\/money/);
  await expect(page.getByTestId('emi-value')).toContainText('₹'); // the maths runs on the phone too
  await page.getByTestId('money-next').click();
  await page.getByTestId('partner-next').click().catch(() => undefined);

  // With no way to reach the server, the send screen offers the SMS route.
  await page.goto('/apply/send').catch(() => undefined);
  const fallback = page.getByTestId('sms-fallback');
  await expect(fallback).toBeVisible();
  const wire = (await page.getByTestId('sms-fallback-body').innerText()).trim();
  expect(wire.startsWith('SM1*')).toBe(true);
  expect(wire).toContain('d=TN-MDU');
  expect(wire).toContain('l=200000');
  expect(wire.split('\n').length).toBeLessThanOrEqual(3);
  await expect(page.getByTestId('sms-fallback-send')).toHaveAttribute('href', /^sms:/);

  // Back on the network, the queued work goes out by itself.
  await context.setOffline(false);
  await page.goto('/track');
  await expect(page.getByTestId('offline-status')).toBeHidden({ timeout: 15_000 });
});

test('a mistyped tracking ID is caught before it reaches the database', async ({ request }) => {
  // People read these IDs off an SMS and type them back in, so the check character matters (C9).
  const wellFormedButUnknown = await request.get('/api/v1/track/SM-TN-26-K7Q2MX9');
  expect([404, 422]).toContain(wellFormedButUnknown.status());
  const typo = await request.get('/api/v1/track/SM-TN-26-K7Q2MX8');
  expect(typo.status()).toBe(422);
  const nonsense = await request.get('/api/v1/track/hello');
  expect(nonsense.status()).toBe(422);
});
