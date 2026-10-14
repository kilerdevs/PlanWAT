// End-to-end tests against the built site (site/), served the way GitHub Pages serves it
// (tests/e2e/serve.js): plain static files, no security headers, so the per-page meta CSP is what
// the browser enforces.
// Build first: npm run build   (fixed --today so term selection matches the frozen clock in the specs)
const { defineConfig, devices } = require('@playwright/test');

const PORT = 4173;
// Optional: PW_CHROMIUM=/usr/bin/chromium runs the Chromium projects on a system browser
// (e.g. Alpine, where Playwright's bundled build is unavailable). CI uses the bundled browsers.
const chromium = process.env.PW_CHROMIUM ? { launchOptions: { executablePath: process.env.PW_CHROMIUM } } : {};

module.exports = defineConfig({
  testDir: 'tests/e2e',
  timeout: 30000,
  expect: { timeout: 7000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    timezoneId: 'Europe/Warsaw',
    locale: 'pl-PL',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    // The offline service worker would answer requests the specs mock with page.route; only offline.spec.js allows it.
    serviceWorkers: 'block',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 }, ...chromium } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'], viewport: { width: 1440, height: 900 } } },
    { name: 'mobile-safari', use: { ...devices['iPhone 13'] } },
    { name: 'mobile-chrome', use: { ...devices['Pixel 7'], ...chromium } },
  ],
  webServer: {
    command: `node tests/e2e/serve.js`,
    env: { PORT: String(PORT) },
    url: `http://127.0.0.1:${PORT}/`,
    reuseExistingServer: !process.env.CI,
  },
});
