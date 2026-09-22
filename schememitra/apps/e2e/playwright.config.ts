import { defineConfig, devices } from '@playwright/test';

// Runs against a live stack (`make dev` or `make demo`). Locally we use the installed Chrome;
// CI installs Playwright's Chromium (`PW_CHANNEL=` unset there).
const channel = process.env.PW_CHANNEL ?? (process.env.CI ? undefined : 'chrome');

export default defineConfig({
  testDir: './tests',
  timeout: 180_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: process.env.BASE_URL ?? 'http://localhost:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    locale: 'en-IN',
    permissions: ['geolocation'],
  },
  projects: [
    { name: 'mobile-chrome', use: { ...devices['Pixel 7'], channel } },
  ],
});
