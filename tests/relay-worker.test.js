// Tests for tools/egress/cloudflare/worker.js (the Cloudflare fetch relay).
// Run: node --test tests/relay-worker.test.js
//
// The Worker is an ES module and the rest of the suite is CommonJS, so load its source as a
// data: URL instead of adding a package.json next to it (wrangler should not need one).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const SOURCE = fs.readFileSync(
  path.join(__dirname, '..', 'tools', 'egress', 'cloudflare', 'worker.js'), 'utf8');
const MODULE_URL = 'data:text/javascript;base64,' + Buffer.from(SOURCE).toString('base64');
let loaded;
function worker() {
  loaded ||= import(MODULE_URL);
  return loaded;
}

const ENV = {
  PLANWAT_RELAY_TOKEN: 'relay-secret',
  PLANWAT_RELAY_HOSTS: 'wtc.wat.edu.pl,www.wig.wat.edu.pl',
};
const RELAY = 'https://relay.example/';

function relayRequest(target, init = {}) {
  const headers = { Authorization: 'Bearer relay-secret', ...(init.headers || {}) };
  return new Request(RELAY + '?url=' + encodeURIComponent(target), { ...init, headers });
}

function stubFetch(respond) {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return respond(String(url), init);
  };
  return { calls, restore: () => { globalThis.fetch = original; } };
}

function stubCaches(initial = []) {
  const store = new Map(initial);
  globalThis.caches = {
    default: {
      async match(request) {
        const body = store.get(request.url);
        return body === undefined ? undefined : new Response(body);
      },
      async put(request, response) {
        store.set(request.url, await response.text());
      },
      async delete(request) {
        store.delete(request.url);
      },
    },
  };
  return { store, restore: () => { delete globalThis.caches; } };
}

const COOKIE_KEY = 'https://planwat-relay.invalid/cookies/wtc.wat.edu.pl';

test('host list defaults, trims and can be switched off', async () => {
  const { hostSet } = await worker();
  const defaults = hostSet({});
  assert.ok(defaults.has('wtc.wat.edu.pl'));
  assert.ok(defaults.has('wig.wat.edu.pl'));
  assert.ok(defaults.has('wlo.wat.edu.pl'));
  assert.equal(hostSet({ PLANWAT_RELAY_HOSTS: 'off' }).size, 0);
  assert.deepEqual(
    [...hostSet({ PLANWAT_RELAY_HOSTS: ' WTC.WAT.EDU.PL. , wml.wat.edu.pl ' })],
    ['wtc.wat.edu.pl', 'wml.wat.edu.pl']);
});

test('targets are https-only, credential-free and on the default port', async () => {
  const { targetFrom } = await worker();
  const target = (url) => targetFrom(new Request(RELAY + '?url=' + encodeURIComponent(url)));

  assert.equal(target('https://wtc.wat.edu.pl/a#fragment').href, 'https://wtc.wat.edu.pl/a');
  assert.equal(target('http://wtc.wat.edu.pl/a'), null);
  assert.equal(target('https://user:pass@wtc.wat.edu.pl/a'), null);
  assert.equal(target('https://wtc.wat.edu.pl:8443/a'), null);
  assert.equal(target('not a url'), null);
  assert.equal(targetFrom(new Request(RELAY)), null);
});

test('the bearer token is required and must match exactly', async () => {
  const { authorized } = await worker();
  const withToken = (value) => new Request(RELAY, { headers: { Authorization: value } });

  assert.equal(await authorized(withToken('Bearer relay-secret'), ENV), true);
  assert.equal(await authorized(withToken('bearer relay-secret'), ENV), true);
  assert.equal(await authorized(withToken('Bearer wrong'), ENV), false);
  assert.equal(await authorized(withToken('relay-secret'), ENV), false);
  assert.equal(await authorized(new Request(RELAY), ENV), false);
  assert.equal(await authorized(withToken('Bearer relay-secret'), {}), false);
});

test('the handler refuses bad methods, tokens and targets before fetching', async () => {
  const handler = (await worker()).default;
  const stub = stubFetch(() => assert.fail('must not fetch'));
  try {
    const post = await handler.fetch(
      relayRequest('https://wtc.wat.edu.pl/', { method: 'POST' }), ENV);
    assert.equal(post.status, 405);

    const noSecret = await handler.fetch(relayRequest('https://wtc.wat.edu.pl/'), {});
    assert.equal(noSecret.status, 503);

    const wrong = await handler.fetch(new Request(
      RELAY + '?url=' + encodeURIComponent('https://wtc.wat.edu.pl/'),
      { headers: { Authorization: 'Bearer wrong' } }), ENV);
    assert.equal(wrong.status, 401);

    const missing = await handler.fetch(
      new Request(RELAY, { headers: { Authorization: 'Bearer relay-secret' } }), ENV);
    assert.equal(missing.status, 400);

    const outside = await handler.fetch(relayRequest('https://example.com/'), ENV);
    assert.equal(outside.status, 403);

    assert.deepEqual(stub.calls, []);
  } finally {
    stub.restore();
  }
});

