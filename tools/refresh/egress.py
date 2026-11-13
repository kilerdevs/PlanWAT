"""The crawler's side of the egress hunt (docs/EGRESS.md, "Polowanie na wyjścia").

When no runner up gets through a faculty's wall from its own address, stack.py has a runner with an egress search the
pool of public proxies for exits that do, and crawl the faculty through them. This module talks to that egress:

  remote   the egress box beside the runner (deploy/runner/compose.yml, plebania's compose.fragment.yml): its GUI API
           (PLANWAT_EGRESS_API, http://egress:8080) and its hunt port (PLANWAT_EGRESS_HUNT_PROXY, http://egress:8889),
           which rides only exits verified for the host. An egress built before the hunt answers 404: no hunt here.
  local    a runner without one (northflank) runs tools/egress/server.py on its own loopback, with a token of its own
           and every faculty host off its regular pool (only the scout and hunts probe anybody). During a crawl it is
           started the first time a hunt is needed and stopped when the crawl ends. On a runner (a tool cache) it also
           scouts between passes (docs/EGRESS.md, "Zwiad"): the end of a crawl starts it from a copy of the code in the
           tool cache, with a venv of its own there, detached from the job (RUNNER_TRACKING_ID keeps the runner's orphan
           cleanup off it); the next job stops it before its pip install (512 MB do not hold both, 13.11.2026), and its
           hunts use what the scout found (the same pool.json and seen.json in the tool cache). Beside it runs a Tor
           client with Polish exits (docs/EGRESS.md, "Tor"; LocalTor), whose ports the egress pins in its pool: the
           walls of WLO, WML, WTC and WCY let Polish addresses through. Its binary is the Tor Project's expert bundle,
           checked against a pinned sha256 and kept in the tool cache.

Every call bypasses the job's HTTP proxy (the egress answers 403 for its own address). Unit-tested offline
(tests/test_refresh.py).
"""
import hashlib
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
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
CODE = ('server.py', 'pool.py')  # what a persistent local egress runs, copied out of the checkout
REQUIREMENTS = SERVER.parent / 'requirements.txt'
LOG_CAP = 5 * 1024 * 1024
# A small shared box (northflank: 0.2 vCPU): the scout looks slowly and gives the crawl beside it the CPU.
SMALL_SCOUT = {'EGRESS_SCOUT': 'on', 'EGRESS_SCOUT_TCP': '48', 'EGRESS_SCOUT_R1': '6', 'EGRESS_FACULTY_PROBES': '2',
               'EGRESS_SCOUT_BATCH': '600', 'EGRESS_SCOUT_PAUSE': '120', 'EGRESS_NICE': '10'}
# Tor for the local egress (LocalTor): the Tor Project's expert bundle, pinned. The hash is the one in the release's
# sha256sums-signed-build.txt, whose signature (and the tarball's own) verified against the Tor Browser Developers
# signing key EF6E 286D DA85 EA2A 4BA7 DE68 4E2C 6E87 9329 8290 (13.11.2026). A new version: the same checks.
TOR_VERSION = '16.0.1'  # tor 0.4.9.16
TOR_URL = (f'https://dist.torproject.org/torbrowser/{TOR_VERSION}/'
           f'tor-expert-bundle-linux-x86_64-{TOR_VERSION}.tar.gz')
TOR_SHA256 = '7039cb16060ab22e669852e55774d894b55f25ea8bd0ab7194d3478429a58725'
TOR_FILES = ('tor/tor', 'tor/libcrypto.so.3', 'tor/libevent-2.1.so.7', 'tor/libssl.so.3', 'data/geoip', 'data/geoip6')
TOR_PORTS = 4  # SOCKS ports, one circuit each: four pool entries
TOR_WAIT = 90  # bootstrap (with a cached consensus it takes seconds)


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

    def ensure(self):
        """Have the egress up before it is needed (a remote one is somebody else's to run)."""
        return True

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
        # patience counts from when the egress starts on this host: it may first finish another host's hunt
        begun, until, cap = None, self.clock() + wait, self.clock() + 2 * wait
        while True:
            self.sleep(POLL)
            code, got = self._call('/api/hunt', timeout=15)
            state = ((got.get('hosts') or {}).get(host) or {}) if code == 200 else {}
            if begun is None and state.get('state') != 'queued':
                begun = self.clock()
                until = min(cap, begun + wait)
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


