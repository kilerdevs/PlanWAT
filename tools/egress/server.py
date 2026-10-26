#!/usr/bin/env python3
"""Rotating egress proxy for the refresh runner (+ LAN monitoring GUI).

Replaces tinyproxy's job for the runner: one HTTP_PROXY for the whole box, with
per-destination policy instead of a static allowlist tunnel:

  * infra hosts (GitHub, PyPI, proxy lists, …)  -> direct egress, as today;
  * faculty hosts (*.wat.edu.pl)                -> chained through a rotating pool of
    public proxies (tools/egress/pool.py), a different egress IP per connection —
    except those listed in EGRESS_DIRECT_FACULTY: they answer the pool's exits with
    block pages while the operator's own line serves them fine (WTC is the canonical
    case), so they go direct;
  * anything else                               -> 403, same default-deny as tinyproxy.

When the pool has no healthy proxy, faculty traffic falls back to direct egress
(PLANWAT_EGRESS_DIRECT_FALLBACK=1, the default) and the GUI shows DIRECT mode
instead of ROTATING. Set it to 0 for DeadDropMGMT-style fail-closed; EGRESS_FAIL_CLOSED
does the same for named hosts (FAIL-CLOSED in the GUI). EGRESS_POOL=off (volunteers)
sends every faculty host direct and leaves the pool unused.

Ports: 8888 forward proxy (inner network only), 8080 status GUI + run reports
(host port bound to localhost by default; with EGRESS_API_TOKEN set, reads need the
token too and browsers sign in at /login). The runner POSTs a run summary to /api/run after each refresh and,
whenever a faculty answers with a block page through a pooled exit, a block notice
to /api/block — the crawler sees what the CONNECT tunnel hides, so the proxy can
demote that exit (see ProxyServer.demote_recent); the GUI shows pool health, mode,
and the last runs side by side. While a crawl runs it also streams coarse progress
to /api/progress (see LiveRun), which the GUI turns into a progress bar with a
finish estimate built from the crawl's own measured throughput.

Threat model (unchanged from tinyproxy): job code on the runner is untrusted, so
this proxy never fetches an arbitrary host on a job's behalf — routing above is
the whole policy, CONNECT is limited to port 443, plain HTTP to port 80.
"""
import hmac
import itertools
import json
import os
import re
import secrets
import socket
import struct
import threading
import time
import urllib.parse
from calendar import timegm
from collections import deque
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import median

from pool import ProxyPool

HERE = Path(__file__).resolve().parent


def env(name, default):
    return os.environ.get(name, default)


def env_int(name, default, minimum=1):
    """A positive integer from the environment; a typo falls back instead of crashing boot."""
    try:
        value = int(env(name, default))
    except (TypeError, ValueError):
        return default
    return value if value >= minimum else default


# Parity with <runner dir>/allow.txt: everything here goes direct.
DIRECT_SUFFIXES = ('github.com', 'githubusercontent.com', 'actions.githubusercontent.com',
                   'pypi.org', 'pythonhosted.org', 'codeload.github.com',
                   'blob.core.windows.net')
DIRECT_EXACT = ('api.github.com',)
# Faculty traffic rides the rotating pool (CHAIN_SUFFIXES), except the hosts listed here (env,
# comma or space separated): the pool's public exits are what their WAF blocks, while the
# operator's own line serves them, so they go direct. wtc.wat.edu.pl is the canonical example.
DIRECT_FACULTY = tuple(s.lower() for s in env('EGRESS_DIRECT_FACULTY', '').replace(',', ' ').split() if s)
CHAIN_SUFFIXES = ('wat.edu.pl',)
# EGRESS_POOL=off is the volunteer mode: every faculty host goes out directly and the pool is never
# refreshed, probed or picked from. A mode, not a hand-copied host list that silently starts pool work
# the day a faculty is added to faculty_targets() but not to the list.
POOL_OFF = env('EGRESS_POOL', 'on').strip().lower() in ('0', 'off', 'false', 'no')

CONNECT_TIMEOUT = 10
TUNNEL_IDLE = 120
BUF = 65536
CONNECT_HEAD_CAP = 32 * 1024
RELAY_CAP_S = 600
TUNNEL_SLOTS = threading.BoundedSemaphore(64)
MAX_CONNECTIONS = env_int('EGRESS_MAX_CONNECTIONS', 96, 8)
GUI_BODY_CAP = 256 * 1024
TUNNEL_COUNTER = itertools.count(1)
CONNECT_STATUS_RE = re.compile(br'^HTTP/1\.[01] 200')

# Hosts that must never fall back to this box's own line: when the pool has no healthy
# exit for them, the request fails closed instead of leaking the operator's address.
# `1`/`true`/`all` means every chained faculty host; otherwise a comma/space list.
_FAIL_CLOSED_RAW = env('EGRESS_FAIL_CLOSED', '').strip().lower()
FAIL_CLOSED_ALL = _FAIL_CLOSED_RAW in ('1', 'true', 'yes', 'all', '*')
FAIL_CLOSED = frozenset(
    s.lower() for s in env('EGRESS_FAIL_CLOSED', '').replace(',', ' ').split()
    if s and s.lower() not in ('1', 'true', 'yes', 'all', '*')
)


def fail_closed_listed(host):
    """True when `host` is named on the EGRESS_FAIL_CLOSED list (not the `all` switch)."""
    h = (host or '').lower().rstrip('.')
    return any(h == s or h.endswith('.' + s) for s in FAIL_CLOSED)


def fail_closed(host):
    """True when `host` must not use direct fallback (its pool exits are the only route)."""
    h = (host or '').lower().rstrip('.')
    if FAIL_CLOSED_ALL:
        return any(h == s or h.endswith('.' + s) for s in CHAIN_SUFFIXES)
    return fail_closed_listed(h)


def falls_back_direct(host):
    """True when `host` may go out from this box's own line once the pool has no exit for it."""
    return (not fail_closed(host)
            and env('PLANWAT_EGRESS_DIRECT_FALLBACK', '1') in ('1', 'true', 'yes'))


def faculty_targets(season=None):
    """Round-2 verification targets: each chain host's own index page + content marker.

    XML indexes must contain <?xml; the HTML ones (WCY Drupal, WML landing, WIG file listing) need a
    positive marker too — a WAF block page is also a 200 with a large body. The
    proxy pool additionally rejects known block-page markers on every probe.
    """
    season = season or env('EGRESS_SEASON', 'zima')
    xml = b'<?xml'
    return {
        'wlo.wat.edu.pl': (f'https://wlo.wat.edu.pl/planyzajec/{season}/index.xml', xml),
        'wel.wat.edu.pl': (f'https://wel.wat.edu.pl/planyzajec/{season}/index.xml', xml),
        'www.wim.wat.edu.pl': (f'https://www.wim.wat.edu.pl/wp-content/uploads/rozklady/{season}/index.xml', xml),
        'ioe.wat.edu.pl': ('https://ioe.wat.edu.pl/plany/lato/index.xml', xml),
        'planzajec.wcy.wat.edu.pl': ('https://planzajec.wcy.wat.edu.pl/pl/rozklad', b'grupa_id=wcy'),
        'wml.wat.edu.pl': ('https://wml.wat.edu.pl/rozklady-zajec/', b'index.xml'),
        'wtc.wat.edu.pl': ('https://wtc.wat.edu.pl/Plany/index.xml', xml),
        'www.wig.wat.edu.pl': ('https://www.wig.wat.edu.pl/cpp/phocadownloadpap/budownictwo/', b'Index of /cpp/'),
    }



def host_is_direct(host):
    """True when `host` is on the EGRESS_DIRECT_FACULTY list."""
    h = (host or '').lower().rstrip('.')
    return any(h == s or h.endswith('.' + s) for s in DIRECT_FACULTY)


_LABEL_RE = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?')


def canonical_host(host):
    """The one spelling every policy and pool key uses: lowercase, no trailing dot, DNS-valid.

    '' for anything else (an over-long name, an empty or illegal label, an IP literal in
    brackets): job code on the runner is untrusted, and a malformed or case-varied name must
    neither reach the pool as a fresh key nor be blamed on the exits it was tried through.
    """
    h = (host or '').lower().rstrip('.')
    if not h or len(h) > 253:
        return ''
    return h if all(_LABEL_RE.fullmatch(label) for label in h.split('.')) else ''


def route(host):
    """'direct' | 'chain' | 'deny' for a destination hostname."""
    h = canonical_host(host)
    if not h or h in ('localhost',) or h.startswith('127.'):
        return 'deny'
    if h in DIRECT_EXACT or any(h == s or h.endswith('.' + s) for s in DIRECT_SUFFIXES):
        return 'direct'
    # A host named on EGRESS_FAIL_CLOSED stays on the pool even if a direct list (or the
    # volunteer mode) also names it: "never from the home line" must win over "go direct".
    pinned = fail_closed_listed(h)
    if host_is_direct(h) and not pinned:
        return 'direct'
    if any(h == s or h.endswith('.' + s) for s in CHAIN_SUFFIXES):
        return 'direct' if POOL_OFF and not pinned else 'chain'
    return 'deny'


def split_target(target):
    """('host', port) from CONNECT 'host:port', host canonical. None when malformed or off-limits."""
    if not target or '@' in target or '/' in target:
        return None
    host, _, port = target.rpartition(':')
    if not host or not port.isdigit():
        return None
    port = int(port)
    if port not in (80, 443):
        return None
    host = canonical_host(host)
    if not host:
        return None
    return host, port


# Plain-HTTP forwarding is a courtesy for the few non-TLS URLs; the crawler uses CONNECT.
# Bodies are small (nothing in the refresh path POSTs through the proxy), so cap them.
PLAIN_BODY_CAP = 1024 * 1024
HOP_BY_HOP = frozenset({
    'connection', 'proxy-connection', 'keep-alive', 'proxy-authenticate',
    'proxy-authorization', 'te', 'trailer', 'transfer-encoding', 'upgrade', 'expect',
})


def plain_forward_headers(headers):
    """Forwarded header block for an absolute-URI request, without hop-by-hop fields.

    Drops the client's Host (the caller writes the destination's own), its
    Content-Length (the caller writes the body length it actually forwards), and any
    header named by Connection — forwarding those is how a proxy smuggles a second
    request or leaks its own connection semantics upstream.
    """
    drop = set(HOP_BY_HOP)
    try:
        values = headers.get_all('Connection') or []
    except AttributeError:
        values = []
    for value in values:
        drop.update(token.strip().lower() for token in str(value).split(',') if token.strip())
    lines = []
    for key, value in headers.items():
        low = key.lower()
        if low in drop or low in ('host', 'content-length'):
            continue
        if any(ch in key for ch in '\r\n:') or any(ch in str(value) for ch in '\r\n'):
            continue
        lines.append(f'{key}: {value}\r\n')
    return ''.join(lines)



# -- upstream chaining ----------------------------------------------------
def _recv_exact(sock, n, timeout=10):
    deadline = time.monotonic() + timeout
    data = b''
    while len(data) < n:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise OSError('upstream handshake timed out')
        sock.settimeout(remaining)
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise OSError('upstream closed the handshake')
        data += chunk
    return data


class BadTarget(OSError):
    """The destination itself is unusable; raised before any proxy is contacted."""


