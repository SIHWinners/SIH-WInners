import { expect, test, type APIRequestContext, type Page } from '@playwright/test';

import { expectNoSeriousA11yViolations, setLocale, signInWithDemoOtp } from './helpers';

// Phase 5 gate: a lender scans/opens a file in the portal, asks for a paper, then sanctions it —
// and the citizen's tracking page and SMS reflect each decision within two seconds.
// Claims: C9 (QR + SMS tracking), C21 (only the lender decides), C5 (next step always shown).

const RAMESH = '9000000002';
const BARMER_OFFICER = '9000000021';

async function apiJson(request: APIRequestContext, method: 'get' | 'post', url: string, data?: unknown) {
  const res = await request[method](url, data === undefined ? {} : { data });
  expect(res.ok(), `${method.toUpperCase()} ${url} → ${res.status()} ${await res.text()}`).toBeTruthy();
  return res.json();
}

/** Creates Ramesh's file through the API (the citizen UI path is covered by persona 2). */
async function submitRameshFile(page: Page) {
  const request = page.request;
  const me = await apiJson(request, 'get', '/api/v1/auth/me');
  expect(me.role).toBe('citizen');
  const officerPartner = await apiJson(request, 'get', '/api/v1/partners/nearby?lat=25.7521&lng=71.3967&scheme=NSFDC_TERM_LOAN&category=sc&radius_km=60');
  const partner = officerPartner.partners.find((p: { name: string }) => p.name.startsWith('Barmer District SCA'));
  expect(partner, 'Barmer District SCA must be seeded').toBeTruthy();

  const app = await apiJson(request, 'post', '/api/v1/applications', {
    client_uuid: `e2e-partner-${Date.now()}`,
    lang: 'hi',
    personal: { full_name: 'Ramesh Kanaram Meghwal', father_name: 'Kanaram', dob: '1985-07-02', phone: RAMESH },
    facts: {
      age: 41, gender: 'male', social_category: 'sc', has_disability: false, state_code: 'RJ', district_code: 'RJ-BAR',
      pincode: '344001', annual_family_income_paise: 18000000, education_level: 'secondary', occupation: 'tailor',
      business_type: 'tailoring', project_cost_paise: 45000000, loan_needed_paise: 40000000, existing_loans: false,
      shg_member: false, course_admitted: false, lat: 25.7521, lng: 71.3967,
    },
    scheme_code: 'NSFDC_TERM_LOAN',
    plan: { principal_paise: 40000000, rate_bps: 800, tenure_months: 84, moratorium_months: 6 },
    partner_id: partner.id,
  });

  for (const type of ['aadhaar', 'income_certificate', 'bank_passbook', 'project_quotation']) {
    const image = await page.request.get(`/api/v1/demo/documents/ramesh/${type}?variant=digilocker`);
    const body = image.ok() ? await image.body() : await (await page.request.get(`/api/v1/demo/documents/ramesh/${type}`)).body();
    const upload = await page.request.post('/api/v1/documents', {
      multipart: {
        application_id: app.id,
        doc_type: type,
        source: 'upload',
        file: { name: `${type}.png`, mimeType: 'image/png', buffer: body },
      },
    });
    expect(upload.ok(), `upload ${type}: ${await upload.text()}`).toBeTruthy();
  }
  // The caste certificate is deliberately faded in the demo data: pull the clean copy (C10).
  const consent = await apiJson(page.request, 'post', '/api/v1/documents/digilocker/consent', { code: 'sandbox' });
  await apiJson(page.request, 'post', '/api/v1/documents/digilocker/pull', {
    application_id: app.id, doc_type: 'caste_certificate', consent_token: consent.consent_token,
  });

  const readiness = await apiJson(page.request, 'post', `/api/v1/applications/${app.id}/readiness`);
  expect(readiness.ready, `file must be ready: ${JSON.stringify(readiness.fixes)}`).toBeTruthy();
  await apiJson(page.request, 'post', `/api/v1/applications/${app.id}/consent`, {
    method: 'otp', language: 'hi', evidence: { otp_verified: true },
  });
  const submitted = await apiJson(page.request, 'post', `/api/v1/applications/${app.id}/submit`);
  return { id: app.id as string, trackingId: submitted.tracking_id as string };
}

