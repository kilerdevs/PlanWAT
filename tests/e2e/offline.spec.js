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

test('Chromium finds nothing that stops the front page, a group and the map from being installed', async ({ page, context, browserName }) => {
  test.skip(browserName !== 'chromium', 'installability is read from Chromium');
  for (const path of ['/', '/WCY26KY3S1/', '/mapa/']) {
    await page.goto(path);
    await page.evaluate(() => navigator.serviceWorker.ready.then(() => true)).catch(() => {});
    await page.reload();
    const cdp = await context.newCDPSession(page);
    const { installabilityErrors } = await cdp.send('Page.getInstallabilityErrors');
    expect(installabilityErrors, path).toEqual([]);
    expect((await cdp.send('Page.getAppManifest')).errors, path).toEqual([]);
  }
});

test('an install button appears when the browser offers installation, and asks it to prompt', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === 'mobile-safari', 'iOS has no install prompt: it shows a Safari hint instead');
  await page.addInitScript(() => { window.__prompted = 0; });
  await page.goto('/WCY26KY3S1/');
  await expect(page.locator('#installBtn')).toBeHidden();
  await page.evaluate(() => {
    const e = new Event('beforeinstallprompt', { cancelable: true });
    e.prompt = () => { window.__prompted++; return Promise.resolve(); };
    window.dispatchEvent(e);
  });
  const tools = page.locator('#toolsBtn'); // on desktop the tools sit in a side panel
  if (await tools.isVisible()) await tools.click();
  await expect(page.locator('#installBtn')).toBeVisible();
  await page.locator('#installBtn').click();
  expect(await page.evaluate(() => window.__prompted)).toBe(1);
  await expect(page.locator('#installBtn')).toBeHidden();
});
