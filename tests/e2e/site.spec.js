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
  await page.locator('#cuFree').check();
  await expect(tool(page).locator('.tag.warn')).toHaveCount(0);
  await page.keyboard.press('Escape');
  await expect(tool(page)).toBeHidden();
  await noCsp(page);
});

test('statistics sum up the semester', async ({ page }) => {
  await openGroup(page);
  await page.locator('#statsBtn').click();
  await expect(page.locator('#toolTitle')).toHaveText('Statystyki planu');
  await expect(tool(page).locator('.tile b').first()).toHaveText('216');
  await expect(tool(page).locator('.cols span')).toHaveCount(22);
  await expect(tool(page).locator('.cols span.is-cur')).toHaveCount(1);
  await tool(page).getByRole('button', { name: 'Pokaż dane liczbowe' }).click();
  await expect(tool(page).locator('table.data tbody tr')).toHaveCount(22);
});

test('the calendar sheet offers subscription links and the file', async ({ page }) => {
  await openGroup(page);
  await page.locator('#calBtn').click();
  await expect(page.locator('#calApple')).toHaveAttribute('href', /^webcal:\/\/127\.0\.0\.1:\d+\/WCY26KY3S1\/plan\.ics$/);
  await expect(page.locator('#calGoogle')).toHaveAttribute('href', /^https:\/\/calendar\.google\.com\/calendar\/render\?cid=webcal%3A%2F%2F/);
  await expect(tool(page).locator('a[download="plan-WCY26KY3S1.ics"]')).toHaveAttribute('href', 'plan.ics');
});

test('share hands the page link to the system share sheet', async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'share', { configurable: true, value: (d) => { window.__shared = d; return Promise.resolve(); } });
  });
  await openGroup(page);
  await page.locator('#shareBtn').click();
  await expect.poll(() => page.evaluate(() => window.__shared && window.__shared.url)).toMatch(/\/WCY26KY3S1\/$/);
});

test('comparing groups shows both plans and the shared free time', async ({ page }) => {
  await openGroup(page);
  await page.locator('#compareBtn').click();
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

test('favourites and recent groups appear on the front page', async ({ page }) => {
  await openGroup(page);
  await page.locator('#favBtn').click();
  await expect(page.locator('#favBtn')).toHaveAttribute('aria-pressed', 'true');
  await page.goto('/');
  await expect(page.locator('#favList a.pick')).toHaveText(['WCY26KY3S1']);
  await expect(page.locator('#recentWrap')).toBeHidden(); // the only recent group is already a favourite
  await page.locator('#favList a.pick').click();
  await expect(page).toHaveURL(ON_GROUP);
  await page.locator('#favBtn').click();
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
  test.slow(); // five full axe scans
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await openGroup(page);
  const scan = async () => {
    // a sheet still fading in reads as low contrast; wait for every finite animation to end
    await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running' || a.effect.getComputedTiming().iterations === Infinity));
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
  for (const id of ['#statsBtn', '#calBtn']) {
    await page.locator(id).click();
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
