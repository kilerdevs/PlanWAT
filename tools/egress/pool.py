"""Public proxy pool for the PlanWAT egress rotator (DeadDropMGMT pattern, ported to Python).

Sources are the same GitHub proxy lists DeadDropMGMT discovers from: proxifly (JSON),
monosans / thespeedx / roosterkid (plain ip:port text).

Two-round acceptance, like DeadDropMGMT's Round 1 / Round 2:
  Round 1 (alive): the proxy fetches a neutral page (OSM tile). Pass = the proxy works.
  Round 2 (verified for a host): the proxy fetches that faculty's own index page.
  Pass = the proxy actually reaches our target (an Incapsula-fronted host drops
  datacenter IPs at the network level, so aliveness alone says nothing).

`pick(host)` hands out proxies verified for that host, healthy-first by latency —
the same ok → new → fail + latency sort as osm_proxy_pool()/maps_pick_proxy().
Hosts with no verified proxy get None and the server falls back to direct egress
(operator's fail-open choice) instead of failing closed.

Dead proxies are auto-replaced: the maintain loop reseeds from fresh lists whenever
coverage drops, and entries that keep failing are pruned. The server also marks
every real use (ok + latency on success, fail on refusal), so the pool learns
between reseeds — the osm_proxy_mark() equivalent.

Nothing here imports the proxy server, so it is unit-tested offline (tests/test_egress.py).
"""
import json
import os
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

POOL_VERSION = 2

