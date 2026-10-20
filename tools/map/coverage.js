// Write tools/map/coverage.json: every vector tile any view of the campus map can ask for.
//
// The map is held inside the campus bounds (src/campus.js) but may be tilted to MapLibre's maximum pitch, which shows the
// horizon well past them. Rather than guess a margin, this asks MapLibre itself: on a copy of the live map's transform it
// walks zoom, pitch, bearing and centre over the whole allowed range at screen sizes from a small phone to 5K, and
// collects the tiles each view covers, plus the three parent levels the source cache may fetch while children load.
//
//   npm run build && node tools/map/coverage.js && python3 tools/map/vendor_map.py
//
// Needs Playwright's Chromium (a dev dependency) and a built site/.
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('@playwright/test');

const ROOT = path.resolve(__dirname, '..', '..');
const PORT = 4199;
const SIZES = [[320, 568], [360, 640], [390, 844], [430, 932], [768, 1024], [1024, 1366], [1080, 1920],
  [1280, 800], [1440, 900], [1920, 1080], [2560, 1440], [3840, 2160], [5120, 2880]];

(async () => {
  const server = spawn(process.execPath, [path.join(ROOT, 'tests', 'e2e', 'serve.js')], { env: { ...process.env, PORT: String(PORT) }, stdio: 'ignore' });
  const browser = await chromium.launch({ args: ['--enable-unsafe-swiftshader', '--use-angle=swiftshader'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
    // keep a handle on the map the page creates (it lives in a closure)
    await page.addInitScript(() => {
      let lib;
      Object.defineProperty(window, 'maplibregl', { configurable: true, get: () => lib, set: (v) => {
        lib = v;
        const add = v.Map.prototype.addControl;
        v.Map.prototype.addControl = function (...a) { window.__map = this; return add.apply(this, a); };
      } });
    });
    await new Promise((r) => setTimeout(r, 500));
    await page.goto(`http://127.0.0.1:${PORT}/mapa/`);
    await page.waitForFunction(() => window.__map && window.__map.loaded(), null, { timeout: 90000 });
    const all = new Set();
    for (const [width, height] of SIZES) {
      await page.setViewportSize({ width, height });
      const tiles = await page.evaluate(() => {
        const map = window.__map;
        map.resize();
        const source = Object.values(map.getStyle().sources).find((s) => s.type === 'vector');
        const [[W, S], [E, N]] = map.getMaxBounds().toArray();
        const t = map.transform.clone();
        const found = new Set();
        for (let zoom = 0; zoom <= map.getMaxZoom(); zoom += 0.5) {
          for (const pitch of [0, 30, 45, 55, map.getMaxPitch()]) {
            for (let bearing = 0; bearing < 360; bearing += 15) {
              for (let i = 0; i <= 4; i++) {
                for (let j = 0; j <= 4; j++) {
                  t.zoom = zoom; t.pitch = pitch; t.bearing = bearing;
                  t.center = new maplibregl.LngLat(W + (E - W) * i / 4, S + (N - S) * j / 4);  // the transform clamps it to the bounds
                  const ids = t.coveringTiles({ tileSize: 512, minzoom: source.minzoom || 0, maxzoom: source.maxzoom, roundZoom: false, reparseOverscaled: true });
                  for (const { canonical: c } of ids) {
                    for (let up = 0; up <= 3 && c.z - up >= 0; up++) found.add(`${c.z - up}/${c.x >> up}/${c.y >> up}`);
                  }
                }
              }
            }
          }
        }
        return [...found];
      });
      tiles.forEach((tile) => all.add(tile));
      console.log(`${width}x${height}: ${tiles.length} tiles, ${all.size} in all`);
    }
    const sorted = [...all].sort((a, b) => {
      const [p, q] = [a, b].map((s) => s.split('/').map(Number));
      return p[0] - q[0] || p[1] - q[1] || p[2] - q[2];
    });
    fs.writeFileSync(path.join(__dirname, 'coverage.json'), JSON.stringify(sorted, null, 0).replace(/","/g, '",\n"') + '\n');
    console.log(`wrote tools/map/coverage.json: ${sorted.length} tiles`);
  } finally {
    await browser.close();
    server.kill();
  }
})();