test('a successful fetch keeps representation headers and drops cookies and length', async () => {
  const handler = (await worker()).default;
  const stub = stubFetch(() => new Response('<html>ok</html>', {
    status: 200,
    headers: {
      'Content-Type': 'text/html; charset=utf-8',
      'Content-Length': '14',
      'Content-Encoding': 'gzip',
      'Set-Cookie': 'session=upstream',
      ETag: '"v1"',
      'Last-Modified': 'Mon, 26 Oct 2026 10:00:00 GMT',
    },
  }));
  try {
    const response = await handler.fetch(relayRequest('https://wtc.wat.edu.pl/Plany/index.xml', {
      headers: { Cookie: 'runner=1', 'If-None-Match': '"v1"' },
    }), ENV);

    assert.equal(response.status, 200);
    assert.equal(await response.text(), '<html>ok</html>');
    assert.equal(response.headers.get('content-type'), 'text/html; charset=utf-8');
    assert.equal(response.headers.get('etag'), '"v1"');
    assert.equal(response.headers.get('last-modified'), 'Mon, 26 Oct 2026 10:00:00 GMT');
    assert.equal(response.headers.get('set-cookie'), null);
    assert.equal(response.headers.get('content-length'), null);
    assert.equal(response.headers.get('content-encoding'), null);
    assert.equal(response.headers.get('cache-control'), 'no-store');

    const sent = stub.calls[0];
    assert.equal(sent.url, 'https://wtc.wat.edu.pl/Plany/index.xml');
    assert.equal(sent.init.headers.get('authorization'), null);
    assert.equal(sent.init.headers.get('cookie'), null);
    assert.equal(sent.init.headers.get('if-none-match'), '"v1"');
  } finally {
    stub.restore();
  }
});

test('redirects are followed manually and must stay on the allowlist', async () => {
  const handler = (await worker()).default;
  const stub = stubFetch((url) => {
    if (url.endsWith('/a')) return new Response(null, { status: 302, headers: { Location: '/b' } });
    if (url.endsWith('/b')) return new Response('done', { status: 200 });
    if (url.endsWith('/out')) {
      return new Response(null, { status: 302, headers: { Location: 'https://example.com/' } });
    }
    return new Response('loop', { status: 200 });
  });
  try {
    const followed = await handler.fetch(relayRequest('https://wtc.wat.edu.pl/a'), ENV);
    assert.equal(followed.status, 200);
    assert.equal(await followed.text(), 'done');
    assert.deepEqual(stub.calls.map((call) => call.url), [
      'https://wtc.wat.edu.pl/a',
      'https://wtc.wat.edu.pl/b',
    ]);

    stub.calls.length = 0;
    const escaped = await handler.fetch(relayRequest('https://wtc.wat.edu.pl/out'), ENV);
    assert.equal(escaped.status, 403);
    assert.deepEqual(stub.calls.map((call) => call.url), ['https://wtc.wat.edu.pl/out']);
  } finally {
    stub.restore();
  }
});

test('a same-URL redirect that sets a cookie is retried with it', async () => {
  const handler = (await worker()).default;
  const stub = stubFetch((url, init) => {
    if (stub.calls.length === 1) {
      return new Response(null, {
        status: 307,
        headers: {
          Location: 'https://wtc.wat.edu.pl/Plany/index.xml',
          'Set-Cookie': 'incap_ses_1=abc; Path=/; Domain=.wat.edu.pl; Secure; HttpOnly',
        },
      });
    }
    return new Response('plan', { status: 200 });
  });
  try {
    const response = await handler.fetch(relayRequest('https://wtc.wat.edu.pl/Plany/index.xml', {
      headers: { Cookie: 'runner=1' },
    }), ENV);
    assert.equal(response.status, 200);
    assert.equal(await response.text(), 'plan');
    assert.equal(stub.calls.length, 2);
    assert.equal(stub.calls[0].init.headers.get('cookie'), null);
    assert.equal(stub.calls[1].init.headers.get('cookie'), 'incap_ses_1=abc');
    assert.equal(response.headers.get('set-cookie'), null);
  } finally {
    stub.restore();
  }
});

test('upstream cookies are kept per host between requests', async () => {
  const handler = (await worker()).default;
  const store = new Map();
  globalThis.caches = {
    default: {
      async match(request) {
        const body = store.get(request.url);
        return body === undefined ? undefined : new Response(body);
      },
      async put(request, response) {
        store.set(request.url, await response.text());
      },
    },
  };
  let first = true;
  const stub = stubFetch((url, init) => {
    if (first) {
      assert.equal(init.headers.get('cookie'), null);
      first = false;
      return new Response(null, {
        status: 307,
        headers: {
          Location: 'https://wtc.wat.edu.pl/Plany/index.xml',
          'Set-Cookie': 'incap_ses_1=abc; Path=/; Domain=.wat.edu.pl',
        },
      });
    }
    return new Response('plan', { status: 200 });
  });
  try {
    const a = await handler.fetch(relayRequest('https://wtc.wat.edu.pl/Plany/index.xml'), ENV);
    assert.equal(a.status, 200);

    stub.calls.length = 0;
    first = false;  // the second request starts with the cached cookie, no challenge
    const b = await handler.fetch(relayRequest('https://wtc.wat.edu.pl/Plany/index.xml'), ENV);
    assert.equal(b.status, 200);
    assert.equal(stub.calls.length, 1);
    assert.equal(stub.calls[0].init.headers.get('cookie'), 'incap_ses_1=abc');
  } finally {
    stub.restore();
    delete globalThis.caches;
  }
});

