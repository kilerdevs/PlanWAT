"""The crawler's side of the egress hunt (docs/EGRESS.md, "Polowanie na wyjścia").

When no runner up gets through a faculty's wall from its own address, stack.py has a runner with an egress search the
pool of public proxies for exits that do, and crawl the faculty through them. This module talks to that egress:

  remote   the egress box beside the runner (deploy/runner/compose.yml, plebania's compose.fragment.yml): its GUI API
           (PLANWAT_EGRESS_API, http://egress:8080) and its hunt port (PLANWAT_EGRESS_HUNT_PROXY, http://egress:8889),
           which rides only exits verified for the host. An egress built before the hunt answers 404: no hunt here.
  local    a runner without one (northflank) starts tools/egress/server.py from the checkout on its own loopback, the
           first time a hunt is needed, with a token of its own and every faculty host off its regular pool (only hunts
           probe anybody); stopped when the crawl ends. Its pool.json stays in the runner's tool cache between jobs.

Every call bypasses the job's HTTP proxy (the egress answers 403 for its own address). Unit-tested offline
(tests/test_refresh.py).
"""
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SERVER = HERE.parent / 'egress' / 'server.py'
HUNT_WAIT = 480  # the egress hunts for up to 5 minutes, after fetching the lists and Round-1 probing if it must
POLL = 5
START_WAIT = 60  # a local egress that does not answer in this long is not coming


class Unavailable(Exception):
    """No egress that can hunt (none, an old one without the hunt, a local one that would not start)."""


class Egress:
    def __init__(self, api, proxy, token='', log=print, sleep=time.sleep, clock=time.monotonic, opener=None):
        self.api, self.proxy, self.token = api.rstrip('/'), proxy, token
        self.log, self.sleep, self.clock = log, sleep, clock
        self.opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self._ok = None

    def _call(self, path, body=None, timeout=30):
        """(status, json) of one API call; status 0 when the egress did not answer."""
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers.update({'X-Token': self.token, 'Authorization': f'Bearer {self.token}'})
        data = json.dumps(body).encode('utf-8') if body is not None else None
        req = urllib.request.Request(self.api + path, data=data, headers=headers,
                                     method='POST' if data is not None else 'GET')
        try:
            with self.opener.open(req, timeout=timeout) as r:
                return r.status, json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as err:
            try:
                return err.code, json.loads(err.read() or b'{}')
            except ValueError:
                return err.code, {}
        except (OSError, ValueError):
            return 0, {}

    def available(self):
        if self._ok is None:
            code, _ = self._call('/api/hunt', timeout=10)
            self._ok = code == 200
            if not self._ok:
                self.log(f'egress: no hunt at {self.api} ({code or "no answer"})')
        return self._ok

    def proxy_url(self):
        return self.proxy

    def hunt(self, host, exits=(), wait=HUNT_WAIT):
        """Exits that get through to `host`: the shared `exits` checked first, then a search of the pool if none
        of those works. [] when nothing gets through; Unavailable when this egress cannot hunt."""
        if not self.available():
            raise Unavailable(self.api)
        exits = [e for e in exits or () if isinstance(e, str)][:8]
        if exits:
            code, got = self._call('/api/exits', {'host': host, 'exits': exits}, timeout=120)
            ok = [e for e in (got.get('verified') or []) if isinstance(e, str)] if code == 200 else []
            self.log(f'egress: {len(ok)} of the {len(exits)} shared exits get through to {host}')
            if ok:
                return ok
        code, _ = self._call('/api/hunt', {'hosts': [host]})
        if code != 202:
            raise Unavailable(f'{self.api}: the hunt was refused ({code or "no answer"})')
        until = self.clock() + wait
        while True:
            self.sleep(POLL)
            code, got = self._call('/api/hunt', timeout=15)
            state = ((got.get('hosts') or {}).get(host) or {}) if code == 200 else {}
            if state.get('state') == 'done':
                found = [e for e in state.get('exits') or [] if isinstance(e, str)]
                self.log(f"egress: hunted {host}: {len(found)} exits through, {state.get('tried', 0)} tried")
                return found
            if state.get('state') == 'error':
                raise RuntimeError(f"the hunt for {host} failed: {state.get('error')}")
            if self.clock() >= until:
                self.log(f'egress: the hunt for {host} is still running after {wait} s; giving up on it')
                return []

    def report_block(self, host):
        """A block page met through the hunt port: the egress withdraws the exit that carried it."""
        self._call('/api/block', {'host': host}, timeout=5)

    def close(self):
        pass


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def faculty_hosts():
    """Every faculty host the egress knows (its Round-2 targets), so a local one keeps them all off its pool."""
    sys.path.insert(0, str(SERVER.parent))
    import server  # noqa: E402  (no side effects at import)
    return sorted(server.faculty_targets())


class LocalEgress(Egress):
    """An egress this runner starts itself, on loopback, the first time a hunt is needed."""

    def __init__(self, data=None, python=None, log=print, sleep=time.sleep, clock=time.monotonic, popen=None,
                 opener=None):
        self.ports = {'gui': _free_port(), 'proxy': _free_port(), 'hunt': _free_port()}
        super().__init__(f"http://127.0.0.1:{self.ports['gui']}", f"http://127.0.0.1:{self.ports['hunt']}",
                         secrets.token_hex(24), log, sleep, clock, opener)
        cache = os.environ.get('RUNNER_TOOL_CACHE') or tempfile.gettempdir()
        self.data = Path(data or Path(cache) / 'planwat' / 'egress')
        self.python = python or sys.executable
        self.popen = popen or subprocess.Popen
        self.proc = None

    def _start(self):
        if self.proc is not None:
            return self.proc.poll() is None
        self.data.mkdir(parents=True, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if not k.lower().endswith('_proxy')}
        env.update(EGRESS_DATA=str(self.data), EGRESS_BIND='127.0.0.1', EGRESS_API_TOKEN=self.token,
                   EGRESS_GUI_PORT=str(self.ports['gui']), EGRESS_PROXY_PORT=str(self.ports['proxy']),
                   EGRESS_HUNT_PORT=str(self.ports['hunt']), EGRESS_POOL='on', EGRESS_HUNT='on',
                   # no regular pool work: every faculty goes "direct" on the (unused) main port, only hunts probe
                   EGRESS_DIRECT_FACULTY=','.join(faculty_hosts()), EGRESS_FAIL_CLOSED='')
        self.log(f"egress: starting a local one (hunt port {self.ports['hunt']})")
        self.proc = self.popen([self.python, str(SERVER)], env=env, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, cwd=str(SERVER.parent))
        until = self.clock() + START_WAIT
        while self.clock() < until:
            if self.proc.poll() is not None:
                return False
            code, _ = self._call('/api/status', timeout=3)
            if code == 200:
                return True
            self.sleep(1)
        return False

    def available(self):
        if self._ok is None:
            if not self._start():
                self.log('egress: the local one did not start; no hunt here')
                self._ok = False
                return False
        return super().available()

    def close(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except Exception:
                self.proc.kill()


def make(kind, log=print):
    """The egress a runner of this kind (fleet.json `egress`) hunts with, or None."""
    if kind == 'remote':
        return Egress(os.environ.get('PLANWAT_EGRESS_API', 'http://egress:8080'),
                      os.environ.get('PLANWAT_EGRESS_HUNT_PROXY', 'http://egress:8889'),
                      os.environ.get('EGRESS_API_TOKEN', '').strip(), log)
    if kind == 'local':
        return LocalEgress(log=log)
    return None