def chain_connect(proxy_url, host, port, timeout=CONNECT_TIMEOUT):
    """Open `host:port` *through* the public proxy. Returns the tunnelled socket."""
    try:
        hb = host.encode('idna')
    except Exception:
        raise BadTarget('bad hostname')
    if len(hb) > 255:
        raise BadTarget('hostname too long')
    parts = urllib.parse.urlsplit(proxy_url)
    scheme, phost, pport = parts.scheme.lower(), parts.hostname, parts.port
    sock = socket.create_connection((phost, pport), timeout=timeout)
    try:
        if scheme == 'http':
            sock.sendall(f'CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n'
                         .encode('ascii'))
            deadline = time.monotonic() + (timeout if timeout else 10)
            head = b''
            while b'\r\n\r\n' not in head:
                if len(head) > CONNECT_HEAD_CAP:
                    raise OSError('proxy CONNECT header too large')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise OSError('proxy CONNECT timed out')
                sock.settimeout(remaining)
                chunk = sock.recv(4096)
                if not chunk:
                    raise OSError('proxy closed CONNECT')
                head += chunk
                if len(head) > CONNECT_HEAD_CAP:
                    raise OSError('proxy CONNECT header too large')
            if not CONNECT_STATUS_RE.match(head):
                first = head.splitlines()[0][:60] if head.splitlines() else b''
                raise OSError(f'proxy refused CONNECT ({first!r})')
        elif scheme == 'socks5':
            sock.sendall(b'\x05\x01\x00')
            if _recv_exact(sock, 2, timeout) != b'\x05\x00':
                raise OSError('socks5: no anonymous method')
            sock.sendall(b'\x05\x01\x00\x03' + bytes([len(hb)]) + hb + struct.pack('!H', port))
            rep = _recv_exact(sock, 4, timeout)
            if rep[:2] != b'\x05\x00':
                raise OSError(f'socks5: refused ({rep.hex()})')
            atyp = rep[3]
            if atyp == 1:      # IPv4: 4-byte address + 2-byte port
                _recv_exact(sock, 6, timeout)
            elif atyp == 4:    # IPv6: 16-byte address + 2-byte port
                _recv_exact(sock, 18, timeout)
            elif atyp == 3:    # domain: 1-byte length, then name + 2-byte port
                length = _recv_exact(sock, 1, timeout)[0]
                _recv_exact(sock, length + 2, timeout)
            else:
                raise OSError(f'socks5: unknown address type {atyp}')
        elif scheme == 'socks4':
            sock.sendall(b'\x04\x01' + struct.pack('!H', port) + b'\x00\x00\x00\x01anonymous\x00'
                         + hb + b'\x00')
            rep = _recv_exact(sock, 8, timeout)
            if rep[:2] != b'\x00\x5a':
                raise OSError('socks4a: refused')
        else:
            raise OSError(f'unsupported proxy scheme {scheme}')
    except Exception:
        sock.close()
        raise
    try:
        sock.settimeout(None)
    except OSError:
        pass
    return sock


def relay(a, b, cap=RELAY_CAP_S, idle=TUNNEL_IDLE):
    """Copy both ways, joining the copy threads (cap `cap` s of wall clock, `idle` s quiet).

    up = bytes a->b, down = bytes b->a. Half-close is preserved: EOF on one side only
    shuts down the write half of the other, so a client that finished sending can still
    read the whole response. A tunnel that moves no bytes for `idle` seconds is dropped
    instead of occupying a slot until the hard cap.
    """
    start = time.monotonic()
    deadline = start + cap
    counts = [0, 0]
    activity = [start]
    activity_lock = threading.Lock()
    done = threading.Event()
    for s in (a, b):
        try:
            s.settimeout(1.0)
        except OSError:
            pass

    def _copy(src, dst, idx):
        try:
            while not done.is_set() and time.monotonic() < deadline:
                try:
                    chunk = src.recv(BUF)
                except socket.timeout:
                    with activity_lock:
                        quiet = time.monotonic() - activity[0]
                    if quiet >= idle:
                        break
                    continue
                except OSError:
                    break
                if not chunk:
                    try:
                        dst.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass
                    break
                try:
                    dst.sendall(chunk)
                except OSError:
                    break
                counts[idx] += len(chunk)
                with activity_lock:
                    activity[0] = time.monotonic()
        finally:
            # One direction ending must not tear down the other (HTTP responses flow
            # only after the request body has been sent in full).
            pass

    threads = [threading.Thread(target=_copy, args=(a, b, 0), daemon=True),
               threading.Thread(target=_copy, args=(b, a, 1), daemon=True)]
    for t in threads:
        t.start()
    while any(t.is_alive() for t in threads):
        now = time.monotonic()
        with activity_lock:
            quiet = now - activity[0]
        if now >= deadline or quiet >= idle:
            break
        for t in threads:
            t.join(timeout=0.5)
    if any(t.is_alive() for t in threads):
        done.set()
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        for t in threads:
            t.join(timeout=1.0)
    for s in (a, b):
        try:
            s.close()
        except OSError:
            pass
    return counts[0], counts[1], time.monotonic() - start


