// End-to-end checks of the built site in Chromium, Firefox and WebKit (desktop and phone sizes).
// The browser clock is frozen at Thursday 15 Oct 2026, 10:30 (Matematyka II is on), Europe/Warsaw.
const fs = require('node:fs');
const path = require('node:path');
const { test, expect } = require('@playwright/test');
const AxeBuilder = require('@axe-core/playwright').default;

const THURSDAY_1030 = new Date('2026-10-15T10:30:00+02:00');
const GROUP = '/WCY26KY3S1/';

/* Open the group page at a frozen time; collect uncaught errors, console errors and CSP violations. */
async function openGroup(page, { at = THURSDAY_1030, path = GROUP } = {}) {
  const problems = [];
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error') problems.push(`console: ${m.text()}`); });
  await page.addInitScript(() => {
    window.__csp = [];
    document.addEventListener('securitypolicyviolation', (e) => {
      window.__csp.push(`${e.violatedDirective} blocked ${e.blockedURI || 'inline'}`);
    });
  });
  await page.clock.setFixedTime(at);
  await page.goto(path);
  await expect(page.locator('.lesson').first()).toBeVisible();
  return problems;
}

const weekLabel = (page) => page.locator('#weekLabel');
const ON_GROUP = /\/WCY26KY3S1\/$/;

/* Every group the build wrote into site/ (a directory holding plan.ics). */
const SITE = path.join(__dirname, '..', '..', 'site');
const GROUPS = fs.readdirSync(SITE).filter((d) => fs.existsSync(path.join(SITE, d, 'plan.ics'))).sort();

test('the root lists the groups (or goes straight to the only one) and links to a group page', async ({ page }) => {
  await page.clock.setFixedTime(THURSDAY_1030);
  await page.goto('/');
  const link = page.locator('a.group[href="WCY26KY3S1/"]');
  await expect(async () => {
    expect(ON_GROUP.test(page.url()) || (await link.count()) > 0).toBe(true);
  }).toPass();
  if (!ON_GROUP.test(page.url())) {
    await expect(page.locator('a.group')).toHaveCount(GROUPS.length);
    await link.click();
  }
  await expect(page).toHaveURL(ON_GROUP);
  await expect(page.locator('.lesson').first()).toBeVisible();
});

test('the root picks a faculty first, then searches the group', async ({ page }) => {
  await page.clock.setFixedTime(THURSDAY_1030);
  await page.goto('/');
  for (const fac of ['WCY', 'WEL', 'WIG', 'WML', 'WTC']) {
    await expect(page.locator(`[data-facbtn="${fac}"]`), fac).toBeVisible();
  }
  await expect(page.locator('[data-facbtn="WCY"]')).toContainText('Wydział Cybernetyki');

  const search = page.locator('#groupSearch');
  await search.fill('wcy26ky3s1');
  await expect(page.locator('a.group[href="WCY26KY3S1/"]')).toBeVisible();
  await expect(page.locator('#resultCount')).toContainText('1 grupa');

  await search.fill('');
  await page.locator('[data-facbtn="WEL"]').click();
  await expect(page.locator('#noResults')).toBeVisible();
  await page.locator('[data-facbtn="WCY"]').click();
  await expect(page.locator('a.group[href="WCY26KY3S1/"]')).toBeVisible();
  await expect(page.locator('#noResults')).toBeHidden();

  await page.goto('/#wydzial=WEL');
  await expect(page.locator('[data-facbtn="WEL"]')).toHaveAttribute('aria-pressed', 'true');
});

test('the root page has no serious or critical accessibility violations', async ({ page }) => {
  await page.clock.setFixedTime(THURSDAY_1030);
  await page.goto('/');
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze();
  const serious = results.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
  expect(serious).toEqual([]);
});

test('on a weekend without classes the next week is shown', async ({ page }) => {
  const problems = [];
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));

  await page.clock.setFixedTime(new Date('2026-10-17T10:30:00+02:00')); // Saturday
  await page.goto(GROUP);
  await expect(page.locator('.lesson').first()).toBeVisible();
  await expect(weekLabel(page)).toHaveText('19.10–24.10');

  await page.clock.setFixedTime(new Date('2026-10-18T10:30:00+02:00')); // Sunday
  await page.goto(GROUP);
  await expect(page.locator('.lesson').first()).toBeVisible();
  await expect(weekLabel(page)).toHaveText('19.10–24.10');

  expect(problems).toEqual([]);
});

test('every group page renders its calendar without errors', async ({ page }) => {
  expect(GROUPS.length).toBeGreaterThan(0);
  const problems = [];
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  await page.addInitScript(() => {
    window.__csp = [];
    document.addEventListener('securitypolicyviolation', (e) => window.__csp.push(e.violatedDirective));
  });
  await page.clock.setFixedTime(THURSDAY_1030);
  for (const group of GROUPS) {
    await page.goto(`/${group}/`);
    await expect(page.locator('h1'), group).toHaveText(group);
    await expect(page.locator('.lesson, .session-banner').first(), group).toBeVisible();
    await expect(page.locator('.session-banner', { hasText: 'Nie udało się' }), group).toHaveCount(0);
    expect(await page.evaluate(() => window.__csp), group).toEqual([]);
  }
  expect(problems).toEqual([]);
});

