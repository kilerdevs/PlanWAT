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

/* The tools row has three tabs (Plan, Eksport, Analiza): open the one that holds a button, then press it. */
async function showTool(page, selector) {
  const button = page.locator(selector);
  if (await button.isVisible()) return;
  const tab = await button.evaluate((n) => n.closest('.toolpanel').id.replace('tp-', 'tt-'));
  await page.locator('#' + tab).click();
}
async function pressTool(page, selector) {
  await showTool(page, selector);
  await page.locator(selector).click();
}

const weekLabel = (page) => page.locator('#weekLabel');
const ON_GROUP = /\/WCY26KY3S1\/$/;

/* Every group the build wrote into site/ (a directory holding plan.ics). */
const SITE = path.join(__dirname, '..', '..', 'site');
const GROUPS = fs.readdirSync(SITE).filter((d) => fs.existsSync(path.join(SITE, d, 'plan.ics'))).sort();

test('the root lists the groups (or goes straight to the only one) and links to a group page', async ({ page }) => {
  await page.clock.setFixedTime(THURSDAY_1030);
  await page.goto('/');
  // The development notice is hidden for now (see src/index.html).
  // await expect(page.locator('.devnote')).toContainText('w trakcie rozwoju');
  const link = page.locator('a.group[href="WCY26KY3S1/"]');
  await expect(async () => {
    expect(ON_GROUP.test(page.url()) || (await link.count()) > 0).toBe(true);
  }).toPass();
  if (!ON_GROUP.test(page.url())) {
    await expect(page.locator('a.group')).toHaveCount(GROUPS.length);
    await page.locator('details[data-fac-section="WCY"] > summary').click();
    await link.click();
  }
  await expect(page).toHaveURL(ON_GROUP);
  await expect(page.locator('.lesson').first()).toBeVisible();
});

test('the root searches groups in faculty sections collapsed by default', async ({ page }) => {
  await page.clock.setFixedTime(THURSDAY_1030);
  await page.goto('/');
  const sections = page.locator('details[data-fac-section]');
  expect(await sections.count()).toBeGreaterThan(0);
  for (const sec of await sections.all()) {
    await expect(sec).not.toHaveAttribute('open', '');
  }

  const search = page.locator('#groupSearch');
  await search.fill('wcy26ky3s1');
  await expect(page.locator('a.group[href="WCY26KY3S1/"]')).toBeVisible();
  await expect(page.locator('#resultCount')).toContainText('1 grupa');
  await expect(page.locator('details[data-fac-section="WCY"]')).toHaveAttribute('open', '');

  await search.fill('zzz-no-such-group');
  await expect(page.locator('#noResults')).toBeVisible();

  await search.fill('');
  await expect(page.locator('#noResults')).toBeHidden();
  await expect(page.locator('#resultCount')).toContainText(String(GROUPS.length));
  for (const sec of await sections.all()) {
    await expect(sec).not.toHaveAttribute('open', '');
  }

  // sections still open by hand
  await page.locator('details[data-fac-section="WCY"] > summary').click();
  await expect(page.locator('details[data-fac-section="WCY"]')).toHaveAttribute('open', '');
  await expect(page.locator('a.group[href="WCY26KY3S1/"]')).toBeVisible();
});

test('the root page has no serious or critical accessibility violations', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.clock.setFixedTime(THURSDAY_1030);
  await page.goto('/');
  // a section still fading in reads as low contrast; wait for every finite animation to end
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running' || a.effect.getComputedTiming().iterations === Infinity));
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze();
  const serious = results.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
  expect(serious).toEqual([]);
});

test('the privacy page is linked from the footer, accessible and runs no script', async ({ page }) => {
  const csp = [];
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (e) => { window.__csp = (window.__csp || []).concat(e.violatedDirective); });
  });
  await page.goto('/');
  await expect(page.locator('footer')).toContainText('PlanWAT nigdy nie poprosi Cię o adres e-mail');
  await page.locator('footer a[href="prywatnosc/"]').click();
  await expect(page).toHaveURL(/\/prywatnosc\/$/);
  await expect(page.locator('h1')).toHaveText('Prywatność i zasady');
  // a section still fading in reads as low contrast; wait for every finite animation to end
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running' || a.effect.getComputedTiming().iterations === Infinity));
  // read before the scan: axe-core fetches stylesheets itself, which this page's connect-src 'none' blocks
  csp.push(...(await page.evaluate(() => window.__csp || [])));
  expect(csp).toEqual([]);
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze();
  const serious = results.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
  expect(serious).toEqual([]);
});

