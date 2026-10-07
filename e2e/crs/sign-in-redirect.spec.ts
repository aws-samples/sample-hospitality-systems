import { test, expect, type Page } from '@playwright/test';

/**
 * CRS sign-in routing.
 *
 * After signing in, the CRS sends the guest to the `returnUrl` query parameter.
 * Because anyone can craft a sign-in link, that target must stay on this site:
 * a same-site path is honoured, and anything else falls back to /account.
 * Also covers the protected-route redirect that sends unauthenticated users
 * to /signin.
 *
 * The CRS has no data-testid hooks, so these use label/role selectors.
 */

const CRS_URL = process.env.CRS_URL!;
const EMAIL = process.env.TEST_CRS_BROWSER_EMAIL!;
const PASSWORD = process.env.TEST_PASSWORD!;
const CRS_ORIGIN = new URL(CRS_URL).origin;

async function signInWithReturnUrl(page: Page, returnUrl: string) {
  await page.goto(`${CRS_ORIGIN}/signin?returnUrl=${encodeURIComponent(returnUrl)}`);
  await page.getByLabel('Email Address').fill(EMAIL);
  await page.getByLabel('Password').fill(PASSWORD);
  await page.getByRole('button', { name: 'Sign In' }).click();
}

test.describe('CRS sign-in redirect', () => {
  test('honours a same-site returnUrl', async ({ page }) => {
    await signInWithReturnUrl(page, '/search?city=Boston');
    await expect(page).toHaveURL((url) => url.origin === CRS_ORIGIN && url.pathname === '/search');
    expect(new URL(page.url()).searchParams.get('city')).toBe('Boston');
  });

  // Each value is a way a naive check could be tricked into leaving the site.
  // (A `javascript:` value isn't listed: the CloudFront WAF blocks that page
  // before the app loads, so it never reaches the check under test.)
  const offSite: Array<[string, string]> = [
    ['absolute URL', 'https://evil.example/'],
    ['protocol-relative', '//evil.example/'],
    ['backslash protocol-relative', '/\\evil.example/'],
    ['tab-stripped protocol-relative', '/\t/evil.example/'],
    ['no leading slash', 'evil.example/path'],
    ['non-http scheme', 'mailto:x@evil.example'],
  ];

  for (const [label, returnUrl] of offSite) {
    test(`ignores an off-site returnUrl (${label})`, async ({ page }) => {
      await signInWithReturnUrl(page, returnUrl);
      await expect(page).toHaveURL((url) => url.origin === CRS_ORIGIN && url.pathname === '/account');
    });
  }
});

test.describe('CRS protected routes', () => {
  test('unauthenticated /account redirects to sign-in', async ({ page }) => {
    await page.goto(`${CRS_ORIGIN}/account`);
    await expect(page).toHaveURL((url) => url.origin === CRS_ORIGIN && url.pathname === '/signin');
  });
});
