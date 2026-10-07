import { test, expect } from '@playwright/test';

/**
 * PMS client-side routing.
 *
 * Walks every sidebar section, deep-links to a page by URL, follows a
 * parameterised route (folio detail), and checks the catch-all redirect for
 * unknown paths. Guards the router behaviour each page depends on.
 *
 * Signs in as the seeded testsuite-admin, which sees every section.
 */

const PMS_URL = process.env.PMS_URL!;
const PMS_ORIGIN = new URL(PMS_URL).origin;
const EMAIL = process.env.TEST_ADMIN_EMAIL!;
const PASSWORD = process.env.TEST_PASSWORD!;

const SECTIONS: Array<[RegExp, string, string]> = [
  [/stays/i, '/stays', 'stays-page'],
  [/housekeeping/i, '/housekeeping', 'housekeeping-page'],
  [/billing/i, '/billing', 'billing-page'],
  [/guests/i, '/guests', 'guests-page'],
  [/reports/i, '/reports', 'reports-page'],
  [/night audit/i, '/audit', 'audit-page'],
  [/dashboard/i, '/', 'dashboard-page'],
];

test.describe('PMS navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto(PMS_URL);
    await page.getByTestId('sign-in-email-input').fill(EMAIL);
    await page.getByTestId('sign-in-password-input').fill(PASSWORD);
    await page.getByTestId('sign-in-submit-button').click();
    await expect(page.getByTestId('dashboard-page')).toBeVisible();
  });

  test('sidebar reaches every section', async ({ page }) => {
    const nav = page.getByTestId('pms-navigation');
    for (const [name, path, testId] of SECTIONS) {
      await nav.getByRole('link', { name }).click();
      await expect(page).toHaveURL((url) => url.pathname === path);
      await expect(page.getByTestId(testId)).toBeVisible();
    }
  });

  test('deep link loads the page directly', async ({ page }) => {
    await page.goto(`${PMS_ORIGIN}/housekeeping`);
    await expect(page.getByTestId('housekeeping-page')).toBeVisible();
  });

  test('folio detail route resolves its id', async ({ page }) => {
    await page.getByTestId('pms-navigation').getByRole('link', { name: /billing/i }).click();
    await expect(page.getByTestId('billing-page')).toBeVisible();
    const folioLink = page.locator('a[href^="/billing/"]').first();
    // The list loads asynchronously; give it time before concluding it's empty.
    const hasFolios = await folioLink
      .waitFor({ state: 'visible', timeout: 15_000 })
      .then(() => true, () => false);
    test.skip(!hasFolios, 'No folios to open on this stack.');
    const href = await folioLink.getAttribute('href');
    await folioLink.click();
    await expect(page).toHaveURL((url) => url.pathname === href);
    await expect(page.getByTestId('folio-detail-page')).toBeVisible();
  });

  test('unknown path redirects to the dashboard', async ({ page }) => {
    await page.goto(`${PMS_ORIGIN}/no-such-page`);
    await expect(page).toHaveURL((url) => url.pathname === '/');
    await expect(page.getByTestId('dashboard-page')).toBeVisible();
  });
});
