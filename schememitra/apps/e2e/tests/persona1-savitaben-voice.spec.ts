import { expect, test } from '@playwright/test';

import { expectNoSeriousA11yViolations, setLocale, signInWithDemoOtp } from './helpers';

// Persona 1 — Savitaben Rathwa, Dahod (fictional). Gujarati voice intake, spoken read-back,
// submit. Claims exercised: C6, C7, C17 (+ C1, C2, C3, C5, C9, C16, C18 on the way).
// The first turn goes through the microphone (Chromium's fake audio device); with
// BHASHINI_MODE=sandbox the transcript is the scripted line, visibly labelled SANDBOX.
test.use({
  launchOptions: { args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream'] },
  permissions: ['geolocation', 'microphone'],
});

test('Savitaben applies by voice in Gujarati within 3 minutes', async ({ page }) => {
  const started = Date.now();
  await setLocale(page, 'gu');
  await page.goto('/');
  await page.locator('a[href="/apply/voice"]').first().click();

  await expect(page).toHaveURL(/\/apply\/voice/);
  await expect(page.getByTestId('voice-reply').first()).toContainText('નમસ્તે');
  await expectNoSeriousA11yViolations(page);

  // Turn 1 by microphone.
  const mic = page.getByTestId('voice-mic');
  await mic.click();
  await expect(mic).toHaveAttribute('aria-pressed', 'true');
  await page.waitForTimeout(1_500);
  await mic.click();
  await expect(page.getByTestId('voice-user-line').first()).toContainText('સવિતાબેન રાઠવા');
  await expect(page.getByText(/^SANDBOX/).first()).toBeVisible();
  await expect(page.getByTestId('voice-field-district_code')).toHaveAttribute('data-filled', 'true');
  await expect(page.getByTestId('voice-field-district_code')).toContainText('દાહોદ');

  // Turns 2–6 with the demo utterance chips (same text a speaker would say).
  for (let i = 0; i < 5; i++) {
    const chip = page.getByTestId('voice-demo-chip');
    await expect(chip).toBeEnabled();
    const before = await page.getByTestId('voice-user-line').count();
    await chip.click();
    await expect(page.getByTestId('voice-user-line')).toHaveCount(before + 1);
  }
  await expect(page.getByTestId('voice-filled')).toContainText('13 માંથી 13');
  for (const field of ['full_name', 'age', 'gender', 'social_category', 'business_type', 'project_cost_paise', 'loan_needed_paise',
    'annual_family_income_paise', 'education_level', 'shg_member', 'existing_loans']) {
    await expect(page.getByTestId(`voice-field-${field}`)).toHaveAttribute('data-filled', 'true');
  }
  await expect(page.getByTestId('voice-field-loan_needed_paise')).toContainText('₹60,000');
  await expectNoSeriousA11yViolations(page);
  await page.getByTestId('voice-finish').click();

  // Rule Check → Money → Partner
  await expect(page).toHaveURL(/\/apply\/rules/);
  await expect(page.getByTestId('scheme-NSFDC_MICRO_CREDIT')).toBeVisible();
  await page.getByTestId('choose-NSFDC_MICRO_CREDIT').click();
  await expect(page).toHaveURL(/\/apply\/money/);
  await expect(page.getByTestId('funding-split')).toContainText('90%');
  await page.getByTestId('money-next').click();
  await expect(page).toHaveURL(/\/apply\/partner/);
  await page.getByTestId('partner-list').locator('[data-testid^="choose-partner-"]').first().click();
  await page.getByTestId('partner-next').click();

  // Send: sign in, documents, spoken read-back confirmed by voice, consent, submit.
  await expect(page).toHaveURL(/\/apply\/send/);
  await page.locator('a[href^="/login"]').first().click();
  await signInWithDemoOtp(page, '9000000001');
  await expect(page).toHaveURL(/\/apply\/send/);

  const docButtons = page.locator('[data-testid^="demo-doc-"]');
  await expect(docButtons.first()).toBeVisible();
  const docCount = await docButtons.count();
  for (let i = 0; i < docCount; i++) {
    await page.locator('[data-testid^="demo-doc-"]:not([disabled])').first().click();
    await page.waitForTimeout(400);
  }
  const readiness = page.getByTestId('readiness');
  await expect(readiness).toContainText('તમારી ફાઇલ મોકલવા માટે તૈયાર છે.', { timeout: 40_000 });

  const readback = page.getByTestId('readback');
  await expect(page.getByTestId('readback-text')).toContainText('સવિતાબેન રાઠવા');
  await page.getByTestId('readback-demo-chip').click();
  await expect(page.getByTestId('readback-reply')).toContainText('હા, બરાબર છે');
  await expect(readback.getByTestId('readback-confirm')).toHaveClass(/bg-success/);
  await page.getByTestId('consent-agree').check();
  await page.getByTestId('submit-application').click();

  await expect(page).toHaveURL(/\/apply\/done/);
  const tid = (await page.getByTestId('tracking-id').innerText()).trim();
  expect(tid).toMatch(/^SM-GJ-\d{2}-[0-9A-Z]{7}$/);
  expect(Date.now() - started).toBeLessThan(180_000);
});