test('pages draw with Inter from the site itself and ask no other host for fonts', async ({ page, browserName }) => {
  const foreign = [];
  page.on('request', (r) => { if (r.resourceType() === 'font' && !r.url().startsWith('http://127.0.0.1')) foreign.push(r.url()); });
  await openGroup(page);
  const loaded = await page.evaluate(async () => {
    await document.fonts.ready;
    return [...document.fonts].filter((f) => f.family.replace(/"/g, '') === 'Inter' && f.status === 'loaded').length;
  });
  // Chromium and Firefox here have no SF Pro, so they fall back to Inter; WebKit may resolve -apple-system first
  if (browserName !== 'webkit') expect(loaded).toBeGreaterThan(0);
  expect(foreign).toEqual([]);
});

test('a group link in the wrong case goes to the group, keeping the rest of the address', async ({ page }) => {
  await page.goto('/wcy26ky3s1/?t=x#y');
  await expect(page).toHaveURL(/\/WCY26KY3S1\/\?t=x#y$/);
  await page.goto('/wcy26ky3s1');
  await expect(page).toHaveURL(/\/WCY26KY3S1\/$/);
});

test('a mistyped group link suggests the closest groups and a search', async ({ page }) => {
  const csp = [];
  page.on('console', (m) => { if (m.type() === 'error' && /Content.Security/i.test(m.text())) csp.push(m.text()); });
  const res = await page.goto('/WCY26KY3S9/');
  expect(res.status()).toBe(404);
  await expect(page.locator('h1')).toHaveText('Nie znaleziono strony');
  const guesses = page.locator('#guess-list a');
  await expect(guesses.first()).toBeVisible();
  await expect(page.locator('#guess-list a[href="/WCY26KY3S1/"]')).toHaveCount(1);
  expect(await guesses.count()).toBeLessThanOrEqual(6);
  await expect(guesses.last()).toHaveAttribute('href', '/?q=WCY26KY3S9');
  expect(csp).toEqual([]);
});

test('an address that is no group code shows the plain 404 page', async ({ page }) => {
  await page.goto('/zupelnie/nic/');
  await expect(page.locator('h1')).toHaveText('Nie znaleziono strony');
  await page.waitForLoadState('networkidle');
  await expect(page.locator('#guess')).toBeHidden();
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
  test.slow(); // visits every group page in one test; grows with timetables/
  test.setTimeout(120_000 + GROUPS.length * 1_000);
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
  // the title search engines index is the one after the script ran: it keeps the built one
  await expect(page).toHaveTitle('Plan zajęć WCY26KY3S1 – Wydział Cybernetyki, WAT | PlanWAT');
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

test('the group page links back to the list of groups', async ({ page }) => {
  await openGroup(page);
  const back = page.locator('#backLink');
  await expect(back).toBeVisible();
  await expect(back).toHaveAttribute('href', '../');
  await expect(back).toHaveText('Wszystkie grupy');
});

test('a change of building between classes shows the walk and links to the map', async ({ page }) => {
  await openGroup(page);
  await page.locator('#viewSeg button[data-view="list"]').click();
  // Friday 16 Oct: 307 S until 9:35, then 201 65 from 9:50
  const walk = page.locator('#listView .gap').filter({ hasText: 'Do bud. 65' }).first();
  await expect(walk).toContainText('~6 min pieszo');
  await expect(walk).not.toHaveClass(/tight/);
  await expect(walk.locator('a')).toHaveAttribute('href', '../mapa/?b=65');
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
  await expect(page.locator('.session-banner')).toContainText('Brak zajęć w tym tygodniu');
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

  await showTool(page, '#icsLink');
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
  // a section still fading in reads as low contrast; wait for every finite animation to end
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running' || a.effect.getComputedTiming().iterations === Infinity));
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
    .analyze();
  const serious = results.violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
  expect(serious).toEqual([]);
});

/* ---------- tools: views, progress, statistics, calendar, sharing, comparison, catch-up ---------- */

const tool = (page) => page.locator('#toolSheet');
const noCsp = async (page) => expect(await page.evaluate(() => window.__csp)).toEqual([]);

test('the list view shows today onwards with the class on now, and can show past days', async ({ page }) => {
  const problems = await openGroup(page);
  await page.locator('#viewSeg button[data-view="list"]').click();
  await expect(page.locator('#weekBody')).toBeHidden();
  const list = page.locator('#listView');
  await expect(list.locator('.dow').first()).toHaveText('Dziś · Czwartek');
  await expect(list.locator('.lesson.is-now .subj')).toHaveText('Matematyka II');
  await expect(list.locator('.gap').first()).toContainText('Okienko');
  const past = list.locator('.past-toggle');
  await expect(past).toContainText('Pokaż odbyte');
  const before = await list.locator('.day').count();
  await past.click();
  await expect.poll(() => list.locator('.day').count()).toBeGreaterThan(before);

  await page.locator('#viewSeg button[data-view="week"]').click();
  await expect(list).toBeHidden();
  await expect(page.locator('.lesson')).toHaveCount(13);
  await noCsp(page);
  expect(problems).toEqual([]);
});

test('the month view opens the week of a picked day', async ({ page }) => {
  await openGroup(page);
  await page.locator('#viewSeg button[data-view="month"]').click();
  await expect(page.locator('#monthTitle')).toHaveText('Październik 2026');
  await expect(page.locator('.mday.is-today')).toHaveCount(1);
  await page.locator('#monthNext').click();
  await expect(page.locator('#monthTitle')).toHaveText('Listopad 2026');
  await page.locator('#monthPrev').click();
  await page.locator('.mday', { hasText: /^21/ }).click();
  await expect(page.locator('#monthView')).toBeHidden();
  await expect(weekLabel(page)).toHaveText('19.10–24.10');
});

test('the Live card leads back to the week view from the other views', async ({ page }) => {
  await openGroup(page);
  await page.locator('#viewSeg button[data-view="month"]').click();
  await page.locator('#live').click();
  await expect(page.locator('#weekBody')).toBeVisible();
  await expect(page.locator('#viewSeg button[data-view="week"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#weekBody .lesson.is-now')).toBeInViewport();
});

test('the chosen view is remembered', async ({ page }) => {
  await openGroup(page);
  await page.locator('#viewSeg button[data-view="list"]').click();
  await page.reload();
  await expect(page.locator('#listView .lesson').first()).toBeVisible();
  await expect(page.locator('#viewSeg button[data-view="list"]')).toHaveAttribute('aria-pressed', 'true');
});

test('week blocks sharing a start time have one height on desktop', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === 'mobile-safari' || testInfo.project.name === 'mobile-chrome',
    'the day x block grid is desktop-only');
  await openGroup(page);
  const heights = await page.locator('#weekBody .lesson').evaluateAll((els) =>
    els.map((e) => ({ start: e.getAttribute('data-start'), h: e.getBoundingClientRect().height })));
  const byStart = {};
  heights.forEach(({ start, h }) => { (byStart[start] = byStart[start] || []).push(h); });
  expect(Object.keys(byStart).length).toBeGreaterThan(1);
  Object.entries(byStart).forEach(([start, hs]) => {
    expect({ start, spread: Math.max(...hs) - Math.min(...hs) }.spread).toBeLessThanOrEqual(1);
  });
});

test('subject progress counts classes and finds where to catch up in other groups', async ({ page }) => {
  await openGroup(page);
  await page.locator('#progress summary').click();
  const row = page.locator('.subj-row', { hasText: 'Matematyka II' });
  await expect(row.locator('.subj-n')).toHaveText(/^\d+ z \d+$/);
  await expect(row.locator('.subj-meta').first()).toContainText('Następne:');
  await expect(row.locator('.subj-meta').nth(1)).toContainText('W planie: Wykład');
  await row.getByRole('button', { name: /Gdzie odrobić/ }).click();
  await expect(tool(page)).toBeVisible();
  await expect(page.locator('#toolTitle')).toHaveText('Gdzie odrobić: Matematyka II');
  await expect(tool(page).locator('p[role="status"]')).toContainText(/Znaleziono \d+ termin|Brak takich zajęć/);
  // only peer groups of the same major and year, each carrying its ordinal in the term
  const rows = tool(page).locator('ul.rows li');
  await expect.poll(() => rows.count()).toBeGreaterThan(0);
  for (const li of await rows.all()) {
    await expect(li.locator('.x')).toHaveText(/^WCY26KY/);
    await expect(li.locator('.m')).toContainText(/· nr \d+/);
  }
  await page.locator('#cuFree').check();
  await expect(tool(page).locator('.tag.warn')).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(tool(page)).toBeHidden();
  await noCsp(page);
});

test('statistics sum up the semester', async ({ page }) => {
  await openGroup(page);
  await pressTool(page, '#statsBtn');
  await expect(page.locator('#toolTitle')).toHaveText('Statystyki planu');
  await expect(tool(page).locator('.tile b').first()).toHaveText('216');
  await expect(tool(page).locator('.cols span')).toHaveCount(22);
  await expect(tool(page).locator('.cols span.is-cur')).toHaveCount(1);
  await tool(page).getByRole('button', { name: 'Pokaż dane liczbowe' }).click();
  await expect(tool(page).locator('table.data tbody tr')).toHaveCount(22);
});

test('the calendar sheet offers subscription links and the file', async ({ page }) => {
  await openGroup(page);
  await pressTool(page, '#calBtn');
  await expect(page.locator('#calApple')).toHaveAttribute('href', /^webcal:\/\/127\.0\.0\.1:\d+\/WCY26KY3S1\/plan\.ics$/);
  await expect(page.locator('#calGoogle')).toHaveAttribute('href', /^https:\/\/calendar\.google\.com\/calendar\/render\?cid=webcal%3A%2F%2F/);
  await expect(page.locator('#calFile')).toBeVisible();

  // the reminder switch points the subscription actions at the calendar with alarms
  await page.locator('#calRemind').check();
  await expect(page.locator('#calApple')).toHaveAttribute('href', /^webcal:\/\/127\.0\.0\.1:\d+\/WCY26KY3S1\/plan-przypomnienia\.ics$/);
  await expect(page.locator('#calGoogle')).toHaveAttribute('href', /plan-przypomnienia\.ics$/);
  await page.locator('#calRemind').uncheck();

  // the downloaded file is generated in the browser with the chosen reminder
  await page.locator('#calFileRemind .choice[data-value="30"]').click();
  const first = page.waitForEvent('download');
  await page.locator('#calFile').click();
  expect((await first).suggestedFilename()).toBe('plan-WCY26KY3S1-przypomnienie-30min.ics');
  await page.locator('#calFileRemind .choice[data-value="0"]').click();
  const second = page.waitForEvent('download');
  await page.locator('#calFile').click();
  expect((await second).suggestedFilename()).toBe('plan-WCY26KY3S1.ics');
});

test('share hands the page link to the system share sheet', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'share', { configurable: true, value: (d) => { window.__shared = d; return Promise.resolve(); } });
  });
  await openGroup(page);
  await pressTool(page, '#shareBtn');
  await expect(page.locator('#sharePreview')).toContainText('Plan WCY26KY3S1');
  await expect(page.locator('#sharePreview')).toContainText('Matematyka II');
  const png = page.waitForEvent('download');
  await page.locator('#shareImage').click();
  const file = await png;
  expect(file.suggestedFilename()).toBe('plan-WCY26KY3S1-2026-10-15.png');
  const pngBytes = fs.readFileSync(await file.path());
  expect(pngBytes.subarray(1, 4).toString()).toBe('PNG');
  expect(pngBytes.readUInt32BE(16)).toBe(1080);
  expect(pngBytes.readUInt32BE(20)).toBe(1350);
  await page.locator('#shareLink').click();
  await expect.poll(() => page.evaluate(() => window.__shared && window.__shared.url)).toMatch(/\/WCY26KY3S1\/$/);
});

