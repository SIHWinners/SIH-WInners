import AxeBuilder from '@axe-core/playwright';
import { expect, type Page } from '@playwright/test';

export async function setLocale(page: Page, locale: string) {
  await page.goto('/');
  await page.evaluate(async (l) => {
    await fetch('/api/locale', { method: 'POST', body: JSON.stringify({ locale: l }) });
    try {
      indexedDB.deleteDatabase('schememitra');
      localStorage.clear();
    } catch {
      /* fresh context */
    }
  }, locale);
}

/** Answers the current intake screen and presses Continue. */
export async function answer(page: Page, value: { choice?: string; text?: string; skip?: boolean }) {
  if (value.choice) await page.getByRole('radio', { name: value.choice, exact: true }).click();
  if (value.text !== undefined) {
    const input = page.locator('main input').first();
    await input.fill(value.text);
  }
  await page.getByTestId('intake-next').click();
}

/** Works in any UI language: the demo OTP is pre-filled in dev mode. */
export async function signInWithDemoOtp(page: Page, phone: string) {
  await expect(page).toHaveURL(/\/login/);
  const field = page.getByTestId('login-phone');
  if ((await field.inputValue()) !== phone) await field.fill(phone);
  await page.getByTestId('login-submit').click();
  await expect(page.getByTestId('login-otp')).toBeVisible();
  await expect(page.getByTestId('login-otp')).not.toHaveValue('');
  await page.getByTestId('login-submit').click();
}

export async function expectNoSeriousA11yViolations(page: Page, disable: string[] = []) {
  const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa']).disableRules(disable).analyze();
  const serious = results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  expect(serious.map((v) => `${v.id}: ${v.nodes.map((n) => `${n.target.join(' ')} — ${n.failureSummary ?? ''}`).join(' | ')}`)).toEqual([]);
}
