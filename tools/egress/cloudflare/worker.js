/**
 * PlanWAT fetch relay.
 *
 * Cloudflare's egress is served by the WAT faculties that wall the runners' datacenter and
 * home addresses. This Worker fetches one allowlisted URL and returns the upstream status,
 * validators and body, so the crawler can keep its own URL handling and block detection.
 *
 * It is deliberately not an open proxy:
 *   - PLANWAT_RELAY_TOKEN must be set (wrangler secret put) and sent as a bearer token;
 *   - only HTTPS targets on the exact hosts in PLANWAT_RELAY_HOSTS are fetched;
 *   - redirects are followed manually, at most three, and every hop stays on that list;
 *   - the caller's cookies and Authorization header are never forwarded upstream. Cookies an
 *     upstream sets are replayed along that request's redirect chain and kept per host for a
 *     short while (Incapsula answers a first visit with a same-URL 307 plus cookies, and treats
 *     a client that keeps them as one session), and upstream Set-Cookie, Content-Encoding and
 *     Content-Length headers are not returned.
 *
 * Configuration: see wrangler.toml and README.md.
 */

const DEFAULT_HOSTS = [
  'wlo.wat.edu.pl',
  'wel.wat.edu.pl',
  'wml.wat.edu.pl',
  'wtc.wat.edu.pl',
  'www.wig.wat.edu.pl',
  'wig.wat.edu.pl',
];

// Mirrors tools/refresh/relay.py. Keep the crawler and the Worker in step when this changes.
const FORWARD_HEADERS = [
  'accept',
  'accept-language',
  'if-modified-since',
  'if-none-match',
  'range',
  'referer',
  'user-agent',
];

// Only headers that describe the representation. Content-Length is omitted because fetch may
// decode the body, and Content-Encoding/Set-Cookie are intentionally not relayed.
const RESPONSE_HEADERS = [
  'accept-ranges',
  'cache-control',
  'content-disposition',
  'content-language',
  'content-range',
  'content-type',
  'etag',
  'expires',
  'last-modified',
  'vary',
];

const REDIRECT_STATUSES = new Set([301, 302, 303, 307, 308]);
const MAX_REDIRECTS = 3;
const MAX_TARGET_LENGTH = 4096;
const FETCH_TIMEOUT_MS = 45000;
const COOKIE_TTL_S = 600;

class RelayError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function hostSet(env) {
  const raw = String(env.PLANWAT_RELAY_HOSTS || '').trim().toLowerCase();
  if (['off', 'none', '0', 'false', 'no'].includes(raw)) return new Set();
  const values = (!raw || ['auto', 'default', '1', 'true', 'yes'].includes(raw))
    ? DEFAULT_HOSTS
    : raw.split(/[\s,]+/);
  return new Set(values
    .map((host) => host.trim().replace(/\.$/, ''))
    .filter(Boolean));
}

function textResponse(status, message) {
  return new Response(`${message}\n`, {
    status,
    headers: {
      'Content-Type': 'text/plain; charset=utf-8',
      'Cache-Control': 'no-store',
      'X-Content-Type-Options': 'nosniff',
    },
  });
}

async function digest(value) {
  const bytes = new TextEncoder().encode(value);
  return new Uint8Array(await crypto.subtle.digest('SHA-256', bytes));
}

async function authorized(request, env) {
  const secret = String(env.PLANWAT_RELAY_TOKEN || '').trim();
  if (!secret) return false;
  const match = /^Bearer\s+(.+)$/i.exec(request.headers.get('Authorization') || '');
  if (!match) return false;
  const [got, want] = await Promise.all([digest(match[1].trim()), digest(secret)]);
  let diff = 0;
  for (let i = 0; i < got.length; i += 1) diff |= got[i] ^ want[i];
  return diff === 0;
}

function targetFrom(request) {
  const raw = new URL(request.url).searchParams.get('url');
  if (!raw || raw.length > MAX_TARGET_LENGTH) return null;
  let target;
  try {
    target = new URL(raw);
  } catch {
    return null;
  }
  if (target.protocol !== 'https:' || target.username || target.password) return null;
  if (target.port && target.port !== '443') return null;
  target.hash = '';
  return target;
}

function upstreamHeaders(request) {
  const headers = new Headers();
  for (const name of FORWARD_HEADERS) {
    const value = request.headers.get(name);
    if (value !== null) headers.set(name, value);
  }
  return headers;
}