def code_hash(files=CODE, folder=SERVER.parent):
    h = hashlib.sha256()
    for name in files:
        h.update(name.encode() + b'\0' + (folder / name).read_bytes())
    return h.hexdigest()[:16]


def _pid_alive(pid, name=b'server.py'):
    """A live (not zombie) process running the egress server (or `name`)."""
    try:
        os.kill(pid, 0)
    except (OSError, TypeError, ValueError):
        return False
    try:
        stat = Path(f'/proc/{pid}/stat').read_text()
        if stat.rsplit(')', 1)[1].split()[0] == 'Z':
            return False
        return name in Path(f'/proc/{pid}/cmdline').read_bytes()
    except (OSError, IndexError):
        return True  # no /proc to ask: the signal check is all there is


class LocalTor:
    """The Tor client of a local egress: Polish exits only, TOR_PORTS SOCKS ports on loopback (each its own circuit),
    its data (the consensus cache) and state in `home`. It runs while an egress does, detached from the job like the
    scouting daemon, and keeps its ports, so the pool's pinned entries stay the same across restarts."""

    def __init__(self, home, log=print, sleep=time.sleep, clock=time.monotonic, popen=None, fetch=None):
        self.home = Path(home)
        self.bundle = self.home.parent / f'tor-{TOR_VERSION}'
        self.log, self.sleep, self.clock = log, sleep, clock
        self.popen = popen or subprocess.Popen
        self.fetch = fetch or self._download

    @property
    def state_path(self):
        return self.home / 'tor.json'

    def _read_state(self):
        try:
            st = json.loads(self.state_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
        ok = isinstance(st, dict) and isinstance(st.get('pid'), int) and isinstance(st.get('ports'), list) \
            and all(isinstance(p, int) for p in st['ports'])
        return st if ok else None

    @staticmethod
    def urls(ports):
        return [f'socks5://127.0.0.1:{p}' for p in ports]

    @staticmethod
    def _download(url, dest):
        with urllib.request.urlopen(url, timeout=120) as r, open(dest, 'wb') as f:
            shutil.copyfileobj(r, f)

    def binary(self):
        """The bundle's tor, fetched and checked once per runner (None when it cannot be had)."""
        tor = self.bundle / 'tor' / 'tor'
        if all((self.bundle / n).exists() for n in TOR_FILES):
            return tor
        self.log(f'egress: fetching Tor {TOR_VERSION} (once per runner)')
        tmp = Path(tempfile.mkdtemp(prefix='planwat-tor-'))
        try:
            tgz = tmp / 'tor.tar.gz'
            self.fetch(TOR_URL, tgz)
            h = hashlib.sha256()
            with open(tgz, 'rb') as f:
                for chunk in iter(lambda: f.read(1 << 20), b''):
                    h.update(chunk)
            if h.hexdigest() != TOR_SHA256:
                self.log('egress: the Tor bundle does not match its pinned sha256; no Tor')
                return None
            out = tmp / 'x'
            with tarfile.open(tgz) as tar:
                tar.extractall(out, members=[tar.getmember(n) for n in TOR_FILES], filter='data')
            os.chmod(out / 'tor' / 'tor', 0o755)
            shutil.rmtree(self.bundle, ignore_errors=True)
            self.bundle.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(out), str(self.bundle))
            return tor
        except (OSError, KeyError, tarfile.TarError, urllib.error.URLError) as err:
            self.log(f'egress: Tor: {err}')
            return None
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _ports(self, old):
        """The ports it had (still free), else new ones."""
        def free(p):
            with socket.socket() as s:
                try:
                    s.bind(('127.0.0.1', p))
                    return True
                except OSError:
                    return False
        if len(old) == TOR_PORTS and all(free(p) for p in old):
            return list(old)
        return [_free_port() for _ in range(TOR_PORTS)]

    def ensure(self):
        """The SOCKS URLs of a running Tor, started (and bootstrapped) if need be; [] when there is none."""
        st = self._read_state()
        if st and _pid_alive(st['pid'], b'tor'):
            return self.urls(st['ports'])
        tor = self.binary()
        if tor is None:
            return []
        ports = self._ports((st or {}).get('ports') or [])
        data = self.home / 'tor'
        data.mkdir(parents=True, exist_ok=True)
        os.chmod(data, 0o700)
        log = self.home / 'tor.log'
        rc = self.home / 'torrc'
        rc.write_text(''.join(f'SocksPort 127.0.0.1:{p}\n' for p in ports)
                      + f'DataDirectory {data}\nGeoIPFile {self.bundle}/data/geoip\n'
                        f'GeoIPv6File {self.bundle}/data/geoip6\n'
                        'ExitNodes {pl}\nStrictNodes 1\nAvoidDiskWrites 1\n'
                        f'Log notice file {log}\n', encoding='utf-8')
        try:
            log.unlink()
        except OSError:
            pass
        env = {k: v for k, v in os.environ.items() if not k.lower().endswith('_proxy')}
        env.update(LD_LIBRARY_PATH=str(tor.parent), RUNNER_TRACKING_ID='0')
        try:
            proc = self.popen([str(tor), '-f', str(rc)], env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, cwd=str(self.home), start_new_session=True)
        except OSError as err:
            self.log(f'egress: Tor: {err}')
            return []
        self.home.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({'pid': proc.pid, 'ports': ports}), encoding='utf-8')
        until = self.clock() + TOR_WAIT
        while self.clock() < until and proc.poll() is None:
            try:
                if 'Bootstrapped 100%' in log.read_text(encoding='utf-8', errors='replace'):
                    self.log(f'egress: Tor up (pid {proc.pid}, Polish exits, {len(ports)} circuits)')
                    return self.urls(ports)
            except OSError:
                pass
            self.sleep(1)
        if proc.poll() is not None:
            self.log('egress: Tor did not start')
            return []
        self.log(f'egress: Tor still bootstrapping after {TOR_WAIT} s; the pool retries its ports every cycle')
        return self.urls(ports)

    def stop(self):
        """Stopped, and gone (its data directory is locked while it runs)."""
        st = self._read_state()
        if not st or not _pid_alive(st['pid'], b'tor'):
            return
        try:
            os.kill(st['pid'], signal.SIGTERM)
        except OSError:
            return
        until = self.clock() + 10
        while self.clock() < until and _pid_alive(st['pid'], b'tor'):
            self.sleep(0.5)


