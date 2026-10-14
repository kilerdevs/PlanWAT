// The offline copy: once the service worker has seen the group page, it opens without a network.
// Chromium only: Playwright drives service workers reliably there.
const { test, expect } = require('@playwright/test');

const THURSDAY_1030 = new Date('2026-10-15T10:30:00+02:00');

test.use({ serviceWorkers: 'allow' });

test('the group page and its plan open offline from the saved copy', async ({ page, context, browserName }) => {
  test.skip(browserName !== 'chromium', 'service workers are tested in Chromium');
  await page.clock.setFixedTime(THURSDAY_1030);
  await page.goto('/WCY26KY3S1/');
  await expect(page.locator('.lesson').first()).toBeVisible();
  await expect(page.locator('#offlineNotice')).toBeHidden();
  await page.evaluate(() => navigator.serviceWorker.ready.then(() => true));
  // the first visit is not yet controlled by the worker; the second one goes through it and is saved
  await page.reload();
  await expect.poll(() => page.evaluate(() => !!navigator.serviceWorker.controller)).toBe(true);
  await expect(page.locator('.lesson').first()).toBeVisible();

  await context.setOffline(true);
  await page.reload();
  await expect(page.locator('.lesson').first()).toBeVisible();
  await expect(page.locator('#offlineNotice')).toBeVisible();
  await expect(page.locator('#offlineNotice')).toContainText('offline');

  await context.setOffline(false);
  await page.evaluate(() => window.dispatchEvent(new Event('online')));
  await expect(page.locator('#offlineNotice')).toBeHidden();
});

test('the manifest and the worker are served from the site', async ({ request }) => {
  const manifest = await request.get('/WCY26KY3S1/manifest.webmanifest');
  expect(manifest.ok()).toBe(true);
  expect((await manifest.json()).start_url).toBe('./');
  const sw = await request.get('/sw.js');
  expect(sw.headers()['content-type']).toMatch(/javascript/);
  expect(await sw.text()).toMatch(/var VERSION = '[0-9a-f]{16}';/);
  expect((await request.get('/robots.txt')).ok()).toBe(true);
  expect(await (await request.get('/.well-known/security.txt')).text()).toContain('Contact: ');
  expect((await request.get('/prywatnosc/')).ok()).toBe(true);
});
