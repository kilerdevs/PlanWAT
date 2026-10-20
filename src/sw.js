/* PlanWAT offline support. build.py copies this file to site/sw.js and fills in the version.
   Pages and calendars: network first (fresh when online), the last copy when the network fails or is slow.
   Shared styles, scripts and fonts (assets/): cache first — their names carry a hash of their bytes, so a
   name never changes meaning. Styles and scripts are precached with the worker; a font is saved the first
   time a page draws with it. The map's engine and tiles (mapa/lib/, mapa/tiles/) are left to the browser's own cache.
   The production site and the dev preview share an origin: each worker names its caches after its own scope,
   cleans up only those, and the root worker leaves dev/ to the preview's own worker. */
'use strict';
var VERSION = '@@VERSION@@';
var SCOPE = self.registration.scope; /* ends with "/" */
var PREFIX = 'planwat:' + SCOPE + ':';
var CACHE = PREFIX + VERSION;
var PRECACHE = ['./', 'mapa/'@@ASSETS@@];
var SHARED = /^assets\/.*\.(js|css|woff2)$/;
var FRESH = /\.(ics|json|webmanifest|png|svg)$/;
var TIMEOUT = 4000; /* ms before a slow network gives way to the saved copy */

function save(req, res) {
  if (!res || res.redirected || !(res.ok || res.type === 'opaque')) return;
  var copy = res.clone();
  caches.open(CACHE).then(function (c) { return c.put(req, copy); }).catch(function () {});
}

function saved(req, loose) {
  return caches.open(CACHE).then(function (c) { return c.match(req, { ignoreSearch: !!loose }); });
}

function networkFirst(req, loose) {
  var network = fetch(req).then(function (res) { save(req, res); return res; });
  network.catch(function () {}); /* handled below; keeps a late failure from being reported as unhandled */
  var slow = new Promise(function (resolve) { setTimeout(resolve, TIMEOUT); })
    .then(function () { return saved(req, loose); })
    .then(function (hit) { return hit || network; });
  return Promise.race([network, slow]).catch(function () {
    return saved(req, loose).then(function (hit) { return hit || Response.error(); });
  });
}

function cacheFirst(req) {
  return saved(req).then(function (hit) {
    return hit || fetch(req).then(function (res) { save(req, res); return res; });
  });
}

self.addEventListener('install', function (e) {
  e.waitUntil(caches.open(CACHE).then(function (c) {
    /* one by one: a page that fails to load must not stop the worker from installing */
    return Promise.all(PRECACHE.map(function (p) { return c.add(new URL(p, SCOPE).href).catch(function () {}); }));
  }).then(function () { return self.skipWaiting(); }));
});

self.addEventListener('activate', function (e) {
  e.waitUntil(caches.keys().then(function (keys) {
    return Promise.all(keys.filter(function (k) { return k.indexOf(PREFIX) === 0 && k !== CACHE; })
      .map(function (k) { return caches.delete(k); }));
  }).then(function () { return self.clients.claim(); }));
});

self.addEventListener('fetch', function (e) {
  var req = e.request;
  if (req.method !== 'GET') return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin || req.url.indexOf(SCOPE) !== 0) return;
  var rel = url.pathname.slice(new URL(SCOPE).pathname.length);
  if (rel.indexOf('dev/') === 0) return; /* the dev preview has its own worker */
  if (req.mode === 'navigate') e.respondWith(networkFirst(req, true));
  else if (SHARED.test(rel)) e.respondWith(cacheFirst(req));
  else if (FRESH.test(rel)) e.respondWith(networkFirst(req));
});
