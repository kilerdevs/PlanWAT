"""Public proxy pool for the PlanWAT egress rotator (DeadDropMGMT pattern, ported to Python).

Sources are public GitHub proxy lists: proxifly (JSON, with a per-country Polish list), monosans, thespeedx,
roosterkid, vakhov, hookzof, ErcinDedeoglu (plain ip:port text). They are fetched whole and cached for LIST_TTL_S;
every entry is a candidate, not just the head of each list.

A candidate goes through three gates, cheapest first:
  Screen (TCP):  a non-blocking connect to the proxy's port, thousands at once on a few sockets. Most list entries
                 are dead and fail here for almost nothing.
  Round 1 (alive): the proxy fetches a neutral, tiny page (Cloudflare's generate_204) over end-to-end TLS. Pass =
                 the proxy works; its time is the proxy's latency.
  Round 2 (verified for a host): the proxy fetches that faculty's own index page. Pass = the proxy actually reaches
                 our target (an Incapsula-fronted host drops datacenter IPs at the network level, so aliveness alone
                 says nothing). The verdict is kept per host: these are the exits marked for that faculty.

`pick(host)` hands out proxies verified for that host, healthy-first by latency. Hosts with no verified proxy get
None and the server falls back to direct egress (operator's fail-open choice) instead of failing closed.

The scout (scout_once, docs/EGRESS.md "Zwiad") keeps looking all the time where it is switched on: it screens the
candidates nobody has seen, tests every new live one with a sensible ping on every faculty page, keeps the fastest
exits per faculty fresh, and only tries a faculty that already has SCOUT_KEEP exits with proxies faster than those.
The hunt (hunt) is the urgent version for a crawl that met a wall. A dead candidate goes to a compact `dead` map
(seen.json) and is not looked at again for DEAD_RETRY_S. The server also marks every real use (ok + latency on
success, fail on refusal), so the pool learns between cycles.

Nothing here imports the proxy server, so it is unit-tested offline (tests/test_egress.py).
"""
import errno
import json
import os
import random
import selectors
import socket
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
    # WLO, WML and WTC let a Polish home line in and wall datacenter and Cloudflare addresses: Polish exits first.
    ('proxifly-pl', 'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/PL/data.json',
     'proxifly', ''),
    ('vakhov-http', 'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt', 'plain', 'http'),
    ('vakhov-socks5', 'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt', 'plain', 'socks5'),
    ('vakhov-socks4', 'https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks4.txt', 'plain', 'socks4'),
    ('hookzof-socks5', 'https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt', 'plain', 'socks5'),
    ('ercin-http', 'https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/http.txt', 'plain', 'http'),
    ('ercin-socks5', 'https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/socks5.txt', 'plain', 'socks5'),
    ('ercin-socks4', 'https://raw.githubusercontent.com/ErcinDedeoglu/proxies/main/proxies/socks4.txt', 'plain', 'socks4'),
)

# Round 1: a neutral aliveness target made for connectivity checks: an empty 204 over TLS (the certificate is
# checked, so a proxy cannot fake it). Tiny, so its time is the proxy's latency, not a download's.
ROUND1_URL = 'https://cp.cloudflare.com/generate_204'

SUPPORTED_SCHEMES = ('http', 'socks5', 'socks4')
FAIL_COOLDOWN = 10 * 60  # a failed proxy sits out this long before it may be picked again
PRUNE_AFTER = 24 * 3600  # entries failing this long are dropped to make room for fresh ones
MAX_ENTRIES = 2000  # hard cap on pool size; fails, then stale, then slow entries make room (_make_room)
LATENCY_CUTOFF_MS = 6000  # probe_alive passes only below this
LIST_TTL_S = 30 * 60  # the lists are fetched whole at most this often; every cycle in between reuses them
DEAD_RETRY_S = 12 * 3600  # a candidate that failed the screen or Round 1 is not looked at again for this long
DEAD_CAP = 120000  # the dead map's size (oldest forgotten first)
TCP_TIMEOUT_S = 3.0  # the screen's connect timeout
ALIVE_TTL_S = 3600  # an alive verdict older than this is re-checked (and not trusted for a hunt)
REFRESH_DEADLINE_S = 540  # cooperative refresh deadline (checked between phases)
STALE_REPROBE_N = 90  # oldest-checked global-ok entries re-probed at thin hosts
BREAKER_N = 10  # >=N global failures ...
BREAKER_WINDOW_S = 60  # ... in 60 s trips the breaker ...
BREAKER_HOLD_S = 60  # ... for 60 s (picks return empty; any mark-ok clears)
HOST_BREAKER_N = 8  # >=N live failures for one host ...
HOST_BREAKER_WINDOW_S = 120  # ... in 120 s stop offering exits for it ...
HOST_BREAKER_HOLD_S = 120  # ... for 120 s (a live success clears immediately)
RETRY_AFTER_S = 5 * 60  # after a total list-fetch failure, retry soon instead of freezing for max_age
HEAL_MIN_GAP_S = 10 * 60  # thin coverage alone re-runs a refresh at most this often (max_age still applies)
MIN_ROUND2_CAP = 12
# The hunt (hunt()): when nobody's own line gets through a faculty's wall, every alive proxy with a sensible
# Round-1 latency is tried against it, fastest first, until a few pass or the budget runs out.
HUNT_MAX_MS = 2500  # "sensible ping": Round-1 latency at most this
HUNT_WANT = 4  # exits per host that end its search (enough to rotate)
HUNT_WORKERS = 4  # probes at once, all hosts together: the faculty sites see a trickle, not a scan
HUNT_BUDGET_S = 300
HUNT_MIN_ALIVE = 40  # fewer fresh-enough alive candidates than this: fetch the lists and Round-1 them first
HUNT_PROBE = 800  # candidates Round-1 probed per discovery round of a hunt (a neutral page, not the faculty)
HUNT_ROUNDS = 4  # discovery rounds at most, each over candidates not probed yet
HUNT_R1_WORKERS = 48
HUNT_FRESH_S = ALIVE_TTL_S  # an alive verdict older than this is not trusted for a hunt
HUNT_CACHE_S = 30 * 60  # a host hunted this recently only has its known exits re-checked, nobody else probed
HUNT_TRUST_S = 10 * 60  # an exit verified for a host this recently is handed to a hunt without a re-check
ADOPT_CAP = 8  # shared exits checked per request
FACULTY_PROBES = 4  # faculty-page probes at once in this pool, whoever asks (hunt, scout, adopt, refresh)
# The scout (scout_once): always looking, where switched on (EGRESS_SCOUT).
SCOUT_BATCH = 1500  # unseen candidates screened per cycle
SCOUT_RECHECK = 200  # stale alive entries re-checked per cycle
SCOUT_TESTS = 400  # faculty-page probes per cycle at most (new exits and better ones)
SCOUT_KEEP = 12  # a faculty with this many fresh exits is only tried with proxies faster than the slowest of them
SCOUT_PAUSE_S = 60
SCOUT_HOST_GAP_S = 2.0  # at least this long between two scout probes of one faculty
HOST_RETRY_S = 12 * 3600  # a proxy a faculty refused is not tried on it again for this long (walls are sticky)
VERIFY_TTL_S = 20 * 60  # the scout re-probes a faculty's exits verified longer ago than this