test('a lender decides in the portal and the citizen sees it within two seconds', async ({ page, browser }) => {
  await setLocale(page, 'en');
  await page.goto('/login');
  await signInWithDemoOtp(page, RAMESH);
  await expect(page).toHaveURL(/\/apply/);
  const { id: applicationId, trackingId } = await submitRameshFile(page);

  // The citizen keeps watching their tracking page while the lender works.
  const citizenTab = page;
  await citizenTab.goto(`/track/${trackingId}`);
  await expect(citizenTab.getByTestId('track-status')).toHaveText('Sent to lender');

  // The officer works in a separate browser session (its own cookie jar).
  const officerContext = await browser.newContext();
  const officer = await officerContext.newPage();
  await setLocale(officer, 'en');
  await officer.goto('/login');
  await signInWithDemoOtp(officer, BARMER_OFFICER);
  await expect(officer).toHaveURL(/\/partner/);
  await expect(officer.getByTestId('queue-table')).toContainText('Ramesh Kanaram Meghwal');
  await expectNoSeriousA11yViolations(officer);
  await officer.getByTestId(`queue-open-${trackingId}`).click();

  // Review: papers, rule trace, integrity and the audit trail are all on screen.
  await expect(officer).toHaveURL(new RegExp('/partner/applications/'));
  await expect(officer.getByTestId('review-integrity')).toContainText('Unchanged since submission');
  await expect(officer.getByTestId('review-document')).toBeVisible();
  await expect(officer.getByTestId('review-audit')).toContainText('application.submitted');
  await expectNoSeriousA11yViolations(officer);

  // Ask for a paper → citizen sees it live, without reloading.
  await officer.getByTestId('action-receive').click();
  await officer.getByTestId('decision-confirm').click();
  await expect(officer.getByTestId('action-request_documents')).toBeVisible();
  await officer.getByTestId('action-request_documents').click();
  await officer.getByTestId('request-doc-project_quotation').check();
  const askedAt = Date.now();
  await officer.getByTestId('decision-confirm').click();
  await expect(officer.getByTestId('decision-done')).toBeVisible();
  await expect(citizenTab.getByTestId('track-status')).toHaveText('Lender needs more papers', { timeout: 2_000 });
  expect(Date.now() - askedAt).toBeLessThan(4_000);
  await expect(citizenTab.getByTestId('track-next')).toContainText('Upload the papers');

  // The citizen resends, the lender reviews and sanctions: letter appears, citizen sees it live.
  await apiJson(citizenTab.request, 'post', `/api/v1/applications/${applicationId}/resubmit`);
  await officer.reload();
  await officer.getByTestId('action-start_review').click();
  await officer.getByTestId('decision-confirm').click();
  await expect(officer.getByTestId('action-approve')).toBeVisible();
  await officer.getByTestId('action-approve').click();
  await officer.getByTestId('sanction-amount').fill('380000');
  const approvedAt = Date.now();
  await officer.getByTestId('decision-confirm').click();
  await expect(officer.getByTestId('decision-done')).toBeVisible();
  await expect(citizenTab.getByTestId('track-status')).toHaveText('Loan sanctioned', { timeout: 2_000 });
  expect(Date.now() - approvedAt).toBeLessThan(4_000);

  // The sanction letter is issued by the lender and downloadable by both sides.
  const letter = await citizenTab.request.get(`/api/v1/applications/${applicationId}/sanction-letter.pdf`);
  expect(letter.status()).toBe(200);
  expect(letter.headers()['content-type']).toContain('application/pdf');

  // C21: SchemeMitra itself never sanctions — an admin has no lender decision to make.
  const adminContext = await browser.newContext();
  const admin = await adminContext.newPage();
  await setLocale(admin, 'en');
  await admin.goto('/login');
  await signInWithDemoOtp(admin, '9000000030');
  await admin.goto(`/partner/applications/${applicationId}`);
  await expect(admin.getByTestId('action-disburse')).toHaveCount(0);
  await expect(admin.getByTestId('action-approve')).toHaveCount(0);
  await officerContext.close();
  await adminContext.close();
});