test('choice rows keep a clear gap before the block they introduce', async ({ page }) => {
  await openGroup(page);
  // measured at rest: a field that was just shown settles a few pixels into place (scroll-linked effects, like the
  // header's, always count as running and are left out)
  const gap = async (first, second) => {
    await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running' || a.timeline !== document.timeline
      || a.effect.getComputedTiming().iterations === Infinity));
    return page.evaluate(([a, b]) => {
      return document.querySelector(b).getBoundingClientRect().top - document.querySelector(a).getBoundingClientRect().bottom;
    }, [first, second]);
  };

  await pressTool(page, '#calBtn');
  await expect(page.locator('#calFile')).toBeVisible();
  expect(await gap('#calFileRemind', '#calFile')).toBeGreaterThanOrEqual(10);
  await page.locator('#toolClose').click();
  await expect(tool(page)).toBeHidden();

  await pressTool(page, '#shareBtn');
  await expect(page.locator('#shareCanvas')).toBeVisible();
  expect(await gap('#shareDate', '#shareQuick')).toBeGreaterThanOrEqual(10);
  await page.locator('#toolClose').click();
  await expect(tool(page)).toBeHidden();

  await pressTool(page, '#profileBtn');
  await expect(tool(page).locator('.pm-hero')).toBeVisible();
  await tool(page).locator('#pmt-like').click();
  await expect(tool(page).locator('.pm-sim li').first()).toBeVisible();
  expect(await gap('#pmMode', '.pm-list')).toBeGreaterThanOrEqual(10);
});

test('a break is a banner, not a class, and the statistics separate it from teaching', async ({ page }) => {
  const problems = [];
  page.on('pageerror', (e) => problems.push(e.message));
  await page.clock.setFixedTime(new Date('2027-02-10T10:00:00+01:00'));
  await page.goto('/WME24BM1S1/');
  const breakNote = page.locator('.week-note:not(.session)', { hasText: 'Przerwa' });
  await expect(breakNote).toContainText('10.02');
  await expect(page.locator('.week-note.session')).toContainText('Sesja');
  await expect(page.locator('.day-note', { hasText: 'Przerwa' })).toHaveCount(5);

  await pressTool(page, '#statsBtn');
  await expect(tool(page).locator('.tile').nth(1)).toContainText('godzin dydaktycznych');
  await expect(tool(page)).toContainText('Poza zajęciami');
  await expect(tool(page)).toContainText('Rezerwacje sal');
  await expect(tool(page)).toContainText('Bloki sesji');
  await page.keyboard.press('Escape');
  await expect(page.locator('#toolSheet')).toBeHidden();
  expect(problems).toEqual([]);
});

test('the session sheet lists exams and credits, filters them and exports them', async ({ page }) => {
  await openGroup(page);
  await pressTool(page, '#sessionBtn');
  await expect(page.locator('#toolTitle')).toHaveText('Sesja egzaminacyjna');
  await expect(tool(page).locator('.session-row').first()).toContainText('Zaliczenie');
  const file = page.waitForEvent('download');
  await page.locator('#sessionDownload').click();
  expect((await file).suggestedFilename()).toBe('egzaminy-i-zaliczenia-WCY26KY3S1.ics');
  await page.locator('#sessionKind .choice[data-value="exam"]').click();
  await expect(tool(page)).toContainText('Brak nadchodzących terminów');
  await expect(page.locator('#sessionDownload')).toBeDisabled();
  await page.keyboard.press('Escape');
});