class LocalEgress(Egress):
    """An egress this runner runs itself, on loopback. Persistent: kept running across jobs (the scout never stops);
    otherwise started the first time a hunt is needed and stopped with the crawl."""

    def __init__(self, data=None, python=None, log=print, sleep=time.sleep, clock=time.monotonic, popen=None,
                 opener=None, persistent=False, home=None, run=None, scout=None, tor=None):
        self.ports = {'gui': _free_port(), 'proxy': _free_port(), 'hunt': _free_port()}
        super().__init__(f"http://127.0.0.1:{self.ports['gui']}", f"http://127.0.0.1:{self.ports['hunt']}",
                         secrets.token_hex(24), log, sleep, clock, opener)
        cache = os.environ.get('RUNNER_TOOL_CACHE') or tempfile.gettempdir()
        self.home = Path(home or Path(cache) / 'planwat' / 'egress')
        self.data = Path(data or self.home)
        self.python = python or sys.executable
        self.popen = popen or subprocess.Popen
        self.run = run or subprocess.run
        self.persistent = persistent
        self.scout = dict(SMALL_SCOUT if scout is None else scout)
        self.proc = None
        self.pid = None
        # the Tor client beside it (LocalTor); False: none
        self.tor = LocalTor(self.home, log, sleep, clock) if tor is None else tor
        self.tor_urls = []

    def _tor(self):
        self.tor_urls = self.tor.ensure() if self.tor else []
        return self.tor_urls

    # -- persistent: one daemon per runner, reused while its code is this checkout's
    @property
    def state_path(self):
        return self.home / 'daemon.json'

    def _read_state(self):
        try:
            st = json.loads(self.state_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None
        ok = (isinstance(st, dict) and isinstance(st.get('pid'), int) and isinstance(st.get('token'), str)
              and isinstance(st.get('ports'), dict) and all(isinstance(st['ports'].get(k), int)
                                                            for k in ('gui', 'proxy', 'hunt')))
        return st if ok else None

    def _write_state(self, st):
        self.home.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix('.tmp')
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)  # holds the token
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(st, f)
        tmp.replace(self.state_path)

    def _use(self, st):
        self.ports, self.token, self.pid = dict(st['ports']), st['token'], st['pid']
        self.api = f"http://127.0.0.1:{self.ports['gui']}"
        self.proxy = f"http://127.0.0.1:{self.ports['hunt']}"

    def _venv(self):
        """The daemon's own python, with the egress requirements, built once in the tool cache (None if it cannot)."""
        venv = self.home.parent / 'egress-venv'
        py = venv / 'bin' / 'python'
        want = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()[:16]
        stamp = venv / '.planwat-requirements'
        try:
            if py.exists() and stamp.read_text().strip() == want:
                return str(py)
        except OSError:
            pass
        self.log('egress: building the local egress venv (once per runner)')
        shutil.rmtree(venv, ignore_errors=True)
        env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
        for cmd in ([self.python, '-m', 'venv', str(venv)],
                    [str(py), '-m', 'pip', 'install', '--disable-pip-version-check', '-q', '-r', str(REQUIREMENTS)]):
            try:
                done = self.run(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=600)
            except (OSError, subprocess.SubprocessError) as err:
                self.log(f'egress: venv: {err}')
                return None
            if done.returncode != 0:
                self.log(f"egress: venv: {' '.join(cmd[1:3])} failed: {(done.stderr or b'')[-300:]!r}")
                return None
        stamp.write_text(want)
        return str(py)

    def _install_code(self, digest):
        """A copy of the egress code the daemon runs, so cleaning the checkout pulls nothing from under it."""
        root = self.home / 'code'
        dest = root / digest
        if not all((dest / n).exists() for n in CODE):
            dest.mkdir(parents=True, exist_ok=True)
            for n in CODE:
                shutil.copy2(SERVER.parent / n, dest / n)
        for old in root.iterdir():
            if old.is_dir() and old.name != digest:
                shutil.rmtree(old, ignore_errors=True)
        return dest

    def _stop_pid(self, pid):
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            return
        until = self.clock() + 10
        while self.clock() < until and _pid_alive(pid):
            self.sleep(0.5)
        if _pid_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass

    def _env(self):
        env = {k: v for k, v in os.environ.items() if not k.lower().endswith('_proxy')}
        env.update(EGRESS_DATA=str(self.data), EGRESS_BIND='127.0.0.1', EGRESS_API_TOKEN=self.token,
                   EGRESS_GUI_PORT=str(self.ports['gui']), EGRESS_PROXY_PORT=str(self.ports['proxy']),
                   EGRESS_HUNT_PORT=str(self.ports['hunt']), EGRESS_POOL='on', EGRESS_HUNT='on',
                   # no regular pool work: every faculty goes "direct" on the (unused) main port, only the scout and
                   # hunts probe
                   EGRESS_DIRECT_FACULTY=','.join(faculty_hosts()), EGRESS_FAIL_CLOSED='',
                   EGRESS_TOR=','.join(self.tor_urls))
        return env

    def _wait_up(self, alive):
        until = self.clock() + START_WAIT
        while self.clock() < until:
            if not alive():
                return False
            if self._call('/api/status', timeout=3)[0] == 200:
                return True
            self.sleep(1)
        return False

    def ensure(self):
        """At the start of a crawl: a scouting daemon still running gives the crawl its memory back (northflank has
        512 MB, and the daemon, the crawl and its pip install do not fit together; the action stops it before the pip
        install already). A hunt during the crawl starts a temporary egress on the same data, so it has everything
        the scout found."""
        if self.persistent:
            self.stop(quiet=True)
        return True

    def resume(self):
        """Have the scouting daemon run this checkout's code: left alone when it already does, else (re)started."""
        st = self._read_state()
        tor = self._tor()
        if st and st.get('hash') == code_hash() and st.get('tor', []) == tor and _pid_alive(st['pid']):
            self.pid = st['pid']
            self.log(f"egress: scouting between passes (pid {st['pid']}, already on this code)")
            return True
        if st and _pid_alive(st['pid']):
            self._stop_pid(st['pid'])
        return self._launch()

    def _launch(self):
        """At the end of a crawl: start the scouting daemon from this checkout's code, detached from the job."""
        try:
            digest = code_hash()
            python = self._venv()
            if python is None:
                return False
            code = self._install_code(digest)
            self.data.mkdir(parents=True, exist_ok=True)
            self.ports = {'gui': _free_port(), 'proxy': _free_port(), 'hunt': _free_port()}
            self.token = secrets.token_hex(24)
            self.api = f"http://127.0.0.1:{self.ports['gui']}"
            self.proxy = f"http://127.0.0.1:{self.ports['hunt']}"
            env = self._env()
            env.update(self.scout)
            env['RUNNER_TRACKING_ID'] = '0'  # not this job's: the runner's orphan cleanup leaves it running
            log = self.home / 'egress.log'
            if log.exists() and log.stat().st_size > LOG_CAP:
                log.replace(log.with_suffix('.log.1'))
            with open(log, 'ab') as out:
                proc = self.popen([python, str(code / 'server.py')], env=env, stdin=subprocess.DEVNULL, stdout=out,
                                  stderr=subprocess.STDOUT, cwd=str(code), start_new_session=True)
            self.pid = proc.pid
            if not self._wait_up(lambda: proc.poll() is None):
                self.log('egress: the scouting egress did not come up')
                if proc.poll() is None:
                    proc.terminate()
                return False
            self._write_state({'pid': proc.pid, 'ports': self.ports, 'token': self.token, 'hash': digest,
                               'tor': self.tor_urls, 'started': time.time()})
            self.log(f'egress: scouting between passes (pid {proc.pid})')
            return True
        except OSError as err:
            self.log(f'egress: the scouting egress: {err}')
            return False

    # -- temporary: started for a hunt, stopped with the crawl
    def _start(self):
        if self.proc is not None:
            return self.proc.poll() is None
        self.data.mkdir(parents=True, exist_ok=True)
        self._tor()
        self.log(f"egress: starting a local one (hunt port {self.ports['hunt']})")
        self.proc = self.popen([self.python, str(SERVER)], env=self._env(), stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, cwd=str(SERVER.parent))
        return self._wait_up(lambda: self.proc.poll() is None)

    def available(self):
        if self._ok is None:
            if not self._start():
                self.log('egress: the local one did not start; no hunt here')
                self._ok = False
                return False
        return super().available()

    def close(self):
        """The end of the crawl: the temporary egress (if a hunt started one) goes, and a persistent runner starts
        scouting again until the next crawl."""
        if self.proc is not None and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except Exception:
                self.proc.kill()
        if self.persistent:
            self.resume()
        elif self.tor and self.proc is not None:
            self.tor.stop()

    def stop(self, quiet=False):
        """Stop the scouting daemon (the action before a job's pip install, ensure(), or by hand: egress.py stop)."""
        st = self._read_state()
        if st and _pid_alive(st['pid']):
            self._stop_pid(st['pid'])
            self.log(f"egress: stopped the scouting egress (pid {st['pid']}) for the crawl" if quiet
                     else f"egress: stopped the local one (pid {st['pid']})")
        if self.tor:
            self.tor.stop()
        try:
            self.state_path.unlink()
        except OSError:
            pass