test('a 403 is retried from a fresh session and drops the cached cookies', async () => {
  const handler = (await worker()).default;
  const cache = stubCaches([[COOKIE_KEY, JSON.stringify(['incap_ses_1=stale'])]]);
  let first = true;
  const stub = stubFetch((url, init) => {
    if (first) {
      first = false;
      assert.equal(init.headers.get('cookie'), 'incap_ses_1=stale');
      return new Response('blocked', {
        status: 403,
        headers: { 'Set-Cookie': 'incap_ses_1=blocked; Path=/' },
      });
    }
    assert.equal(init.headers.get('cookie'), null);  // the stale session did not ride along
    return new Response('plan', {
      status: 200,
      headers: { 'Set-Cookie': 'incap_ses_1=fresh; Path=/' },
    });
  });
  try {
    const response = await handler.fetch(relayRequest('https://wtc.wat.edu.pl/Plany/index.xml'), ENV);
    assert.equal(response.status, 200);
    assert.equal(await response.text(), 'plan');
    assert.equal(stub.calls.length, 2);
    assert.deepEqual(JSON.parse(cache.store.get(COOKIE_KEY)), ['incap_ses_1=fresh']);
  } finally {
    stub.restore();
    cache.restore();
  }
});

test('a wall that survives every retry is returned without poisoning the cookie cache', async () => {
  const handler = (await worker()).default;
  const cache = stubCaches([[COOKIE_KEY, JSON.stringify(['incap_ses_1=stale'])]]);
  const stub = stubFetch(() => new Response('blocked', {
    status: 403,
    headers: { 'Set-Cookie': 'incap_ses_1=blocked; Path=/' },
  }));
  try {
    const response = await handler.fetch(relayRequest('https://wtc.wat.edu.pl/'), ENV);
    assert.equal(response.status, 403);
    assert.equal(stub.calls.length, 3);  // initial + two fresh-session retries
    assert.equal(stub.calls[0].init.headers.get('cookie'), 'incap_ses_1=stale');
    assert.equal(stub.calls[1].init.headers.get('cookie'), null);
    assert.equal(stub.calls[2].init.headers.get('cookie'), null);
    assert.equal(cache.store.has(COOKIE_KEY), false);
  } finally {
    stub.restore();
    cache.restore();
  }
});

test('a same-URL redirect without cookies is a loop, not a retry', async () => {
  const handler = (await worker()).default;
  const stub = stubFetch(() => new Response(null, {
    status: 307,
    headers: { Location: 'https://wtc.wat.edu.pl/Plany/index.xml' },
  }));
  try {
    const response = await handler.fetch(relayRequest('https://wtc.wat.edu.pl/Plany/index.xml'), ENV);
    assert.equal(response.status, 502);
    assert.equal(stub.calls.length, 1);
  } finally {
    stub.restore();
  }
});

test('a redirect loop stops after three hops', async () => {
  const handler = (await worker()).default;
  const stub = stubFetch((url) => new Response(null, {
    status: 302,
    headers: { Location: url.replace(/\/\d+$/, (n) => '/' + (Number(n.slice(1)) + 1)) },
  }));
  try {
    const response = await handler.fetch(relayRequest('https://wtc.wat.edu.pl/0'), ENV);
    assert.equal(response.status, 502);
    assert.equal(stub.calls.length, 4);  // initial + three redirects
  } finally {
    stub.restore();
  }
});

test('HEAD is relayed without a body', async () => {
  const handler = (await worker()).default;
  const stub = stubFetch((url, init) => {
    assert.equal(init.method, 'HEAD');
    return new Response(null, { status: 200, headers: { 'Content-Type': 'text/html' } });
  });
  try {
    const response = await handler.fetch(
      relayRequest('https://wtc.wat.edu.pl/', { method: 'HEAD' }), ENV);
    assert.equal(response.status, 200);
    assert.equal(await response.text(), '');
  } finally {
    stub.restore();
  }
});

test('a conditional 304 keeps its validator and has no body', async () => {
  const handler = (await worker()).default;
  const stub = stubFetch(() => new Response(null, {
    status: 304,
    headers: { ETag: '"v2"', 'Last-Modified': 'Mon, 26 Oct 2026 10:00:00 GMT' },
  }));
  try {
    const response = await handler.fetch(relayRequest('https://wtc.wat.edu.pl/', {
      headers: { 'If-None-Match': '"v2"' },
    }), ENV);
    assert.equal(response.status, 304);
    assert.equal(response.headers.get('etag'), '"v2"');
    assert.equal(response.headers.get('last-modified'), 'Mon, 26 Oct 2026 10:00:00 GMT');
    assert.equal(await response.text(), '');
  } finally {
    stub.restore();
  }
});