test('my extra classes appear in the plan, survive a reload and stay out of the statistics', async ({ page }) => {
  const problems = await openGroup(page);
  await pressTool(page, '#extrasBtn');
  await page.locator('#extraAdd').click();
  await page.locator('#extraTitle').fill('SKS test');
  await page.locator('#extraStart').fill('18:00');
  await page.locator('#extraEnd').fill('19:30');
  await page.locator('#extraSave').click();
  await expect(page.locator('#extraList')).toContainText('SKS test');
  await page.keyboard.press('Escape');
  await expect(page.locator('#toolSheet')).toBeHidden();
  await expect(page.locator('.lesson.is-extra')).toHaveCount(1);
  await expect(page.locator('.lesson.is-extra')).toContainText('SKS test');

  await pressTool(page, '#statsBtn');
  await expect(tool(page).locator('.tile b').first()).toHaveText('216');
  await page.keyboard.press('Escape');
  await expect(page.locator('#toolSheet')).toBeHidden();

  await page.reload();
  await expect(page.locator('.lesson.is-extra')).toHaveCount(1);
  page.on('dialog', (d) => d.accept());
  await pressTool(page, '#extrasBtn');
  await page.locator('#extraList .link', { hasText: 'Usuń' }).click();
  await expect(page.locator('#extraList')).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(page.locator('#toolSheet')).toBeHidden();
  await expect(page.locator('.lesson.is-extra')).toHaveCount(0);
  expect(problems).toEqual([]);
});

test('comparing groups shows both plans and the shared free time', async ({ page }) => {
  await openGroup(page);
  await pressTool(page, '#compareBtn');
  const input = page.locator('#cmpInput');
  await input.fill('wcy26ky1s1');
  await input.press('Enter');
  await expect(tool(page).locator('.gchips .chip')).toHaveCount(2);
  await expect(page.locator('#cmpWeek')).toHaveText('12.10–17.10');
  await expect(tool(page).locator('.cmp-day').first()).toContainText('Wszyscy wolni');
  await expect(tool(page).locator('.rows .x', { hasText: 'WCY26KY1S1' }).first()).toBeVisible();
  await tool(page).getByRole('button', { name: 'Następny tydzień' }).click();
  await expect(page.locator('#cmpWeek')).toHaveText('19.10–24.10');
  await tool(page).getByRole('button', { name: 'Usuń WCY26KY1S1 z porównania' }).click();
  await expect(tool(page).locator('.gchips .chip')).toHaveCount(1);
  await noCsp(page);
});

test('physical education shows SWF and every map link is real: none points at ?b=null', async ({ page }) => {
  await openGroup(page);
  await expect(page.locator('.lesson .room', { hasText: /^SWF$/ }).first()).toBeAttached();
  await expect(page.locator('a[href$="mapa/?b=OSS"]').first()).toBeAttached();
  await expect(page.locator('a[href*="?b=null"], a[href*="?b=undefined"]')).toHaveCount(0);
  // the walk to it reads "SWF", not the full name
  await expect(page.locator('a[href$="mapa/?b=OSS"]:not(:text-is("SWF"))')).toHaveCount(0);
});

test('the plan map explains the coefficient and every number, tab by tab', async ({ page }) => {
  await openGroup(page);
  await pressTool(page, '#profileBtn');
  const sheet = tool(page);
  // Twój plan
  const hero = sheet.locator('.pm-hero');
  await expect(hero.locator('.pm-herotext strong')).toHaveText('Współczynnik przejebania™');
  await expect(hero.locator('.pm-big b')).toHaveText(/^\d{1,3}$/);
  await expect(hero).toContainText('porównanych planów jest lżejszych niż WCY26KY3S1');
  await expect(sheet.locator('.pm-gauge')).toHaveAttribute('aria-label', /^Współczynnik \d+ na 100$/);
  await sheet.locator('.pm-what summary').click();
  await expect(sheet.locator('.pm-what p')).toContainText('jaka część porównanych planów jest lżejsza');
  await expect(sheet.locator('.pm-arch strong')).not.toBeEmpty();
  await expect(sheet.locator('.pm-arch .pm-badge')).toHaveText(/^[1-8]$/);
  await expect(sheet.locator('.pm-trait').first()).toContainText('Ty:');
  await expect(sheet.locator('.pm-trait').first()).toContainText('średnia:');
  // Mapa: the canvas, the numbered legend that defines the badges, and the plan's own card
  await sheet.locator('#pmt-map').click();
  await expect(sheet.locator('canvas#pmMap')).toBeVisible();
  await expect(sheet.locator('.pm-card strong')).toHaveText('WCY26KY3S1 (Twój plan)');
  const legend = sheet.locator('.pm-legrow');
  await expect(legend).toHaveCount(8);
  await expect(legend.first().locator('.pm-badge')).toHaveText('1');
  await expect(legend.first()).toContainText('grup');
  await expect(sheet.locator('.pm-legrow.mine')).toContainText('Twój');
  await legend.first().click();
  await expect(legend.first()).toHaveAttribute('aria-pressed', 'true');
  await legend.first().click();
  await expect(legend.first()).toHaveAttribute('aria-pressed', 'false');
  // Podobne: other plans, each with how it differs
  await sheet.locator('#pmt-like').click();
  await expect(sheet.locator('.pm-sim a').first()).toHaveAttribute('href', /^\.\.\/[A-Z0-9_]+\/$/);
  await expect(sheet.locator('.pm-sim li').first()).toContainText(/podobny|trochę inny/);
  await sheet.getByRole('button', { name: 'Lżejszego' }).click();
  await expect(sheet.locator('#pmMode [aria-pressed="true"]')).toHaveText('Lżejszego');
  await expect(sheet.locator('.pm-sim li').first()).toContainText('współczynnik');
  // Metoda: a definition for every feature and a row for every archetype
  await sheet.locator('#pmt-how').click();
  await expect(sheet.locator('.pm-feats li')).toHaveCount(13);
  await expect(sheet.locator('.pm-feats li').first().locator('.pm-def')).not.toBeEmpty();
  await expect(sheet.locator('.pm-tab tbody tr')).toHaveCount(8);
  await expect(sheet.locator('.pm-tab tbody tr.mine')).toHaveCount(1);
  await noCsp(page);
});