# -- run reports -----------------------------------------------------------
class RunLog:
    STALE_OPEN_S = 12 * 3600  # a 'started' report without a finish is not live forever

    def __init__(self, path, cap=30):
        self.path = Path(path)
        self.cap = cap
        self.lock = threading.Lock()
        self.runs = []
        self.open_runs = []
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(data, list):
                self.runs = data[-cap:]
            elif isinstance(data, dict):
                runs = data.get('runs', [])
                if isinstance(runs, list):
                    self.runs = runs[-cap:]
                opened = data.get('open', [])
                if isinstance(opened, list):
                    self.open_runs = self._fresh(opened)[-cap:]
        except (OSError, ValueError):
            pass

    @staticmethod
    def _stamp(entry):
        """Unix seconds from a report's `received`/`started` stamp, or None."""
        for key in ('received', 'started'):
            value = entry.get(key) if isinstance(entry, dict) else None
            if not isinstance(value, str):
                continue
            try:
                return timegm(time.strptime(value, '%Y-%m-%dT%H:%M:%SZ'))
            except (ValueError, OverflowError, OSError):
                continue
        return None

    def _fresh(self, entries):
        now = time.time()
        return [e for e in entries
                if isinstance(e, dict)
                and ((stamp := self._stamp(e)) is None or now - stamp <= self.STALE_OPEN_S)]

    def _expire_open(self):
        fresh = self._fresh(self.open_runs)
        changed = len(fresh) != len(self.open_runs)
        self.open_runs = fresh
        return changed

    def open_snapshot(self):
        with self.lock:
            if self._expire_open():
                self._persist()
            return list(self.open_runs)

    def _persist(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix('.tmp')
            payload = json.dumps({'runs': self.runs, 'open': self.open_runs}, indent=1)
            # Back-compat: old readers expect a bare list; keep new dict shape only
            # when open runs exist, else write the plain list.
            if not self.open_runs:
                payload = json.dumps(self.runs, indent=1)
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

    def add(self, report):
        with self.lock:
            report['received'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
            self._expire_open()
            if isinstance(report, dict) and report.get('phase') == 'started':
                self.open_runs.append(report)
                del self.open_runs[:-self.cap]
                self._persist()
                return report
            # final report closes any open run
            if self.open_runs:
                self.open_runs = []
            self.runs.append(report)
            del self.runs[:-self.cap]
            self._persist()
            return report


# -- live crawl progress ---------------------------------------------------
class LiveRun:
    """Live crawl progress for the GUI: fed by POST /api/progress, read by GET /api/progress.

    The crawler sends coarse events (run_start, faculty_start, tick, faculty_done, wait_start/end,
    run_done) and this handler stamps each arrival, so a slot's throughput below is measured from
    its own ticks — pages per second over the last RATE_WINDOW seconds. The finish estimate adds
    up what remains per slot at that rate (the run's median rate for a slot that has not spoken
    yet, its group count estimated from its siblings' median), and a lane's total is its slots'
    sum: lanes crawl side by side, so the run ends with the slowest lane plus a tail for
    publishing. A slot that is waiting out a block or has gone quiet makes its lane's estimate
    read 'wstrzymane' instead of a made-up hour. One run at a time, memory only: a run whose
    events stopped for STALE_S reads stale, and a report in /api/run still lands in runs.json.
    """

    RATE_WINDOW = 180.0   # seconds of a slot's own history its throughput is measured over
    MIN_SPAN = 15.0       # below this much history, trust the run's median rate instead
    STALL_S = 150.0       # 'crawling' but no event for this long -> stalled (honest, not wrong)
    STALE_S = 600.0       # no event at all for this long -> the whole run reads stale
    TAIL_S = 60.0         # publishing the changed calendars after the last page
    FALLBACK_TOTAL = 150  # groups assumed for a faculty that has not listed yet
    SAMPLE_CAP = 90       # ticks kept per slot (a few minutes at the crawler's throttle)
    MAX_SLOTS = 128       # hard cap: an untrusted client cannot grow GUI memory without bound
    MAX_LANES = 32
    MAX_WAITS = 16

    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = threading.Lock()
        self.state = None

    # -- writes ------------------------------------------------------------
    def _slot(self, key, faculty, lane, now, ahead=False, term=''):
        return {'key': key, 'faculty': faculty, 'lane': lane, 'status': 'queued', 'total': None,
                'done': 0, 'pass': 0, 'ahead': bool(ahead), 'term': term, 'changed': None,
                'updated': now, 'samples': deque(maxlen=self.SAMPLE_CAP)}

    @staticmethod
    def _names(value, limit):
        """A bounded list of names from an untrusted event field (never a string's chars)."""
        if not isinstance(value, (list, tuple)):
            return []
        return [str(v)[:80] for v in value][:limit]

    def _start(self, rid, body, now):
        slots, lanes = {}, []
        lanes_in = body.get('lanes')
        if not isinstance(lanes_in, (list, tuple)):
            lanes_in = []
        for lane in lanes_in[:self.MAX_LANES]:
            if not isinstance(lane, dict):
                continue
            names, chosen = [], set()
            for name in self._names(lane.get('faculties'), self.MAX_SLOTS):
                if not name or name in slots or name in chosen:
                    continue
                if len(slots) + len(names) >= self.MAX_SLOTS:
                    break
                names.append(name)
                chosen.add(name)
            if not names:
                continue
            name = str(lane.get('lane') or names[0])[:80]
            lanes.append({'lane': name, 'slots': list(names)})
            for fac in names:
                slots[fac] = self._slot(fac, fac, name, now)
        self.state = {'run': rid, 'started': now, 'updated': now, 'finished': None, 'exit': None,
                      'blocked': False, 'incomplete': False, 'degraded': False, 'changed': None,
                      'profile': str(body.get('profile') or ''), 'parallel': bool(body.get('parallel')),
                      'waits': {}, 'lanes': lanes, 'slots': slots}

    def _lane_add(self, lane, key):
        lane = (lane or '?')[:80]
        for entry in self.state['lanes']:
            if entry['lane'] == lane:
                if key not in entry['slots']:
                    entry['slots'].append(key)
                return
        if len(self.state['lanes']) >= self.MAX_LANES:
            return  # a late/unknown lane must not grow the page without bound
        self.state['lanes'].append({'lane': lane, 'slots': [key]})

    def _slot_of(self, body, now):
        key = str(body.get('slot') or body.get('faculty') or '?')[:80]
        slot = self.state['slots'].get(key)
        if slot is None:  # a slot the run_start did not announce (an ahead pass, a lost event)
            if len(self.state['slots']) >= self.MAX_SLOTS:
                return None
            lane = str(body.get('lane') or '')[:80]
            slot = self._slot(key, str(body.get('faculty') or key)[:80], lane, now,
                              ahead=bool(body.get('ahead')), term=str(body.get('term') or '')[:32])
            self.state['slots'][key] = slot
            self._lane_add(lane, key)
        return slot

    def _sample(self, slot, now):
        slot['samples'].append((now, slot['done']))

    def _wait_key(self, body, faculties):
        return str(body.get('id') or body.get('lane') or ','.join(faculties) or '?')[:80]

    def _apply(self, kind, body, now):
        if kind == 'faculty_start':
            slot = self._slot_of(body, now)
            if slot is None:
                return
            total = body.get('total')
            slot['total'] = int(total) if isinstance(total, (int, float)) else None
            slot['done'] = 0
            slot['pass'] += 1
            slot['status'] = 'crawling'
            slot['ahead'] = bool(body.get('ahead'))
            slot['term'] = str(body.get('term') or slot['term'])
            slot['updated'] = now
            slot['samples'].clear()  # a resumed pass measures from its own zero
            self._sample(slot, now)
        elif kind == 'tick':
            slot = self._slot_of(body, now)
            if slot is None:
                return
            done, total = body.get('done'), body.get('total')
            if isinstance(done, (int, float)):
                slot['done'] = int(done)
            if slot['total'] is None and isinstance(total, (int, float)):
                slot['total'] = int(total)
            if slot['status'] == 'queued':
                slot['status'] = 'crawling'
            slot['updated'] = now
            self._sample(slot, now)
        elif kind == 'faculty_done':
            slot = self._slot_of(body, now)
            if slot is None:
                return
            blocked, complete = bool(body.get('blocked')), bool(body.get('complete'))
            changed = body.get('changed')
            slot['changed'] = int(changed) if isinstance(changed, (int, float)) else None
            if complete and slot['total'] is not None:
                slot['done'] = slot['total']
            slot['status'] = 'blocked' if blocked else ('done' if complete else 'stopped')
            slot['updated'] = now
            self._sample(slot, now)
        elif kind == 'wait_start':
            faculties = self._names(body.get('faculties'), self.MAX_SLOTS)
            slots = self._names(body.get('slots'), self.MAX_SLOTS)
            key = self._wait_key(body, faculties)
            waits = self.state['waits']
            if len(waits) >= self.MAX_WAITS and key not in waits:
                oldest = min(waits, key=lambda k: waits[k].get('since', now))
                waits.pop(oldest, None)
            waits[key] = {'id': key, 'lane': str(body.get('lane') or '')[:80], 'faculties': faculties,
                          'slots': slots,
                          'budget': body.get('budget') if isinstance(body.get('budget'), (int, float)) else None,
                          'since': now}
            for slot_key in (slots or faculties):
                slot = self.state['slots'].get(slot_key)
                if slot is not None:
                    slot['status'] = 'waiting'
                    slot['updated'] = now
        elif kind == 'wait_end':
            faculties = self._names(body.get('faculties'), self.MAX_SLOTS)
            key = self._wait_key(body, faculties)
            wait = self.state['waits'].pop(key, None)
            recovered = bool(body.get('recovered'))
            slots = (self._names(body.get('slots'), self.MAX_SLOTS)
                     or (wait or {}).get('slots') or faculties or (wait or {}).get('faculties') or [])
            for slot_key in slots:
                slot = self.state['slots'].get(slot_key)
                if slot is not None:
                    # A recovered wall is re-crawled immediately; an unrecovered one stays blocked.
                    slot['status'] = 'queued' if recovered else 'blocked'
                    slot['updated'] = now
        elif kind == 'run_done':
            self.state['finished'] = now
            if isinstance(body.get('exit'), (int, float)):
                self.state['exit'] = int(body['exit'])
            if isinstance(body.get('changed'), (int, float)):
                self.state['changed'] = int(body['changed'])
            self.state['blocked'] = bool(body.get('blocked'))
            self.state['incomplete'] = bool(body.get('incomplete'))
            self.state['degraded'] = bool(body.get('degraded'))
            # A wall still outstanding when the run ends is a stopped slot, not a live wait.
            for wait in self.state['waits'].values():
                for slot_key in (wait.get('slots') or wait.get('faculties') or []):
                    slot = self.state['slots'].get(slot_key)
                    if slot is not None and slot['status'] == 'waiting':
                        slot['status'] = 'stopped'
                        slot['updated'] = now
            self.state['waits'].clear()

    def event(self, body):
        """Apply one crawler event; returns a small acknowledgement (None = ignored)."""
        if not isinstance(body, dict):
            return None
        kind = str(body.get('event') or '')
        rid = str(body.get('run') or '')
        now = self.clock()
        with self.lock:
            if kind == 'run_start' or self.state is None:
                self._start(rid, body, now)
            elif rid and rid != self.state.get('run'):
                if self.state.get('finished') is None:
                    return None  # a straggler of an older run while this one is live
                self._start(rid, {}, now)  # a new run whose run_start never made it
            self._apply(kind, body, now)
            self.state['updated'] = now
            return {'ok': True, 'event': kind, 'run': self.state['run']}

    # -- reads -------------------------------------------------------------
    def _rate(self, slot):
        samples = slot['samples']
        if len(samples) < 2:
            return None
        t_end, d_end = samples[-1]
        t_ref, d_ref = samples[0]
        for t, d in samples:
            if t_end - t <= self.RATE_WINDOW:
                t_ref, d_ref = t, d
                break
        span = t_end - t_ref
        if span < self.MIN_SPAN or d_end <= d_ref:
            return None
        return (d_end - d_ref) / span

    def snapshot(self, now=None):
        """The GUI's whole crawl card, ETAs included, computed from the arrival-stamped state."""
        now = self.clock() if now is None else now
        with self.lock:
            st = self.state
            if st is None:
                return {'active': False, 'run': None}
            rates, totals = {}, []
            for key, slot in st['slots'].items():
                rate = self._rate(slot)
                if rate:
                    rates[key] = rate
                if slot['total']:
                    totals.append(slot['total'])
            med_rate = median(rates.values()) if rates else None
            med_total = int(median(totals)) if totals else self.FALLBACK_TOTAL
            finished = st.get('finished')
            waits = list(st.get('waits', {}).values())
            wait = None
            if waits:
                faculties, slots = [], []
                for w in waits:
                    for f in w.get('faculties') or []:
                        if f not in faculties:
                            faculties.append(f)
                    for s in w.get('slots') or []:
                        if s not in slots:
                            slots.append(s)
                wait = {'lanes': sorted({w.get('lane') or '' for w in waits}),
                        'lane': waits[0].get('lane') or '',
                        'faculties': faculties, 'slots': slots,
                        'budget': max((w.get('budget') or 0) for w in waits),
                        'since': min((w.get('since') or now) for w in waits)}
            views = {}
            for key, slot in st['slots'].items():
                status = slot['status']
                ago = max(0.0, now - slot['updated'])
                if finished is None and status == 'crawling' and ago > self.STALL_S:
                    status = 'stalled'
                total, est = slot['total'], False
                if total is None:
                    total, est = med_total, True  # not listed yet: siblings' median, flagged
                done = slot['done']
                rate = rates.get(key) or med_rate
                if finished is not None or status in ('done', 'stopped'):
                    eta = 0.0  # the run is over, or this slot will do no more work in it
                elif status in ('waiting', 'blocked', 'stalled'):
                    eta = None  # honesty over precision: unknown, not a guess
                elif rate:
                    eta = max(0.0, (total - done) / rate)
                else:
                    eta = None  # too early to measure a rate (or no median to borrow)
                views[key] = {'slot': key, 'faculty': slot['faculty'], 'lane': slot['lane'],
                              'status': status, 'done': done, 'total': total,
                              'pct': round(100.0 * done / total, 1) if total else 0.0,
                              'rate': round(rate, 3) if rate else None,
                              'eta_s': None if eta is None else round(eta),
                              'estimated': est, 'ahead': slot['ahead'], 'term': slot['term'],
                              'pass': slot['pass'], 'changed': slot['changed'],
                              'updated_ago': round(ago)}
            lanes_out = []
            for lane in st['lanes']:
                members = [views[k] for k in lane['slots'] if k in views]
                etas = [m['eta_s'] for m in members]
                unknown = any(e is None for e in etas)
                lanes_out.append({'lane': lane['lane'], 'slots': members, 'unknown': unknown,
                                  'eta_s': None if unknown else round(sum(etas))})
            known = [v for v in views.values()]
            done_total = sum(v['done'] for v in known)
            total_all = sum(v['total'] for v in known)
            active = finished is None
            if not active:
                eta = 0.0
            elif any(l['unknown'] for l in lanes_out):
                eta = None
            else:
                eta = max([l['eta_s'] or 0.0 for l in lanes_out] or [0.0]) + self.TAIL_S
            elapsed = (finished or now) - st['started']
            return {'active': active, 'stale': active and (now - st['updated']) > self.STALE_S,
                    'run': st['run'], 'started': st['started'], 'finished': finished,
                    'elapsed_s': round(elapsed), 'exit': st['exit'], 'changed': st['changed'],
                    'blocked': st['blocked'], 'incomplete': st['incomplete'],
                    'degraded': st['degraded'], 'profile': st['profile'], 'parallel': st['parallel'],
                    'waiting': bool(wait) and active, 'wait': wait,
                    'done': done_total, 'total': total_all,
                    'pct': round(100.0 * done_total / total_all, 1) if total_all else 0.0,
                    'estimated': any(v['estimated'] for v in known),
                    'rate': round(done_total / elapsed, 3) if done_total and elapsed > 0 else 0.0,
                    'eta_s': None if eta is None else round(eta),
                    'eta_at': None if eta is None else now + eta,
                    'lanes': lanes_out, 'updated': st['updated'],
                    'updated_ago': round(max(0.0, now - st['updated']))}


# -- forward proxy ----------------------------------------------------------
class ProxyHandler(BaseHTTPRequestHandler):
    server_version = 'PlanWAT-Egress/1'
    protocol_version = 'HTTP/1.1'
    timeout = 30

    def log_message(self, *args):  # keep docker logs to one line per tunnel, not per chunk
        pass

    def _deny(self, code=403):
        if code == 403:
            body = b'filtered domain'
        elif code == 503:
            body = b'slot exhausted'
        else:
            body = b'bad request'
        self.close_connection = True  # a denied request may have an unread body
        self.send_response(code)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def _open(self, host, port):
        """(socket, via, connect_ms) to host:port per routing policy. Raises OSError when denied.

        A successful chain_connect only proves the tunnel opened; the caller records the
        live success after bytes actually flowed, so a blackholing exit cannot stay
        "verified" just because it accepted CONNECT.
        """
        import time as _time
        policy = route(host)
        if policy == 'deny' or port not in (80, 443):
            raise OSError('deny')
        if policy == 'direct':
            start = _time.monotonic()
            sock = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT)
            return sock, 'direct', int((_time.monotonic() - start) * 1000)
        try:
            if hasattr(self.server.pool, 'pick_many'):
                candidates = self.server.pool.pick_many(host, 3)
            else:
                single = self.server.pool.pick(host)
                candidates = [single] if single else []
        except Exception as err:
            print(f'pick failed: {err}', flush=True)
            candidates = []
        candidates = [c for c in candidates if c][:3]
        if not candidates:
            return self._fallback(host, port)
        for proxy in candidates:
            start = _time.monotonic()
            try:
                sock = chain_connect(proxy, host, port, timeout=6)
            except BadTarget:
                raise OSError('deny')  # the name failed here, not at the exit: blame no proxy
            except Exception as err:
                print(f'chain via {proxy} failed: {err}', flush=True)
                try:
                    self.server.pool.mark(proxy, host, False, live=True)  # dead for this host
                except Exception as merr:
                    print(f'mark fail failed: {merr}', flush=True)
                continue
            ms = int((_time.monotonic() - start) * 1000)
            try:
                self.server.remember_tunnel(host, proxy)
            except Exception as merr:
                print(f'remember tunnel failed: {merr}', flush=True)
            return sock, proxy, ms
        return self._fallback(host, port)

    def _fallback(self, host, port):
        if fail_closed(host):
            raise OSError('proxy_empty')  # this host must never leak the operator's line
        if falls_back_direct(host):
            lock = getattr(self.server, 'fallbacks_lock', None)
            if lock is not None:
                with lock:
                    self.server.fallbacks[host] = self.server.fallbacks.get(host, 0) + 1
            else:
                self.server.fallbacks[host] = self.server.fallbacks.get(host, 0) + 1
            start = time.monotonic()
            sock = socket.create_connection((host, port), timeout=CONNECT_TIMEOUT)
            return sock, 'direct-fallback', int((time.monotonic() - start) * 1000)
        raise OSError('proxy_empty')

    def _record_use(self, host, via, ms, ok):
        """Feed a finished live request back to the pool (never for direct exits)."""
        if not via or via in ('direct', 'direct-fallback'):
            return
        try:
            self.server.pool.mark(via, host, ok, ms if ok else None, live=True)
        except Exception as err:
            print(f'mark {"ok" if ok else "fail"} failed for {via}: {err}', flush=True)

    def do_CONNECT(self):
        if not TUNNEL_SLOTS.acquire(blocking=False):
            return self._deny(503)
        self.server.requests += 1
        self.server.active += 1
        try:
            target = split_target(self.path)
            if target is None:
                return self._deny(400)
            host, port = target
            try:
                upstream, via, ms = self._open(host, port)
            except Exception as err:
                print(f'open {host}:{port} failed: {err}', flush=True)
                self.server.blocks += 1
                return self._deny(403 if str(err) in ('deny', 'proxy_empty') else 502)
            try:
                self.send_response(200)
                self.end_headers()
            except OSError:
                try:
                    upstream.close()
                except OSError:
                    pass
                return
            self.close_connection = True  # the tunnel owns the socket from here on
            up = down = 0
            secs = 0.0
            try:
                up, down, secs = relay(self.connection, upstream)
                self._record_use(host, via, ms, up + down > 0)
            except Exception as err:
                print(f'relay {host}:{port} failed: {err}', flush=True)
                self._record_use(host, via, ms, False)
            print(json.dumps({'id': next(TUNNEL_COUNTER), 'host': host, 'port': port,
                              'via': via, 'secs': round(secs, 3), 'up': up, 'down': down}),
                  flush=True)
        finally:
            self.server.active -= 1
            TUNNEL_SLOTS.release()

    def _forward_plain(self):
        if not TUNNEL_SLOTS.acquire(blocking=False):
            return self._deny(503)
        self.server.requests += 1
        self.server.active += 1
        try:
            try:
                parts = urllib.parse.urlsplit(self.path)
                if parts.scheme not in ('http',) or not parts.hostname:
                    return self._deny(400)  # only absolute-URI forwarding; origin-form is a client bug
                host, port = canonical_host(parts.hostname), parts.port or 80
            except ValueError:
                return self._deny(400)  # malformed authority (bad port, brackets, …)
            if not host:
                return self._deny(400)
            if self.headers.get('Transfer-Encoding'):
                return self._deny(400)  # chunked request bodies are not forwarded
            try:
                length = int(self.headers.get('Content-Length') or 0)
            except ValueError:
                return self._deny(400)
            if length < 0 or length > PLAIN_BODY_CAP:
                return self._deny(413)
            try:
                body = self.rfile.read(length) if length else b''
            except OSError:
                self.close_connection = True
                return self._deny(400)
            if len(body) != length:
                self.close_connection = True
                return self._deny(400)
            try:
                upstream, via, ms = self._open(host, port)
            except Exception as err:
                print(f'open {host}:{port} failed: {err}', flush=True)
                self.server.blocks += 1
                return self._deny(403 if str(err) in ('deny', 'proxy_empty') else 502)
            raw_path = urllib.parse.urlunsplit(('', '', parts.path or '/', parts.query, ''))
            headers = plain_forward_headers(self.headers)
            host_header = host if port == 80 else f'{host}:{port}'
            up = down = secs = 0
            try:
                head = (f'{self.command} {raw_path} HTTP/1.1\r\nHost: {host_header}\r\n'
                        f'Connection: close\r\n{headers}'
                        f'Content-Length: {len(body)}\r\n\r\n')
                wire = head.encode('latin-1') + body
                upstream.sendall(wire)
                up = len(wire)
                # One request per connection: stop reading the client so relay() can finish
                # as soon as the upstream response ends, instead of holding the slot for the
                # idle timeout waiting for a next request we would not forward.
                self.close_connection = True
                try:
                    self.connection.shutdown(socket.SHUT_RD)
                except OSError:
                    pass
                _up, down, secs = relay(self.connection, upstream)
                self._record_use(host, via, ms, down > 0)
                print(json.dumps({'id': next(TUNNEL_COUNTER), 'host': host, 'port': port,
                                  'via': via, 'secs': round(secs, 3), 'up': up, 'down': down}),
                      flush=True)
            except (OSError, UnicodeError) as err:
                print(f'forward http://{host}{raw_path} failed: {err}', flush=True)
                self.close_connection = True
                self._record_use(host, via, ms, False)
                try:
                    upstream.close()
                except OSError:
                    pass
        finally:
            self.server.active -= 1
            TUNNEL_SLOTS.release()

    do_GET = _forward_plain
    do_POST = _forward_plain
    do_HEAD = _forward_plain


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with a hard cap on live connections (slowloris/thread growth)."""

    connection_limit = 96

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._conn_slots = threading.BoundedSemaphore(self.connection_limit)

    def process_request(self, request, client_address):
        if not self._conn_slots.acquire(blocking=False):
            try:
                request.sendall(b'HTTP/1.1 503 Service Unavailable\r\n'
                                b'Content-Length: 0\r\nConnection: close\r\n\r\n')
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._conn_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._conn_slots.release()


class ProxyServer(BoundedThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 32
    connection_limit = MAX_CONNECTIONS

    def __init__(self, addr, pool):
        super().__init__(addr, ProxyHandler)
        self.pool = pool
        self.blocks = 0
        self.started = time.time()
        self.requests = 0   # proxy requests handled (CONNECT + absolute-URI) since start
        self.active = 0     # requests relaying right now
        self.fallbacks = {}  # host -> direct-fallback count
        self.fallbacks_lock = threading.Lock()
        self.recent = deque(maxlen=200)  # (host, via, monotonic) of pooled tunnels, for block reports
        self.recent_lock = threading.Lock()

    def remember_tunnel(self, host, via):
        with self.recent_lock:
            self.recent.append((host, via, time.monotonic()))

    def demote_recent(self, host, window=90.0):
        """Withdraw the exit that carried the most recent tunnel to `host`, or None.

        A WAF block page inside the tunnel is invisible to this proxy; the crawler reports
        it (POST /api/block) right after reading the response, so the newest tunnel to that
        host is almost always the one to blame. Direct tunnels have no exit to demote, and
        when the newest tunnel was direct the block came through it, so no older exit is blamed.
        Tunnels are remembered under the canonical host (split_target), so is the lookup.
        """
        host = canonical_host(host)
        now = time.monotonic()
        with self.recent_lock:
            candidates = [(via, at) for h, via, at in reversed(self.recent) if h == host]
        for via, at in candidates:
            if now - at > window:
                break
            if via in ('direct', 'direct-fallback'):
                return None
            try:
                self.pool.mark(via, host, False, live=False)  # host-failed: sits out its cooldown
            except Exception as err:
                print(f'block report: mark failed for {via}: {err}', flush=True)
                return None
            print(f'block report: demoted {via} for {host}', flush=True)
            return via
        return None


# -- LAN GUI -----------------------------------------------------------------
DASHBOARD = '''<!doctype html><html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' height='64' rx='14' fill='%23000'/%3E%3Crect x='13' y='16' width='38' height='35' rx='9' fill='none' stroke='%23f5f5f7' stroke-width='3.5'/%3E%3Cpath d='M13 27h38M24 11v9M40 11v9' stroke='%23f5f5f7' stroke-width='3.5' stroke-linecap='round'/%3E%3Ccircle cx='40' cy='39.5' r='4.5' fill='%230a84ff'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400..700&display=swap" rel="stylesheet">
<title>PlanWAT egress</title>
<style>
  /* the site's tokens, dark first; light restates them (auto follows the system) */
  :root {
    --bg:#000000; --s1:#111113; --s2:#1c1c1e; --s3:#2c2c2e; --s4:#3a3a3c; --s2-hover:#232326;
    --t1:#f5f5f7; --t2:#a1a1a6; --t3:#86868b; --t4:#6e6e73;
    --hl:255,255,255;
    --line:rgba(var(--hl),.08); --line-2:rgba(var(--hl),.14); --edge:inset 0 1px 0 rgba(var(--hl),.06);
    --accent:#0a84ff; --accent-text:#4da3ff; --accent-soft:rgba(10,132,255,.14); --accent-line:rgba(10,132,255,.5);
    --free:#32d74b; --busy:#ff6b63; --warn:#ffb340;
    --font:-apple-system,BlinkMacSystemFont,"SF Pro Display","SF Pro Text","Inter",system-ui,sans-serif;
    --fs-12:.75rem; --fs-13:.8125rem; --fs-15:.9375rem; --fs-17:1.0625rem; --fs-20:1.25rem; --fs-28:1.75rem;
    --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-5:24px; --sp-6:32px;
    --r-card:16px; --r-ctl:12px; --r-pill:999px;
    --ease-out:cubic-bezier(.22,1,.36,1); --dur-fast:150ms; --dur-base:300ms;
    color-scheme:dark;
  }
  :root[data-theme="light"] {
    --bg:#f2f2f7; --s1:#ffffff; --s2:#ffffff; --s3:#e9e9ee; --s4:#d8d8de; --s2-hover:#f6f6fa;
    --t1:#1c1c1e; --t2:#55555a; --t3:#6c6c70; --t4:#8e8e93; --hl:0,0,0;
    --line:rgba(0,0,0,.12); --line-2:rgba(0,0,0,.2); --edge:inset 0 1px 0 rgba(255,255,255,.8);
    --accent:#0a84ff; --accent-text:#0060df; --accent-soft:rgba(10,132,255,.12); --accent-line:rgba(10,132,255,.4);
    --warn:#a35200; --free:#1b8a35; --busy:#d2453d; color-scheme:light;
  }
  @media (prefers-color-scheme: light) {
    :root:not([data-theme="dark"]) {
      --bg:#f2f2f7; --s1:#ffffff; --s2:#ffffff; --s3:#e9e9ee; --s4:#d8d8de; --s2-hover:#f6f6fa;
      --t1:#1c1c1e; --t2:#55555a; --t3:#6c6c70; --t4:#8e8e93; --hl:0,0,0;
      --line:rgba(0,0,0,.12); --line-2:rgba(0,0,0,.2); --edge:inset 0 1px 0 rgba(255,255,255,.8);
      --accent:#0a84ff; --accent-text:#0060df; --accent-soft:rgba(10,132,255,.12); --accent-line:rgba(10,132,255,.4);
      --warn:#a35200; --free:#1b8a35; --busy:#d2453d; color-scheme:light;
    }
  }
  *,*::before,*::after { box-sizing:border-box; }
  html { background:var(--bg); -webkit-text-size-adjust:100%; text-size-adjust:100%; }
  body { margin:0; min-height:100vh; background:var(--bg); color:var(--t1); font-family:var(--font); line-height:1.45; -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale; }
  main { max-width:calc(960px + 32px); margin:0 auto; padding:40px max(16px,env(safe-area-inset-right)) 20px max(16px,env(safe-area-inset-left)); }
  h1 { margin:0; font-size:1.75rem; font-weight:700; line-height:1.1; letter-spacing:-.035em; }
  .sub { margin:2px 0 0; color:var(--t2); font-size:var(--fs-13); }
  .head { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:20px; }
  .brand { display:flex; align-items:center; gap:12px; min-width:0; }
  .brand svg { width:44px; height:44px; flex:none; border-radius:11px; }
  .pill { display:inline-flex; align-items:center; gap:8px; padding:6px 14px; border-radius:var(--r-pill); background:var(--s2); box-shadow:var(--edge),inset 0 0 0 1px var(--line); font-size:var(--fs-13); font-weight:600; white-space:nowrap; }
  .pill .dot { width:8px; height:8px; border-radius:50%; background:var(--t3); }
  .pill.rot .dot { background:var(--free); }
  .pill.dir .dot { background:var(--warn); }
  .pill.empty .dot { background:var(--busy); }
  .pill.sm { padding:2px 10px; font-size:var(--fs-12); box-shadow:none; background:var(--s3); }
  .pill.sm.rot { color:var(--free); } .pill.sm.dir { color:var(--warn); } .pill.sm.empty { color:var(--busy); } .pill.sm.dim { color:var(--t3); }
  .card { padding:var(--sp-4) var(--sp-5) var(--sp-5); border-radius:var(--r-card); background:var(--s2); box-shadow:var(--edge); margin-bottom:16px; }
  .card h2 { margin:0; font-size:var(--fs-17); font-weight:600; letter-spacing:-.012em; white-space:nowrap; }
  .card-head { display:flex; align-items:baseline; flex-wrap:wrap; gap:2px 12px; margin-bottom:12px; }
  .card-head > :not(h2) { margin-left:auto; text-align:right; }
  .dim { color:var(--t3); } .small { font-size:var(--fs-12); }
  .status { font-size:var(--fs-13); font-weight:600; color:var(--t2); }
  .status.live { color:var(--accent-text); } .status.done { color:var(--free); } .status.blocked { color:var(--busy); }
  .bigbar { height:12px; border-radius:6px; background:var(--s3); overflow:hidden; box-shadow:inset 0 0 0 1px var(--line); }
  .bigbar i { display:block; height:100%; width:0; border-radius:6px; background:var(--accent); transition:width var(--dur-base) var(--ease-out); }
  .bigbar.live i { background:linear-gradient(90deg,var(--accent),#4da3ff); }
  .bigbar.blocked i { background:var(--busy); }
  .bigbar.done i { background:var(--free); }
  .crawl-line { display:flex; align-items:baseline; flex-wrap:wrap; gap:2px 14px; margin-top:10px; font-size:var(--fs-13); color:var(--t2); font-variant-numeric:tabular-nums; }
  .crawl-line strong { font-size:var(--fs-15); font-weight:600; color:var(--t1); }
  .grow { flex:1 1 auto; }
  #crawl-eta { font-weight:600; color:var(--t1); }
  #crawl-eta.blocked { color:var(--busy); }
  #crawl-eta.done { color:var(--free); }
  .lanes { list-style:none; margin:16px 0 0; padding:12px 0 0; border-top:1px solid var(--line); display:grid; gap:8px; }
  .lane { display:grid; grid-template-columns:138px minmax(40px,1fr) minmax(0,auto); gap:12px; align-items:center; font-size:var(--fs-13); }
  .lane .lbl { display:flex; align-items:center; gap:8px; min-width:0; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-variant-numeric:tabular-nums; }
  .lane .dot { width:8px; height:8px; flex:none; border-radius:50%; background:var(--s4); }
  .lane .dot.crawling { background:var(--accent); animation:pulse 1.8s ease-in-out infinite; }
  .lane .dot.waiting { background:var(--warn); animation:pulse 1.8s ease-in-out infinite; }
  .lane .dot.blocked, .lane .dot.stalled { background:var(--busy); }
  .lane .dot.done { background:var(--free); }
  .lane .track { height:8px; border-radius:4px; background:var(--s3); overflow:hidden; }
  .lane .track i { display:block; height:100%; width:0; border-radius:4px; background:var(--t3); transition:width var(--dur-base) var(--ease-out); }
  .lane .val { color:var(--t2); font-variant-numeric:tabular-nums; white-space:nowrap; text-align:right; }
  .lane .val b { color:var(--t1); font-weight:600; }
  @keyframes pulse { 50% { opacity:.35; } }
  .grid2 { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.05fr); gap:16px; align-items:start; }
  @media (max-width:780px) { .grid2 { grid-template-columns:1fr; } .lane { grid-template-columns:112px minmax(40px,1fr) minmax(0,auto); } }
  @media (max-width:640px) {
    table.runs > thead { display:none; }
    table.runs { display:block; }
    table.runs > tbody, table.runs > tbody > tr, table.runs > tbody > tr > td { display:block; }
    table.runs > tbody > tr[hidden] { display:none; }
    table.runs > tbody > tr.runrow { padding:8px 0; border-bottom:1px solid var(--line); }
    table.runs > tbody > tr.runrow > td { border:0; padding:0; }
    table.runs > tbody > tr.runrow > td:nth-child(1) { font-size:var(--fs-12); color:var(--t2); }
    table.runs > tbody > tr.runrow > td:nth-child(2) { margin:2px 0; }
    table.runs > tbody > tr.runrow > td:nth-child(3) { margin:6px 0 2px; }
    table.runs > tbody > tr.runrow:nth-last-child(2) { border-bottom:0; }
    table.runs > tbody > tr.runrow:hover > td, table.runs > tbody > tr.runrow[aria-expanded="true"] > td { background:none; }
    table.runs > tbody > tr.runrow:hover, table.runs > tbody > tr.runrow[aria-expanded="true"] { background:var(--s2-hover); }
    .detbox { overflow-x:auto; }
    .detbox table.data { min-width:540px; }
    table.hosts col.c4, table.hosts tr > *:nth-child(4) { display:none; }
    table.pool col.c5, table.pool tr > *:nth-child(5) { display:none; }
  }
  .tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(78px,1fr)); gap:var(--sp-2); margin-bottom:12px; }
  .tile { min-width:0; padding:10px 8px; border-radius:var(--r-ctl); background:var(--s3); }
  .tile b { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:var(--fs-20); font-weight:700; letter-spacing:-.02em; font-variant-numeric:tabular-nums; }
  .tile span { display:block; font-size:var(--fs-12); color:var(--t2); hyphens:auto; -webkit-hyphens:auto; overflow-wrap:break-word; }
  table.data { width:100%; border-collapse:collapse; font-size:var(--fs-13); font-variant-numeric:tabular-nums; }
  table.data th, table.data td { padding:6px; border-bottom:1px solid var(--line); text-align:left; vertical-align:middle; }
  table.data thead th { color:var(--t2); font-weight:500; }
  table.data tbody tr:last-child td { border-bottom:0; }
  table.data.fixed { table-layout:fixed; }
  table.data .num { text-align:right; }
  table.data .ell { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  table.data th[title], table.data td[title] { cursor:help; }
  table.data.fixed th { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .scroll { max-height:300px; overflow:auto; scrollbar-gutter:stable; }
  .scroll.more { -webkit-mask-image:linear-gradient(180deg,#000 calc(100% - 20px),transparent); mask-image:linear-gradient(180deg,#000 calc(100% - 20px),transparent); }
  .scroll thead th { position:sticky; top:0; z-index:1; background:var(--s2); border-bottom:0; box-shadow:inset 0 -1px 0 var(--line); }
  .meta-warn { color:var(--warn); } .meta-bad { color:var(--busy); }
  .runrow { cursor:pointer; }
  .runrow:hover td, .runrow[aria-expanded="true"] td { background:var(--s2-hover); }
  .runrow:focus-visible { outline:2px solid var(--accent); outline-offset:-2px; }
  .chev { display:inline-block; width:0; height:0; margin-right:7px; border-left:5px solid var(--t3); border-top:4px solid transparent; border-bottom:4px solid transparent; transition:transform var(--dur-fast) var(--ease-out); vertical-align:1px; }
  .runrow[aria-expanded="true"] .chev { transform:rotate(90deg); }
  .rundet td { padding:0; background:var(--s3); }
  .detbox { padding:10px 12px 12px; }
  .det-meta { margin-bottom:8px; font-size:var(--fs-12); color:var(--t2); font-variant-numeric:tabular-nums; }
  .detbox table.data { font-size:var(--fs-12); }
  .detbox table.data th, .detbox table.data td { padding:4px 6px; }
  .chips { display:flex; flex-wrap:wrap; gap:4px; }
  .tag { display:inline-flex; align-items:center; gap:4px; padding:2px 8px; border-radius:var(--r-pill); background:var(--s3); font-size:var(--fs-12); color:var(--t2); white-space:nowrap; }
  .tag.chg { color:var(--accent-text); background:var(--accent-soft); }
  .tag.bad { color:var(--busy); background:rgba(255,107,99,.14); }
  .tag.warn { color:var(--warn); background:rgba(255,179,64,.14); }
  .banner { margin-bottom:16px; padding:12px 16px; border-radius:var(--r-card); background:var(--accent-soft); box-shadow:inset 0 0 0 1px var(--accent-line); color:var(--accent-text); font-size:var(--fs-13); font-weight:600; }
  footer { max-width:calc(960px + 32px); margin:0 auto; padding:0 max(16px,env(safe-area-inset-right)) 40px max(16px,env(safe-area-inset-left)); }
  .themerow { display:flex; justify-content:center; padding:8px 0 12px; }
  .themeswitch { display:inline-flex; gap:2px; padding:3px; border-radius:var(--r-pill); background:var(--s3); vertical-align:middle; }
  .themeswitch button { font:inherit; font-size:var(--fs-13); font-weight:600; color:var(--t2); background:none; border:0; border-radius:var(--r-pill); padding:6px 14px; min-height:32px; cursor:pointer; }
  .themeswitch button[aria-pressed="true"] { background:var(--t1); color:var(--bg); }
  .themeswitch button:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .stamp { margin:0; text-align:center; font-size:var(--fs-12); color:var(--t3); font-variant-numeric:tabular-nums; }
</style>
</head><body>
<main>
  <header class="head">
    <div class="brand">
      <svg viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="14" fill="#1c1c1e"/><rect x="13" y="16" width="38" height="35" rx="9" fill="none" stroke="#f5f5f7" stroke-width="3.5"/><path d="M13 27h38M24 11v9M40 11v9" stroke="#f5f5f7" stroke-width="3.5" stroke-linecap="round"/><circle cx="40" cy="39.5" r="4.5" fill="#0a84ff"/></svg>
      <div><h1>Egress</h1><p class="sub">rotujący proxy odświeżania planów &middot; PlanWAT</p></div>
    </div>
    <span class="pill" id="mode-pill"><i class="dot"></i><span id="mode-text">&hellip;</span></span>
  </header>

  %BANNER%

  <section class="card">
    <div class="card-head"><h2>Odświeżanie planów</h2><span class="status" id="crawl-state">wczytywanie&hellip;</span></div>
    <div class="bigbar" id="crawl-bar" role="progressbar" aria-label="postęp odświeżania" aria-valuemin="0" aria-valuemax="100"><i id="crawl-fill"></i></div>
    <div class="crawl-line"><strong id="crawl-count">&ndash;</strong><span id="crawl-sub"></span><span class="grow"></span><span id="crawl-eta"></span></div>
    <ul class="lanes" id="crawl-lanes"></ul>
  </section>

    <section class="card">
      <div class="card-head"><h2>Egress</h2><span class="dim small" id="egress-meta"></span></div>
      <div class="tiles" id="egress-tiles"></div>
    </section>

  <div class="grid2">
    <section class="card">
      <div class="card-head"><h2>Wydziały</h2><span class="dim small">weryfikacja per host</span></div>
      <table class="data fixed hosts"><colgroup><col><col style="width:132px"><col style="width:68px"><col class="c4" style="width:78px"></colgroup><thead><tr><th>host</th><th>tryb</th><th class="num" title="wyjścia potwierdzone dla tego hosta">zweryf.</th><th class="num" title="połączenia awaryjne z łącza domowego">obejścia</th></tr></thead><tbody id="hosts-rows"></tbody></table>
    </section>
    <section class="card">
      <div class="card-head"><h2>Pula proxy</h2><span class="dim small" id="pool-meta"></span></div>
      <div class="tiles" id="pool-tiles"></div>
      <div class="scroll" id="pool-scroll"><table class="data fixed pool"><colgroup><col><col style="width:64px"><col style="width:52px"><col style="width:60px"><col class="c5" style="width:92px"></colgroup><thead><tr><th>proxy</th><th>status</th><th class="num">ping</th><th class="num" title="nieudane próby dla hostów obsługiwanych przez ten wychód">pudła</th><th>źródło</th></tr></thead><tbody id="proxy-rows"></tbody></table></div>
    </section>
  </div>

  <section class="card">
    <div class="card-head"><h2>Przebiegi odświeżania</h2><span class="dim small">ostatnie 10 &middot; kliknij wiersz</span></div>
    <table class="data runs"><thead><tr><th>odebrano</th><th>start &ndash; koniec</th><th>exit</th><th>wydziały</th></tr></thead><tbody id="runs-rows"></tbody></table>
  </section>
</main>
<footer>
  <div class="themerow"><div class="themeswitch" role="group" aria-label="Motyw">
    <button type="button" data-t="auto" aria-pressed="true">Auto</button><button type="button" data-t="dark" aria-pressed="false">Ciemny</button><button type="button" data-t="light" aria-pressed="false">Jasny</button>
  </div></div>
  <p class="stamp" id="stamp">dane wczytywane&hellip;</p>
</footer>
<script id="boot" type="application/json" nonce="%NONCE%">%BOOT%</script>
<script nonce="%NONCE%">
(function () {
  'use strict';
  var boot = JSON.parse(document.getElementById('boot').textContent);
  var POLL = 4000;
  function $(id) { return document.getElementById(id); }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]; }); }
  function fmtNum(n) { return n == null ? '\u2013' : Number(n).toLocaleString('pl-PL'); }
  function fmtDur(s) {
    if (s == null || !isFinite(s)) return null;
    s = Math.max(0, Math.round(s));
    if (s < 45) return s + ' s';
    if (s < 3600) { var m = Math.max(1, Math.round(s / 60)); if (m < 60) return m + ' min'; }
    var h = Math.floor(s / 3600), m2 = Math.round((s % 3600) / 60);
    if (m2 === 60) { h += 1; m2 = 0; }
    return h + ' h' + (m2 ? ' ' + m2 + ' min' : '');
  }
  function fmtMs(ms) {
    if (ms == null) return '\u2013';
    if (ms < 1000) return fmtNum(ms) + ' ms';
    return (ms / 1000).toFixed(1).replace('.', ',') + ' s';
  }
  function clock(ep) { return ep == null ? '\u2013' : new Date(ep * 1000).toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' }); }
  function ts(iso) { if (!iso) return null; iso = String(iso); return new Date(/[zZ]$|[+-][0-9][0-9]:?([0-9][0-9])?$/.test(iso) ? iso : iso + 'Z'); }
  function isoClock(iso) { var d = ts(iso); if (!d) return '\u2013'; return isNaN(d) ? String(iso) : d.toLocaleTimeString('pl-PL', { hour: '2-digit', minute: '2-digit' }); }
  function ago(ep) {
    if (!ep) return 'nieznane';
    var d = Math.max(0, Math.floor(Date.now() / 1000 - ep));
    if (d < 60) return 'przed chwil\u0105';
    if (d < 3600) return Math.round(d / 60) + ' min temu';
    if (d < 86400) return Math.round(d / 3600) + ' h temu';
    return Math.round(d / 86400) + ' dni temu';
  }
  function nextRunAt() {
    var t = new Date(Date.now());
    t.setUTCSeconds(0); t.setUTCMilliseconds(0); t.setUTCMinutes(23);
    while (t.getTime() <= Date.now() || t.getUTCHours() % 2) t.setTime(t.getTime() + 3600000);
    return t;
  }
  function fade(el) { if (el) el.classList.toggle('more', el.scrollTop + el.clientHeight < el.scrollHeight - 2); }
  function modeClass(mode) { mode = String(mode); return mode.indexOf('ROTATING') === 0 ? 'rot' : ((mode.indexOf('DIRECT (pula') === 0 || mode.indexOf('FAIL-CLOSED') === 0) ? 'empty' : 'dir'); }
  function tile(v, l) { return '<div class="tile"><b>' + v + '</b><span>' + l + '</span></div>'; }
  function exitPill(exit) {
    if (exit == null) return '<span class="pill sm dim" title="raport bez kodu wyj\u015bcia">nieznany</span>';
    var cls = exit === 0 ? 'rot' : (exit === 3 ? 'empty' : (exit === 4 ? 'dir' : 'dim'));
    var label = exit === 0 ? 'ok' : (exit === 3 ? 'zablokowany' : (exit === 4 ? 'niekompletny' : 'exit ' + exit));
    return '<span class="pill sm ' + cls + '" title="kod wyj\u015bcia ' + esc(exit) + '">' + esc(label) + '</span>';
  }
  var SLOT = { queued: 'w kolejce', crawling: 'sprawdza', waiting: 'czeka na odblokowanie', blocked: 'zablokowany', stalled: 'brak postępu', stopped: 'przerwany', done: 'gotowe' };
  var SLOTCOLOR = { crawling: 'var(--accent)', waiting: 'var(--warn)', blocked: 'var(--busy)', stalled: 'var(--busy)', stopped: 'var(--t4)', done: 'var(--free)', queued: 'var(--s4)' };

  function renderMode(st) {
    var mode = st.mode || '?';
    $('mode-pill').className = 'pill ' + modeClass(mode);
    var label = mode;
    if (mode === 'ROTATING') label = 'tryb: rotujący';
    else if (String(mode).indexOf('DIRECT') === 0) label = 'tryb: bezpośredni' + (String(mode).indexOf('pusta') > -1 ? ' \u00b7 pula pusta' : '');
    else if (String(mode).indexOf('FAIL-CLOSED') === 0) label = 'tryb: odmowa (fail-closed) \u00b7 pula pusta';
    $('mode-text').textContent = label;
  }

  function renderCrawl(p, st) {
    var bar = $('crawl-bar'), fill = $('crawl-fill'), state = $('crawl-state');
    var count = $('crawl-count'), sub = $('crawl-sub'), eta = $('crawl-eta'), lanes = $('crawl-lanes');
    p = p || {};
    if (!p.run) {
      bar.className = 'bigbar'; fill.style.width = '0%'; bar.setAttribute('aria-valuenow', '0');
      state.className = 'status'; state.textContent = 'bez przebiegu';
      count.textContent = '';
      var nx = nextRunAt();
      sub.textContent = 'harmonogram: co 2 h \u00b7 nast\u0119pny \u2248 ' + clock(nx.getTime() / 1000)
        + ' (za ' + fmtDur((nx.getTime() - Date.now()) / 1000) + ')';
      var last = (st.runs || [])[0];
      if (last) {
        var changed = 0, blocked = 0, checked = 0, degradedN = 0, facs = last.faculties || {};
        Object.keys(facs).forEach(function (k) {
          var c = facs[k] || {};
          changed += c.changed || 0; checked += c.checked || 0;
          if (c.blocked) blocked += 1;
          if (c.degraded) degradedN += 1;
        });
        eta.className = (blocked || degradedN || last.exit === 3 || last.exit === 4) ? 'blocked' : 'done';
        eta.textContent = 'ostatni: ' + isoClock(last.started) + ' \u00b7 exit ' + (last.exit == null ? '?' : last.exit)
          + ' \u00b7 zmiany: ' + changed + (checked ? ' \u00b7 sprawdzone: ' + fmtNum(checked) : '')
          + (blocked ? ' \u00b7 zablokowane: ' + blocked : '') + (degradedN ? ' \u00b7 zdegradowane: ' + degradedN : '');
      } else { eta.textContent = ''; eta.className = ''; }
      lanes.innerHTML = '';
      return;
    }
    var pct = Math.max(0, Math.min(100, p.pct || 0));
    bar.className = 'bigbar' + (p.active ? (p.blocked ? ' blocked' : ' live') : ' done');
    fill.style.width = pct + '%';
    bar.setAttribute('aria-valuenow', String(Math.round(pct)));
    if (p.active) {
      state.className = 'status' + (p.blocked ? ' blocked' : ' live');
      state.textContent = p.stale ? 'przebieg bez wieści' : (p.waiting ? 'czekam na odblokowanie' : 'odświeżanie w toku');
    } else {
      state.className = 'status done';
      state.textContent = 'zakończony';
    }
    count.innerHTML = '<b>' + fmtNum(p.done) + ' / ' + (p.estimated ? '~' : '') + fmtNum(p.total) + '</b> grup \u00b7 ' + Math.round(pct) + '%';
    var bits = ['start ' + clock(p.started), fmtDur(p.elapsed_s) || '\u2013'];
    if (p.rate) bits.push(p.rate.toFixed(1).replace('.', ',') + ' grup/s');
    if (p.profile) bits.push(p.profile);
    bits.push('nast\u0119pny za ' + fmtDur((nextRunAt().getTime() - Date.now()) / 1000));
    sub.textContent = bits.join(' \u00b7 ');
    if (!p.active) {
      var tail = ['exit ' + p.exit];
      if (p.changed != null) tail.push('zmiany: ' + p.changed);
      if (p.blocked) tail.push('zablokowane');
      if (p.incomplete || p.degraded) tail.push('niekompletny');
      eta.className = p.blocked ? 'blocked' : 'done';
      eta.textContent = tail.join(' \u00b7 ');
    } else if (p.waiting) {
      var wf = (p.wait && p.wait.faculties) || [];
      eta.className = 'blocked';
      eta.textContent = 'wstrzymane \u2014 ' + (wf.length ? wf.map(function (f) { return f.toUpperCase(); }).join(', ') + ' czeka na odblokowanie' : 'czekam na odblokowanie');
    } else if (p.eta_s != null) {
      eta.className = '';
      eta.textContent = 'koniec \u2248 ' + clock(p.eta_at) + ' \u00b7 za ' + fmtDur(p.eta_s);
    } else if (p.stale) {
      eta.className = 'blocked';
      eta.textContent = 'brak danych od ' + fmtDur(p.updated_ago);
    } else {
      eta.className = '';
      eta.textContent = 'liczę tempo\u2026';
    }
    var html = '';
    (p.lanes || []).forEach(function (lane) {
      (lane.slots || []).forEach(function (s) {
        var label = String(s.faculty || s.slot).toUpperCase() + (s.ahead ? ' \u00b7 nadchodzący' : '');
        var spct = s.total ? Math.round(100 * s.done / s.total) : 0;
        var color = SLOTCOLOR[s.status] || 'var(--t3)';
        var val;
        if (s.status === 'queued') val = 'w kolejce';
        else if (s.status === 'waiting' || s.status === 'blocked') val = SLOT[s.status] + (s.pass > 1 ? ' (podejście ' + s.pass + ')' : '');
        else if (s.status === 'done') val = '<b>' + fmtNum(s.done) + ' / ' + fmtNum(s.total) + '</b> \u00b7 gotowe' + (s.changed ? ' \u00b7 +' + s.changed : '');
        else if (s.status === 'stopped') val = fmtNum(s.done) + ' / ' + fmtNum(s.total) + ' \u00b7 przerwany';
        else if (s.status === 'stalled') val = fmtNum(s.done) + ' / ' + fmtNum(s.total) + ' \u00b7 brak postępu od ' + fmtDur(s.updated_ago);
        else val = '<b>' + fmtNum(s.done) + ' / ' + fmtNum(s.total) + '</b>' + (s.eta_s != null ? ' \u00b7 \u2248' + fmtDur(s.eta_s) : '');
        html += '<li class="lane"><span class="lbl"><i class="dot ' + s.status + '"></i>' + esc(label) + '</span>'
             + '<span class="track" title="' + esc(SLOT[s.status] || s.status) + '"><i style="width:' + spct + '%;background:' + color + '"></i></span>'
             + '<span class="val">' + val + '</span></li>';
      });
    });
    lanes.innerHTML = html;
  }

  function renderHosts(st) {
    var rows = '';
    var hosts = st.hosts || {};
    Object.keys(hosts).forEach(function (h) {
      var v = hosts[h] || {};
      rows += '<tr><td class="ell" title="' + esc(h) + '">' + esc(h) + '</td><td><span class="pill sm ' + modeClass(v.mode) + '">' + esc(v.mode) + '</span></td><td class="num">' + fmtNum(v.verified) + '</td><td class="num">' + fmtNum(v.fallbacks) + '</td></tr>';
    });
    $('hosts-rows').innerHTML = rows || '<tr><td colspan="4" class="dim">brak hostów</td></tr>';
  }

  function renderPool(st) {
    var pool = st.pool || {}, bs = pool.by_status || {};
    $('pool-tiles').innerHTML = tile(fmtNum(pool.total), 'w puli') + tile(fmtNum(bs.ok || 0), 'zdro\u00adwych')
      + tile(fmtNum(bs.fail || 0), 'odrzu\u00adconych') + tile(fmtMs(pool.p95_ok_ms), 'p95');
    var meta = 'mediana ' + fmtMs(pool.median_ok_ms) + ' \u00b7 nowych ' + fmtNum(bs.new || 0)
      + ' \u00b7 od\u015bwie\u017cono ' + (pool.last_refresh ? new Date(pool.last_refresh * 1000).toLocaleTimeString('pl-PL') : 'nigdy')
      + ' \u00b7 obej\u015bcia ' + fmtNum(st.fallbacks_total);
    if (pool.tripped) meta += ' \u00b7 <span class="meta-bad" title="pula wstrzyma\u0142a rotacj\u0119 po serii niepowodze\u0144">przerwa</span>';
    if (pool.last_error) meta += ' \u00b7 <span class="meta-warn" title="' + esc(pool.last_error) + '">b\u0142\u0105d od\u015bwie\u017cania</span>';
    $('pool-meta').innerHTML = meta;
    var rows = '';
    (st.proxies || []).slice(0, 100).forEach(function (p) {
      var cls = p.status === 'ok' ? 'rot' : (p.status === 'fail' ? 'empty' : 'dim');
      var tip = [p.url, p.source ? 'źr\u00f3d\u0142o: ' + p.source : '',
                 p.last_checked ? 'sprawdzony ' + ago(p.last_checked) : '',
                 p.fails ? p.fails + ' nieudanych pr\u00f3b' : ''].filter(Boolean).join(' \u00b7 ');
      rows += '<tr title="' + esc(tip) + '"><td class="ell">' + esc(p.url) + '</td>'
        + '<td><span class="pill sm ' + cls + '">' + esc(p.status) + '</span></td>'
        + '<td class="num">' + (p.latency_ms ? fmtNum(p.latency_ms) : '\u2013') + '</td>'
        + '<td class="num">' + (p.fails ? fmtNum(p.fails) : '\u2013') + '</td>'
        + '<td class="ell dim" title="' + esc(p.source || '') + '">' + esc(p.source || '') + '</td></tr>';
    });
    $('proxy-rows').innerHTML = rows || '<tr><td colspan="5" class="dim">pula jest pusta</td></tr>';
    fade($('pool-scroll'));
  }

  function renderEgress(st) {
    var up = st.started ? (Date.now() / 1000 - st.started) : null;
    $('egress-tiles').innerHTML = tile(up == null ? '\u2013' : fmtDur(up), 'dzia\u0142a')
      + tile(fmtNum(st.requests), 'obs\u0142u\u017cone')
      + tile(fmtNum(st.active), 'w toku')
      + tile(fmtNum(st.denied), 'odrzucone');
    $('egress-meta').textContent = 'proxy na porcie ' + (st.proxy_port == null ? '\u2013' : st.proxy_port)
      + ' \u00b7 liczniki od startu';
  }

  function pl(n, one, few, many) {
    n = Math.abs(n || 0);
    if (n === 1) return one;
    var d = n % 10, h = n % 100;
    if (d >= 2 && d <= 4 && (h < 12 || h > 14)) return few;
    return many;
  }
  var openRuns = {};
  function runDetail(r) {
    var facs = r.faculties || {}, keys = Object.keys(facs);
    var meta = ['odebrano ' + isoClock(r.received), 'start ' + isoClock(r.started), 'koniec ' + isoClock(r.ended)];
    var d1 = ts(r.started), d2 = ts(r.ended);
    if (d1 && d2 && !isNaN(d1) && !isNaN(d2) && d2 > d1) { var dur = fmtDur((d2 - d1) / 1000); if (dur) meta.push(dur); }
    if (r.profile) meta.push(String(r.profile));
    if (r.dry_run) meta.push('pr\u00f3ba na sucho');
    meta.push('exit ' + (r.exit == null ? 'nieznany' : String(r.exit)));
    var h = '<div class="detbox"><div class="det-meta">' + esc(meta.join(' \u00b7 ')) + '</div>';
    if (!keys.length) return h + '<span class="dim">brak szczeg\u00f3\u0142\u00f3w wydzia\u0142\u00f3w</span></div>';
    h += '<table class="data"><thead><tr><th>wydzia\u0142</th><th>termin</th>'
      + '<th class="num">sprawdzone</th><th class="num">zmiany</th><th class="num">pomini\u0119te</th><th class="num">niegotowe</th>'
      + '<th>stan</th><th>czeka\u0142</th><th>kiedy</th></tr></thead><tbody>';
    keys.forEach(function (k) {
      var c = facs[k] || {}, st2 = [];
      if (c.blocked) st2.push('<span class="tag bad">zablokowany' + (c.cause ? ' (' + esc(c.cause) + ')' : '') + '</span>');
      if (c.degraded) st2.push('<span class="tag warn">zdegradowany' + (c.cause && !c.blocked ? ' (' + esc(c.cause) + ')' : '') + '</span>');
      if (c.ahead) st2.push('<span class="tag">nadchodz\u0105cy</span>');
      if (!st2.length) st2.push('<span class="tag">ok</span>');
      var wait = c.wait ? fmtDur(c.wait.waited) + ' (' + fmtNum(c.wait.probes) + ' ' + pl(c.wait.probes, 'pr\u00f3ba', 'pr\u00f3by', 'pr\u00f3b') + (c.wait.recovered ? ', wr\u00f3ci\u0142' : '') + ')' : '\u2013';
      h += '<tr><td><b>' + esc(k.toUpperCase()) + '</b></td><td class="dim">' + esc(c.term || '\u2013') + '</td>'
        + '<td class="num">' + fmtNum(c.checked) + '</td>'
        + '<td class="num">' + (c.changed ? '<b>' + fmtNum(c.changed) + '</b>' : '0') + '</td>'
        + '<td class="num">' + (c.skipped ? fmtNum(c.skipped) : '0') + '</td>'
        + '<td class="num">' + (c.not_ready ? fmtNum(c.not_ready) : '0') + '</td>'
        + '<td>' + st2.join(' ') + '</td>'
        + '<td>' + wait + '</td>'
        + '<td class="dim">' + esc(isoClock(c.at)) + '</td></tr>';
    });
    return h + '</tbody></table></div>';
  }

  function renderRuns(st) {
    var rows = '';
    (st.runs || []).forEach(function (r, i) {
      var tags = '', checked = 0, skipped = 0;
      var facs = r.faculties || {};
      Object.keys(facs).forEach(function (k) {
        var c = facs[k] || {};
        checked += c.checked || 0; skipped += c.skipped || 0;
        var cls = c.blocked ? 'bad' : (c.degraded ? 'warn' : (c.changed ? 'chg' : ''));
        var tip = k.toUpperCase() + (c.term ? ' \u00b7 termin ' + c.term : '')
          + ' \u00b7 sprawdzone: ' + (c.checked == null ? '?' : c.checked)
          + ' \u00b7 zmiany: ' + (c.changed || 0)
          + (c.skipped ? ' \u00b7 pomini\u0119te: ' + c.skipped : '')
          + (c.not_ready ? ' \u00b7 niegotowe: ' + c.not_ready : '')
          + (c.blocked ? ' \u00b7 zablokowany' + (c.cause ? ' (' + c.cause + ')' : '') : '')
          + (c.degraded ? ' \u00b7 zdegradowany' + (!c.blocked && c.cause ? ' (' + c.cause + ')' : '') : '')
          + (c.ahead ? ' \u00b7 nadchodz\u0105cy semestr' : '')
          + (c.wait ? ' \u00b7 czeka\u0142 ' + fmtDur(c.wait.waited) + (c.wait.recovered ? ' (wr\u00f3ci\u0142)' : '') : '')
          + (c.at ? ' \u00b7 o ' + isoClock(c.at) : '');
        tags += '<span class="tag ' + cls + '" title="' + esc(tip) + '">' + esc(k.toUpperCase()) + (c.changed ? ' +' + esc(fmtNum(c.changed)) : '') + (c.blocked ? ' \u26d4' : '') + (c.degraded ? ' \u26a0' : '') + '</span>';
      });
      var d1 = ts(r.started), d2 = ts(r.ended);
      var bits = [];
      if (d1 && d2 && !isNaN(d1) && !isNaN(d2) && d2 > d1) { var dur = fmtDur((d2 - d1) / 1000); if (dur) bits.push(dur); }
      if (checked) bits.push(fmtNum(checked) + ' ' + pl(checked, 'sprawdzony', 'sprawdzone', 'sprawdzonych'));
      if (skipped) bits.push(fmtNum(skipped) + ' ' + pl(skipped, 'pomini\u0119ty', 'pomini\u0119te', 'pomini\u0119tych'));
      var span = esc(isoClock(r.started)) + ' \u2013 ' + esc(isoClock(r.ended))
        + (bits.length ? ' <span class="dim">\u00b7 ' + esc(bits.join(' \u00b7 ')) + '</span>' : '');
      var key = esc(r.received || 'i' + i);
      var open = openRuns[key] ? ' aria-expanded="true"' : ' aria-expanded="false"';
      rows += '<tr class="runrow" data-key="' + key + '" tabindex="0" role="button"' + open + ' title="kliknij, aby rozwin\u0105\u0107 szczeg\u00f3\u0142y"><td><span class="chev"></span>' + esc(isoClock(r.received)) + '</td><td>' + span + '</td><td>' + exitPill(r.exit) + '</td><td><span class="chips">' + (tags || '<span class="dim">\u2013</span>') + '</span></td></tr>'
        + '<tr class="rundet" id="rundet-' + key + '"' + (openRuns[key] ? '' : ' hidden') + '><td colspan="4">' + runDetail(r) + '</td></tr>';
    });
    $('runs-rows').innerHTML = rows || '<tr><td colspan="4" class="dim">brak przebieg\u00f3w</td></tr>';
  }

  function render(st) {
    renderMode(st);
    renderCrawl(st.progress || {}, st);
    renderHosts(st);
    renderPool(st);
    renderEgress(st);
    renderRuns(st);
  }

  var poolScroll = $('pool-scroll');
  if (poolScroll) poolScroll.addEventListener('scroll', function () { fade(poolScroll); });
  if (window.addEventListener) window.addEventListener('resize', function () { fade(poolScroll); });

  var runsBody = $('runs-rows');
  function runRowOf(node) {
    while (node && node !== runsBody) {
      if (String(node.className || '').indexOf('runrow') > -1) return node;
      node = node.parentNode;
    }
    return null;
  }
  function toggleRun(tr) {
    var key = tr.getAttribute('data-key'), det = $('rundet-' + key);
    if (!det) return;
    det.hidden = !det.hidden;
    tr.setAttribute('aria-expanded', String(!det.hidden));
    if (det.hidden) delete openRuns[key]; else openRuns[key] = true;
  }
  if (runsBody) {
    runsBody.addEventListener('click', function (ev) { var tr = runRowOf(ev.target); if (tr) toggleRun(tr); });
    runsBody.addEventListener('keydown', function (ev) {
      if (ev.key !== 'Enter' && ev.key !== ' ') return;
      var tr = runRowOf(ev.target);
      if (tr) { ev.preventDefault(); toggleRun(tr); }
    });
  }

  render(boot);
  function poll() {
    fetch('/api/status', { cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (st) { if (st && st.auth === 'required') { location.reload(); return; } $('stamp').textContent = 'aktualizacja ' + new Date().toLocaleTimeString('pl-PL'); render(st); })
      .catch(function () { $('stamp').textContent = 'brak połączenia \u2014 ponawiam\u2026'; })
      .then(function () { setTimeout(poll, POLL); });
  }
  setTimeout(poll, POLL);

  (function () {
    var root = document.documentElement;
    function stored() { try { var t = window.localStorage.getItem('planwat:theme'); return (t === 'light' || t === 'dark') ? t : 'auto'; } catch (e) { return 'auto'; } }
    function apply(t) {
      if (t === 'auto') root.removeAttribute('data-theme'); else root.setAttribute('data-theme', t);
      var btns = document.querySelectorAll('.themeswitch button');
      for (var i = 0; i < btns.length; i++) btns[i].setAttribute('aria-pressed', String(btns[i].getAttribute('data-t') === t));
    }
    var btns = document.querySelectorAll('.themeswitch button');
    for (var i = 0; i < btns.length; i++) {
      (function (b) { b.addEventListener('click', function () { var t = b.getAttribute('data-t'); try { window.localStorage.setItem('planwat:theme', t); } catch (e) {} apply(t); }); })(btns[i]);
    }
    apply(stored());
  })();
})();
</script>
</body></html>'''


def _live(server):
    """The server's LiveRun, made on first use so every test harness works untouched."""
    live = getattr(server, 'live', None)
    if live is None:
        live = server.live = LiveRun()
    return live


def dashboard(status, nonce=''):
    """The GUI shell with the first snapshot baked in (instant paint) and the page escaping-safe."""
    banner = ('<div class="banner">przebieg w toku — raport otwarty (bez postępu na żywo)</div>'
              if status.get('open_runs') else '')
    boot = json.dumps(status, ensure_ascii=False).replace('<', '\\u003c')
    # Banner and nonce first, BOOT last: replacing it first would also rewrite a literal
    # %BANNER%/%NONCE% inside crawler-provided run data and corrupt the baked JSON.
    template = DASHBOARD.replace('%BANNER%', banner).replace('%NONCE%', nonce)
    return template.replace('%BOOT%', boot)


def api_token():
    """EGRESS_API_TOKEN; surrounding whitespace (a quoted .env value) is not part of it — the
    crawler strips it before sending, so a padded value here would refuse every report."""
    return env('EGRESS_API_TOKEN', '').strip()


def _wants_auth():
    return bool(api_token())


GUI_COOKIE = 'egress_session'
LOGIN_BODY_CAP = 4096


def gui_session(token):
    """The panel's browser cookie for `token`: derived, so the cookie never holds the API secret."""
    return hmac.new(token.encode('utf-8', 'replace'), b'planwat-egress-gui', 'sha256').hexdigest()


LOGIN_PAGE = '''<!doctype html><html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light"><title>PlanWAT egress</title>
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:22rem;margin:15vh auto;padding:0 16px}
input,button{font:inherit;padding:8px 12px;margin-top:8px;width:100%;box-sizing:border-box}
.err{color:#d2453d}</style></head><body>
<h1>PlanWAT egress</h1><p>Panel wymaga tokenu API (<code>EGRESS_API_TOKEN</code>).</p>%ERROR%
<form method="post" action="/login"><input type="password" name="token" aria-label="token API"
autocomplete="current-password" required autofocus><button type="submit">Wejdź</button></form>
</body></html>'''
LOGIN_CSP = ("default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; "
             "base-uri 'none'; frame-ancestors 'none'")


class GuiHandler(BaseHTTPRequestHandler):
    server_version = 'PlanWAT-Egress-GUI/1'
    timeout = 30

    def _send(self, body, ctype='application/json', code=200, csp=None, extra=None):
        data = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Cache-Control', 'no-store')
        if csp:
            self.send_header('Content-Security-Policy', csp)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        try:
            self.wfile.write(data)
        except OSError:
            pass

    def _check_token(self, cookie=False):
        """Accept `X-Token: <token>` or `Authorization: Bearer <token>` (constant time).

        With `cookie`, a browser that signed in (POST /login) also passes on its session
        cookie — for reads only: the POST API never takes a cookie, so no other page can
        ride a signed-in browser into it.
        """
        want = api_token()
        if not want:
            return True
        got = self.headers.get('X-Token') or ''
        auth = self.headers.get('Authorization') or ''
        if auth[:7].lower() == 'bearer ':
            got = auth[7:].strip()
        # Compare bytes: a non-ASCII header value must read as "wrong token", not raise.
        if hmac.compare_digest(got.encode('utf-8', 'replace'), want.encode('utf-8', 'replace')):
            return True
        if not cookie:
            return False
        jar = SimpleCookie()
        try:
            jar.load(self.headers.get('Cookie') or '')
        except CookieError:
            return False
        morsel = jar.get(GUI_COOKIE)
        return morsel is not None and hmac.compare_digest(
            morsel.value.encode('utf-8', 'replace'), gui_session(want).encode('ascii'))

    def _login_page(self, error='', code=200):
        note = f'<p class="err">{error}</p>' if error else ''
        return self._send(LOGIN_PAGE.replace('%ERROR%', note), 'text/html', code=code, csp=LOGIN_CSP)

    def _login(self):
        """Browser sign-in for the panel: the token in a form body, a derived session cookie back."""
        want = api_token()
        if not want:
            return self._send(b'', 'text/plain', code=303, extra={'Location': '/'})
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= LOGIN_BODY_CAP:
            self.close_connection = True
            return self._send('{"error":"bad length"}', code=400)
        try:
            body = self.rfile.read(length) if length else b''
        except OSError:
            self.close_connection = True
            return self._send('{"error":"bad length"}', code=400)
        got = (urllib.parse.parse_qs(body.decode('utf-8', 'replace')).get('token') or [''])[0].strip()
        if not hmac.compare_digest(got.encode('utf-8', 'replace'), want.encode('utf-8', 'replace')):
            return self._login_page('Zły token.', code=401)
        cookie = f'{GUI_COOKIE}={gui_session(want)}; Path=/; HttpOnly; SameSite=Strict'
        return self._send(b'', 'text/plain', code=303, extra={'Location': '/', 'Set-Cookie': cookie})

    def _read_body(self):
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except ValueError:
            return None
        if length < 0:
            return None
        if length > GUI_BODY_CAP:
            raise OverflowError
        if not length:
            return b''
        try:
            return self.rfile.read(length)
        except OSError:
            return None  # timed out mid-body: the caller answers 400 and drops the connection

    def status(self):
        pool, runs = self.server.pool, self.server.runs
        stats = pool.stats()
        with pool.lock:
            proxies = sorted(({'url': u, **e} for u, e in pool.entries.items()),
                             key=lambda e: (e.get('latency_ms') or 10 ** 9))
        verified_total = sum(stats.get('verified', {}).values())
        if not getattr(pool, 'enabled', True):
            mode = 'DIRECT (wszystkie hosty)'
        elif verified_total > 0:
            mode = 'ROTATING'
        elif any(not falls_back_direct(h) for h in getattr(pool, 'active_hosts', ())):
            mode = 'FAIL-CLOSED (pula pusta)'  # a pooled host with no exit is refused, not sent direct
        else:
            mode = 'DIRECT (pula pusta)'
        lock = getattr(self.server.proxy_server, 'fallbacks_lock', None)
        if lock is not None:
            with lock:
                fallbacks = dict(self.server.proxy_server.fallbacks)
        else:
            fallbacks = dict(getattr(self.server.proxy_server, 'fallbacks', {}))
        host_modes = {}
        for h in self.server.pool.round2:
            n = stats.get('verified', {}).get(h, 0)
            if route(h) == 'direct':
                host_mode = 'DIRECT (lista)' if host_is_direct(h) else 'DIRECT (bez puli)'
            elif n:
                host_mode = 'ROTATING'
            else:
                # No exit: either this box's own line carries it, or every request gets a 403.
                host_mode = 'DIRECT' if falls_back_direct(h) else 'FAIL-CLOSED'
            host_modes[h] = {'mode': host_mode, 'verified': n, 'fallbacks': fallbacks.get(h, 0)}
        open_runs = (runs.open_snapshot() if hasattr(runs, 'open_snapshot')
                     else list(getattr(runs, 'open_runs', [])))
        ps = self.server.proxy_server
        return {'mode': mode, 'proxy_port': self.server.proxy_port,
                'started': getattr(ps, 'started', None),
                'requests': getattr(ps, 'requests', 0),
                'active': getattr(ps, 'active', 0),
                'pool': stats,
                'fallbacks': fallbacks, 'fallbacks_total': sum(fallbacks.values()),
                'hosts': host_modes,
                'denied': getattr(ps, 'blocks', 0),
                'open_runs': open_runs,
                'progress': _live(self.server).snapshot(),
                'proxies': [{'url': p['url'], 'status': p.get('status', 'new'),
                             'latency_ms': p.get('latency_ms'), 'source': p.get('source', ''),
                             'fails': p.get('fails', 0), 'last_checked': p.get('last_checked')}
                            for p in proxies[:200]],
                'runs': runs.runs[::-1][:10]}

    def do_GET(self):
        # With a token set, reads need it too (header, or the panel's session cookie).
        authed = self._check_token(cookie=True)
        if self.path == '/api/status':
            if not authed:
                # Liveness only: healthchecks and probes keep their 200 without holding the
                # secret, while the pool, its exits and the runs stay behind the token.
                return self._send('{"ok":true,"auth":"required"}')
            return self._send(json.dumps(self.status(), ensure_ascii=False))
        if self.path == '/api/progress':
            if not authed:
                return self._send('{"error":"unauthorized"}', code=401)
            return self._send(json.dumps(_live(self.server).snapshot(), ensure_ascii=False))
        if self.path in ('/', '/index.html'):
            if not authed:
                return self._login_page()
            nonce = secrets.token_urlsafe(18)
            csp = ("default-src 'none'; script-src 'nonce-{n}'; "
                   "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                   "font-src https://fonts.gstatic.com; img-src 'self' data:; "
                   "connect-src 'self'; base-uri 'none'; form-action 'none'; "
                   "frame-ancestors 'none'").format(n=nonce)
            return self._send(dashboard(self.status(), nonce), 'text/html', csp=csp)
        return self._send('{"error":"not found"}', code=404)

    def do_POST(self):
        if self.path == '/login':
            return self._login()  # the body is the credential, so it is read before any check
        if self.path not in ('/api/run', '/api/progress', '/api/block', '/api/refresh'):
            self.close_connection = True  # a body may be waiting unread
            return self._send('{"error":"not found"}', code=404)
        # Authenticate before reading a single body byte: an unauthenticated client
        # must not be able to make the GUI allocate or wait on its payload.
        if not self._check_token():
            self.close_connection = True
            return self._send('{"error":"unauthorized"}', code=401)
        try:
            body = self._read_body()
        except OverflowError:
            self.close_connection = True  # the unread body would poison keep-alive
            return self._send('{"error":"body too large"}', code=413)
        if body is None:
            self.close_connection = True
            return self._send('{"error":"bad length"}', code=400)
        if self.path == '/api/run':
            try:
                report = json.loads(body.decode('utf-8'))
            except ValueError:
                return self._send('{"error":"bad json"}', code=400)
            if not isinstance(report, dict):
                return self._send('{"error":"bad json"}', code=400)
            return self._send(json.dumps(self.server.runs.add(report), ensure_ascii=False))
        if self.path == '/api/progress':
            try:
                event = json.loads(body.decode('utf-8'))
            except ValueError:
                return self._send('{"error":"bad json"}', code=400)
            ack = _live(self.server).event(event)
            if ack is None:
                return self._send('{"ok":false,"ignored":true}')  # a straggler of an older run
            return self._send(json.dumps(ack))
        if self.path == '/api/block':
            try:
                report = json.loads(body.decode('utf-8'))
            except ValueError:
                return self._send('{"error":"bad json"}', code=400)
            host = canonical_host(str(report.get('host') or '')) if isinstance(report, dict) else ''
            if not host:
                return self._send('{"error":"bad json"}', code=400)
            demoted = self.server.proxy_server.demote_recent(host)
            return self._send(json.dumps({'demoted': demoted}))
        # /api/refresh
        pool = self.server.pool
        if not getattr(pool, 'enabled', True):
            # Every host goes direct: no maintainer runs, so a 202 would promise work nobody does.
            return self._send('{"error":"pool-disabled"}', code=409)
        lock = getattr(pool, '_refresh_lock', None)
        if lock is not None:
            if lock.locked() or getattr(pool, 'force_refresh', False):
                return self._send('{"error":"already-running"}', code=409)
            pool.force_refresh = True
            try:
                pool.heal_event.set()
            except Exception:
                pass
            return self._send('{"started":true}', code=202)
        threading.Thread(target=self.server.pool.refresh, daemon=True).start()
        return self._send('{"started":true}', code=202)


class GuiServer(BoundedThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 32
    connection_limit = 32


def maintain_once(pool):
    """One needs_refresh-gated refresh cycle. Returns a status string."""
    force = bool(getattr(pool, 'force_refresh', False))
    if not force:
        try:
            if not pool.needs_refresh():
                return 'fresh'
        except Exception:
            return 'fresh'
    try:
        pool.force_refresh = False
    except Exception:
        pass
    lock = getattr(pool, '_refresh_lock', None)
    if lock is not None:
        if not lock.acquire(blocking=False):
            try:
                pool.force_refresh = True
            except Exception:
                pass
            return 'already-running'
        try:
            alive, tried, verified = pool.refresh()
            return (f'pool refresh: {alive}/{tried} healthy, {verified} verified, '
                    f'{len(pool.entries)} known')
        except Exception as err:
            return f'pool refresh failed: {err}'
        finally:
            lock.release()
    try:
        alive, tried, verified = pool.refresh()
        return (f'pool refresh: {alive}/{tried} healthy, {verified} verified, '
                f'{len(pool.entries)} known')
    except Exception as err:
        return f'pool refresh failed: {err}'


def maintain_wait(pool, interval, now=None):
    """Seconds until the next maintenance pass.

    A failed list fetch sets `retry_after` (five minutes), which is shorter than the normal
    ten-minute interval; honour it instead of sleeping past the retry window.
    """
    now = time.time() if now is None else now
    try:
        retry = float(getattr(pool, 'retry_after', 0) or 0)
    except (TypeError, ValueError):
        retry = 0.0
    if retry > now:
        return max(5.0, min(float(interval), retry - now))
    return float(interval)


def maintain(pool, interval=600):
    """Seed on start, then refresh when stale — the cron/proxy_heal.php equivalent.

    Waits on pool.heal_event (heal-kick / manual trigger) with `interval` timeout;
    pool.force_refresh is consumed per cycle so POST /api/refresh wakes it promptly.
    """
    while True:
        try:
            msg = maintain_once(pool)
            if msg and msg not in ('fresh',):
                print(msg, flush=True)
        except Exception as err:
            print(f'pool refresh failed: {err}', flush=True)
        wait = maintain_wait(pool, interval)
        try:
            evt = getattr(pool, 'heal_event', None)
            if evt is not None:
                evt.wait(timeout=wait)
                try:
                    evt.clear()
                except Exception:
                    pass
            else:
                time.sleep(wait)
        except Exception:
            time.sleep(wait)


def main():
    data = Path(env('EGRESS_DATA', '/data'))
    targets = faculty_targets()
    # The GUI still lists every faculty host, but only hosts that actually ride the pool
    # are probed/refreshed. A volunteer deployment (EGRESS_POOL=off) performs no pool work
    # at all, whatever faculty_targets() grows to.
    active = [] if POOL_OFF else [h for h in targets if route(h) == 'chain']
    for h in targets:
        if host_is_direct(h) and fail_closed_listed(h):
            print(f'WARNING: {h} is on EGRESS_DIRECT_FACULTY and EGRESS_FAIL_CLOSED; '
                  f'fail-closed wins: it stays on the pool and never goes direct', flush=True)
    pool = ProxyPool(data / 'pool.json', targets, active_hosts=active,
                     max_probe=env_int('EGRESS_MAX_PROBE', 240))
    runs = RunLog(data / 'runs.json')
    proxy_port = env_int('EGRESS_PROXY_PORT', 8888)
    gui_port = env_int('EGRESS_GUI_PORT', 8080)
    proxy_server = ProxyServer(('0.0.0.0', proxy_port), pool)
    gui = GuiServer(('0.0.0.0', gui_port), GuiHandler)
    if not api_token():
        print(f'WARNING: EGRESS_API_TOKEN is empty: the GUI API on :{gui_port} is open to anyone '
              f'who reaches it; fine only while its host port is bound to localhost', flush=True)
    gui.pool, gui.runs, gui.proxy_server, gui.proxy_port = pool, runs, proxy_server, proxy_port
    gui.live = LiveRun()
    if pool.enabled:
        threading.Thread(target=maintain, args=(pool,), daemon=True).start()
    threading.Thread(target=gui.serve_forever, daemon=True).start()
    print(f'egress proxy on :{proxy_port}, GUI on :{gui_port} (pool={len(pool.entries)} known, '
          f'{len(active)} pooled host(s))', flush=True)
    try:
        proxy_server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