# (name, url, kind, scheme for bare ip:port entries) — same set as DeadDropMGMT's
# PROXY_DISCOVERY_SOURCES, http+socks only (https upstreams dropped: no TLS-wrap
# exists in chain_connect, so an https:// proxy could never be chained).
LIST_SOURCES = (
    ('proxifly', 'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.json', 'proxifly', ''),
    ('monosans-http', 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt', 'plain', 'http'),
    ('monosans-socks5', 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt', 'plain', 'socks5'),
    ('monosans-socks4', 'https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt', 'plain', 'socks4'),
    ('thespeedx-http', 'https://raw.githubusercontent.com/TheSpeedX/PROXY-LIST/master/http.txt', 'plain', 'http'),
    ('thespeedx-socks5', 'https://raw.githubusercontent.com/TheSpeedX/PROXY-LIST/master/socks5.txt', 'plain', 'socks5'),
    ('thespeedx-socks4', 'https://raw.githubusercontent.com/TheSpeedX/PROXY-LIST/master/socks4.txt', 'plain', 'socks4'),
    ('roosterkid-socks5', 'https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt', 'plain', 'socks5'),
)

# Round 1: neutral aliveness target (same tile DeadDropMGMT probes).
ROUND1_URL = 'https://a.tile.openstreetmap.org/13/4051/2749.png'

SUPPORTED_SCHEMES = ('http', 'socks5', 'socks4')
FAIL_COOLDOWN = 15 * 60  # a failed proxy sits out this long before it may be picked again
PRUNE_AFTER = 24 * 3600  # entries failing this long are dropped to make room for fresh ones
MAX_ENTRIES = 2000  # hard cap on pool size; oldest-checked fails are dropped first
LATENCY_CUTOFF_MS = 6000  # probe_alive passes only below this
PER_SOURCE_CAP = 60  # max candidates kept per list source
REFRESH_DEADLINE_S = 540  # cooperative refresh deadline (checked between phases)
STALE_REPROBE_N = 60  # oldest-checked global-ok entries re-probed at thin hosts
BREAKER_N = 10  # >=N global failures ...
BREAKER_WINDOW_S = 60  # ... in 60 s trips the breaker ...
BREAKER_HOLD_S = 60  # ... for 60 s (picks return empty; any mark-ok clears)


def parse_proxy_url(raw):
    """('http://1.2.3.4:8080') from ' 1.2.3.4:8080 ' (bare entries are plain HTTP).

    Returns None for loopback/private/reserved/multicast/link-local/unspecified
    addresses (never chain through those), garbage, hostnames, and unsupported
    schemes (https included: no TLS-wrap exists) — the same public-only rule as
    osm_proxy_host_public(). socks5h normalizes to socks5, socks4a/socks4h to socks4.
    """
    from urllib.parse import urlsplit
    import ipaddress
    text = (raw or '').strip()
    if not text or len(text) > 256:
        return None
    if '://' not in text:
        text = 'http://' + text
    try:
        parts = urlsplit(text)
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    if scheme == 'socks5h':
        scheme = 'socks5'
    elif scheme in ('socks4a', 'socks4h'):
        scheme = 'socks4'
    if scheme not in SUPPORTED_SCHEMES or not parts.hostname:
        return None
    try:
        port = parts.port
    except ValueError:
        return None  # out-of-range port
    if port is None or not 1 <= port <= 65535:
        return None
    try:
        ip = ipaddress.ip_address(parts.hostname)
        if (ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_multicast
                or ip.is_link_local or ip.is_unspecified):
            return None
    except ValueError:
        return None  # a hostname, not an IP: free lists are IP-based, skip DNS games
    return f'{scheme}://{parts.hostname}:{port}'


def normalize_list(text, kind, scheme='http'):
    """Candidate proxy URLs from one downloaded list (proxifly JSON or plain text).

    Plain lists hold bare ip:port lines, so the list's own protocol tags them.
    """
    found = []

    def tag(raw):
        if isinstance(raw, str) and scheme and '://' not in raw.strip():
            return scheme + '://' + raw.strip()
        return raw

    if kind == 'proxifly':
        try:
            data = json.loads(text)
        except ValueError:
            return found
        # Proxifly groups bare ip:port entries by protocol bucket: tag each with its scheme.
        buckets = data.items() if isinstance(data, dict) else (('http', data),)
        bucket_alias = {'socks5h': 'socks5', 'socks4a': 'socks4', 'socks4h': 'socks4'}
        for bucket, entries in buckets:
            name = str(bucket).lower()
            if name == 'https':
                continue  # dropped: https upstreams can never chain
            name = bucket_alias.get(name, name)
            prefix = name + '://' if name in SUPPORTED_SCHEMES else ''
            if not isinstance(entries, list):
                continue
            for entry in entries:
                raw = entry.get('proxy') or entry.get('url') or '' if isinstance(entry, dict) else entry
                if isinstance(raw, str) and prefix and '://' not in raw:
                    raw = prefix + raw
                url = parse_proxy_url(raw) if isinstance(raw, str) else None
                if url:
                    found.append(url)
        return found
    for line in text.splitlines():
        url = parse_proxy_url(tag(line))
        if url:
            found.append(url)
    return found


def _sort_key(entry):
    """Healthy (ok) first, then untested (new), then failed — fastest latency wins inside a tier.

    Fails penalize the key (+30 s per fail) so flaky proxies sink below stable ones.
    """
    tier = {'ok': 0, 'new': 1}.get(entry.get('status'), 2)
    lat = entry.get('latency_ms') if entry.get('latency_ms') is not None else 10 ** 9
    return (tier, lat + entry.get('fails', 0) * 30000)


def _ewma(old, new):
    if new is None:
        return old
    if old is None:
        return new
    return int(0.7 * old + 0.3 * new)


class ProxyPool:
    """Thread-safe pool: refresh (fetch lists + Round 1/2 probes), per-host pick, mark, persist."""

    def __init__(self, path, round2, max_probe=150, probe_timeout=8, max_age=6 * 3600,
                 min_alive=25, min_verified=5):
        # round2: {hostname: (url, marker_bytes)} — the per-faculty verification targets.
        self.path = Path(path)
        self.round2 = dict(round2)
        self.max_probe = max_probe
        self.probe_timeout = probe_timeout
        self.max_age = max_age
        self.min_alive = min_alive
        self.min_verified = min_verified
        self.lock = threading.Lock()
        self.entries = {}  # url -> {status, latency_ms, fails, last_checked, source, hosts: {h: {...}}}
        self.last_refresh = None
        self.last_error = None
        self._last_save = 0
        self.heal_event = threading.Event()
        self.force_refresh = False
        self._refresh_lock = threading.Lock()
        self._fail_times = deque()
        self._breaker_until = 0.0
        self._rotor = {}  # host -> rotation cursor over the verified tier (see pick_many)
        self.load()

    # -- persistence -----------------------------------------------------
    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return
        if isinstance(data, dict) and data.get('version') == POOL_VERSION:
            self.entries = data.get('entries', {})
            self.last_refresh = data.get('last_refresh')

    def save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
            payload = json.dumps({'version': POOL_VERSION, 'entries': self.entries,
                                  'last_refresh': self.last_refresh,
                                  'saved': time.time()}, indent=1, sort_keys=True)
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(payload)
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
            tmp.replace(self.path)
        except OSError:
            pass

    def _save_throttled(self, force=False):
        if force or time.time() - self._last_save > 30:
            self._last_save = time.time()
            self.save()

    # -- circuit breaker -------------------------------------------------
    def _tripped(self):
        return time.monotonic() < self._breaker_until

    # -- selection (the maps_pick_proxy() equivalent, per host) ------------
    def verified(self, host):
        """Proxies verified for `host`, healthy-first by latency (only ok, no cooldown waits)."""
        with self.lock:
            return sorted(
                ({'url': u, **e, 'via_ms': e['hosts'][host]['ms']}
                 for u, e in self.entries.items()
                 if e.get('hosts', {}).get(host, {}).get('ok')),
                key=lambda c: c['via_ms'] if c['via_ms'] is not None else 10 ** 9)

    def _candidate_key(self, e, ms, now):
        base = ms if ms is not None else 10 ** 9
        # Stale aliveness is worthless with free proxies (entries die or change hands hourly):
        # an entry unchecked for 3 h sinks below a fresh slow one. Missing timestamps count
        # as fresh (legacy entries).
        age = max(0.0, now - e.get('last_checked', now))
        return base + e.get('fails', 0) * 30000 + min(300000.0, age * 100.0)

    def _pick_ranked(self, host):
        """[(key, url)] of eligible candidates for host, sorted best-first."""
        now_wall = time.time()
        now_mono = time.monotonic()
        ranked = []
        for url, e in self.entries.items():
            hv = e.get('hosts', {}).get(host)
            if hv is not None and not hv.get('ok'):
                mono = hv.get('checked_mono')
                if mono is not None:
                    if now_mono - mono <= FAIL_COOLDOWN:
                        continue  # host-failed, cooling down (monotonic)
                elif now_wall - hv.get('checked', 0) <= FAIL_COOLDOWN:
                    continue  # fallback to wall when mono missing
                hv = None  # cooldown over: treat as untried again
            if hv is not None and hv.get('ok'):
                key = (0, self._candidate_key(e, hv.get('ms'), now_wall))
            elif e.get('status') == 'ok':
                key = (1, self._candidate_key(e, e.get('latency_ms'), now_wall))
            else:
                continue
            ranked.append((key, url))
        ranked.sort()
        return ranked

    def pick(self, host):
        """Best proxy verified for `host`. Globally-alive but host-untried proxies are
        offered optimistically (the server verifies on use); host-failed ones sit out
        their cooldown. None when nobody qualifies — the caller falls back to direct."""
        with self.lock:
            if self._tripped():
                return None
            ranked = self._pick_ranked(host)
            return ranked[0][1] if ranked else None

    def pick_many(self, host, n=3):
        """Up to `n` candidate URLs for `host`, best-first — but rotating across the verified tier.

        One fast verified exit would otherwise absorb every request (each pick returns the same
        best-first order) and a proxy that absorbs a whole crawl gets flagged by the WAF, after
        which every later request through it fails. Round-robin spreads the load, so the tier
        and the exits' reputations survive; unverified globally-alive proxies stay the tail.
        """
        with self.lock:
            if self._tripped():
                return []
            ranked = self._pick_ranked(host)
            verified = [url for key, url in ranked if key[0] == 0]
            rest = [url for key, url in ranked if key[0] != 0]
            if len(verified) > 1:
                k = self._rotor.get(host, 0) % len(verified)
                self._rotor[host] = k + 1
                verified = verified[k:] + verified[:k]
            return (verified + rest)[:max(0, n)]

    def mark(self, url, host, ok, latency_ms=None, live=False):
        """Record one use through `url` for `host` (the osm_proxy_mark() equivalent).

        Only LIVE traffic (live=True, from the proxy server) feeds the circuit breaker:
        background probes fail constantly on walled hosts and must never trip the
        request path.
        """
        now_wall = time.time()
        now_mono = time.monotonic()
        with self.lock:
            e = self.entries.setdefault(url, {'fails': 0, 'hosts': {}})
            e['last_checked'] = now_wall
            e['last_checked_mono'] = now_mono
            hv = e.setdefault('hosts', {}).setdefault(host, {})
            before = hv.get('ok')
            hv['checked'] = now_wall
            hv['checked_mono'] = now_mono
            if ok:
                hv.update(ok=True, ms=latency_ms)
                if e.get('status') != 'ok':
                    e.update(status='ok', fails=0)
                if latency_ms is not None:
                    e['latency_ms'] = _ewma(e.get('latency_ms'), latency_ms)
                if live:
                    self._fail_times.clear()
                    self._breaker_until = 0.0
            else:
                hv['ok'] = False
                e['fails'] = e.get('fails', 0) + 1
                if live:
                    self._fail_times.append(now_mono)
                    while self._fail_times and now_mono - self._fail_times[0] > BREAKER_WINDOW_S:
                        self._fail_times.popleft()
                    if len(self._fail_times) >= BREAKER_N:
                        self._breaker_until = now_mono + BREAKER_HOLD_S
            # heal-kick: thin host coverage wakes the maintainer promptly.
            try:
                cnt = sum(1 for _e in self.entries.values()
                          if _e.get('hosts', {}).get(host, {}).get('ok'))
                if cnt < self.min_verified:
                    self.heal_event.set()
            except Exception:
                pass
            self._save_throttled(force=hv.get('ok') != before)

    def mark_alive(self, url, ok, latency_ms=None):
        """Record a Round 1 (neutral) probe result."""
        now_wall = time.time()
        now_mono = time.monotonic()
        with self.lock:
            e = self.entries.setdefault(url, {'fails': 0, 'hosts': {}})
            before = e.get('status')
            e['last_checked'] = now_wall
            e['last_checked_mono'] = now_mono
            if ok:
                e.update(status='ok', fails=0)
                if latency_ms is not None:
                    e['latency_ms'] = _ewma(e.get('latency_ms'), latency_ms)
                # No breaker touch: probes must neither trip nor clear the live path.
            else:
                # A failed re-probe revokes aliveness outright: a dead entry must never be
                # offered optimistically to a new host (host-verified picks are unaffected).
                e['status'] = 'fail'
            self._save_throttled(force=e.get('status') != before)

    # -- coverage / healing -------------------------------------------------
    def coverage(self):
        """{host: verified-count} + alive total — what the GUI and the healer look at."""
        with self.lock:
            cov = {h: 0 for h in self.round2}
            alive = 0
            for e in self.entries.values():
                if e.get('status') == 'ok':
                    alive += 1
                for h, hv in e.get('hosts', {}).items():
                    if h in cov and hv.get('ok'):
                        cov[h] += 1
            return cov, alive

    def stats(self):
        cov, alive = self.coverage()
        with self.lock:
            by_status = {}
            for e in self.entries.values():
                by_status[e.get('status', 'new')] = by_status.get(e.get('status', 'new'), 0) + 1
            lats = sorted(e['latency_ms'] for e in self.entries.values()
                          if e.get('status') == 'ok' and e.get('latency_ms') is not None)
            med = lats[len(lats) // 2] if lats else None
            if lats:
                p50 = lats[len(lats) // 2]
                p95 = lats[min(len(lats) - 1, int(len(lats) * 0.95))]
            else:
                p50, p95 = None, None
            tripped = time.monotonic() < self._breaker_until
            return {'total': len(self.entries), 'by_status': by_status, 'alive': alive,
                    'verified': cov, 'median_ok_ms': med, 'p50_ok_ms': p50, 'p95_ok_ms': p95,
                    'tripped': tripped,
                    'last_refresh': self.last_refresh, 'last_error': self.last_error}

    def needs_refresh(self):
        if not self.last_refresh or time.time() - self.last_refresh > self.max_age:
            return True
        cov, alive = self.coverage()
        return alive < self.min_alive or any(n < self.min_verified for n in cov.values())

    def prune(self):
        """Drop entries failing longer than PRUNE_AFTER — dead weight makes room for fresh blood."""
        now = time.time()
        with self.lock:
            drop = [u for u, e in self.entries.items()
                    if e.get('status') == 'fail' and now - e.get('last_checked', 0) > PRUNE_AFTER
                    and not any(hv.get('ok') for hv in e.get('hosts', {}).values())]
            for u in drop:
                del self.entries[u]
        if drop:
            self.save()
        return len(drop)

    # -- probing ------------------------------------------------------------
    def fetch_via(self, url, target, timeout):
        from curl_cffi import requests as cr
        # Remote DNS: let the proxy resolve faculty hostnames, never us (DNS-leak fix).
        if url.startswith('socks5://'):
            url = 'socks5h://' + url[len('socks5://'):]
        elif url.startswith('socks4://'):
            url = 'socks4a://' + url[len('socks4://'):]
        start = time.monotonic()
        r = cr.get(target, timeout=timeout, proxies={'http': url, 'https': url},
                   headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) PlanWAT-healthcheck'})
        return r, int((time.monotonic() - start) * 1000)

    def probe_alive(self, url):
        """Round 1: neutral page, 200 = the proxy works. Returns ms or None."""
        try:
            r, ms = self.fetch_via(url, ROUND1_URL, self.probe_timeout)
            if ms is not None and ms > LATENCY_CUTOFF_MS:
                return None
            return ms if r.status_code == 200 and len(r.content) > 1000 else None
        except Exception:
            return None

    def probe_host(self, url, host):
        """Round 2: the faculty's own index through the proxy. Returns ms or None."""
        target, marker = self.round2[host]
        try:
            r, ms = self.fetch_via(url, target, self.probe_timeout)
            if r.status_code != 200 or len(r.content) < 500:
                return None
            return ms if marker is None or marker in r.content[:400] else None
        except Exception:
            return None

    def refresh(self, fetcher=None, workers=20, round2_cap=40):
        """Fetch the lists, Round-1 the new candidates, Round-2 the survivors at
        under-covered hosts. Dead entries are replaced by fresh ones (prune first)."""
        import random
        start_mono = time.monotonic()
        self.prune()

        def _fetch_one(item):
            name, url, kind, scheme = item
            try:
                text = fetcher(url) if fetcher else _direct_get(url)
                return name, normalize_list(text, kind, scheme)[:PER_SOURCE_CAP], None
            except Exception as err:
                return name, [], f'{name}: {err}'

        fetched = {}
        with ThreadPoolExecutor(max_workers=max(1, len(LIST_SOURCES))) as ex:
            futs = {ex.submit(_fetch_one, item): item[0] for item in LIST_SOURCES}
            for fut, name in ((f, futs[f]) for f in list(futs)):
                try:
                    rname, urls, err = fut.result(timeout=30)
                except Exception as err:
                    self.last_error = f'{name}: {err}'
                    continue
                if err:
                    self.last_error = err
                fetched[rname] = urls
        with self.lock:
            known = set(self.entries)
        fresh = []
        seen = set()
        for name, urls in fetched.items():
            for u in urls:
                if u not in known and u not in seen:
                    seen.add(u)
                    fresh.append((u, name))
        # Entry cap: drop oldest-checked fails first, then trim fresh.
        with self.lock:
            over = len(self.entries) + len(fresh) - MAX_ENTRIES
            if over > 0:
                fails = sorted(((u, e) for u, e in self.entries.items()
                                if e.get('status') != 'ok'),
                               key=lambda kv: kv[1].get('last_checked', 0))
                for u, _ in fails[:over]:
                    del self.entries[u]
                over = len(self.entries) + len(fresh) - MAX_ENTRIES
                if over > 0:
                    # drop oldest fresh tail (fresh already shuffled later; trim head room here)
                    fresh = fresh[:len(fresh) - over]
        random.shuffle(fresh)
        fresh = fresh[:self.max_probe]
        alive = []

        def _r1(candidate):
            url, name = candidate
            ms = self.probe_alive(url)
            self.mark_alive(url, ms is not None, ms)
            with self.lock:
                if url in self.entries:
                    self.entries[url]['source'] = name
            return url if ms is not None else None

        with ThreadPoolExecutor(max_workers=workers) as tpool:
            for url in tpool.map(_r1, fresh):
                if url:
                    alive.append(url)
        if time.monotonic() - start_mono > REFRESH_DEADLINE_S:
            self.last_refresh = time.time()
            cov, alive_n = self.coverage()
            self.last_error = None if alive_n else (self.last_error or 'no candidate passed Round 1')
            self.save()
            return alive_n, len(fresh), 0
        # Round 2 only where coverage is thin, cheapest hosts first.
        cov, _ = self.coverage()
        thin = sorted([h for h, n in cov.items() if n < self.min_verified],
                      key=lambda h: cov[h])
        # Stale re-probe: oldest-checked global-ok entries get re-verified at thin hosts.
        with self.lock:
            ok_old = sorted(((u, e) for u, e in self.entries.items() if e.get('status') == 'ok'),
                            key=lambda kv: kv[1].get('last_checked', 0))[:STALE_REPROBE_N]
            stale_urls = [u for u, _ in ok_old]
        verified = 0
        with ThreadPoolExecutor(max_workers=workers) as pool2:
            for host in thin:
                if time.monotonic() - start_mono > REFRESH_DEADLINE_S:
                    break
                deficit = self.min_verified - cov.get(host, 0)
                cap = min(round2_cap, max(10, deficit * 10))
                random.shuffle(alive)
                cands = []
                seen_jobs = set()
                for u in alive[:cap]:
                    with self.lock:
                        hv = self.entries.get(u, {}).get('hosts', {}).get(host, {})
                    if not hv.get('ok') and u not in seen_jobs:
                        cands.append((u, host))
                        seen_jobs.add(u)
                for u in stale_urls:
                    if u in seen_jobs:
                        continue
                    with self.lock:
                        hv = self.entries.get(u, {}).get('hosts', {}).get(host, {})
                    if not hv.get('ok'):
                        cands.append((u, host))
                        seen_jobs.add(u)

                def _r2once(job):
                    url, h = job
                    ms = self.probe_host(url, h)
                    self.mark(url, h, ms is not None, ms)
                    return url if ms is not None else None

                for url in pool2.map(_r2once, cands):
                    if url:
                        verified += 1
        self.last_refresh = time.time()
        cov, alive_n = self.coverage()
        self.last_error = None if alive_n else (self.last_error or 'no candidate passed Round 1')
        self.save()
        return alive_n, len(fresh), verified


def _direct_get(url, timeout=30):
    """Fetch a proxy list with no proxy at all (the egress box has its own route out)."""
    from curl_cffi import requests as cr
    r = cr.get(url, timeout=timeout)
    if r.status_code != 200:
        raise OSError(f'HTTP {r.status_code}')
    return r.text