test('the tools row has three tabs, moves with the arrow keys and remembers the one used last', async ({ page }) => {
  await openGroup(page);
  const tabs = page.locator('#toolTabs [role="tab"]');
  await expect(tabs).toHaveText(['Plan', 'Eksport', 'Analiza']);
  await expect(page.locator('#tp-plan')).toBeVisible();
  await expect(page.locator('#tp-export')).toBeHidden();
  await expect(page.locator('#favBtn')).toBeVisible();
  await expect(page.locator('#statsBtn')).toBeHidden();
  await tabs.first().focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('#tt-export')).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('#icsLink')).toBeVisible();
  await page.keyboard.press('End');
  await expect(page.locator('#tt-analysis')).toBeFocused();
  await expect(page.locator('#profileBtn')).toBeVisible();
  await page.reload();
  await expect(page.locator('#tt-analysis')).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('#profileBtn')).toBeVisible();
  await expect(page.locator('#favBtn')).toBeHidden();
});

test('free rooms lists rooms with no class at the chosen time, with a day bar on each', async ({ page }) => {
  await openGroup(page);
  await pressTool(page, '#roomsBtn');
  await expect(page.locator('#frDate')).toHaveValue('2026-10-15');
  await expect(page.locator('#frTime')).toHaveValue('10:30');
  const status = tool(page).locator('#frResult .fr-sum');
  await expect(status).toContainText(/wolnych sal|wolne sale|wolna sala/);
  await expect(tool(page).locator('.fr-card').first().locator('.fr-bar')).toHaveCount(1);
  await expect(tool(page).locator('#frAsof')).toContainText('Według opublikowanych planów');
  await page.locator('#frPresetTomorrow').click();
  await expect(page.locator('#frDate')).toHaveValue('2026-10-16');
  await expect(page.locator('#frTime')).toHaveValue('08:00');
  await page.locator('#frPresetNow').click();
  await expect(page.locator('#frDate')).toHaveValue('2026-10-15');
  await expect(page.locator('#frTime')).toHaveValue('10:30');
  // 314 S hosts a class right now, so it is not free; asking for later rooms may list it with a later start
  await page.locator('#frQuery').fill('314 S');
  await expect(tool(page).locator('.fr-card.fr-card:not(.later) .fr-room', { hasText: /^314 S$/ })).toHaveCount(0);
  await page.locator('#frLater').check();
  await expect(tool(page).locator('.fr-card.later').first()).toContainText('dopiero od');
  await page.locator('#frDate').fill('2030-01-01');
  await page.locator('#frDate').dispatchEvent('change');
  await expect(tool(page).locator('#frResult')).toContainText('Brak danych dla tego dnia');
  await noCsp(page);
});

test('favourites and recent groups appear on the front page', async ({ page }) => {
  await openGroup(page);
  await pressTool(page, '#favBtn');
  await expect(page.locator('#favBtn')).toHaveAttribute('aria-pressed', 'true');
  await page.goto('/');
  await expect(page.locator('#favList a.pick')).toHaveText(['WCY26KY3S1']);
  await expect(page.locator('#recentWrap')).toBeHidden(); // the only recent group is already a favourite
  await page.locator('#favList a.pick').click();
  await expect(page).toHaveURL(ON_GROUP);
  await pressTool(page, '#favBtn');
  await expect(page.locator('#favBtn')).toHaveAttribute('aria-pressed', 'false');
  await page.goto('/');
  await expect(page.locator('#recentList a.pick')).toHaveText(['WCY26KY3S1']);
});

test('enter in the front page search opens the only matching group', async ({ page }) => {
  await page.goto('/');
  await page.locator('#groupSearch').fill('wcy26ky3s1');
  await page.locator('#groupSearch').press('Enter');
  await expect(page).toHaveURL(ON_GROUP);
});

test('a plan that changed since the last visit says what changed', async ({ page }) => {
  await openGroup(page);
  await expect(page.locator('#changeNotice')).toBeHidden();
  await page.evaluate(() => {
    const key = 'planwat:seen:WCY26KY3S1';
    const seen = JSON.parse(localStorage.getItem(key));
    seen.shift();
    seen.push('2026-10-16|08:00|09:35|Stary przedmiot|Wykład|1 S');
    localStorage.setItem(key, JSON.stringify(seen));
  });
  await page.reload();
  await expect(page.locator('#changeNotice')).toBeVisible();
  await expect(page.locator('#changeText')).toHaveText('Plan zmienił się od ostatniej wizyty: 1 nowe zajęcia, 1 usunięte.');
  await page.locator('#changeShow').click();
  await expect(tool(page)).toContainText('Stary przedmiot');
  await page.keyboard.press('Escape');
  await page.locator('#changeOk').click();
  await expect(page.locator('#changeNotice')).toBeHidden();
  await page.reload();
  await expect(page.locator('.lesson').first()).toBeVisible();
  await expect(page.locator('#changeNotice')).toBeHidden();
});

test('the list view and the tool sheets have no serious or critical accessibility violations', async ({ page }) => {
  test.slow(); // several full axe scans
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openGroup(page);
  const scan = async () => {
    // a sheet still fading in reads as low contrast; wait for every finite animation to end and for an open sheet to be
    // fully opaque (WebKit can report its fade as done a frame or two early)
    await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running' || a.effect.getComputedTiming().iterations === Infinity)
      && Array.prototype.every.call(document.querySelectorAll('dialog[open]'), (d) => getComputedStyle(d).opacity === '1'));
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
    return results.violations
      .filter((v) => v.impact === 'serious' || v.impact === 'critical')
      .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
  };
  await page.locator('#progress summary').click();
  await page.locator('#viewSeg button[data-view="list"]').click();
  expect(await scan()).toEqual([]);
  await page.locator('#viewSeg button[data-view="month"]').click();
  expect(await scan()).toEqual([]);
  for (const id of ['#statsBtn', '#sessionBtn', '#roomsBtn', '#profileBtn', '#calBtn', '#extrasBtn', '#shareBtn']) {
    await pressTool(page, id);
    await expect(tool(page)).toBeVisible();
    await expect(tool(page).locator('.muted', { hasText: 'Wczytywanie' })).toHaveCount(0);
    expect(await scan(), id).toEqual([]);
    await page.keyboard.press('Escape');
    await expect(tool(page)).toBeHidden();
  }
});

test('the front page shows what is on now in a favourite group', async ({ page }) => {
  await page.clock.setFixedTime(THURSDAY_1030);
  await page.addInitScript(() => localStorage.setItem('planwat:favs', JSON.stringify(['WCY26KY3S1'])));
  await page.goto('/');
  const card = page.locator('#liveCards a.now-card');
  await expect(card).toHaveCount(1);
  await expect(card).toHaveClass(/live/);
  await expect(card).toContainText('Teraz · do');
  await expect(card).toContainText('314 S');
  await card.click();
  await expect(page).toHaveURL(ON_GROUP);
});