test('renders the current week from plan.ics with live status and no CSP violations', async ({ page }) => {
  const problems = await openGroup(page);
  await expect(page.locator('h1')).toHaveText('WCY26KY3S1');
  await expect(page).toHaveTitle('Plan zajęć WCY26KY3S1');
  await expect(weekLabel(page)).toHaveText('12.10–17.10');
  await expect(page.locator('#weekMeta')).toHaveText('Tydzień 3 z 22 · 13 bloków');
  await expect(page.locator('.lesson')).toHaveCount(13);
  await expect(page.locator('.dow')).toHaveText(['Poniedziałek', 'Wtorek', 'Środa', 'Czwartek', 'Piątek']);

  const live = page.locator('#live');
  await expect(live).toBeVisible();
  await expect(live).toContainText('Teraz · do 11:25');
  await expect(live).toContainText('Matematyka II');
  await expect(live).toContainText('314 S');
  await expect(page.locator('.lesson.is-now .subj')).toHaveText('Matematyka II');
  await expect(page.locator('.lesson.is-next .st-text')).toHaveText('Następne · za 3 h');

  expect(await page.evaluate(() => window.__csp)).toEqual([]);
  expect(problems).toEqual([]);
});

test('arrow buttons, keys and the current-week pill move between weeks', async ({ page }) => {
  await openGroup(page);
  const pill = page.locator('#todayBtn');

  await page.locator('#nextBtn').click();
  await expect(weekLabel(page)).toHaveText('19.10–24.10');
  await expect(pill).toHaveClass(/\bshow\b/);
  await pill.click();
  await expect(weekLabel(page)).toHaveText('12.10–17.10');
  await expect(pill).not.toHaveClass(/\bshow\b/);

  await page.keyboard.press('ArrowLeft');
  await expect(weekLabel(page)).toHaveText('05.10–10.10');
  await page.keyboard.press('t');
  await expect(weekLabel(page)).toHaveText('12.10–17.10');
});

test('the week sheet closes with Escape and picks a week', async ({ page }) => {
  await openGroup(page);
  const sheet = page.locator('#weekSheet');

  await page.locator('#weekBtn').click();
  await expect(sheet).toBeVisible();
  await expect(sheet.locator('.opt[aria-selected="true"] .opt-label')).toHaveText('12.10–17.10');
  await page.keyboard.press('Escape');
  await expect(sheet).toBeHidden();

  await page.locator('#weekBtn').click();
  await sheet.locator('.opt[data-i="13"]').click();
  await expect(sheet).toBeHidden();
  await expect(weekLabel(page)).toHaveText('28.12–02.01');
  await expect(page.locator('.session-banner')).toContainText('sesja egzaminacyjna');
});

test('the legend highlights one subject across the week', async ({ page }) => {
  await openGroup(page);
  await page.locator('#legend summary').click();
  const chip = page.locator('.chip[data-subject="Matematyka II"]');
  await chip.click();
  await expect(chip).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.lesson.is-dim')).toHaveCount(11);
  await chip.click();
  await expect(page.locator('.lesson.is-dim')).toHaveCount(0);
});

test('the download button saves the group calendar', async ({ page, request }) => {
  await openGroup(page);
  const link = page.locator('#icsLink');
  await expect(link).toHaveAttribute('href', 'plan.ics');
  await expect(link).toHaveAttribute('download', 'plan-WCY26KY3S1.ics');

  const res = await request.get(GROUP + 'plan.ics');
  expect(res.status()).toBe(200);
  expect(res.headers()['content-type']).toContain('text/calendar');
  expect((await res.text()).startsWith('BEGIN:VCALENDAR')).toBe(true);

  const [download] = await Promise.all([page.waitForEvent('download'), link.click()]);
  expect(download.suggestedFilename()).toBe('plan-WCY26KY3S1.ics');
});

test('phones open at the class that is on now', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'auto-scroll is for the phone list layout');
  await openGroup(page);
  await expect.poll(() => page.evaluate(() => window.scrollY), { timeout: 5000 }).toBeGreaterThan(300);
  await expect.poll(async () => {
    const head = await page.locator('.day.is-today .dayhead').boundingBox();
    return head ? Math.round(head.y) : -1;
  }, { timeout: 5000 }).toBeLessThan(200);
});

test('with reduced motion the page still navigates and opens the sheet', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openGroup(page);
  await page.locator('#nextBtn').click();
  await expect(weekLabel(page)).toHaveText('19.10–24.10');
  await page.locator('#weekBtn').click();
  await expect(page.locator('#weekSheet')).toBeVisible();
});

test('a calendar that cannot be loaded shows an error and disables navigation', async ({ page }) => {
  await page.route('**/plan.ics', (route) => route.fulfill({ status: 500, body: 'unavailable' }));
  await page.goto(GROUP);
  await expect(page.locator('.session-banner')).toContainText('Nie udało się wczytać danych planu');
  await expect(page.locator('#prevBtn')).toBeDisabled();
  await expect(page.locator('#weekBtn')).toBeDisabled();
});

test('the group page has no serious or critical accessibility violations', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openGroup(page);
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze();
  const serious = results.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
  expect(serious).toEqual([]);
});
