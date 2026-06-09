import { test, expect } from '@playwright/test';

/**
 * PMS staff journey: sign in as the seeded testsuite-admin, land on the
 * dashboard, navigate to Stays, and sign out. Exercises the real Cognito SRP
 * login + the authenticated SPA shell end-to-end against the deployed app.
 *
 * Uses the data-testid selectors already present in the PMS components.
 */

const PMS_URL = process.env.PMS_URL!;
const EMAIL = process.env.TEST_ADMIN_EMAIL!;
const PASSWORD = process.env.TEST_PASSWORD!;

test.describe('PMS staff journey', () => {
  test('sign in, reach dashboard, navigate to stays, sign out', async ({ page }) => {
    // 1. Land on the app; unauthenticated users get the sign-in page.
    await page.goto(PMS_URL);
    await expect(page.getByTestId('sign-in-page')).toBeVisible();

    // 2. Sign in as admin.
    await page.getByTestId('sign-in-email-input').fill(EMAIL);
    await page.getByTestId('sign-in-password-input').fill(PASSWORD);
    await page.getByTestId('sign-in-submit-button').click();

    // 3. Authenticated shell + dashboard render.
    await expect(page.getByTestId('pms-layout')).toBeVisible();
    await expect(page.getByTestId('dashboard-page')).toBeVisible();

    // 4. Navigate to Stays via the sidebar nav.
    await page.getByTestId('pms-navigation').getByRole('link', { name: /stays/i }).click();
    await expect(page.getByTestId('stays-page')).toBeVisible();
    await expect(page.getByTestId('stays-status-filter')).toBeVisible();

    // 5. Sign out -> back to the sign-in page.
    await page.getByTestId('sign-out-button').click();
    await expect(page.getByTestId('sign-in-page')).toBeVisible();
  });

  test('rejects bad credentials', async ({ page }) => {
    await page.goto(PMS_URL);
    await page.getByTestId('sign-in-email-input').fill(EMAIL);
    await page.getByTestId('sign-in-password-input').fill('wrong-password-123');
    await page.getByTestId('sign-in-submit-button').click();

    // Error surfaces; we never reach the dashboard.
    await expect(page.getByTestId('sign-in-error')).toBeVisible();
    await expect(page.getByTestId('dashboard-page')).toHaveCount(0);
  });
});