# WAF/captive-portal bodies can be HTTP 200 with plenty of bytes. A probe that lands on
# one must not count as "this proxy reaches the faculty".
BLOCK_MARKERS = (
    b'incapsula', b'request unsuccessful', b'access denied',
    b'attention required! | cloudflare', b'cf-error-details',
    b'cloudflare ray id', b'cf-browser-verification', b'__cf_chl',
    b'captcha-delivery', b'are you a robot', b'zablokowan',
)


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
    host = f'[{parts.hostname}]' if ip.version == 6 else parts.hostname
    return f'{scheme}://{host}:{port}'


def normalize_list(text, kind, scheme='http', meta=None):
    """Candidate proxy URLs from one downloaded list (proxifly JSON or plain text).

    Plain lists hold bare ip:port lines, so the list's own protocol tags them. `meta`, when given, collects
    {url: country code} from proxifly's geolocation.
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
                    geo = entry.get('geolocation') if isinstance(entry, dict) else None
                    cc = geo.get('country') if isinstance(geo, dict) else None
                    if meta is not None and isinstance(cc, str) and len(cc) == 2 and cc.isalpha():
                        meta[url] = cc.upper()
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

    def __init__(self, path, round2, max_probe=150, probe_timeout=8, max_age=4 * 3600,
                 min_alive=25, min_verified=5, active_hosts=None, hunt=False, faculty_probes=FACULTY_PROBES):
        # round2: {hostname: (url, marker_bytes)} — the per-faculty verification targets.
        # active_hosts: the subset that actually rides the pool (all by default). Hosts in
        # EGRESS_DIRECT_FACULTY are filtered out by the server, so a volunteer deployment
        # never fetches proxy lists or probes anybody.
        self.path = Path(path)
        self.round2 = dict(round2)
        self.active_hosts = [h for h in self.round2 if active_hosts is None or h in active_hosts]
        self.max_probe = max_probe
        self.probe_timeout = probe_timeout
        self.max_age = max_age
        self.min_alive = min_alive
        self.min_verified = min_verified
        self.lock = threading.RLock()
        self._save_lock = threading.Lock()
        self.entries = {}  # url -> {status, latency_ms, fails, last_checked, source, hosts: {h: {...}}}
        self.last_refresh = None
        self.last_error = None
        self.retry_after = 0.0
        self._last_save = 0
        self.heal_event = threading.Event()
        self.force_refresh = False
        self._refresh_lock = threading.Lock()
        self._fail_times = deque()
        self._breaker_until = 0.0
        self._host_fails = {}  # host -> deque of live-failure monotonic stamps
        self._host_open = {}   # host -> monotonic until which it is not offered
        self._rotor = {}  # host -> rotation cursor over the verified tier (see pick_many)
        # hunt(): on demand, for any faculty host (direct ones included), whatever active_hosts says
        self.hunt_on = bool(hunt)
        self.hunts = {}  # host -> {state, verified, tried, exits, at, error}
        self._hunt_lock = threading.Lock()
        self._hunt_pending = {}  # host -> kwargs of the hunt asked for, while the worker runs
        self._hunt_thread = None
        self._hunting = 0  # hunts running right now: the scout steps aside while any is
        # every faculty-page probe goes through this gate, so the sites see a trickle whoever asks
        self.faculty_probes = max(1, int(faculty_probes))
        self._faculty_gate = threading.BoundedSemaphore(self.faculty_probes)
        self.host_gap = SCOUT_HOST_GAP_S
        self._host_next = {}  # host -> monotonic time of its next allowed scout probe
        self._gap_lock = threading.Lock()
        self.dead = {}  # url -> wall time it failed the screen or Round 1 (seen.json)
        self.sources = {}  # list name -> [candidates tried, alive] (seen.json): how much each list is worth
        self.dead_path = self.path.with_name('seen.json')
        self._lists_cache = None  # (monotonic fetched, {url: (source, cc)})
        self.unseen_left = None  # candidates on the lists nobody has looked at yet (after the last discovery)
        self.scout = {}  # the scout's last cycle, for the GUI
        self.load()
        self._load_dead()

    @property
    def enabled(self):
        return bool(self.active_hosts)

    # -- persistence -----------------------------------------------------
    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict) or data.get('version') != POOL_VERSION:
            return
        entries = data.get('entries')
        if not isinstance(entries, dict):
            return
        clean = {}
        for url, entry in entries.items():
            if not isinstance(url, str) or not isinstance(entry, dict):
                continue  # a corrupted line must never crash pick()
            hosts = entry.get('hosts')
            if not isinstance(hosts, dict):
                hosts = {}
            # Old/hand-edited pool files may carry strings where numbers belong; sorting a
            # mixed list or subtracting a string raises inside pick()/stats(), so coerce
            # or drop every field the selection path reads.
            hosts = {h: hv for h, hv in hosts.items()
                     if isinstance(h, str) and isinstance(hv, dict)}
            entry = dict(entry, hosts=hosts)
            for field in ('latency_ms', 'last_checked'):
                if field in entry and not isinstance(entry[field], (int, float)):
                    entry.pop(field, None)
            if not isinstance(entry.get('fails'), int):
                entry['fails'] = 0
            # Monotonic stamps are only comparable within one boot: after a reboot an old one sits
            # ahead of the clock and would hold its entry in cooldown for the old uptime. Drop them;
            # the wall-clock `checked` carries the cooldown across restarts.
            entry.pop('last_checked_mono', None)
            for hv in hosts.values():
                hv.pop('checked_mono', None)
                for field in ('ms', 'checked'):
                    if field in hv and not isinstance(hv[field], (int, float)):
                        hv.pop(field, None)
                if not isinstance(hv.get('ok'), bool):
                    hv['ok'] = False
            clean[url] = entry
        self.entries = clean
        self.last_refresh = data.get('last_refresh')
        if not isinstance(self.last_refresh, (int, float)):
            self.last_refresh = None

    def _load_dead(self):
        try:
            data = json.loads(self.dead_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return
        if isinstance(data, dict) and isinstance(data.get('dead'), dict):
            cut = time.time() - DEAD_RETRY_S
            self.dead = {u: t for u, t in data['dead'].items()
                         if isinstance(u, str) and isinstance(t, (int, float)) and t > cut}
        if isinstance(data, dict) and isinstance(data.get('sources'), dict):
            self.sources = {n: [int(v[0]), int(v[1])] for n, v in data['sources'].items()
                            if isinstance(n, str) and isinstance(v, list) and len(v) == 2
                            and all(isinstance(x, int) and x >= 0 for x in v)}

    def save_dead(self):
        """The dead map, beside pool.json (written per cycle, not per mark: it is large and only a cache)."""
        cut = time.time() - DEAD_RETRY_S
        with self.lock:
            dead = {u: int(t) for u, t in self.dead.items() if t > cut}
            if len(dead) > DEAD_CAP:
                dead = dict(sorted(dead.items(), key=lambda kv: kv[1])[-DEAD_CAP:])
            self.dead = dict(dead)
        try:
            self.dead_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.dead_path.with_suffix('.tmp')
            with self.lock:
                sources = {n: list(v) for n, v in self.sources.items()}
            tmp.write_text(json.dumps({'version': 1, 'dead': dead, 'sources': sources}, separators=(',', ':')),
                           encoding='utf-8')
            tmp.replace(self.dead_path)
        except OSError:
            pass

    def _retire(self, url):
        """A candidate that failed the screen or Round 1: out of the pool into the dead map, unless some faculty has
        it verified (its own probes decide that one)."""
        with self.lock:
            e = self.entries.get(url)
            if e is not None and any(hv.get('ok') for hv in e.get('hosts', {}).values()):
                return False
            self.entries.pop(url, None)
            self.dead[url] = time.time()
            return True

    def save(self):
        with self._save_lock:
            self._write_payload()

    def _write_payload(self):
        """Serialize a consistent snapshot; callers hold `_save_lock`."""
        try:
            with self.lock:
                payload = json.dumps({'version': POOL_VERSION, 'entries': self.entries,
                                      'last_refresh': self.last_refresh,
                                      'saved': time.time()}, indent=1, sort_keys=True)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
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
        with self._save_lock:
            now = time.time()
            if not force and now - self._last_save <= 30:
                return
            self._last_save = now
            self._write_payload()

    # -- circuit breaker -------------------------------------------------
    def _tripped(self, host=None):
        now = time.monotonic()
        if now < self._breaker_until:
            return True
        return bool(host) and now < self._host_open.get(host, 0.0)

    # -- selection (the maps_pick_proxy() equivalent, per host) ------------
    def verified(self, host):
        """Proxies verified for `host`, healthy-first by latency (only ok, no cooldown waits)."""
        with self.lock:
            return sorted(
                ({'url': u, **e, 'via_ms': e['hosts'][host]['ms']}
                 for u, e in self.entries.items()
                 if e.get('hosts', {}).get(host, {}).get('ok')),
                key=lambda c: c['via_ms'] if c['via_ms'] is not None else 10 ** 9)

    def _candidate_key(self, e, ms, now, fails=None, checked=None):
        base = ms if ms is not None else 10 ** 9
        # Stale aliveness is worthless with free proxies (entries die or change hands hourly):
        # an entry unchecked for 3 h sinks below a fresh slow one. Missing timestamps count
        # as fresh (legacy entries). A verified exit ages from its host verdict.
        stamp = checked if isinstance(checked, (int, float)) else e.get('last_checked', now)
        age = max(0.0, now - stamp)
        fails = e.get('fails', 0) if fails is None else fails
        return base + fails * 30000 + min(300000.0, age * 100.0)

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
                # Verified for this host: its own verdict ranks it. The entry-wide fail count
                # also holds misses at other faculties, which say nothing about this one.
                key = (0, self._candidate_key(e, hv.get('ms'), now_wall, fails=0, checked=hv.get('checked')))
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
            if not self.enabled or self._tripped(host):
                return None  # disabled: a stale pool.json must never hand out an exit
            ranked = self._pick_ranked(host)
            return ranked[0][1] if ranked else None

    def pick_many(self, host, n=3, verified_only=False):
        """Up to `n` candidate URLs for `host`, best-first — but rotating across the verified tier.

        One fast verified exit would otherwise absorb every request (each pick returns the same
        best-first order) and a proxy that absorbs a whole crawl gets flagged by the WAF, after
        which every later request through it fails. Round-robin spreads the load, so the tier
        and the exits' reputations survive; unverified globally-alive proxies stay the tail.
        """
        with self.lock:
            # verified_only: the hunt port (server.py), which only rides exits checked for the host, so it works
            # for hunted hosts even where no host rides the pool by default
            usable = self.enabled or (verified_only and self.hunt_on)
            if not usable or self._tripped(host):
                return []
            ranked = self._pick_ranked(host)
            verified = [url for key, url in ranked if key[0] == 0]
            rest = [] if verified_only else [url for key, url in ranked if key[0] != 0]
            if len(verified) > 1:
                k = self._rotor.get(host, 0) % len(verified)
                self._rotor[host] = k + 1
                verified = verified[k:] + verified[:k]
            return (verified + rest)[:max(0, n)]

    def mark(self, url, host, ok, latency_ms=None, live=False):
        """Record one use through `url` for `host` (the osm_proxy_mark() equivalent).

        Only LIVE traffic (live=True, from the proxy server) feeds the circuit breakers:
        background probes fail constantly on walled hosts and must never trip the
        request path. Failures are tracked globally and per host; a success resets the
        entry's failure count so an old bad spell cannot sink it forever.

        Per-host verdicts, breakers and heal-kicks are kept only for the faculty hosts the
        pool knows (round2): any other *.wat.edu.pl name comes from untrusted job code, and
        inventing names must neither grow the maps without bound nor trip the breaker that
        guards the real crawl. Such a use still counts on the entry's own fail tally.

        A failure is the host's verdict only: a faculty refusing a proxy says nothing about whether the proxy is
        alive, so it neither refreshes the entry's Round-1 stamp (which used to keep dead entries looking fresh
        forever) nor, for a probe, counts on the entry's fail tally. A success proves both.
        """
        now_wall = time.time()
        now_mono = time.monotonic()
        save_now = False
        managed = host in self.round2
        with self.lock:
            e = self.entries.setdefault(url, {'fails': 0, 'hosts': {}})
            hosts = e.setdefault('hosts', {})
            hv = hosts.setdefault(host, {}) if managed else {}
            before = hv.get('ok')
            hv['checked'] = now_wall
            hv['checked_mono'] = now_mono
            if ok:
                hv['ms'] = _ewma(hv.get('ms') if before else None, latency_ms) if latency_ms is not None \
                    else (hv.get('ms') if before else None)
                hv['ok'] = True
                hv['n_ok'] = int(hv.get('n_ok') or 0) + 1
                e['status'] = 'ok'
                e['last_checked'] = now_wall
                e['last_checked_mono'] = now_mono
                e['fails'] = 0  # decay completely: a recovered exit starts clean
                if live and managed:
                    self._fail_times.clear()
                    self._breaker_until = 0.0
                    self._host_fails.pop(host, None)
                    self._host_open.pop(host, None)
            else:
                hv['ok'] = False
                if managed:
                    hv['n_fail'] = int(hv.get('n_fail') or 0) + 1
                if live or not managed:
                    e['fails'] = e.get('fails', 0) + 1
                if live and managed:
                    self._fail_times.append(now_mono)
                    while self._fail_times and now_mono - self._fail_times[0] > BREAKER_WINDOW_S:
                        self._fail_times.popleft()
                    if len(self._fail_times) >= BREAKER_N:
                        self._breaker_until = now_mono + BREAKER_HOLD_S
                    fails = self._host_fails.setdefault(host, deque())
                    fails.append(now_mono)
                    while fails and now_mono - fails[0] > HOST_BREAKER_WINDOW_S:
                        fails.popleft()
                    if len(fails) >= HOST_BREAKER_N:
                        self._host_open[host] = now_mono + HOST_BREAKER_HOLD_S
                        fails.clear()
            # heal-kick: thin coverage of a host the pool maintains wakes the maintainer promptly
            # (needs_refresh still spaces coverage-driven refreshes by HEAL_MIN_GAP_S).
            if host in self.active_hosts:
                try:
                    cnt = sum(1 for _e in self.entries.values()
                              if _e.get('hosts', {}).get(host, {}).get('ok'))
                    if cnt < self.min_verified:
                        self.heal_event.set()
                except Exception:
                    pass
            save_now = managed and hv.get('ok') != before
        self._save_throttled(force=save_now)

    def mark_alive(self, url, ok, latency_ms=None):
        """Record a Round 1 (neutral) probe result."""
        now_wall = time.time()
        now_mono = time.monotonic()
        save_now = False
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
            save_now = e.get('status') != before
        self._save_throttled(force=save_now)

    # -- coverage / healing -------------------------------------------------
    def coverage(self, hosts=None):
        """{host: verified-count} + alive total — what the GUI and the healer look at. The pooled hosts by default;
        `hosts` counts others too (the exits marked for every faculty)."""
        with self.lock:
            cov = {h: 0 for h in (self.active_hosts if hosts is None else hosts)}
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
        now = time.monotonic()
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
            tripped = now < self._breaker_until
            hosts_tripped = sum(1 for until in self._host_open.values() if until > now)
            exits, _ = self.coverage(list(self.round2))
            return {'total': len(self.entries), 'by_status': by_status, 'alive': alive,
                    'verified': cov, 'exits': exits, 'dead': len(self.dead), 'unseen': self.unseen_left,
                    'median_ok_ms': med, 'p50_ok_ms': p50, 'p95_ok_ms': p95,
                    'tripped': tripped, 'hosts_tripped': hosts_tripped,
                    'last_refresh': self.last_refresh, 'last_error': self.last_error}

    def needs_refresh(self):
        if not self.enabled:
            return False  # every host is direct: there is no pool to maintain
        now = time.time()
        if self.retry_after > now:
            return False  # a failed list fetch gets a short pause, not a full max_age freeze
        if not self.last_refresh or now - self.last_refresh > self.max_age:
            return True
        if now - self.last_refresh < HEAL_MIN_GAP_S:
            # Just refreshed: thin coverage (a WAF-walled host stays thin) must not chain one
            # full list fetch + probe round straight into the next. POST /api/refresh still can.
            return False
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

    @staticmethod
    def _is_block_page(content):
        low = (content or b'')[:32768].lower()
        return any(marker in low for marker in BLOCK_MARKERS)

    def probe_alive(self, url):
        """Round 1: Cloudflare's generate_204 through the proxy, an empty 204 = the proxy works. Returns ms or None."""
        try:
            r, ms = self.fetch_via(url, ROUND1_URL, self.probe_timeout)
            if ms is not None and ms > LATENCY_CUTOFF_MS:
                return None
            body = r.content or b''
            # A captive or error page answers 200 with a body; only the real endpoint gives an empty 204.
            return ms if r.status_code == 204 and len(body) < 64 else None
        except Exception:
            return None

    def probe_host(self, url, host):
        """Round 2: the faculty's own index through the proxy. Returns ms or None.

        A 200 + byte count is not enough: WAF block pages are large 200s. Every target
        now carries a positive marker, and known block-page markers veto the probe.
        """
        target, marker = self.round2[host]
        try:
            r, ms = self.fetch_via(url, target, self.probe_timeout)
            body = r.content or b''
            if r.status_code != 200 or len(body) < 500 or self._is_block_page(body):
                return None
            if marker is not None and marker.lower() not in body[:262144].lower():
                return None
            return ms
        except Exception:
            return None

    def _probe_host(self, url, host, gap=False):
        """probe_host through the faculty gate (FACULTY_PROBES at once, whoever asks) and, for the scout, at least
        `host_gap` seconds after its previous probe of that faculty."""
        if gap and self.host_gap > 0:
            with self._gap_lock:
                now = time.monotonic()
                at = max(now, self._host_next.get(host, 0.0))
                self._host_next[host] = at + self.host_gap
            if at > now:
                time.sleep(at - now)
        with self._faculty_gate:
            return self.probe_host(url, host)

    def exits(self, host, limit=None):
        """The exits marked for `host` (its Round 2 passed and has not failed since), fastest first."""
        with self.lock:
            rows = [{'url': u, 'ms': hv.get('ms'), 'checked': hv.get('checked'), 'n_ok': hv.get('n_ok', 0),
                     'n_fail': hv.get('n_fail', 0), 'cc': e.get('cc'), 'latency_ms': e.get('latency_ms'),
                     'source': e.get('source', '')}
                    for u, e in self.entries.items()
                    for hv in (e.get('hosts', {}).get(host),) if isinstance(hv, dict) and hv.get('ok')]
        rows.sort(key=lambda r: r['ms'] if isinstance(r['ms'], (int, float)) else 10 ** 9)
        return rows[:limit] if limit else rows

    # -- candidates: the lists, the screen, Round 1 --------------------------------
    def _lists(self, fetcher=None, force=False):
        """{url: (source, country)} from every list, fetched whole at most every LIST_TTL_S ({} when all failed)."""
        cached = self._lists_cache
        if cached and cached[1] and not force and time.monotonic() - cached[0] < LIST_TTL_S:
            return cached[1]

        def one(item):
            name, url, kind, scheme = item
            meta = {}
            try:
                text = fetcher(url) if fetcher else _direct_get(url)
                return name, normalize_list(text, kind, scheme, meta), meta, None
            except Exception as err:
                return name, [], {}, f'{name}: {err}'

        out = {}
        with ThreadPoolExecutor(max_workers=max(1, len(LIST_SOURCES))) as ex:
            for name, urls, meta, err in ex.map(one, LIST_SOURCES):
                if err:
                    self.last_error = err
                for u in urls:
                    cc = meta.get(u)
                    if u not in out or (cc and not out[u][1]):
                        out[u] = (name, cc)
        if out:
            self._lists_cache = (time.monotonic(), out)
        return out

    def _yield_of(self, source):
        """The share of a list's candidates that came out alive so far (a prior of 1 in 50 for a list not tried)."""
        tried, alive = self.sources.get(source, (0, 0))
        return (alive + 1.0) / (tried + 50.0)

    def _count(self, source, alive):
        with self.lock:
            st = self.sources.setdefault(source or '?', [0, 0])
            st[0] += 1
            st[1] += 1 if alive else 0
            if st[0] > 20000:  # lists change: old evidence fades
                st[0], st[1] = st[0] // 2, st[1] // 2

    def _unseen(self, lists, cap):
        """Up to `cap` listed candidates nobody has looked at (not in the pool, not dead lately): Polish ones first,
        then a random draw weighted by how many of each list's candidates came out alive (a list that is 15% alive
        is drawn from far more than a huge one that is 1% alive), so every cycle reaches further down every list."""
        cut = time.time() - DEAD_RETRY_S
        with self.lock:
            cands = [u for u in lists if u not in self.entries and self.dead.get(u, 0) <= cut]
        weight = {name: self._yield_of(name) for name in {lists[u][0] for u in cands}}
        pl = [u for u in cands if lists[u][1] == 'PL']
        rest = [u for u in cands if lists[u][1] != 'PL']
        random.shuffle(pl)
        # weighted sampling without replacement (Efraimidis-Spirakis): key = U ** (1 / weight), largest first
        rest.sort(key=lambda u: random.random() ** (1.0 / weight[lists[u][0]]), reverse=True)
        picked = (pl + rest)[:max(0, cap)]
        self.unseen_left = len(cands) - len(picked)
        return picked

    def _make_room(self, n):
        """Room for `n` newcomers under MAX_ENTRIES (0: trim the pool back to it); how many of them fit. Failed entries
        go first (oldest first, into the dead map), then alive ones with the oldest verdict, then the slowest; an entry
        some faculty has verified is never dropped."""
        with self.lock:
            over = len(self.entries) + n - MAX_ENTRIES
            if over <= 0:
                return n
            now = time.time()

            def worth(kv):
                e = kv[1]
                verified = any(hv.get('ok') for hv in e.get('hosts', {}).values())
                alive = e.get('status') == 'ok'
                checked = e.get('last_checked', 0)
                fresh = alive and now - checked <= ALIVE_TTL_S
                lat = e.get('latency_ms') if isinstance(e.get('latency_ms'), (int, float)) else 10 ** 9
                return verified, alive, fresh, -lat if fresh else checked

            dropped = 0
            for u, e in sorted(self.entries.items(), key=worth):
                if dropped >= over or worth((u, e))[0]:
                    break
                del self.entries[u]
                if e.get('status') != 'ok':
                    self.dead[u] = e.get('last_checked') or now
                dropped += 1
            return max(0, n - (over - dropped))

    def _tcp_screen(self, urls, timeout=TCP_TIMEOUT_S, concurrency=128):
        """{url: connect ms} of the candidates whose port accepts a TCP connection within `timeout`. Non-blocking
        connects on one selector: `concurrency` at once, no thread per candidate."""
        from urllib.parse import urlsplit
        out = {}
        todo = deque(urls)
        sel = selectors.DefaultSelector()
        live = {}

        def launch():
            while todo and len(live) < max(1, concurrency):
                url = todo.popleft()
                try:
                    parts = urlsplit(url)
                    host, port = parts.hostname, parts.port
                    sock = socket.socket(socket.AF_INET6 if ':' in host else socket.AF_INET, socket.SOCK_STREAM)
                except (OSError, ValueError, TypeError):
                    continue
                try:
                    sock.setblocking(False)
                    err = sock.connect_ex((host, port))
                except OSError:
                    sock.close()
                    continue
                if err not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY):
                    sock.close()
                    continue
                sel.register(sock, selectors.EVENT_WRITE)
                live[sock] = (url, time.monotonic())

        def drop(sock):
            live.pop(sock, None)
            try:
                sel.unregister(sock)
            except (KeyError, ValueError):
                pass
            sock.close()

        try:
            launch()
            while live:
                now = time.monotonic()
                first = min(t0 for _, t0 in live.values())
                for key, _ in sel.select(timeout=max(0.0, first + timeout - now)):
                    sock = key.fileobj
                    url, t0 = live[sock]
                    try:
                        ok = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) == 0
                    except OSError:
                        ok = False
                    if ok:
                        out[url] = int((time.monotonic() - t0) * 1000)
                    drop(sock)
                now = time.monotonic()
                for sock, (url, t0) in list(live.items()):
                    if now - t0 >= timeout:
                        drop(sock)
                launch()
        finally:
            for sock in list(live):
                drop(sock)
            sel.close()
        return out

    def _discover(self, fetcher, workers, start_mono, cap=None, tcp_workers=128):
        """Take up to `cap` (max_probe by default) listed candidates nobody has seen, screen them and Round-1 the ones
        that connect, fastest connect first: ('ok', candidates, alive urls), ('failed', alive count) when every list
        failed, ('late', alive count, tried) past the refresh deadline. The ones that fail go to the dead map."""
        self.prune()
        self._make_room(0)
        lists = self._lists(fetcher)
        if not lists:
            # Every list source failed (or returned nothing). Do not stamp last_refresh:
            # that would freeze the maintainer for max_age with a dead pool. Retry soon.
            self.last_error = self.last_error or 'all proxy list sources returned nothing'
            self.retry_after = time.time() + RETRY_AFTER_S
            cov, alive_n = self.coverage()
            return 'failed', alive_n
        fresh = self._unseen(lists, self.max_probe if cap is None else cap)
        reach = self._tcp_screen(fresh, concurrency=tcp_workers) if fresh else {}
        now = time.time()
        with self.lock:
            for u in fresh:
                if u not in reach:
                    self.dead[u] = now
        for u in fresh:
            if u not in reach:
                self._count(lists.get(u, ('', None))[0], False)
        alive = []

        def _r1(url):
            ms = self.probe_alive(url)
            name, cc = lists.get(url, ('', None))
            self._count(name, ms is not None)
            if ms is None:
                with self.lock:
                    if url not in self.entries:
                        self.dead[url] = time.time()
                return None
            self.mark_alive(url, True, ms)
            with self.lock:
                e = self.entries.get(url)
                if e is not None:
                    e['source'] = name
                    if cc:
                        e['cc'] = cc
            return url

        with ThreadPoolExecutor(max_workers=max(1, workers)) as tpool:
            for url in tpool.map(_r1, sorted(reach, key=reach.get)):
                if url:
                    alive.append(url)
        # room is made for the ones that proved alive, not for the batch: most candidates die on the way, and a
        # known live entry must not go for one of them
        self._make_room(0)
        self.save_dead()
        if time.monotonic() - start_mono > REFRESH_DEADLINE_S:
            self.last_refresh = time.time()
            self.retry_after = 0.0
            cov, alive_n = self.coverage()
            self.last_error = None if alive_n else (self.last_error or 'no candidate passed Round 1')
            self.save()
            return 'late', alive_n, len(fresh)
        return 'ok', fresh, alive

    def _recheck(self, n, workers):
        """Re-Round-1 up to `n` alive entries whose verdict is older than ALIVE_TTL_S, oldest first: (checked, lost).
        A lost one leaves the pool unless a faculty has it verified."""
        now = time.time()
        with self.lock:
            stale = [u for _, u in sorted((e.get('last_checked', 0), u) for u, e in self.entries.items()
                                          if e.get('status') == 'ok'
                                          and now - e.get('last_checked', 0) > ALIVE_TTL_S)[:max(0, n)]]

        def one(url):
            ms = self.probe_alive(url)
            self.mark_alive(url, ms is not None, ms)
            return ms is None and self._retire(url)

        if not stale:
            return 0, 0
        with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
            return len(stale), sum(1 for lost in ex.map(one, stale) if lost)

    # -- faculty tests: which proxies get through to which faculty ------------------
    def _wait_for_hunts(self, sleep=time.sleep):
        while self._hunting > 0:
            sleep(1)

    def _faculty_jobs(self, hosts, keep, max_ms, limit):
        """([(url, host)] to probe now, how many are waiting): every fresh alive proxy with Round-1 latency up to
        `max_ms` (Polish first, then fastest) on every faculty it has not been tried on lately. A faculty that has
        `keep` exits already is only tried with proxies faster than the slowest of its `keep` fastest."""
        now = time.time()
        with self.lock:
            bar = {}
            for h in hosts:
                lats = sorted(e['latency_ms'] if isinstance(e.get('latency_ms'), (int, float)) else 10 ** 9
                              for e in self.entries.values() if (e.get('hosts', {}).get(h) or {}).get('ok'))
                bar[h] = lats[keep - 1] if keep and len(lats) >= keep else None
            cands = sorted((e.get('cc') != 'PL', e['latency_ms'], u) for u, e in self.entries.items()
                           if e.get('status') == 'ok' and isinstance(e.get('latency_ms'), (int, float))
                           and e['latency_ms'] <= max_ms and now - e.get('last_checked', 0) <= ALIVE_TTL_S)
            jobs = []
            for _, lat, u in cands:
                marks = self.entries[u].get('hosts', {})
                for h in hosts:
                    hv = marks.get(h)
                    if hv is not None and (hv.get('ok') or now - hv.get('checked', 0) < HOST_RETRY_S):
                        continue
                    if bar[h] is not None and lat >= bar[h]:
                        continue
                    jobs.append((u, h))
        return jobs[:max(0, limit)], len(jobs)

    def _reverify_jobs(self, hosts, keep):
        """Each faculty's `keep` fastest exits whose verdict is older than VERIFY_TTL_S."""
        now = time.time()
        return [(r['url'], h) for h in hosts for r in self.exits(h, keep)
                if now - (r['checked'] or 0) > VERIFY_TTL_S]

    def _run_faculty(self, jobs, workers, gap=True):
        """Probe each (url, host) and record it; the jobs that passed. The scout's jobs (gap) step aside while a
        hunt runs."""
        jobs = list(jobs)
        if not jobs:
            return []
        it = iter(jobs)
        lock = threading.Lock()
        passed = []

        def worker():
            while True:
                if gap:
                    self._wait_for_hunts()
                with lock:
                    job = next(it, None)
                if job is None:
                    return
                ms = self._probe_host(job[0], job[1], gap=gap)
                self.mark(job[0], job[1], ms is not None, ms)
                if ms is not None:
                    with lock:
                        passed.append(job)

        threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, min(workers, len(jobs))))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return passed

    def scout_once(self, fetcher=None, batch=SCOUT_BATCH, tcp_workers=128, r1_workers=32, keep=SCOUT_KEEP,
                   tests=SCOUT_TESTS, max_ms=HUNT_MAX_MS, hosts=None, recheck=SCOUT_RECHECK):
        """One cycle of the scout (docs/EGRESS.md, "Zwiad"): re-check stale alive entries, screen and Round-1 a batch
        of candidates nobody has seen, test the live fast ones on every faculty page (the new ones, and better ones
        than a faculty's kept exits), and re-probe each faculty's kept exits that have aged. Returns its stats."""
        started, t0 = time.time(), time.monotonic()
        hosts = [h for h in (hosts or self.round2) if h in self.round2]
        self._wait_for_hunts()
        rechecked, lost = self._recheck(recheck, r1_workers)
        found = ('busy',)
        if self._refresh_lock.acquire(timeout=REFRESH_DEADLINE_S):
            try:
                found = self._discover(fetcher, r1_workers, time.monotonic(), cap=batch, tcp_workers=tcp_workers)
            finally:
                self._refresh_lock.release()
        workers = self.faculty_probes
        jobs, waiting = self._faculty_jobs(hosts, keep, max_ms, tests)
        passed = self._run_faculty(jobs, workers)
        again = self._reverify_jobs(hosts, keep)
        kept = self._run_faculty(again, workers)
        cached = self._lists_cache
        exits = {h: self.exits(h) for h in hosts}
        self.scout = {
            'cycle': int(self.scout.get('cycle', 0)) + 1, 'at': started,
            'took_s': round(time.monotonic() - t0, 1),
            'listed': len(cached[1]) if cached else 0, 'unseen': self.unseen_left,
            'screened': len(found[1]) if found[0] == 'ok' else 0,
            'alive_new': len(found[2]) if found[0] == 'ok' else 0,
            'rechecked': rechecked, 'lost': lost,
            'tests': len(jobs), 'tests_left': max(0, waiting - len(jobs)), 'passed': len(passed),
            'reverified': len(again), 'kept': len(kept),
            'exits': {h: len(rows) for h, rows in exits.items()},
            'best_ms': {h: rows[0]['ms'] for h, rows in exits.items() if rows},
            'error': self.last_error if found[0] == 'failed' else None,
        }
        self.save()
        self.save_dead()
        return dict(self.scout)

    def scout_wait(self, pause=SCOUT_PAUSE_S):
        """Seconds until the next scout cycle: `pause` while there is work left, otherwise until the lists may have
        changed (at most until the kept exits need their re-check)."""
        sc = self.scout
        cached = self._lists_cache
        if sc and not sc.get('unseen') and not sc.get('tests_left') and cached:
            left = LIST_TTL_S - (time.monotonic() - cached[0])
            return max(float(pause), min(float(VERIFY_TTL_S) / 2, left))
        return float(pause)

    # -- the hunt: exits for a faculty nobody's own line gets through -------------
    def _fresh_alive(self, max_ms, now=None):
        """Alive candidates with a sensible ping and a recent enough verdict: Polish first, then fastest."""
        now = time.time() if now is None else now
        with self.lock:
            rows = [(e.get('cc') != 'PL', e['latency_ms'], u) for u, e in self.entries.items()
                    if e.get('status') == 'ok' and e.get('latency_ms') is not None and e['latency_ms'] <= max_ms
                    and now - e.get('last_checked', 0) <= HUNT_FRESH_S]
        return [u for _, _, u in sorted(rows)]

    def hunt(self, hosts, max_ms=HUNT_MAX_MS, want=HUNT_WANT, workers=HUNT_WORKERS, budget_s=HUNT_BUDGET_S,
             fetcher=None, clock=time.monotonic):
        """Search for exits that get through to each of `hosts` (faculty hosts the pool knows): {host: result}.

        Exits the scout (or an earlier hunt) verified within HUNT_TRUST_S count at once; older ones are re-checked
        first. Then every alive proxy with Round-1 latency up to `max_ms` is tried, Polish first, then fastest,
        against every host still short of `want` exits, so a proxy that gets through one walled faculty is tried on
        the others at once. Each try is the host's own Round-2 probe (its listing, its marker, no block page) and is
        recorded like one. A host hunted within HUNT_CACHE_S has only its known exits re-checked. The search stops
        when every host has `want` exits, nothing is left to try, or `budget_s` is spent; at most `workers` probes
        run at once, all hosts together (and the scout steps aside). Too few candidates first fetch the lists and
        screen and Round-1 the ones nobody has seen."""
        with self._hunt_lock:
            self._hunting += 1
        try:
            return self._hunt(hosts, max_ms, want, workers, budget_s, fetcher, clock)
        finally:
            with self._hunt_lock:
                self._hunting -= 1

    def _hunt(self, hosts, max_ms, want, workers, budget_s, fetcher, clock):
        start = clock()
        hosts = [h for h in dict.fromkeys(hosts) if h in self.round2]
        found = {h: [] for h in hosts}
        tried = {h: 0 for h in hosts}
        now = time.time()
        recent = {h for h in hosts
                  if self.hunts.get(h, {}).get('state') == 'done' and now - self.hunts[h].get('at', 0) < HUNT_CACHE_S}

        def probe(url, host):
            ms = self._probe_host(url, host)
            self.mark(url, host, ms is not None, ms)
            return ms is not None

        # what is already known to work: trusted when just verified, re-checked first otherwise
        for h in hosts:
            for c in self.exits(h):
                if len(found[h]) >= want:
                    break
                if now - (c['checked'] or 0) <= HUNT_TRUST_S:
                    found[h].append(c['url'])
                    continue
                tried[h] += 1
                if probe(c['url'], h):
                    found[h].append(c['url'])
        searching = [h for h in hosts if len(found[h]) < want and h not in recent]
        if searching:
            # "every proxy with a sensible ping": a fresh pool (a local egress just started) has Round-1 probed only
            # a sample of the lists, so keep probing the ones nobody tried yet until enough fast ones are known
            def untried():
                # alive fast candidates some searching host has not refused lately (a scouted pool is full of ones
                # every walled faculty already turned away: those are not candidates)
                now = time.time()
                with self.lock:
                    return sum(1 for url in self._fresh_alive(max_ms, now)
                               if any(not (hv := self.entries[url].get('hosts', {}).get(h))
                                      or (not hv.get('ok') and now - hv.get('checked', 0) >= HUNT_CACHE_S)
                                      for h in searching))

            for _ in range(HUNT_ROUNDS):
                if untried() >= HUNT_MIN_ALIVE or clock() - start > budget_s / 2:
                    break
                if not self._refresh_lock.acquire(timeout=60):
                    break  # the scout is discovering: what it finds lands in the pool anyway
                try:
                    known = len(self.entries)
                    got = self._discover(fetcher, HUNT_R1_WORKERS, clock(), cap=HUNT_PROBE)
                except Exception as err:
                    self.last_error = f'hunt discovery: {err}'
                    break
                finally:
                    self._refresh_lock.release()
                if got[0] != 'ok' or (not got[1] and len(self.entries) == known):
                    break  # the lists have nobody left to try
            jobs = []
            now = time.time()
            for url in self._fresh_alive(max_ms, now):
                for h in searching:
                    with self.lock:
                        hv = dict(self.entries.get(url, {}).get('hosts', {}).get(h) or {}) or None
                    if hv is not None and (hv.get('ok') or now - hv.get('checked', 0) < HUNT_CACHE_S):
                        continue  # known to work (re-checked above) or failed lately: not again
                    jobs.append((url, h))
            jobs_lock = threading.Lock()
            queue = iter(jobs)

            def worker():
                while clock() - start < budget_s:
                    with jobs_lock:
                        job = next(queue, None)
                        while job is not None and len(found[job[1]]) >= want:
                            job = next(queue, None)
                        if job is None:
                            return
                        tried[job[1]] += 1
                    if probe(*job):
                        with jobs_lock:
                            found[job[1]].append(job[0])

            threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, workers))]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
        done = time.time()
        out = {}
        for h in hosts:
            exits = list(dict.fromkeys(found[h]))
            out[h] = {'state': 'done', 'verified': len(exits), 'tried': tried[h], 'exits': exits[:ADOPT_CAP],
                      'at': done, 'error': None}
        with self._hunt_lock:
            self.hunts.update(out)
        self._save_throttled(force=True)
        return out

    def hunt_async(self, hosts, **kwargs):
        """Start hunt(hosts) in the background, or queue the hosts for the next round while one runs. The state per
        host, as hunt_status() shows it, is 'queued' while it waits for that round, then 'running' until its result
        is in (a caller's patience starts at 'running')."""
        hosts = [h for h in dict.fromkeys(hosts) if h in self.round2]
        with self._hunt_lock:
            busy = self._hunt_thread is not None and self._hunt_thread.is_alive()
            for h in hosts:
                if self.hunts.get(h, {}).get('state') not in ('running', 'queued'):
                    self._hunt_pending[h] = kwargs
                    self.hunts[h] = {**self.hunts.get(h, {}), 'state': 'queued' if busy else 'running',
                                     'error': None}
            if not busy:
                self._hunt_thread = threading.Thread(target=self._hunt_worker, daemon=True)
                self._hunt_thread.start()
        return self.hunt_status()

    def _hunt_worker(self):
        while True:
            with self._hunt_lock:
                if not self._hunt_pending:
                    self._hunt_thread = None
                    return
                batch = dict(self._hunt_pending)
                self._hunt_pending.clear()
                for h in batch:
                    self.hunts[h] = {**self.hunts.get(h, {}), 'state': 'running'}
            kwargs = next(iter(batch.values()))
            try:
                self.hunt(list(batch), **kwargs)
            except Exception as err:
                with self._hunt_lock:
                    for h in batch:
                        self.hunts[h] = {**self.hunts.get(h, {}), 'state': 'error', 'error': str(err)[:200],
                                         'at': time.time()}

    def hunt_status(self):
        with self._hunt_lock:
            return {h: dict(v) for h, v in self.hunts.items()}

    def adopt(self, host, urls, workers=HUNT_WORKERS):
        """The exits another runner found for `host`, each checked here before use (parse_proxy_url, then the
        host's own probe): the list of those that got through, now verified in this pool."""
        if host not in self.round2:
            return []
        cands = []
        for raw in list(urls or [])[:ADOPT_CAP]:
            url = parse_proxy_url(raw) if isinstance(raw, str) else None
            if url and url not in cands:
                cands.append(url)

        def check(url):
            ms = self._probe_host(url, host)
            if ms is not None:
                self.mark_alive(url, True, None)
            self.mark(url, host, ms is not None, ms)
            return url if ms is not None else None

        if not cands:
            return []
        with ThreadPoolExecutor(max_workers=max(1, min(workers, len(cands)))) as ex:
            return [u for u in ex.map(check, cands) if u]

    def refresh(self, fetcher=None, workers=32, round2_cap=56):
        """Fetch the lists, Round-1 the new candidates, Round-2 the survivors at
        under-covered hosts. Dead entries are replaced by fresh ones (prune first)."""
        if not self.enabled:
            return 0, 0, 0  # every faculty host is direct: nothing to discover or probe
        start_mono = time.monotonic()
        found = self._discover(fetcher, workers, start_mono)
        if found[0] == 'failed':
            return found[1], 0, 0
        if found[0] == 'late':
            return found[1], found[2], 0
        _, fresh, alive = found

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
                cap = min(round2_cap, max(MIN_ROUND2_CAP, deficit * 10))
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
                    ms = self._probe_host(url, h)
                    self.mark(url, h, ms is not None, ms)
                    return url if ms is not None else None

                for url in pool2.map(_r2once, cands):
                    if url:
                        verified += 1
        self.last_refresh = time.time()
        self.retry_after = 0.0
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
