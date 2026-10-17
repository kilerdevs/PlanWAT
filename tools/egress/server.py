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
instead of ROTATING. Set it to 0 for DeadDropMGMT-style fail-closed.

Ports: 8888 forward proxy (inner network only), 8080 read-only status GUI + run
reports (LAN). The runner POSTs a run summary to /api/run after each refresh and,
whenever a faculty answers with a block page through a pooled exit, a block notice
to /api/block — the crawler sees what the CONNECT tunnel hides, so the proxy can
demote that exit (see ProxyServer.demote_recent); the GUI shows pool health, mode,
and the last runs side by side.

Threat model (unchanged from tinyproxy): job code on the runner is untrusted, so
this proxy never fetches an arbitrary host on a job's behalf — routing above is
the whole policy, CONNECT is limited to port 443, plain HTTP to port 80.
"""
import itertools
import json
import os
import re
import socket
import struct
import threading
import time
import urllib.parse
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pool import ProxyPool

HERE = Path(__file__).resolve().parent


def env(name, default):
    return os.environ.get(name, default)


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

CONNECT_TIMEOUT = 10
TUNNEL_IDLE = 120
BUF = 65536
CONNECT_HEAD_CAP = 32 * 1024
RELAY_CAP_S = 600
TUNNEL_SLOTS = threading.BoundedSemaphore(64)
TUNNEL_COUNTER = itertools.count(1)
CONNECT_STATUS_RE = re.compile(br'^HTTP/1\.[01] 200')


def faculty_targets(season=None):
    """Round-2 verification targets: each chain host's own index page + content marker.

    XML indexes must start with <?xml; the HTML ones (WCY Drupal, WML landing) only
    need a healthy 200 with a body (marker None). IOE's index only exists for lato.
    """
    season = season or env('EGRESS_SEASON', 'zima')
    xml = b'<?xml'
    return {
        'wlo.wat.edu.pl': (f'https://wlo.wat.edu.pl/planyzajec/{season}/index.xml', xml),
        'wel.wat.edu.pl': (f'https://wel.wat.edu.pl/planyzajec/{season}/index.xml', xml),
        'www.wim.wat.edu.pl': (f'https://www.wim.wat.edu.pl/wp-content/uploads/rozklady/{season}/index.xml', xml),
        'ioe.wat.edu.pl': ('https://ioe.wat.edu.pl/plany/lato/index.xml', xml),
        'planzajec.wcy.wat.edu.pl': ('https://planzajec.wcy.wat.edu.pl/pl/rozklad', None),
        'wml.wat.edu.pl': ('https://wml.wat.edu.pl/rozklady-zajec/', None),
        'wtc.wat.edu.pl': ('https://wtc.wat.edu.pl/Plany/index.xml', xml),
    }


def host_is_direct(host):
    """True when `host` is on the EGRESS_DIRECT_FACULTY list."""
    h = (host or '').lower().rstrip('.')
    return any(h == s or h.endswith('.' + s) for s in DIRECT_FACULTY)


def route(host):
    """'direct' | 'chain' | 'deny' for a destination hostname."""
    h = (host or '').lower().rstrip('.')
    if not h or h in ('localhost',) or h.startswith('127.') or h == '::1':
        return 'deny'
    if h in DIRECT_EXACT or any(h == s or h.endswith('.' + s) for s in DIRECT_SUFFIXES):
        return 'direct'
    if host_is_direct(h):
        return 'direct'
    if any(h == s or h.endswith('.' + s) for s in CHAIN_SUFFIXES):
        return 'chain'
    return 'deny'


def split_target(target):
    """('host', port) from CONNECT 'host:port'. None when malformed or off-limits."""
    if not target or '@' in target or '/' in target:
        return None
    host, _, port = target.rpartition(':')
    if not host or not port.isdigit():
        return None
    port = int(port)
    if port not in (80, 443):
        return None
    return host, port


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


def chain_connect(proxy_url, host, port, timeout=CONNECT_TIMEOUT):
    """Open `host:port` *through* the public proxy. Returns the tunnelled socket."""
    try:
        hb = host.encode('idna')
    except Exception:
        raise OSError('bad hostname')
    if len(hb) > 255:
        raise OSError('hostname too long')
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
            _recv_exact(sock, {1: 6, 3: 1}[atyp] if atyp in (1, 3) else 18, timeout)
            if atyp == 3:
                _recv_exact(sock, _recv_exact(sock, 1, timeout)[0] + 2, timeout)
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


def relay(a, b, cap=RELAY_CAP_S):
    """Copy both ways, joining the copy threads (cap `cap` s). Returns (up, down, secs).

    up = bytes a->b, down = bytes b->a.
    """
    start = time.monotonic()
    counts = [0, 0]
    for s in (a, b):
        try:
            s.settimeout(None)
        except OSError:
            pass

    def _copy(src, dst, idx):
        try:
            while True:
                try:
                    chunk = src.recv(BUF)
                except OSError:
                    break
                if not chunk:
                    break
                try:
                    dst.sendall(chunk)
                except OSError:
                    break
                counts[idx] += len(chunk)
        finally:
            for s in (a, b):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    threads = [threading.Thread(target=_copy, args=(a, b, 0), daemon=True),
               threading.Thread(target=_copy, args=(b, a, 1), daemon=True)]
    for t in threads:
        t.start()
    deadline = start + cap
    for t in threads:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        t.join(timeout=remaining)
    for s in (a, b):
        try:
            s.close()
        except OSError:
            pass
    return counts[0], counts[1], time.monotonic() - start


# -- run reports -----------------------------------------------------------
class RunLog:
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
                    self.open_runs = opened[-cap:]
        except (OSError, ValueError):
            pass

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


# -- forward proxy ----------------------------------------------------------
class ProxyHandler(BaseHTTPRequestHandler):
    server_version = 'PlanWAT-Egress/1'
    protocol_version = 'HTTP/1.1'

    def log_message(self, *args):  # keep docker logs to one line per tunnel, not per chunk
        pass

    def _deny(self, code=403):
        if code == 403:
            body = b'filtered domain'
        elif code == 503:
            body = b'slot exhausted'
        else:
            body = b'bad request'
        self.send_response(code)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except OSError:
            pass

    def _open(self, host, port):
        """(socket, via) to host:port per routing policy. Raises OSError when denied."""
        import time as _time
        policy = route(host)
        if policy == 'deny' or port not in (80, 443):
            raise OSError('deny')
        if policy == 'direct':
            return socket.create_connection((host, port), timeout=CONNECT_TIMEOUT), 'direct'
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
            except Exception as err:
                print(f'chain via {proxy} failed: {err}', flush=True)
                try:
                    self.server.pool.mark(proxy, host, False, live=True)  # dead for this host
                except Exception as merr:
                    print(f'mark fail failed: {merr}', flush=True)
                continue
            ms = int((_time.monotonic() - start) * 1000)
            try:
                self.server.pool.mark(proxy, host, True, ms, live=True)  # verified by real use
            except Exception as merr:
                print(f'mark ok failed: {merr}', flush=True)
            try:
                self.server.remember_tunnel(host, proxy)
            except Exception as merr:
                print(f'remember tunnel failed: {merr}', flush=True)
            return sock, proxy
        return self._fallback(host, port)

    def _fallback(self, host, port):
        if env('PLANWAT_EGRESS_DIRECT_FALLBACK', '1') in ('1', 'true', 'yes'):
            lock = getattr(self.server, 'fallbacks_lock', None)
            if lock is not None:
                with lock:
                    self.server.fallbacks[host] = self.server.fallbacks.get(host, 0) + 1
            else:
                self.server.fallbacks[host] = self.server.fallbacks.get(host, 0) + 1
            return socket.create_connection((host, port), timeout=CONNECT_TIMEOUT), 'direct-fallback'
        raise OSError('proxy_empty')

    def do_CONNECT(self):
        if not TUNNEL_SLOTS.acquire(blocking=False):
            return self._deny(503)
        try:
            target = split_target(self.path)
            if target is None:
                return self._deny(400)
            host, port = target
            try:
                upstream, via = self._open(host, port)
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
            peer = self.connection
            try:
                up, down, secs = relay(peer, upstream)
            except Exception as err:
                print(f'relay {host}:{port} failed: {err}', flush=True)
                up, down, secs = 0, 0, 0.0
            print(json.dumps({'id': next(TUNNEL_COUNTER), 'host': host, 'port': port,
                              'via': via, 'secs': round(secs, 3), 'up': up, 'down': down}),
                  flush=True)
        finally:
            TUNNEL_SLOTS.release()

    def _forward_plain(self):
        if not TUNNEL_SLOTS.acquire(blocking=False):
            return self._deny(503)
        try:
            parts = urllib.parse.urlsplit(self.path)
            if parts.scheme not in ('http',) or not parts.hostname:
                return self._deny(400)  # only absolute-URI forwarding; origin-form is a client bug
            host, port = parts.hostname, parts.port or 80
            try:
                upstream, via = self._open(host, port)
            except Exception as err:
                print(f'open {host}:{port} failed: {err}', flush=True)
                self.server.blocks += 1
                return self._deny(403 if str(err) in ('deny', 'proxy_empty') else 502)
            raw_path = urllib.parse.urlunsplit(('', '', parts.path or '/', parts.query, ''))
            headers = ''.join(f'{k}: {v}\r\n' for k, v in self.headers.items()
                              if k.lower() not in ('proxy-connection', 'connection'))
            try:
                upstream.sendall(f'{self.command} {raw_path} HTTP/1.1\r\nHost: {host}\r\n'
                                f'Connection: close\r\n{headers}\r\n'.encode('latin-1'))
                if self.command in ('POST', 'PUT', 'PATCH'):
                    length = int(self.headers.get('Content-Length') or 0)
                    if length:
                        upstream.sendall(self.rfile.read(length))
                try:
                    up, down, secs = relay(self.connection, upstream)
                except Exception as err:
                    print(f'relay http://{host}{raw_path} failed: {err}', flush=True)
                    up, down, secs = 0, 0, 0.0
                print(json.dumps({'id': next(TUNNEL_COUNTER), 'host': host, 'port': port,
                                  'via': via, 'secs': round(secs, 3), 'up': up, 'down': down}),
                      flush=True)
            except OSError as err:
                print(f'forward http://{host}{raw_path} failed: {err}', flush=True)
                try:
                    upstream.close()
                except OSError:
                    pass
        finally:
            TUNNEL_SLOTS.release()

    do_GET = _forward_plain
    do_POST = _forward_plain
    do_HEAD = _forward_plain


class ProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 32

    def __init__(self, addr, pool):
        super().__init__(addr, ProxyHandler)
        self.pool = pool
        self.blocks = 0
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
        host is almost always the one to blame. Direct tunnels have no exit to demote.
        """
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
<meta http-equiv="refresh" content="30">
<title>PlanWAT egress</title>
<style>body{font-family:system-ui,sans-serif;max-width:960px;margin:2em auto;padding:0 1em;color:#222}
.mode{font-size:1.4em;font-weight:700}.rot{color:#0a7d2c}.dir{color:#b35400}
table{border-collapse:collapse;width:100%;margin:1em 0}td,th{border:1px solid #ccc;padding:.35em .6em;text-align:left;font-size:.9em}
.ok{color:#0a7d2c}.fail{color:#a00}.new{color:#666}.small{color:#666;font-size:.85em}
.banner{background:#fff3cd;border:1px solid #e0c36a;padding:.6em 1em;margin:1em 0}</style>
</head><body>
<h1>PlanWAT egress</h1>
%BANNER%
<div class="mode %MODE_CLASS%">tryb: %MODE%</div>
<p class="small">pool: %TOTAL% proxy (%OK% ok · %NEW% new · %FAIL% fail) · p50: %P50% ms · p95: %P95% ms · mediana ok: %MED% ms
· ostatnie odświeżenie: %REFRESH% · bezpośrednich obejść: %FALLBACKS% · odrzuconych: %BLOCKS%</p>
<h2>Wydziały (weryfikacja per host)</h2>
<table><tr><th>host</th><th>tryb</th><th>zweryfikowane</th><th>obejścia</th></tr>%HOST_ROWS%</table>
<h2>Proxy</h2>
<table><tr><th>proxy</th><th>status</th><th>ping</th><th>źródło</th></tr>%PROXY_ROWS%</table>
<h2>Przebiegi odświeżania</h2>
<table><tr><th>odebrano</th><th>start</th><th>koniec</th><th>exit</th><th>wydziały</th></tr>%RUN_ROWS%</table>
<p class="small">Odświeżenie co 30 s. POST /api/refresh wymusza odświeżenie puli.</p>
</body></html>'''


def _wants_auth():
    return bool(env('EGRESS_API_TOKEN', ''))


class GuiHandler(BaseHTTPRequestHandler):
    server_version = 'PlanWAT-Egress-GUI/1'

    def _send(self, body, ctype='application/json', code=200):
        data = body if isinstance(body, bytes) else body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype + '; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        try:
            self.wfile.write(data)
        except OSError:
            pass

    def _check_token(self):
        want = env('EGRESS_API_TOKEN', '')
        if not want:
            return True
        return self.headers.get('X-Token') == want

    def status(self):
        pool, runs = self.server.pool, self.server.runs
        stats = pool.stats()
        with pool.lock:
            proxies = sorted(({'url': u, **e} for u, e in pool.entries.items()),
                             key=lambda e: (e.get('latency_ms') or 10 ** 9))
        verified_total = sum(stats.get('verified', {}).values())
        mode = 'ROTATING' if verified_total > 0 else 'DIRECT (pula pusta)'
        lock = getattr(self.server.proxy_server, 'fallbacks_lock', None)
        if lock is not None:
            with lock:
                fallbacks = dict(self.server.proxy_server.fallbacks)
        else:
            fallbacks = dict(self.server.proxy_server.fallbacks)
        host_modes = {}
        for h in self.server.pool.round2:
            n = stats['verified'].get(h, 0)
            if host_is_direct(h):
                host_mode = 'DIRECT (lista)'
            else:
                host_mode = 'ROTATING' if n else 'DIRECT'
            host_modes[h] = {'mode': host_mode, 'verified': n, 'fallbacks': fallbacks.get(h, 0)}
        open_runs = list(getattr(runs, 'open_runs', []))
        return {'mode': mode, 'proxy_port': self.server.proxy_port, 'pool': stats,
                'fallbacks': fallbacks, 'fallbacks_total': sum(fallbacks.values()),
                'hosts': host_modes,
                'denied': self.server.proxy_server.blocks,
                'open_runs': open_runs,
                'proxies': [{'url': p['url'], 'status': p.get('status', 'new'),
                             'latency_ms': p.get('latency_ms'), 'source': p.get('source', ''),
                             'fails': p.get('fails', 0)} for p in proxies[:200]],
                'runs': runs.runs[::-1][:10]}

    def do_GET(self):
        if self.path == '/api/status':
            return self._send(json.dumps(self.status(), ensure_ascii=False))
        if self.path in ('/', '/index.html'):
            st = self.status()
            rows = ''.join(
                '<tr><td>' + p['url'] + '</td><td class="' + p['status'] + '">' + p['status'] + '</td>'
                '<td>' + str(p['latency_ms'] or '–') + '</td><td>' + p['source'] + '</td></tr>'
                for p in st['proxies'][:100])
            host_rows = ''.join(
                '<tr><td>' + h + '</td><td>' + v['mode'] + '</td><td>' + str(v['verified'])
                + '</td><td>' + str(v['fallbacks']) + '</td></tr>'
                for h, v in st['hosts'].items())
            cells = []
            for r in st['runs'][:10]:
                facs = []
                for k, c in (r.get('faculties') or {}).items():
                    mark = ' ⛔' if c.get('blocked') else ''
                    facs.append(str(k) + ' Δ' + str(c.get('changed', 0)) + mark)
                cells.append('<tr><td>' + str(r.get('received', '–')) + '</td><td>'
                             + str(r.get('started', '–')) + '</td><td>' + str(r.get('ended', '–'))
                             + '</td><td>' + str(r.get('exit', '–')) + '</td><td>' + ', '.join(facs)
                             + '</td></tr>')
            run_rows = ''.join(cells)
            if st.get('open_runs'):
                banner = '<div class="banner">run in progress: ' + str(len(st['open_runs'])) + '</div>'
            else:
                banner = ''
            page = (DASHBOARD.replace('%BANNER%', banner)
                    .replace('%MODE%', st['mode'])
                    .replace('%MODE_CLASS%', 'rot' if st['mode'] == 'ROTATING' else 'dir')
                    .replace('%TOTAL%', str(st['pool']['total']))
                    .replace('%OK%', str(st['pool']['by_status'].get('ok', 0)))
                    .replace('%NEW%', str(st['pool']['by_status'].get('new', 0)))
                    .replace('%FAIL%', str(st['pool']['by_status'].get('fail', 0)))
                    .replace('%P50%', str(st['pool'].get('p50_ok_ms') or '–'))
                    .replace('%P95%', str(st['pool'].get('p95_ok_ms') or '–'))
                    .replace('%MED%', str(st['pool']['median_ok_ms'] or '–'))
                    .replace('%REFRESH%', time.strftime('%Y-%m-%d %H:%M:%S',
                             time.gmtime(st['pool']['last_refresh'])) if st['pool']['last_refresh'] else 'nigdy')
                    .replace('%FALLBACKS%', str(st['fallbacks_total']))
                    .replace('%BLOCKS%', str(st['denied']))
                    .replace('%HOST_ROWS%', host_rows or '<tr><td colspan="4">brak</td></tr>')
                    .replace('%PROXY_ROWS%', rows or '<tr><td colspan="4">pusto</td></tr>')
                    .replace('%RUN_ROWS%', run_rows or '<tr><td colspan="5">brak przebiegów</td></tr>'))
            return self._send(page, 'text/html')
        return self._send('{"error":"not found"}', code=404)

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length) if length else b''
        if self.path == '/api/run':
            if not self._check_token():
                return self._send('{"error":"unauthorized"}', code=401)
            try:
                report = json.loads(body.decode('utf-8'))
            except ValueError:
                return self._send('{"error":"bad json"}', code=400)
            if not isinstance(report, dict):
                return self._send('{"error":"bad json"}', code=400)
            return self._send(json.dumps(self.server.runs.add(report), ensure_ascii=False))
        if self.path == '/api/block':
            if not self._check_token():
                return self._send('{"error":"unauthorized"}', code=401)
            try:
                report = json.loads(body.decode('utf-8'))
            except ValueError:
                return self._send('{"error":"bad json"}', code=400)
            host = str(report.get('host') or '').lower().rstrip('.') if isinstance(report, dict) else ''
            if not host:
                return self._send('{"error":"bad json"}', code=400)
            demoted = self.server.proxy_server.demote_recent(host)
            return self._send(json.dumps({'demoted': demoted}))
        if self.path == '/api/refresh':
            if not self._check_token():
                return self._send('{"error":"unauthorized"}', code=401)
            pool = self.server.pool
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
        return self._send('{"error":"not found"}', code=404)


class GuiServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 32


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
        try:
            evt = getattr(pool, 'heal_event', None)
            if evt is not None:
                evt.wait(timeout=interval)
                try:
                    evt.clear()
                except Exception:
                    pass
            else:
                time.sleep(interval)
        except Exception:
            time.sleep(interval)


def main():
    data = Path(env('EGRESS_DATA', '/data'))
    pool = ProxyPool(data / 'pool.json', faculty_targets(),
                     max_probe=int(env('EGRESS_MAX_PROBE', '150')))
    runs = RunLog(data / 'runs.json')
    proxy_port = int(env('EGRESS_PROXY_PORT', '8888'))
    gui_port = int(env('EGRESS_GUI_PORT', '8080'))
    proxy_server = ProxyServer(('0.0.0.0', proxy_port), pool)
    gui = GuiServer(('0.0.0.0', gui_port), GuiHandler)
    gui.pool, gui.runs, gui.proxy_server, gui.proxy_port = pool, runs, proxy_server, proxy_port
    threading.Thread(target=maintain, args=(pool,), daemon=True).start()
    threading.Thread(target=gui.serve_forever, daemon=True).start()
    print(f'egress proxy on :{proxy_port}, GUI on :{gui_port} (pool={len(pool.entries)} known)',
          flush=True)
    try:
        proxy_server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
