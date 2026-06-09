import { test, expect } from '@playwright/test';

/**
 * CRS guest-site smoke test.
 *
 * The CRS frontend has no data-testid hooks (unlike PMS), so this uses
 * resilient role/text selectors and stays deliberately lightweight: prove the
 * public site loads and the search entry point works. Deeper guest-booking
 * journeys can be added once the CRS components gain testids.
 */

const CRS_URL = process.env.CRS_URL!;

test.describe('CRS guest site smoke', () => {
  test('homepage loads', async ({ page }) => {
    const resp = await page.goto(CRS_URL);
    expect(resp?.status()).toBeLessThan(400);
    // The SPA mounts something — body is non-empty and the page has a title.
    await expect(page).toHaveTitle(/.+/);
    await expect(page.locator('body')).not.toBeEmpty();
  });

  test('search controls are reachable', async ({ page }) => {
    await page.goto(CRS_URL);
    // The home page exposes a search affordance. Match leniently on common
    // booking-search controls (date inputs or a Search action) to avoid
    // coupling to exact copy.
    const searchAffordance = page
      .getByRole('button', { name: /search/i })
      .or(page.locator('input[type="date"]').first());
    await expect(searchAffordance.first()).toBeVisible();
  });
});