test('a star on a group row adds it to the favourites, and the faculty chips filter the list', async ({ page }) => {
  await page.clock.setFixedTime(THURSDAY_1030);
  await page.goto('/');
  await expect(page.locator('#saved')).toBeHidden();
  await page.locator('details[data-fac-section="WCY"] > summary').click();
  const star = page.locator('button.star[data-star="WCY26KY3S1"]');
  await expect(star).toHaveAttribute('aria-pressed', 'false');
  await star.click();
  await expect(star).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('#favList a.pick')).toHaveText(['WCY26KY3S1']);
  await expect(page.locator('#liveCards a.now-card')).toHaveCount(1);
  await star.click();
  await expect(page.locator('#saved')).toBeHidden();

  await page.locator('#filters .chip[data-fac="WCY"]').click();
  await expect(page.locator('#filters .chip[data-fac="WCY"]')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('details[data-fac-section="WCY"]')).toHaveAttribute('open', '');
  await expect(page.locator('details[data-fac-section]:not([hidden])')).toHaveCount(1);
  await page.locator('#filters .chip[data-fac=""]').click();
  await expect(page.locator('details[data-fac-section]:not([hidden])')).toHaveCount(await page.locator('details[data-fac-section]').count());
});

test('the front page search takes the "/" key and a ?q= link', async ({ page }) => {
  await page.goto('/?q=wcy26ky3');
  await expect(page.locator('#groupSearch')).toHaveValue('wcy26ky3');
  await expect(page.locator('a.group[href="WCY26KY3S1/"]')).toBeVisible();
  await page.locator('#clearSearch').click();
  await expect(page.locator('#groupSearch')).toHaveValue('');
  await page.locator('body').click({ position: { x: 5, y: 5 } });
  await page.keyboard.press('/');
  await expect(page.locator('#groupSearch')).toBeFocused();
});

test('the group finder walks from faculty and intake year to a group', async ({ page }) => {
  await page.clock.setFixedTime(THURSDAY_1030);
  await page.goto('/');
  const opener = page.locator('#findGroup');
  const dialog = page.locator('#groupFinder');
  await opener.click();
  await expect(dialog).toBeVisible();
  await expect(dialog).toHaveAttribute('aria-labelledby', 'finderTitle');
  await expect(page.locator('#finderStep')).toContainText('Krok 1 z 3');
  await expect(dialog.locator('.finder-opt').first()).toBeFocused();
  // Escape closes the sheet and hands focus back to the button that opened it
  await page.keyboard.press('Escape');
  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();

  await opener.click();
  await dialog.locator('.finder-opt[data-fac="WCY"]').click();
  await expect(page.locator('#finderStep')).toContainText('Krok 2 z 3');
  await dialog.locator('.finder-opt[data-year="2026"]').click();
  await expect(page.locator('#finderStep')).toContainText('Krok 3 z 3');
  const link = dialog.locator('a.finder-group[href="WCY26KY3S1/"]');
  await expect(link).toBeVisible();
  await link.click();
  await expect(page).toHaveURL(ON_GROUP);
  await expect(page.locator('.lesson').first()).toBeVisible();
});

test('each class shows which meeting of its subject and type it is', async ({ page }) => {
  const problems = await openGroup(page);
  const types = await page.locator('#weekBody .lesson .type').allTextContents();
  expect(types.some((t) => /^(Wykład|Ćwiczenia|Laboratorium) · \d+\/\d+$/.test(t))).toBe(true);
  for (const t of types) {
    const m = t.match(/(\d+)\/(\d+)$/);
    if (m) expect(Number(m[1])).toBeLessThanOrEqual(Number(m[2]));
  }
  expect(problems).toEqual([]);
});