def make(kind, log=print):
    """The egress a runner of this kind (fleet.json `egress`) hunts with, or None."""
    if kind == 'remote':
        return Egress(os.environ.get('PLANWAT_EGRESS_API', 'http://egress:8080'),
                      os.environ.get('PLANWAT_EGRESS_HUNT_PROXY', 'http://egress:8889'),
                      os.environ.get('EGRESS_API_TOKEN', '').strip(), log)
    if kind == 'local':
        # on a runner (a tool cache that outlives the job) it stays up and scouts between passes
        return LocalEgress(log=log, persistent=bool(os.environ.get('RUNNER_TOOL_CACHE')))
    return None


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description='The runner-local scouting egress: start (or update) it, stop it, or say '
                                             'how it is.')
    ap.add_argument('command', choices=('start', 'stop', 'status'))
    ap.add_argument('--runner', help="with --fleet: start only if this runner's egress is local (fleet.json)")
    ap.add_argument('--fleet', help='tools/refresh/fleet.json')
    args = ap.parse_args(argv)
    if args.command == 'start':
        if args.runner and args.fleet:
            try:
                runners = json.loads(Path(args.fleet).read_text(encoding='utf-8')).get('runners') or []
            except (OSError, ValueError):
                runners = []
            if not any(r.get('name') == args.runner and r.get('egress') == 'local' for r in runners):
                return 0  # an egress box beside it, or none at all: nothing to run here
        return 0 if LocalEgress(persistent=True).resume() else 1
    local = LocalEgress(persistent=True)
    if args.command == 'stop':
        local.stop()
        return 0
    st = local._read_state()
    if not st or not _pid_alive(st['pid']):
        print('not running')
        return 1
    local._use(st)
    code, got = local._call('/api/status', timeout=10)
    print(json.dumps({'pid': st['pid'], 'hash': st.get('hash'), 'tor': st.get('tor'), 'code': code,
                      'scout': got.get('scout'),
                      'exits': (got.get('pool') or {}).get('exits'),
                      'pool': {k: (got.get('pool') or {}).get(k) for k in ('total', 'alive', 'dead', 'unseen')}},
                     indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
