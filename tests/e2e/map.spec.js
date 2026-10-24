// End-to-end checks of the campus map (/mapa/) and its links from the group page.
// The engine, style, tiles, glyphs and sprites are all vendored under mapa/, so the map draws exactly as in production
// with no outside host. Without WebGL the page falls back to a plain building list, which the tests accept too.
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const THURSDAY_1030 = new Date('2026-10-15T10:30:00+02:00');

/* Open a page; collect uncaught errors and CSP violations. engine: false blocks the vendored MapLibre. */
async function open(page, url, { engine = true } = {}) {
  const problems = [];
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  if (!engine) await page.route('**/mapa/lib/**', (r) => r.abort());
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

test('the map draws from the site\'s own files only, and every one of them loads', async ({ page }) => {
  const foreign = [], failed = [];
  // blob: and data: are made in the page (MapLibre's worker, decoded images); anything else must be this origin
  page.on('request', (r) => { if (!/^(blob|data):/.test(r.url()) && !r.url().startsWith('http://127.0.0.1')) foreign.push(r.url()); });
  page.on('response', (r) => { if (r.status() >= 400) failed.push(`${r.status()} ${r.url()}`); });
  page.on('requestfailed', (r) => failed.push(`${r.failure().errorText} ${r.url()}`));
  const problems = await open(page, '/mapa/');
  test.skip(await page.locator('.fallback').count() > 0, 'no WebGL here: the plain list has nothing to load');
  // the tiles in view, their labels' glyphs and the style's sprites, all loaded and drawn
  await page.waitForFunction(() => document.getElementById('status').hidden, null, { timeout: 30000 });
  await page.waitForLoadState('networkidle');
  await page.locator('#toggle3d').click();  // flat, then tilted again: a different set of tiles
  await page.locator('#toggle3d').click();
  await page.waitForLoadState('networkidle');
  expect(foreign).toEqual([]);
  expect(failed).toEqual([]);
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

test('?b=OSS opens the SWF, the place physical education is held at', async ({ page }) => {
  await open(page, '/mapa/?b=OSS');
  await expect(page.locator('#selection h1')).toContainText('Studium Wychowania Fizycznego (SWF)');
  await expect(page.locator('#sheet')).toHaveAttribute('open', '');
});

test('the faculty legend and the 2D/3D switch work', async ({ page }) => {
  await open(page, '/mapa/');
  test.skip(await page.locator('#tools').isHidden(), 'map controls need the map engine');
  await page.locator('#legendToggle').click();
  await expect(page.locator('#legendToggle')).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator('#legendBody .legend-row')).toHaveCount(9);
  await page.locator('#legendBody .legend-row', { hasText: 'WCY' }).click();
  await expect(page.locator('#legendBody')).toBeHidden();
  const t3d = page.locator('#toggle3d');
  await expect(t3d).toHaveText('2D');
  await t3d.click();
  await expect(t3d).toHaveText('3D');
  await expect(t3d).toHaveAttribute('aria-label', 'Przełącz na mapę 3D');
});

test('places show opening hours and accessibility, and the filters keep unknown data out', async ({ page }) => {
  await open(page, '/mapa/');
  test.skip(await page.locator('#tools').isHidden(), 'map controls need the map engine');
  await page.locator('#placesToggle').click();
  await expect(page.locator('#placesBody')).toBeVisible();
  await expect(page.locator('#openNowFilter')).toHaveAttribute('aria-pressed', 'false');
  await page.locator('#openNowFilter').click();
  await expect(page.locator('#openNowFilter')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#placesBody .filter-note').first()).toContainText('pominięte w filtrze');
  await page.locator('#wheelchairFilter').click();
  await expect(page.locator('#wheelchairFilter')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#placesBody .filter-note').first()).toContainText('Bez danych o dostępności');

  await page.locator('#q').fill('Circle K');
  const first = page.locator('#results .result').first();
  await expect(first).toContainText('Circle K');
  await expect(first).toContainText('Otwarte 24/7');
  await first.click();
  await expect(page.locator('#selection h1')).toHaveText('Circle K');
  await expect(page.locator('#selection .place-meta')).toContainText('Otwarte 24/7');
  await expect(page.locator('#selection .place-meta')).toContainText('Dostępne');
  expect(await page.evaluate(() => window.__csp)).toEqual([]);
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
  await page.clock.setFixedTime(THURSDAY_1030);
  await page.goto('/WCY26KY3S1/');
  await expect(page.locator('.lesson').first()).toBeVisible();
  await expect(page.locator('.lesson .room a').first()).toHaveAttribute('href', /^\.\.\/mapa\/\?b=[0-9A-Z]+$/);

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

test('classes hidden in "Moje przedmioty" stay hidden in the day on the map', async ({ page }) => {
  // Thursday 15.10: Matematyka II (lecture), PE, a language and English (exercises)
  await page.addInitScript(() => {
    localStorage.setItem('planwat:hide:WCY26KY3S1', JSON.stringify(['Język angielski', ['Język obcy (II) międzywydziałowy', 'Ćwiczenia']]));
  });
  await open(page, '/mapa/?g=WCY26KY3S1&d=2026-10-15');
  await expect(page.locator('#selection h1')).toHaveText('Twój dzień na kampusie');
  const stops = page.locator('.stops [data-stop]');
  await expect(stops).toHaveCount(2);
  await expect(page.locator('.stops')).toContainText('Matematyka II');
  await expect(page.locator('.stops')).not.toContainText('Język');
  await expect(page.locator('#selection')).toContainText('Bez zajęć ukrytych w „Moich przedmiotach”.');
});

test('the day on the map holds the stop list in a skeleton while the group plan loads', async ({ page }) => {
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  await page.route('**/WCY26KY3S1/plan.ics', async (route) => { await gate; await route.continue(); });
  await open(page, '/mapa/?g=WCY26KY3S1&d=2026-10-15');
  await expect(page.locator('#day .skel')).toBeVisible();
  await expect(page.locator('#day [role="status"]')).toHaveText('Wczytywanie planu grupy…');
  release();
  await expect(page.locator('.stops [data-stop]').first()).toBeVisible();
  await expect(page.locator('#day .skel')).toHaveCount(0);
});

test('a bad group in the day link is ignored', async ({ page }) => {
  await open(page, '/mapa/?g=../../etc&d=2026-10-15');
  await expect(page.locator('#selection h1')).toHaveText('Mapa kampusu WAT');
  await expect(page.locator('#back')).toHaveAttribute('href', '../');
});

test('the map page passes an accessibility scan', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await open(page, '/mapa/');
  // Building markers sit where the buildings are, so neighbours overlap at campus zoom (WCAG 2.2 target size).
  // The search box and the legend reach every building too (the "equivalent control" exception), so only the
  // markers' names are checked here.
  for (const name of await page.locator('.bldg').evaluateAll((els) => els.map((e) => e.getAttribute('aria-label')))) {
    expect(name).toBeTruthy();
  }
  // a panel still fading in reads as low contrast; wait for every finite animation to end
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running' || a.effect.getComputedTiming().iterations === Infinity));
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .exclude('.maplibregl-canvas')
    .exclude('.maplibregl-marker')
    .analyze();
  const serious = results.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
  expect(serious).toEqual([]);
});

test('a day on the map dims the other buildings, keeps the tapped class in view and the search hint fits', async ({ page }) => {
  await open(page, '/mapa/?g=WCY26KY3S1&d=2026-10-13');
  test.skip(await page.locator('#tools').isHidden(), 'map controls need the map engine');
  await expect(page.locator('html')).toHaveClass(/day-on/);
  const onDay = await page.locator('.bldg.on-day').count();
  expect(onDay).toBeGreaterThan(0);
  const dim = page.locator('.bldg:not(.on-day)').first();
  expect(await dim.evaluate((e) => getComputedStyle(e).filter)).toContain('opacity');
  await expect(page.locator('.bldg.on-day').first()).not.toHaveCSS('filter', /opacity/);
  // the hint is short enough not to be cut mid-letter
  expect(await page.locator('#q').evaluate((e) => e.getAttribute('placeholder').length)).toBeLessThan(24);
  // tapping a class compacts the card and leaves that class on screen
  const stop = page.locator('.stops [data-stop]:not([disabled])').nth(1);
  await stop.scrollIntoViewIfNeeded();
  await stop.click();
  await expect(page.locator('#selection')).toHaveClass(/compact/);
  await expect(stop).toBeInViewport();
});

test('collapsing the sheet re-frames the map and a tap on the map closes the legend', async ({ page }) => {
  await open(page, '/mapa/?g=WCY26KY3S1&d=2026-10-13');
  test.skip(await page.locator('#tools').isHidden(), 'map controls need the map engine');
  await page.locator('#legendToggle').click();
  await expect(page.locator('#legendBody')).toBeVisible();
  // a point of bare map: neither a marker nor a control sits on it
  const spot = await page.evaluate(() => {
    for (let y = 130; y < innerHeight * 0.5; y += 14) {
      for (let x = 20; x < innerWidth - 60; x += 14) {
        const e = document.elementFromPoint(x, y);
        if (e && e.classList.contains('maplibregl-canvas')) return { x, y };
      }
    }
    return null;
  });
  expect(spot).not.toBeNull();
  await page.mouse.click(spot.x, spot.y);
  await expect(page.locator('#legendBody')).toBeHidden();
  await page.locator('#sheet > summary').click();
  await expect(page.locator('#sheet')).not.toHaveAttribute('open', '');
});

test('places: the Miejsca panel switches categories and a searched place opens its card with directions', async ({ page }) => {
  await open(page, '/mapa/');
  test.skip(await page.locator('#tools').isHidden(), 'map controls need the map engine');
  await page.locator('#placesToggle').click();
  const rows = page.locator('#placesBody .legend-row');
  expect(await rows.count()).toBe(11);
  await expect(rows.first()).toHaveAttribute('aria-pressed', 'true');
  await rows.first().click();
  await expect(rows.first()).toHaveAttribute('aria-pressed', 'false');
  await page.locator('#placesBody .places-head button', { hasText: 'Wszystkie' }).click();
  await expect(rows.first()).toHaveAttribute('aria-pressed', 'true');
  // opening the faculties legend closes the places panel
  await page.locator('#legendToggle').click();
  await expect(page.locator('#placesBody')).toBeHidden();
  await page.locator('#q').fill('domki');
  await page.locator('#results .result', { hasText: 'Domki Radiowa' }).click();
  await expect(page.locator('#selection h1')).toHaveText('Domki Radiowa');
  await expect(page.locator('#selection a.navigate')).toHaveAttribute('href', /destination=52\.26\d+,20\.89\d+&travelmode=walking/);
});
