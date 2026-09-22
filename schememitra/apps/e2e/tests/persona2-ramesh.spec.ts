import { expect, test } from '@playwright/test';

import { answer, expectNoSeriousA11yViolations, setLocale, signInWithDemoOtp } from './helpers';

// Persona 2 — Ramesh Meghwal, Barmer (fictional). Claims exercised: C1, C2, C3, C4, C5, C8,
// C9, C10, C11, C16, C18.
test('Ramesh completes the PWA journey end to end', async ({ page }) => {
  await setLocale(page, 'en');
  await page.goto('/');
  await expectNoSeriousA11yViolations(page);
  await page.getByRole('link', { name: /start by typing/i }).click();

  await answer(page, { text: 'Ramesh Kanaram Meghwal' });
  await answer(page, { text: '41' });
  await answer(page, { choice: 'Man' });
  await answer(page, { choice: 'Scheduled Caste (SC)' });
  await answer(page, { choice: 'No' });
  await answer(page, { choice: 'Rajasthan' });
  await answer(page, { choice: 'Barmer' });
  await answer(page, { text: '344001' });
  await answer(page, { text: '180000' });
  await expectNoSeriousA11yViolations(page);
  await answer(page, { choice: 'Up to class 10' });
  await answer(page, { choice: 'Tailoring / garments' });
  await answer(page, { text: '450000' });
  await answer(page, { text: '400000' });
  await answer(page, { choice: 'No' });
  await answer(page, { choice: 'No' });
  await answer(page, { text: '9000000002' });

  // Rule Check (C1, C8)
  await expect(page).toHaveURL(/\/apply\/rules/);
  const scheme = page.getByTestId('scheme-NSFDC_TERM_LOAN');
  await expect(scheme).toBeVisible();
  await scheme.getByText('Why?').click();
  await expect(scheme.getByTestId('rule-trace')).toContainText('Your family income ₹1,80,000 is within the ₹5,00,000 limit');
  await expect(page.getByTestId('near-miss-NSFDC_MICRO_CREDIT')).toContainText('You would qualify if');
  await expectNoSeriousA11yViolations(page);
  await page.getByTestId('choose-NSFDC_TERM_LOAN').click();

  // Money Maths (C2)
  await expect(page).toHaveURL(/\/apply\/money/);
  await expect(page.getByTestId('emi-value')).toContainText('₹');
  await expect(page.getByTestId('funding-split')).toContainText('90%');
  await page.getByTestId('money-next').click();

  // Partner Pick (C3, C4)
  await expect(page).toHaveURL(/\/apply\/partner/);
  await expect(page.getByTestId('partner-skipped')).toContainText('Skipped: low repayment record this quarter');
  const list = page.getByTestId('partner-list');
  await expect(list).toContainText('Barmer District SCA Branch');
  await list.getByRole('button', { name: /choose this lender/i }).first().click();
  await page.getByTestId('partner-next').click();

  // Send & Track: sign in with OTP, documents, readiness, read-back, consent (C5, C9, C10, C11, C16)
  await expect(page).toHaveURL(/\/apply\/send/);
  await page.getByRole('link', { name: /send otp/i }).click();
  await signInWithDemoOtp(page, '9000000002');
  await expect(page).toHaveURL(/\/apply\/send/);

  for (const doc of ['aadhaar', 'caste_certificate', 'income_certificate', 'bank_passbook', 'project_quotation']) {
    const row = page.getByTestId(`doc-${doc}`);
    await row.getByTestId(`demo-doc-${doc}`).click();
    await expect(row.getByText(/Received|Checked|blurry|shine|could not read/).first()).toBeVisible();
  }
  const caste = page.getByTestId('doc-caste_certificate');
  await expect(caste).toContainText('blurry');
  await caste.getByTestId('digilocker-caste_certificate').click();
  await page.getByTestId('digilocker-allow').click();
  await expect(caste).toContainText('Fetched from DigiLocker');

  const readiness = page.getByTestId('readiness');
  await expect(readiness).toContainText('Your file is ready to send.');
  await expect(readiness).toContainText('Relation words like S/O removed');
  await expectNoSeriousA11yViolations(page);

  await expect(page.getByTestId('readback-text')).toContainText('Ramesh Kanaram Meghwal');
  await page.getByTestId('readback-confirm').click();
  await page.getByTestId('consent-agree').check();
  await page.getByTestId('submit-application').click();

  // Done + tracking (C9, C18)
  await expect(page).toHaveURL(/\/apply\/done/);
  const tid = (await page.getByTestId('tracking-id').innerText()).trim();
  expect(tid).toMatch(/^SM-RJ-\d{2}-[0-9A-Z]{7}$/);
  const pdf = await page.request.get(await page.getByRole('link', { name: /download loan file/i }).getAttribute('href') ?? '');
  expect(pdf.headers()['content-type']).toContain('application/pdf');
  expect((await pdf.body()).byteLength).toBeLessThan(400_000);

  await page.goto(`/track/${tid}`);
  await expect(page.getByTestId('track-status')).toHaveText('Sent to lender');
  await expect(page.getByTestId('track-next')).toContainText('The lender will open your file soon.');
});
