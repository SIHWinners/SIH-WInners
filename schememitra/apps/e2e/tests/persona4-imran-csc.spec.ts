import { expect, test } from '@playwright/test';

import { answer, expectNoSeriousA11yViolations, setLocale, signInWithDemoOtp } from './helpers';

// Persona 4 — Imran Qureshi, Lucknow (fictional). Urdu, right-to-left, and he does not own a
// smartphone: a CSC operator fills the form at the counter and prints him a slip.
// Claims: C15 (CSC mode), C12 (the operator's own phone is never treated as the applicant's),
// plus the Urdu RTL layout.

const OPERATOR = '9000000010';
const IMRAN = '9000000004';

test('a CSC operator applies for Imran in Urdu and prints his slip', async ({ page }) => {
  await setLocale(page, 'ur');
  await page.goto('/login');
  await signInWithDemoOtp(page, OPERATOR);

  // The operator lands on their own counter view, not the citizen home.
  await expect(page).toHaveURL(/\/csc/);
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expectNoSeriousA11yViolations(page);

  await page.goto('/csc/new');
  for (const step of ['sit', 'explain', 'consent', 'phone']) await page.getByTestId(`csc-check-${step}`).check();
  await page.getByTestId('csc-start-applicant').click();
  await expect(page).toHaveURL(/\/apply$/);

  await answer(page, { text: 'Imran Qureshi' });
  await answer(page, { text: '31' });
  await answer(page, { choice: 'مرد' });
  await answer(page, { choice: 'دیگر پسماندہ طبقہ (OBC)' });
  await answer(page, { choice: 'ہاں' }); // disability certificate (UDID)
  await answer(page, { text: '60' });
  await answer(page, { choice: 'اتر پردیش' });
  await answer(page, { choice: 'Lucknow' });
  await answer(page, { text: '226001' });
  await answer(page, { text: '140000' });
  await answer(page, { choice: 'دسویں تک' });
  await answer(page, { choice: 'ای رکشہ / ٹرانسپورٹ' });
  await answer(page, { text: '180000' });
  await answer(page, { text: '150000' });
  await answer(page, { choice: 'نہیں' });
  await answer(page, { choice: 'نہیں' });
  await answer(page, { text: IMRAN }); // the applicant's number, not the operator's (C12)

  await expect(page).toHaveURL(/\/apply\/rules/);
  await expect(page.getByTestId('scheme-NDFDC_DIVYANG_SELF_EMPLOYMENT')).toBeVisible();
  await page.getByTestId('choose-NDFDC_DIVYANG_SELF_EMPLOYMENT').click();
  await expect(page).toHaveURL(/\/apply\/money/);
  await page.getByTestId('money-next').click();
  await page.getByTestId('partner-list').locator('[data-testid^="choose-partner-"]').first().click();
  await page.getByTestId('partner-next').click();

  // Papers: the operator scans what Imran brought (demo images stand in for the camera).
  await expect(page).toHaveURL(/\/apply\/send/);
  const types = ['aadhaar', 'disability_certificate', 'income_certificate', 'bank_passbook', 'project_quotation'];
  for (const type of types) {
    const row = page.getByTestId(`doc-${type}`);
    await row.getByTestId(`demo-doc-${type}`).click();
    // Wait for this paper to be read before starting the next one.
    await expect(row.getByText(/مل گیا|جانچا گیا|دوبارہ لیں/).first()).toBeVisible({ timeout: 20_000 });
  }
  await expect(page.getByTestId('readiness')).toContainText('آپ کی فائل بھیجنے کے لیے تیار ہے۔', { timeout: 40_000 });

  // Assisted consent: recorded against the operator, not pretended to be an OTP from Imran.
  await expect(page.getByTestId('assisted-note')).toBeVisible();
  await page.getByTestId('readback-confirm').click();
  await page.getByTestId('consent-agree').check();
  await expectNoSeriousA11yViolations(page);
  await page.getByTestId('submit-application').click();

  await expect(page).toHaveURL(/\/apply\/done/);
  const tid = (await page.getByTestId('tracking-id').innerText()).trim();
  expect(tid).toMatch(/^SM-UP-\d{2}-[0-9A-Z]{7}$/);

  // The counter view shows the applicant, how consent was taken, and prints a slip.
  await page.goto('/csc');
  const row = page.getByTestId(`csc-row-${tid}`);
  await expect(row).toContainText('Imran Qureshi');
  // Officer screens are English + Hindi only (ADR-012), so an Urdu operator sees the English label.
  await expect(row).toContainText('Thumb impression');
  await page.goto('/csc/print');
  await expect(page.getByTestId(`slip-${tid}`)).toContainText(tid);

  // The application records that it came through a CSC counter.
  const detail = await page.request.get('/api/v1/csc/queue?days=1');
  expect(detail.ok()).toBeTruthy();
  const queue = await detail.json();
  const item = queue.items.find((i: { tracking_id: string }) => i.tracking_id === tid);
  expect(item).toMatchObject({ consent_method: 'thumb', lang: 'ur' });
});
