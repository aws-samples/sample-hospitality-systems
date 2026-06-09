import { defineConfig, devices } from '@playwright/test';

/**
 * Playwright config for AnyCompany browser E2E.
 *
 * Runs against the DEPLOYED dev frontends (URLs resolved in global-setup from
 * CloudFormation outputs). Chromium-only by default — these are smoke-level
 * journeys, not cross-browser matrix tests; add more projects if that need
 * arises.
 */
export default defineConfig({
  testDir: '.',
  globalSetup: './global-setup.ts',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false, // these journeys mutate shared backend state; run serially to avoid conflicts
  retries: 1,           // tolerate transient cold-start latency on the first request
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
