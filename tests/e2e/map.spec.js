// End-to-end checks of the campus map (/mapa/) and its links from the group page.
// Map tiles are aborted so the tests never depend on OpenFreeMap; the MapLibre engine itself comes from unpkg
// (SRI-pinned). Without WebGL the page falls back to a plain building list, which the tests accept too.
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const THURSDAY_1030 = new Date('2026-10-15T10:30:00+02:00');

/* Open a page with tiles aborted; collect uncaught errors and CSP violations. */
async function open(page, url, { engine = true } = {}) {
  const problems = [];
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  await page.route('https://tiles.openfreemap.org/**', (r) => r.abort());
  if (!engine) await page.route('https://unpkg.com/**', (r) => r.abort());
  await page.addInitScript(() => {
    window.__csp = [];
    document.addEventListener('securitypolicyviolation', (e) => {
      window.__csp.push(`${e.violatedDirective} blocked ${e.blockedURI || 'inline'}`);
    });
  });
  await page.clock.setFixedTime(THURSDAY_1030);
  await page.goto(url);
  // markers (map engine running) or the fallback list (no engine / no WebGL)
  await expect(page.locator('.bldg, .fallback button').first()).toBeAttached();
  return problems;
}

test('the map page loads without errors or CSP violations and offers every building', async ({ page }) => {
  const problems = await open(page, '/mapa/');
  expect(await page.locator('.bldg, .fallback button').count()).toBeGreaterThan(90);
  await expect(page.locator('#selection h1')).toHaveText('Mapa kampusu WAT');
  expect(await page.evaluate(() => window.__csp)).toEqual([]);
  expect(problems).toEqual([]);
});

test('searching a building number selects it and gives walking directions', async ({ page }) => {
  await open(page, '/mapa/');
  test.skip(await page.locator('#q').isHidden(), 'no search without the map engine');
  await page.locator('#q').fill('65');
  const first = page.locator('#results .result').first();
  await expect(first).toContainText('Budynek 65');
  await page.locator('#q').press('Enter');
  await expect(page.locator('#selection h1')).toHaveText('Budynek 65');
  await expect(page.locator('#selection .faculty')).toContainText('Cybernetyka');
  await expect(page.locator('#selection a.navigate')).toHaveAttribute('href', /google\.com\/maps\/dir\/\?api=1&destination=52\.\d+,20\.\d+&travelmode=walking/);
  await page.locator('#q').fill('zzzz');
  await expect(page.locator('#results')).toContainText('Brak wyników');
});

test('?b= opens a building straight away', async ({ page }) => {
  await open(page, '/mapa/?b=135');
  await expect(page.locator('#selection h1')).toHaveText('Budynek 135');
  await expect(page.locator('#sheet')).toHaveAttribute('open', '');
});

test('the faculty legend and the 2D/3D switch work', async ({ page }) => {
  await open(page, '/mapa/');
  test.skip(await page.locator('#tools').isHidden(), 'map controls need the map engine');
  await page.locator('#legendToggle').click();
  await expect(page.locator('#legendToggle')).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('.legend-row')).toHaveCount(9);
  await page.locator('.legend-row', { hasText: 'WCY' }).click();
  await expect(page.locator('#legendBody')).toBeHidden();
  const t3d = page.locator('#toggle3d');
  await expect(t3d).toHaveText('2D');
  await t3d.click();
  await expect(t3d).toHaveText('3D');
  await expect(t3d).toHaveAttribute('aria-label', 'Przełącz na mapę 3D');
});

test('without the map engine a plain list still opens directions', async ({ page }) => {
  const problems = await open(page, '/mapa/', { engine: false });
  await expect(page.locator('#status')).toContainText('Mapa jest niedostępna');
  await expect(page.locator('#tools')).toBeHidden();
  await page.locator('.fallback button', { hasText: 'Biblioteka Główna WAT' }).click();
  await expect(page.locator('#selection h1')).toHaveText('Biblioteka Główna WAT');
  await expect(page.locator('#selection a.navigate')).toBeVisible();
  expect(problems).toEqual([]);
});

test('rooms on the group page link to their building and a day opens its classes on the map', async ({ page }) => {
  await page.route('https://tiles.openfreemap.org/**', (r) => r.abort());
  await page.clock.setFixedTime(THURSDAY_1030);
  await page.goto('/WCY26KY3S1/');
  await expect(page.locator('.lesson').first()).toBeVisible();
  await expect(page.locator('.lesson a.room').first()).toHaveAttribute('href', /^\.\.\/mapa\/\?b=[0-9A-Z]+$/);

  const dayLink = page.locator('#weekBody .day.is-today a.daymap');
  await expect(dayLink).toHaveAttribute('href', '../mapa/?g=WCY26KY3S1&d=2026-10-15');
  await dayLink.click();
  await expect(page).toHaveURL(/\/mapa\/\?g=WCY26KY3S1&d=2026-10-15$/);
  await expect(page.locator('#selection h1')).toHaveText('Twój dzień na kampusie');
  const stops = page.locator('.stops [data-stop]');
  expect(await stops.count()).toBeGreaterThan(0);
  await expect(page.locator('#back')).toHaveAttribute('href', '../WCY26KY3S1/');
  const known = page.locator('.stops [data-stop]:not([disabled])').first();
  await known.click();
  await expect(known).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#selection h1')).toContainText('Budynek');
});

test('a bad group in the day link is ignored', async ({ page }) => {
  await open(page, '/mapa/?g=../../etc&d=2026-10-15');
  await expect(page.locator('#selection h1')).toHaveText('Mapa kampusu WAT');
  await expect(page.locator('#back')).toHaveAttribute('href', '../');
});

test('the map page passes an accessibility scan', async ({ page }) => {
  await open(page, '/mapa/');
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .exclude('.maplibregl-canvas')
    .analyze();
  const serious = results.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
  expect(serious).toEqual([]);
});
