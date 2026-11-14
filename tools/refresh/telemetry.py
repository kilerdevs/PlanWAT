#!/usr/bin/env python3
"""What a runner tells the operator's dashboard (tools/dash, docs/DASHBOARD.md), sealed so nobody else reads it.

The runner's heartbeat doc on the work stack (stack.py, `tel`) carries one snapshot of this process: its load (from
/proc), its requests per faculty host and route, a few egress gauges (Tor, the last hunt per host) and its last log
lines. The repository is public and so are those refs, so the snapshot is sealed with AES-GCM under
PLANWAT_DASH_KEY (64 hex digits, a GitHub secret the operator's own machine also holds): without the key there is
no `tel` at all, and a reader without it sees only noise.

Everything here is best effort: telemetry never fails or slows the crawl (a missing `cryptography` means no `tel`).
"""
import base64
import json
import os
import re
import threading
import time
import zlib
from collections import deque
from pathlib import Path

EVENTS = 60  # log lines kept for the dashboard's feed (a heartbeat every 15 s carries the newest of them)
VERSION = 1
FACULTY_RE = re.compile(r'^\[([a-z0-9~-]+)\]')
KINDS = ('egress', 'stack', 'board', 'relay')  # a line's "<kind>: ..." prefix, when it has one of these


class Telemetry:
    def __init__(self, clock=time.time, proc=Path('/proc')):
        self.clock, self.proc = clock, proc
        self.lock = threading.Lock()
        self.events = deque(maxlen=EVENTS)
        self.req = {}       # host -> route -> {'n', 's2xx', 's304', 's404', 'other', 'err', 'ms', 'bytes'}
        self.gauges = {}
        self.cpu = self.net = None  # the previous /proc samples, for rates
        self.seq = 0

    def event(self, msg, kind=None):
        msg = str(msg)
        if kind is None:
            head = msg.split(':', 1)[0]
            kind = head if head in KINDS else 'log'
        fac = FACULTY_RE.match(msg)
        with self.lock:
            self.seq += 1
            self.events.append({'n': self.seq, 't': round(self.clock(), 1), 'kind': kind, 'msg': msg[:300],
                                **({'fac': fac.group(1)} if fac else {})})

    def request(self, host, route, status, ms, size):
        """One response (`status` 0: no response at all) of `host` over `route` (direct, relay, pool)."""
        key = ('s2xx' if 200 <= status < 300 else 's304' if status == 304 else 's404' if status == 404
               else 'err' if not status else 'other')
        with self.lock:
            c = self.req.setdefault(host or '?', {}).setdefault(route, {'n': 0, 's2xx': 0, 's304': 0, 's404': 0,
                                                                        'other': 0, 'err': 0, 'ms': 0, 'bytes': 0})
            c['n'] += 1
            c[key] += 1
            c['ms'] += int(ms)
            c['bytes'] += int(size or 0)

    def gauge(self, key, value):
        with self.lock:
            self.gauges[key] = value

    def _read(self, name):
        try:
            return (self.proc / name).read_text()
        except OSError:
            return ''

    def system(self):
        """Load, CPU %, memory, this process's RSS and network rates, from /proc (empty fields where it lacks them)."""
        out = {}
        load = self._read('loadavg').split()
        if len(load) >= 3:
            out['load'] = [float(x) for x in load[:3]]
        mem = dict(re.findall(r'^(\w+):\s+(\d+) kB', self._read('meminfo'), re.M))
        if 'MemTotal' in mem:
            out['mem_mb'] = int(mem['MemTotal']) // 1024
            out['mem_free_mb'] = int(mem.get('MemAvailable', mem.get('MemFree', 0))) // 1024
        rss = re.search(r'^VmRSS:\s+(\d+) kB', self._read('self/status'), re.M)
        if rss:
            out['rss_mb'] = int(rss.group(1)) // 1024
        now = self.clock()
        cpu = self._read('stat').split('\n', 1)[0].split()[1:]
        if cpu:
            ticks = [int(x) for x in cpu]
            idle, total = ticks[3] + (ticks[4] if len(ticks) > 4 else 0), sum(ticks)
            if self.cpu and total > self.cpu[1]:
                out['cpu'] = round(100 * (1 - (idle - self.cpu[0]) / (total - self.cpu[1])), 1)
            self.cpu = (idle, total)
        rx = tx = 0
        nics = 0
        for line in self._read('net/dev').splitlines()[2:]:
            name, _, rest = line.partition(':')
            f = rest.split()
            if name.strip() != 'lo' and len(f) >= 9:
                rx, tx, nics = rx + int(f[0]), tx + int(f[8]), nics + 1
        if nics:
            if self.net and now > self.net[0]:
                dt = now - self.net[0]
                out['rx_kbs'] = round(max(0, rx - self.net[1]) / 1024 / dt, 1)
                out['tx_kbs'] = round(max(0, tx - self.net[2]) / 1024 / dt, 1)
            self.net = (now, rx, tx)
        return out

    def snapshot(self):
        sys_ = self.system()
        with self.lock:
            return {'v': VERSION, 't': round(self.clock(), 1), 'sys': sys_,
                    'req': json.loads(json.dumps(self.req)), 'gauges': dict(self.gauges), 'events': list(self.events)}


def _key(hex_key):
    try:
        key = bytes.fromhex((hex_key or '').strip())
    except ValueError:
        return None
    return key if len(key) == 32 else None


def seal(doc, hex_key):
    """`doc` as base64(nonce + AES-GCM(zlib(json))), or None without a valid key or the library."""
    key = _key(hex_key)
    if key is None:
        return None
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError:
        return None
    nonce = os.urandom(12)
    body = zlib.compress(json.dumps(doc, separators=(',', ':')).encode(), 6)
    return base64.b64encode(nonce + AESGCM(key).encrypt(nonce, body, b'planwat-tel')).decode()


def unseal(blob, hex_key):
    """The doc `seal` made, or None when the key is wrong, the blob is damaged or the library is missing."""
    key = _key(hex_key)
    if key is None or not isinstance(blob, str):
        return None
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        raw = base64.b64decode(blob)
        return json.loads(zlib.decompress(AESGCM(key).decrypt(raw[:12], raw[12:], b'planwat-tel')))
    except Exception:
        return None


TEL = Telemetry()  # this process's


def sealed():
    """This process's snapshot, sealed with PLANWAT_DASH_KEY; None without the key (no `tel` on the heartbeat)."""
    hex_key = os.environ.get('PLANWAT_DASH_KEY', '')
    if not hex_key:
        return None
    try:
        return seal(TEL.snapshot(), hex_key)
    except Exception:
        return None  # never the heartbeat's problem