// Incapsula's first answer is a 307 to the same URL with its session cookies; a browser (and
// curl_cffi on the crawler) stores them and retries. Keep that handshake inside one Worker
// request: the caller's own cookies stay behind, and nothing is kept between requests.
function setUpstreamCookies(jar, upstream) {
  const lines = typeof upstream.headers.getSetCookie === 'function'
    ? upstream.headers.getSetCookie()
    : [upstream.headers.get('set-cookie')].filter(Boolean);
  for (const line of lines) {
    const pair = line.split(';', 1)[0].trim();
    const eq = pair.indexOf('=');
    if (eq > 0) jar.set(pair.slice(0, eq), pair);
  }
  return jar;
}

function cookieSnapshot(jar) {
  return [...jar.values()].join('; ');
}

// Incapsula binds its session cookie to the address and treats every request without it as a
// new visitor; a burst of new visitors from one relay address is what its wall blocks. Keeping
// the cookies per host for a few minutes makes the crawler one returning session instead.
function cookieCacheKey(host) {
  return new Request(`https://planwat-relay.invalid/cookies/${host}`);
}

async function loadCookies(host) {
  if (typeof caches === 'undefined') return new Map();
  try {
    const hit = await caches.default.match(cookieCacheKey(host));
    if (!hit) return new Map();
    const pairs = await hit.json();
    return new Map(pairs.map((pair) => [pair.slice(0, pair.indexOf('=')), pair]));
  } catch {
    return new Map();
  }
}

async function saveCookies(host, jar) {
  if (typeof caches === 'undefined' || !jar.size) return;
  try {
    await caches.default.put(cookieCacheKey(host), new Response(JSON.stringify([...jar.values()]), {
      headers: {
        'Cache-Control': `max-age=${COOKIE_TTL_S}`,
        'Content-Type': 'application/json',
      },
    }));
  } catch {
    // The handshake still worked for this request; the next one starts a new session.
  }
}

function responseHeaders(upstream) {
  const headers = new Headers();
  for (const name of RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value !== null) headers.set(name, value);
  }
  headers.set('Cache-Control', 'no-store');
  headers.set('X-Content-Type-Options', 'nosniff');
  return headers;
}

async function fetchAllowed(
  target, request, hosts, redirects = MAX_REDIRECTS, seen = new Set(), jar = new Map()) {
  const host = target.hostname.toLowerCase().replace(/\.$/, '');
  if (!hosts.has(host)) throw new RelayError(403, 'host not allowed');
  if (redirects < 0 || seen.has(target.href)) throw new RelayError(502, 'too many redirects');
  seen.add(target.href);

  const headers = upstreamHeaders(request);
  if (jar.size) headers.set('cookie', cookieSnapshot(jar));

  let upstream;
  try {
    upstream = await fetch(target.href, {
      method: request.method,
      headers,
      redirect: 'manual',
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
  } catch {
    throw new RelayError(502, 'upstream fetch failed');
  }

  const before = cookieSnapshot(jar);
  setUpstreamCookies(jar, upstream);
  const learned = cookieSnapshot(jar) !== before;

  const location = upstream.headers.get('Location');
  if (REDIRECT_STATUSES.has(upstream.status) && location) {
    let next;
    try {
      next = new URL(location, target);
    } catch {
      throw new RelayError(502, 'bad redirect');
    }
    next.hash = '';
    // A same-URL redirect is Incapsula's cookie handshake when it set a cookie, and a loop
    // when it did not.
    if (learned && next.href === target.href) seen.delete(target.href);
    return fetchAllowed(next, request, hosts, redirects - 1, seen, jar);
  }
  return upstream;
}

export default {
  async fetch(request, env, ctx) {
    if (request.method !== 'GET' && request.method !== 'HEAD') {
      return textResponse(405, 'method not allowed');
    }
    if (!String(env.PLANWAT_RELAY_TOKEN || '').trim()) {
      return textResponse(503, 'relay token not configured');
    }
    if (!(await authorized(request, env))) {
      return textResponse(401, 'unauthorized');
    }
    const target = targetFrom(request);
    if (!target) return textResponse(400, 'missing or invalid url');
    const hosts = hostSet(env);
    if (!hosts.size) return textResponse(403, 'relay has no allowed hosts');

    try {
      const jar = await loadCookies(target.hostname);
      const upstream = await fetchAllowed(target, request, hosts, MAX_REDIRECTS, new Set(), jar);
      const saving = saveCookies(target.hostname, jar);
      if (ctx && typeof ctx.waitUntil === 'function') ctx.waitUntil(saving);
      else await saving;
      const noBody = request.method === 'HEAD'
        || upstream.status === 204
        || upstream.status === 205
        || upstream.status === 304;
      return new Response(noBody ? null : upstream.body, {
        status: upstream.status,
        headers: responseHeaders(upstream),
      });
    } catch (err) {
      if (err instanceof RelayError) return textResponse(err.status, err.message);
      return textResponse(502, 'upstream fetch failed');
    }
  },
};

export { authorized, fetchAllowed, hostSet, targetFrom, RelayError };