test('tapping a class finds where to make up that very meeting', async ({ page }) => {
  await openGroup(page);
  const lesson = page.locator('#weekBody .lesson.is-now');
  const type = (await lesson.locator('.type').textContent()).match(/^(.+) · (\d+)\/(\d+)$/);
  expect(type).not.toBeNull();
  await lesson.locator('.time').click();
  await expect(tool(page)).toBeVisible();
  await expect(page.locator('#toolTitle')).toHaveText('Gdzie odrobić: Matematyka II');
  await expect(tool(page)).toContainText(`Spotkanie: ${type[1]} nr ${type[2]} z ${type[3]}`);
  await expect(tool(page).locator('p[role="status"]')).toContainText(/Znaleziono \d+ termin|Brak tego spotkania/);
  for (const li of await tool(page).locator('ul.rows li').all()) {
    await expect(li.locator('.m')).toContainText(`· nr ${type[2]}`);
  }
  // the whole subject is one step away
  await tool(page).getByRole('button', { name: 'Pokaż wszystkie terminy przedmiotu' }).click();
  await expect(tool(page).locator('#cuType')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(tool(page)).toBeHidden();

  // the room link inside the class keeps going to the map, and the subject is a keyboard-reachable button
  await expect(lesson.locator('.room a')).toHaveAttribute('href', /^\.\.\/mapa\/\?b=/);
  // only the room text is the map link: the pin next to it belongs to the class like everything else
  await lesson.locator('.room svg').click();
  await expect(tool(page)).toBeVisible();
  await expect(page).toHaveURL(/\/WCY26KY3S1\/$/);
  await page.keyboard.press('Escape');
  await expect(tool(page)).toBeHidden();
  await lesson.locator('button.subj').focus();
  await page.keyboard.press('Enter');
  await expect(tool(page)).toBeVisible();
  await noCsp(page);
});

test('a plan whose lessons all predate the semester says the faculty has not published it yet', async ({ page }) => {
  await page.route('**/plan.ics', async (route) => {
    const res = await route.fetch();
    const body = (await res.text()).replace(/X-PLAN-SEMESTER-START:\d+/, 'X-PLAN-SEMESTER-START:20990101');
    await route.fulfill({ response: res, body });
  });
  const problems = await openGroup(page);
  await expect(page.locator('#staleNotice')).toBeVisible();
  expect(problems).toEqual([]);
});

test('a term the faculty has not published has no lessons at all, and says so', async ({ page }) => {
  await page.route('**/plan.ics', async (route) => {
    const res = await route.fetch();
    const body = (await res.text()).replace(/BEGIN:VEVENT[\s\S]*?END:VEVENT\r?\n/g, '');
    await route.fulfill({ response: res, body });
  });
  const problems = [];
  page.on('pageerror', (e) => problems.push(`pageerror: ${e.message}`));
  page.on('console', (m) => { if (m.type() === 'error') problems.push(`console: ${m.text()}`); });
  await page.clock.setFixedTime(THURSDAY_1030);
  await page.goto(GROUP);
  await expect(page.locator('#staleNotice')).toBeVisible();
  await expect(page.locator('.session-banner').first()).toContainText('nie jest jeszcze opublikowany');
  await expect(page.locator('.session-banner').first()).not.toContainText('sesja egzaminacyjna');
  await expect(page.locator('.lesson')).toHaveCount(0);
  expect(problems).toEqual([]);
});

test('a current plan does not show the unpublished notice', async ({ page }) => {
  await openGroup(page);
  await expect(page.locator('#staleNotice')).toBeHidden();
});

test('a group with two terms switches between them with ?t= and exports the term on show', async ({ page }) => {
  const nav = '<nav class="termswitch" id="termSwitch" aria-label="Semestr"><a href="./" data-term="2026-27-zima" aria-current="true">Zima 2026/27</a>' +
    '<a href="./?t=2026-27-lato" data-term="2026-27-lato">Lato 2026/27</a></nav>';
  await page.route(/\/WCY26KY3S1\/(\?.*)?$/, async (route) => {
    const res = await route.fetch();
    await route.fulfill({ response: res, body: (await res.text()).replace(/(<p class="sub[^>]*id="termLine">[^<]*<\/p>)/, `$1${nav}`) });
  });
  await page.route('**/plan-2026-27-lato.ics', async (route) => {
    const res = await page.request.get(new URL('plan.ics', route.request().url()).href);
    await route.fulfill({ status: 200, contentType: 'text/calendar', body: (await res.text()).replace(/X-PLAN-TERM:.*/, 'X-PLAN-TERM:semestr letni 2026/27') });
  });
  const problems = await openGroup(page, { path: `${GROUP}?t=2026-27-lato` });
  await expect(page.locator('#termLine')).toContainText('letni');
  await expect(page.locator('#icsLink')).toHaveAttribute('href', 'plan-2026-27-lato.ics');
  await expect(page.locator('#factUpdated')).toBeHidden();
  await expect(page.locator('#termSwitch a[aria-current]')).toHaveText('Zima 2026/27'); // markup is static: current term of the build
  await page.goto(GROUP + '?t=nope');
  await expect(page.locator('#icsLink')).toHaveAttribute('href', 'plan.ics');
  expect(problems).toEqual([]);
});

test('"Moje przedmioty" hides a subject everywhere, remembers it, and the downloaded file leaves it out', async ({ page }) => {
  const problems = await openGroup(page);
  const before = await page.locator('#weekBody .lesson').count();
  const firstSubject = (await page.locator('#weekBody .lesson .subj').first().textContent()).trim();
  await pressTool(page, '#subjectsBtn');
  const boxes = page.locator('#toolBody .mysubjects input');
  expect(await boxes.count()).toBeGreaterThan(1);
  await page.locator('#toolBody .mysubjects label').filter({ has: page.getByText(firstSubject, { exact: true }) }).locator('input').uncheck();
  await page.getByRole('button', { name: 'Zastosuj' }).click();
  await expect(page.locator('#hiddenNotice')).toBeVisible();
  expect(await page.locator('#weekBody .lesson').count()).toBeLessThan(before);
  const shown = (await page.locator('#weekBody .lesson .subj').allTextContents()).map((t) => t.trim());
  expect(shown).not.toContain(firstSubject);
  const href = await page.locator('#icsLink').getAttribute('href');
  expect(href.startsWith('blob:')).toBe(true);
  await showTool(page, '#icsLink');
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#icsLink').click()]);
  const text = fs.readFileSync(await download.path(), 'utf-8');
  expect(text.split(/\r?\n/)).not.toContain('SUMMARY:' + firstSubject);
  expect(text).toContain('BEGIN:VCALENDAR');
  await page.locator('#hiddenEdit').click();
  await page.getByRole('button', { name: 'Pokaż wszystkie' }).click();
  await expect(page.locator('#hiddenNotice')).toBeHidden();
  await expect(page.locator('#weekBody .lesson')).toHaveCount(before);  // waits for the redraw
  expect(problems).toEqual([]);
});

test('"Moje przedmioty" can hide one kind of a subject\'s classes and keep the rest', async ({ page }) => {
  const problems = await openGroup(page);
  const subject = 'Matematyka I';  // a lecture on Monday and exercises on Friday of the opening week
  const ofSubject = page.locator('#weekBody .lesson').filter({ has: page.getByText(subject, { exact: true }) });
  await expect(ofSubject).toHaveCount(2);
  const types = (await ofSubject.locator('.type').allTextContents()).map((t) => t.trim());
  await pressTool(page, '#subjectsBtn');
  const item = page.locator('#toolBody .mysub').filter({ has: page.locator('.mysub-head').getByText(subject, { exact: true }) });
  const parts = item.locator('.mysub-parts');
  await expect(parts).toBeHidden();
  await item.locator('.mysub-toggle').click();
  await expect(item.locator('.mysub-toggle')).toHaveAttribute('aria-expanded', 'true');
  await expect(parts.locator('label')).toHaveText(['wykłady', 'ćwiczenia']);
  await parts.locator('label').filter({ hasText: 'ćwiczenia' }).locator('input').uncheck();
  expect(await item.locator('.mysub-head input').evaluate((n) => n.indeterminate)).toBe(true);
  await page.getByRole('button', { name: 'Zastosuj' }).click();

  await expect(page.locator('#hiddenText')).toContainText('Ukryto 1 rodzaj zajęć');
  await expect(ofSubject).toHaveCount(1);
  expect((await ofSubject.locator('.type').textContent()).trim()).toBe(types[0]);
  await showTool(page, '#icsLink');
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#icsLink').click()]);
  const events = fs.readFileSync(await download.path(), 'utf-8').replace(/\r?\n[ \t]/g, '').split('BEGIN:VEVENT').slice(1);
  const kinds = events.filter((e) => e.split(/\r?\n/).includes('SUMMARY:' + subject)).map((e) => /^CATEGORIES:(.*)$/m.exec(e)[1].trim());
  expect(kinds).toContain('Wykład');
  expect(kinds).not.toContain('Ćwiczenia');

  await page.reload();
  await expect(page.locator('#hiddenText')).toContainText('Ukryto 1 rodzaj zajęć');
  await expect(ofSubject).toHaveCount(1);
  await page.locator('#hiddenEdit').click();
  await expect(item.locator('.mysub-parts')).toBeVisible();  // opened where part of a subject is hidden
  expect(await item.locator('.mysub-head input').evaluate((n) => n.indeterminate)).toBe(true);
  await item.locator('.mysub-head input').check();  // a mixed subject's box shows all of it again
  await expect(item.locator('.mysub-parts input:checked')).toHaveCount(2);
  await page.getByRole('button', { name: 'Zastosuj' }).click();
  await expect(page.locator('#hiddenNotice')).toBeHidden();
  await expect(ofSubject).toHaveCount(2);
  expect(problems).toEqual([]);
});

test('the system light theme is followed, and a stored choice wins and survives a reload', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  const problems = await openGroup(page);
  const bg = () => page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  expect(await bg()).toBe('rgb(242, 242, 247)');
  await page.locator('[data-theme-set="dark"]').click();
  expect(await page.evaluate(() => document.documentElement.getAttribute('data-theme'))).toBe('dark');
  // a chosen theme fades over for a moment, so wait for its final colour
  await expect.poll(bg).toBe('rgb(0, 0, 0)');
  await page.reload();
  await expect(page.locator('.lesson').first()).toBeVisible();
  expect(await bg()).toBe('rgb(0, 0, 0)');
  await expect(page.locator('[data-theme-set="dark"]')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('[data-theme-set="auto"]').click();
  await expect.poll(bg).toBe('rgb(242, 242, 247)');
  expect(problems).toEqual([]);
});

test('the front page and a group page in the light theme have no serious or critical accessibility violations', async ({ page }) => {
  test.slow();
  await page.emulateMedia({ colorScheme: 'light', reducedMotion: 'reduce' });
  const scan = async () => {
    await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running' || a.effect.getComputedTiming().iterations === Infinity));
    const results = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa']).analyze();
    return results.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
      .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
  };
  await openGroup(page);
  expect(await scan()).toEqual([]);
  await page.locator('#viewSeg button[data-view="list"]').click();
  expect(await scan()).toEqual([]);
  await page.goto('/');
  await expect(page.locator('h1')).toBeVisible();
  expect(await scan()).toEqual([]);
});

test('the map page stays dark whatever the system theme', async ({ page }) => {
  await page.emulateMedia({ colorScheme: 'light' });
  await page.goto('/mapa/');
  expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe('rgb(0, 0, 0)');
});

test('printing a week gives one clean A4 sheet without the page chrome', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'page.pdf is Chromium only');
  await openGroup(page);
  await page.emulateMedia({ media: 'print' });
  const pdf = await page.pdf({ format: 'A4', preferCSSPageSize: true });
  expect((pdf.toString('latin1').match(/\/Type\s*\/Page\b/g) || []).length).toBe(1);
  for (const gone of ['.tools', '.viewbar', '.live', '#progress', '.legend', '.themeswitch']) {
    await expect(page.locator(gone).first()).toBeHidden();
  }
  await expect(page.locator('.dow').first()).toBeVisible();
});

test('the first-visit tour opens once, pages with Dalej and is not repeated', async ({ page }) => {
  const problems = await openGroup(page, { path: `${GROUP}?tour=1` });
  const tour = page.locator('#tourSheet');
  await expect(tour).toBeVisible();
  await expect(page.locator('#tourSheet h3').first()).toHaveText('Przesuń, aby zmienić tydzień');
  await page.click('#tourNext');
  await expect(page.locator('#tourDots button[aria-current="true"]')).toHaveAttribute('aria-label', 'Krok 2 z 8');
  for (let i = 0; i < 6; i++) await page.click('#tourNext');
  await expect(page.locator('#tourNext')).toHaveText('Zaczynamy');
  await expect(page.locator('#tourSkip')).toBeHidden();
  await page.click('#tourNext');
  await expect(tour).toBeHidden();
  await page.reload();
  await page.waitForTimeout(2000);
  await expect(tour).toBeHidden();
  await page.click('#tourBtn');
  await expect(tour).toBeVisible();
  await page.click('#tourSkip');
  await expect(tour).toBeHidden();
  expect(problems).toEqual([]);
});

test('the tour stays closed for automated browsers unless asked', async ({ page }) => {
  await openGroup(page);
  await page.waitForTimeout(2000);
  await expect(page.locator('#tourSheet')).toBeHidden();
});

test('every finished class has its tick, on earlier days as well as today, and later ones do not', async ({ page }) => {
  await openGroup(page);
  const past = page.locator('.day.is-past .lesson');
  expect(await past.count()).toBeGreaterThan(0);
  expect(await page.locator('.day.is-past .lesson:not(.is-done)').count()).toBe(0);
  await expect(past.first().locator('.tick')).toBeVisible();
  const future = page.locator('.day:not(.is-past):not(.is-today) .lesson');
  if (await future.count()) await expect(future.first().locator('.tick')).toBeHidden();
  // an earlier week is all ticked too
  const before = await weekLabel(page).innerText();
  await page.keyboard.press('ArrowLeft');
  await expect(weekLabel(page)).not.toHaveText(before);
  const earlier = page.locator('.lesson');
  await expect(earlier.first()).toBeVisible();
  expect(await page.locator('.lesson:not(.is-done)').count()).toBe(0);
  await expect(earlier.first().locator('.tick')).toBeVisible();
});

test('the front page has no install link; installing is offered on the group page only', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('#installBtn')).toHaveCount(0);
  await page.goto(GROUP);
  await expect(page.locator('#installBtn')).toHaveCount(1);
});

test('"Gdzie odrobić?" lists only the type of the class that was clicked', async ({ page }) => {
  await openGroup(page);
  const subject = 'Podstawy grafiki inżynierskiej'; // has both a lecture and exercises in this plan
  for (const [type, other] of [['Ćwiczenia', 'Wykład'], ['Wykład', 'Ćwiczenia']]) {
    await page.goto(GROUP);
    const row = page.locator(`#weekBody .lesson[data-subject="${subject}"]`).filter({ hasText: type }).first();
    await row.locator('.subj').click({ force: true });
    await expect(page.locator('#toolSheet')).toBeVisible();
    await expect(page.locator('#toolBody > p').first()).toContainText(`Spotkanie: ${type} nr`);
    await expect(page.locator('#cuType')).toHaveCount(0); // no "all types" switch while a meeting is chosen
    const rows = page.locator('#toolBody .rows li');
    await expect(page.locator('#toolBody [role="status"]')).toBeVisible();
    const texts = await rows.allInnerTexts();
    for (const t of texts) { expect(t).toContain(type); expect(t).not.toContain(other); }
    await page.keyboard.press('Escape');
  }
});
