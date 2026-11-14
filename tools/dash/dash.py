#!/usr/bin/env python3
"""PlanWAT's fleet dashboard: a live view of the refresh passes, on this machine only (docs/DASHBOARD.md).

    python3 tools/dash/dash.py            # then http://127.0.0.1:8765/ (opened for you)

It reads three things, every few seconds, and serves them on 127.0.0.1 alone:

  * the work stack of every pass (refs/planwat/pass/<planned>-<run>/, tools/refresh/board.py): slots, chunks, walls,
    hunts, the routes through them, and each runner's heartbeat with its lanes;
  * each runner's telemetry on that heartbeat (`tel`, tools/refresh/telemetry.py): load, requests per route, Tor and
    hunts, its last log lines. Sealed with PLANWAT_DASH_KEY; the key is read from ~/.config/planwat/dash.key (or the
    environment), so only this machine opens it;
  * the refresh runs and their jobs, through `gh api` (this machine's own GitHub login).

Passes it was not open for come from their archive (refs/planwat/archive/, `board.py archive`). What it saw is kept
in SQLite (~/.local/share/planwat-dash/dash.db) for KEEP_DAYS, for the history views. The git objects go to a bare
cache repository of its own (~/.cache/planwat-dash/git), never into a checkout. Nothing here writes to GitHub.
"""
import argparse
import calendar
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'refresh'))
import telemetry  # noqa: E402

PORT = 8765
POLL = 10           # seconds between reads of the work stack
GH_POLL = 30        # ... and of the runs
KEEP_DAYS = 60
STALE = 150         # a runner whose heartbeat stood still this long is gone (stack.STALE)
PASS_ROOT = 'refs/planwat/pass/'
ARCHIVE_ROOT = 'refs/planwat/archive/'
LOCAL = 'refs/dash/'
KEY_RE = re.compile(r'^(\d{1,12})-(\d{1,20})$')
NAME_RE = re.compile(r'^(?:r/[a-z0-9][a-z0-9-]{0,38}|s/[a-z]{2,8}(?:@\d{4}-\d{2}-(?:zima|lato))?)$')
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'), '/dash.js': ('dash.js', 'text/javascript; charset=utf-8'),
          '/dash.css': ('dash.css', 'text/css; charset=utf-8')}
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


# -- what the docs say (pure: unit-tested) -------------------------------------------------------------------------

def slot_name(name):
    """'s/wml@2027-28-zima' -> 'wml~2027-28-zima'."""
    return name[2:].replace('@', '~')


def routes_of(d):
    """How each runner reaches a slot: tor / pool (its hunt's exits), wall / error (cannot), lost (exits went dead),
    direct (crawled it from its own address)."""
    out = {}
    via, tor = d.get('via') or {}, set(d.get('via_tor') or ())
    for r, c in (d.get('cant') or {}).items():
        out[r] = (c or {}).get('cause') or 'wall'
    for r, v in via.items():
        if v == 'pool':
            out[r] = 'tor' if r in tor else 'pool'
        elif v == 'lost':
            out[r] = 'lost'
    workers = {c.get('by') for c in d.get('chunks') or ()} | {c.get('done_by') for c in d.get('chunks') or ()}
    for r in workers | {d.get('leader')}:
        if r and r not in out:
            out[r] = 'direct'
    hunter = (d.get('hunting') or {}).get('runner')
    if hunter and out.get(hunter) in (None, 'wall', 'error', 'lost'):
        out[hunter] = 'hunting'
    return out


def slot_view(name, d):
    chunks = d.get('chunks') or []

    def n(c):
        return len(c.get('codes') or ())
    by = {}
    for c in chunks:
        if c.get('state') == 'done' and c.get('done_by'):
            by[c['done_by']] = by.get(c['done_by'], 0) + n(c)
    return {'slot': slot_name(name), 'state': d.get('state'), 'leader': d.get('leader'),
            'total': sum(n(c) for c in chunks), 'done': sum(n(c) for c in chunks if c.get('state') == 'done'),
            'held': sum(n(c) for c in chunks if c.get('state') == 'held'),
            'listed': d.get('listed'), 'fresh': d.get('fresh'), 'not_ready': d.get('not_ready'), 'note': d.get('note'),
            'changed': sum(c.get('changed') or 0 for c in chunks if c.get('state') == 'done'),
            'failed': sum(len(c.get('failed') or ()) for c in chunks),
            'chunks': [{'n': n(c), 'state': c.get('state'), 'by': c.get('by') or c.get('done_by')} for c in chunks],
            'by': by, 'routes': routes_of(d), 'hunting': (d.get('hunting') or {}).get('runner'),
            'exits': len(d.get('exits') or ())}


def runner_status(doc, age, hunting):
    if doc.get('mode') == 'done':
        return 'done'
    if age is not None and age > STALE:
        return 'gone'
    if hunting:
        return 'hunting'
    lanes = (doc.get('lanes') or {}).values()
    if any(lane.get('chunk') is not None for lane in lanes):
        return 'crawling'
    if any(lane.get('slot') for lane in lanes):
        return 'listing'
    return 'idle'


def diff_events(prev, cur):
    """[(slot, runner, kind, msg)] of what changed on the stack between two reads of one pass ({name: doc})."""
    out = []
    for name, d in sorted(cur.items()):
        p = prev.get(name) or {}
        if name.startswith('r/'):
            r = name[2:]
            if d.get('mode') == 'done' and p.get('mode') != 'done':
                out.append((None, r, 'runner', f'{r} finished'))
            elif not p:
                out.append((None, r, 'runner', f'{r} joined'))
            continue
        s = slot_name(name)
        if d.get('state') != p.get('state'):
            v = slot_view(name, d)
            msg = {'open': f'opened by {d.get("leader")}: {v["total"]} groups to check',
                   'closed': f'done {v["done"]}/{v["total"]}, by ' + (', '.join(sorted(v['by'])) or '-')
                   + (f' ({d["note"]})' if d.get('note') else ''),
                   'listing': f'being listed by {d.get("leader")}'}.get(d.get('state'), str(d.get('state')))
            out.append((s, d.get('leader'), 'slot', msg))
        for r, c in (d.get('cant') or {}).items():
            if r not in (p.get('cant') or {}):
                out.append((s, r, 'wall', f'{r} cannot reach it ({(c or {}).get("cause")})'))
        h = (d.get('hunting') or {}).get('runner')
        if h and h != (p.get('hunting') or {}).get('runner'):
            out.append((s, h, 'hunt', f'{h} hunting exits'))
        for r, v in (d.get('via') or {}).items():
            if (p.get('via') or {}).get(r) != v:
                how = ' (own Tor)' if r in (d.get('via_tor') or ()) else ''
                out.append((s, r, 'via', f'{r} gets through via {v}{how}'))
        if d.get('state') == 'open':
            had = {c.get('by') for c in p.get('chunks') or ()} | {c.get('done_by') for c in p.get('chunks') or ()}
            now = {c.get('by') for c in d.get('chunks') or ()} | {c.get('done_by') for c in d.get('chunks') or ()}
            for r in sorted(x for x in now - had if x and x != d.get('leader')):
                out.append((s, r, 'join', f'{r} joins'))
    return out


def req_totals(tel):
    """{'n', 's2xx', ...} summed over every host and route of a telemetry snapshot."""
    tot = {}
    for routes in (tel or {}).get('req', {}).values():
        for c in routes.values():
            for k, v in c.items():
                tot[k] = tot.get(k, 0) + v
    return tot


# -- the collector -------------------------------------------------------------------------------------------------

class Collector:
    def __init__(self, db_path, cache, key='', remote=None, gh_repo=None, run=subprocess.run, clock=time.time):
        self.cache, self.key, self.run, self.clock = Path(cache), key, run, clock
        self.remote, self.gh_repo = remote, gh_repo
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS passes(key TEXT PRIMARY KEY, run INTEGER, planned INTEGER, first REAL, last REAL,
                                              view TEXT, source TEXT);
            CREATE TABLE IF NOT EXISTS samples(key TEXT, t REAL, runner TEXT, data TEXT);
            CREATE INDEX IF NOT EXISTS samples_key ON samples(key);
            CREATE TABLE IF NOT EXISTS events(key TEXT, t REAL, runner TEXT, slot TEXT, kind TEXT, msg TEXT);
            CREATE INDEX IF NOT EXISTS events_key ON events(key);
            CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, created REAL, data TEXT);
        ''')
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.version = 0
        self.live = {}        # key -> {name: doc}
        self.seen = {}        # (key, runner) -> (beat, our clock when it changed)
        self.tel = {}         # (key, runner) -> the last unsealed snapshot
        self.rate = {}        # (key, runner) -> (t, requests) of the previous snapshot, for pages per minute
        self.ppm = {}
        self.last_n = {}      # (key, runner, nonce) -> the newest telemetry event already stored
        self.runs = []
        self.jobs = {}        # run id -> [job]
        self.errors = {}
        self.refs = {}        # ref -> sha already read

    # git, into the cache repository
    def git(self, *args):
        done = self.run(['git', '-C', str(self.cache), *args], capture_output=True, timeout=60,
                        env=dict(os.environ, LC_ALL='C', GIT_TERMINAL_PROMPT='0'))
        if done.returncode != 0:
            raise RuntimeError(f'git {args[0]}: {done.stderr.decode("utf-8", "replace").strip()[-200:]}')
        return done.stdout.decode('utf-8', 'replace')

    def _init_cache(self):
        if not (self.cache / 'HEAD').exists():
            self.cache.mkdir(parents=True, exist_ok=True)
            self.git('init', '-q', '--bare')

    def read_refs(self):
        """{ref: doc} of the pass and archive refs that changed since the last read (fetched by ref, read by the
        fetched copy: a ref that moved meanwhile is read as it now is)."""
        self._init_cache()
        listed = {}
        for line in self.git('ls-remote', self.remote, f'{PASS_ROOT}*', f'{ARCHIVE_ROOT}*').splitlines():
            sha, _, ref = line.partition('\t')
            listed[ref] = sha
        for ref in list(self.refs):
            if ref not in listed:
                del self.refs[ref]
        known = self._archived()
        want = [r for r, sha in listed.items() if self.refs.get(r) != sha
                and not (r.startswith(ARCHIVE_ROOT) and r[len(ARCHIVE_ROOT):] in known)]
        out = {}
        for i in range(0, len(want), 100):
            part = want[i:i + 100]
            self.git('fetch', '-q', '--no-tags', '--no-write-fetch-head', self.remote,
                     *[f'+{r}:{LOCAL}{r[len("refs/"):]}' for r in part])
            for r in part:
                path = 'pass.json' if r.startswith(ARCHIVE_ROOT) else 'doc.json'
                try:
                    out[r] = json.loads(self.git('cat-file', 'blob', f'{LOCAL}{r[len("refs/"):]}:{path}'))
                    self.refs[r] = listed[r]
                except (RuntimeError, ValueError):
                    continue
        return out, set(listed)

    def _archived(self):
        return {k for (k,) in self.db.execute("SELECT key FROM passes WHERE source IN ('live', 'archive')")}

    def unseal(self, doc):
        return telemetry.unseal(doc.get('tel'), self.key) if self.key and doc.get('tel') else None

    # what a read brought
    def ingest(self, changed, listed):
        now = self.clock()
        with self.lock:
            for ref, doc in changed.items():
                if ref.startswith(ARCHIVE_ROOT):
                    self._archive(ref[len(ARCHIVE_ROOT):], doc, now)
                    continue
                rest = ref[len(PASS_ROOT):]
                key, _, name = rest.partition('/')
                if not KEY_RE.match(key) or not NAME_RE.match(name) or not isinstance(doc, dict):
                    continue
                prev = dict(self.live.get(key, {}))
                self.live.setdefault(key, {})[name] = doc
                for slot, runner, kind, msg in diff_events(prev, {name: doc}):
                    self.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?)', (key, now, runner, slot, kind, msg))
                if name.startswith('r/'):
                    self._runner(key, name[2:], doc, now)
            # a pass whose refs went (swept): what was seen of it is its record
            for key in list(self.live):
                if not any(r.startswith(f'{PASS_ROOT}{key}/') for r in listed):
                    self._finish(key, now)
            for key in self.live:
                if self.active(key, now):
                    self._sample(key, now)
                self.db.execute('INSERT OR IGNORE INTO passes VALUES (?,?,?,?,?,?,?)',
                                (key, int(key.split('-')[1]), int(key.split('-')[0]), now, now, None, 'seen'))
                self.db.execute('UPDATE passes SET last=?, view=? WHERE key=?',
                                (now, json.dumps(self.pass_view(key, now)), key))
            self.db.commit()
            self.version += 1
            self.cond.notify_all()

    def _runner(self, key, runner, doc, now):
        beat = doc.get('beat')
        if self.seen.get((key, runner), (None,))[0] != beat:
            self.seen[(key, runner)] = (beat, now)
        tel = self.unseal(doc)
        if not tel:
            return
        self.tel[(key, runner)] = tel
        n = req_totals(tel).get('n', 0)
        prev = self.rate.get((key, runner))
        if prev and tel['t'] > prev[0]:
            self.ppm[(key, runner)] = round((n - prev[1]) * 60 / (tel['t'] - prev[0]), 1)
        self.rate[(key, runner)] = (tel['t'], n)
        mark = (key, runner, doc.get('nonce'))
        newest = self.last_n.get(mark, 0)
        for e in tel.get('events') or ():
            if e.get('n', 0) > newest:
                self.db.execute('INSERT INTO events VALUES (?,?,?,?,?,?)',
                                (key, e.get('t', now), runner, e.get('fac'), e.get('kind', 'log'), e.get('msg', '')))
        self.last_n[mark] = max([newest] + [e.get('n', 0) for e in tel.get('events') or ()])

    def _sample(self, key, now):
        docs = self.live.get(key, {})
        hunting = {(d.get('hunting') or {}).get('runner') for n, d in docs.items() if n.startswith('s/')
                   and d.get('state') in ('open', 'listing', 'unlisted')}
        for name, doc in docs.items():
            if not name.startswith('r/'):
                continue
            r = name[2:]
            age = now - self.seen.get((key, r), (None, now))[1]
            tel = self.tel.get((key, r)) or {}
            self.db.execute('INSERT INTO samples VALUES (?,?,?,?)', (key, now, r, json.dumps({
                'status': runner_status(doc, age, r in hunting), 'lanes': doc.get('lanes') or {},
                'sys': tel.get('sys'), 'ppm': self.ppm.get((key, r)), 'req': req_totals(tel)})))

    def active(self, key, now):
        """Whether a pass with refs on the stack is still running: its run not completed (a pass whose report never
        swept it stays on the stack for hours, finished)."""
        run = next((r for r in self.runs if r['id'] == int(key.split('-')[1])), None)
        if run is not None:
            return run.get('status') != 'completed'
        return now - int(key.split('-')[0]) < 3 * 3600

    def _finish(self, key, now):
        self.db.execute("UPDATE passes SET source='live', view=? WHERE key=?", (json.dumps(self.pass_view(key, now)), key))
        del self.live[key]
        for k in [k for k in self.seen if k[0] == key]:
            self.seen.pop(k, None)

    def _archive(self, key, docs, now):
        if not KEY_RE.match(key) or not isinstance(docs, dict):
            return
        row = self.db.execute('SELECT source FROM passes WHERE key=?', (key,)).fetchone()
        if row and row[0] == 'live':
            return  # watched live: that record is richer
        saved, self.live[key] = self.live.get(key), {n: d for n, d in docs.items() if NAME_RE.match(n)}
        for n, d in self.live[key].items():
            if n.startswith('r/'):
                self.tel[(key, n[2:])] = self.unseal(d) or {}
        view = self.pass_view(key, now, archived=True)
        if saved is None:
            del self.live[key]
        else:
            self.live[key] = saved
        self.db.execute('INSERT OR REPLACE INTO passes VALUES (?,?,?,?,?,?,?)',
                        (key, int(key.split('-')[1]), int(key.split('-')[0]), now, now, json.dumps(view), 'archive'))

    def pass_view(self, key, now, archived=False):
        docs = self.live.get(key, {})
        slots = [slot_view(n, d) for n, d in sorted(docs.items()) if n.startswith('s/')]
        hunting = {s['hunting'] for s in slots if s['hunting'] and s['state'] != 'closed'}
        runners = []
        for name, doc in sorted(docs.items()):
            if not name.startswith('r/'):
                continue
            r = name[2:]
            age = None if archived else now - self.seen.get((key, r), (None, now))[1]
            tel = self.tel.get((key, r)) or {}
            runners.append({'runner': r, 'mode': doc.get('mode'), 'status': runner_status(doc, age, r in hunting),
                            'age': None if age is None else round(age), 'lanes': doc.get('lanes') or {},
                            'sealed': bool(doc.get('tel')), 'tel': bool(tel), 'sys': tel.get('sys') or {},
                            'req': tel.get('req') or {}, 'totals': req_totals(tel), 'gauges': tel.get('gauges') or {},
                            'ppm': self.ppm.get((key, r)),
                            'done': sum(s['by'].get(r, 0) for s in slots),
                            'led': [s['slot'] for s in slots if s['leader'] == r]})
        return {'key': key, 'run': int(key.split('-')[1]), 'planned': int(key.split('-')[0]), 'slots': slots,
                'runners': runners, 'total': sum(s['total'] for s in slots), 'done': sum(s['done'] for s in slots),
                'changed': sum(s['changed'] for s in slots),
                'open': sum(1 for s in slots if s['state'] != 'closed')}

    # GitHub runs
    def gh(self, path):
        done = self.run(['gh', 'api', path], capture_output=True, timeout=60)
        if done.returncode != 0:
            raise RuntimeError(f'gh api: {done.stderr.decode("utf-8", "replace").strip()[-200:]}')
        return json.loads(done.stdout)

    def read_runs(self):
        got = self.gh(f'repos/{self.gh_repo}/actions/workflows/refresh.yml/runs?per_page=30')
        runs = []
        for r in got.get('workflow_runs') or ():
            run = {k: r.get(k) for k in ('id', 'status', 'conclusion', 'event', 'head_branch', 'created_at',
                                         'updated_at', 'run_started_at', 'html_url', 'display_title')}
            runs.append(run)
            if r.get('status') != 'completed' or r['id'] not in self.jobs:
                jobs = self.gh(f'repos/{self.gh_repo}/actions/runs/{r["id"]}/jobs?per_page=50').get('jobs') or ()
                self.jobs[r['id']] = [{k: j.get(k) for k in ('name', 'status', 'conclusion', 'created_at',
                                                            'started_at', 'completed_at', 'runner_name')}
                                      for j in jobs]
            run['jobs'] = self.jobs.get(r['id'], [])
        with self.lock:
            self.runs = runs
            for run in runs:
                self.db.execute('INSERT OR REPLACE INTO runs VALUES (?,?,?)',
                                (run['id'], _epoch(run.get('created_at')), json.dumps(run)))
            self.db.commit()
            self.version += 1
            self.cond.notify_all()

    def prune(self):
        cut = self.clock() - KEEP_DAYS * 86400
        with self.lock:
            for table, col in (('samples', 't'), ('events', 't'), ('passes', 'last'), ('runs', 'created')):
                self.db.execute(f'DELETE FROM {table} WHERE {col} < ?', (cut,))
            self.db.commit()

    def loop(self, halt):
        last_gh = last_prune = 0
        while not halt.is_set():
            # the runs first: they tell a running pass from one its report never swept
            for name, step in (('runs', self.read_runs if self.clock() - last_gh >= GH_POLL else None),
                               ('stack', lambda: self.ingest(*self.read_refs())),
                               ('prune', self.prune if self.clock() - last_prune >= 3600 else None)):
                if step is None:
                    continue
                try:
                    step()
                    self.errors.pop(name, None)
                except Exception as err:  # a dashboard reports trouble, it never stops for it
                    self.errors[name] = str(err)[:300]
                if name == 'runs':
                    last_gh = self.clock()
                if name == 'prune':
                    last_prune = self.clock()
            halt.wait(POLL)

    # what the page reads
    def state(self):
        now = self.clock()
        with self.lock:
            live = [self.pass_view(k, now) for k in sorted(self.live, reverse=True) if self.active(k, now)]
            key = live[0]['key'] if live else None
            if key is None:
                row = self.db.execute('SELECT key FROM passes ORDER BY planned DESC LIMIT 1').fetchone()
                key = row[0] if row else None
            return {'now': now, 'version': self.version, 'key_loaded': bool(self.key), 'errors': dict(self.errors),
                    'live': live, 'last': self._pass(key) if key and not live else None,
                    'timeline': self._timeline(key) if key else [], 'events': self._events(key) if key else [],
                    'runs': self.runs[:12]}

    def _pass(self, key):
        row = self.db.execute('SELECT view FROM passes WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row and row[0] else None

    def _timeline(self, key):
        return [[t, r, json.loads(d)] for t, r, d in
                self.db.execute('SELECT t, runner, data FROM samples WHERE key=? ORDER BY t', (key,))]

    def _events(self, key, limit=400):
        rows = self.db.execute('SELECT t, runner, slot, kind, msg FROM events WHERE key=? ORDER BY t DESC LIMIT ?',
                               (key, limit)).fetchall()
        return [{'t': t, 'runner': r, 'slot': s, 'kind': k, 'msg': m} for t, r, s, k, m in rows]

    def history(self, days=14):
        cut = self.clock() - days * 86400
        with self.lock:
            passes = [json.loads(v) | {'source': src} for v, src in self.db.execute(
                'SELECT view, source FROM passes WHERE planned >= ? AND view IS NOT NULL ORDER BY planned', (cut,))]
            runs = {r: json.loads(d) for r, d in self.db.execute('SELECT id, data FROM runs WHERE created >= ?',
                                                                  (cut,))}
            util = {}
            for key, runner, data in self.db.execute(
                    'SELECT s.key, s.runner, s.data FROM samples s JOIN passes p ON p.key = s.key WHERE p.planned >= ?',
                    (cut,)):
                st = json.loads(data).get('status')
                util.setdefault(key, {}).setdefault(runner, {}).setdefault(st, 0)
                util[key][runner][st] += 1
        for p in passes:
            p['run_info'] = runs.get(p['run'])
            p['util'] = util.get(p['key'], {})
            for s in p['slots']:
                s.pop('chunks', None)
        return {'passes': passes, 'runs': sorted(runs.values(), key=lambda r: r.get('created_at') or '')}


def _epoch(iso):
    try:
        return calendar.timegm(time.strptime(iso, '%Y-%m-%dT%H:%M:%SZ'))
    except (TypeError, ValueError):
        return 0


# -- the page ------------------------------------------------------------------------------------------------------

def make_handler(collector, port):
    allowed = {f'127.0.0.1:{port}', f'localhost:{port}'}

    class Handler(BaseHTTPRequestHandler):
        server_version = 'planwat-dash'

        def log_message(self, *a):
            pass

        def _send(self, body, ctype='application/json', code=200):
            data = body if isinstance(body, bytes) else body.encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Security-Policy', CSP)
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            # only this machine's own names: a page elsewhere cannot rebind a hostname of its own onto this port
            if self.headers.get('Host') not in allowed:
                return self._send('{"error":"wrong host"}', code=421)
            url = urlsplit(self.path)
            if url.path in STATIC:
                fname, ctype = STATIC[url.path]
                return self._send((HERE / fname).read_bytes(), ctype)
            if url.path == '/api/state':
                return self._send(json.dumps(collector.state()))
            if url.path == '/api/history':
                try:
                    days = max(1, min(KEEP_DAYS, int(parse_qs(url.query).get('days', ['14'])[0])))
                except ValueError:
                    days = 14
                return self._send(json.dumps(collector.history(days)))
            if url.path == '/events':
                return self._stream()
            return self._send('{"error":"not found"}', code=404)

        def _stream(self):
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            seen = -1
            try:
                while True:
                    with collector.cond:
                        if collector.version == seen:
                            collector.cond.wait(15)
                        changed = collector.version != seen
                        seen = collector.version
                    if changed:
                        self.wfile.write(f'data: {json.dumps(collector.state())}\n\n'.encode())
                    else:
                        self.wfile.write(b': keepalive\n\n')
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

    return Handler


def load_key():
    key = os.environ.get('PLANWAT_DASH_KEY', '').strip()
    path = Path.home() / '.config' / 'planwat' / 'dash.key'
    if not key and path.is_file():
        if path.stat().st_mode & 0o077:
            print(f'dash: {path} is readable by others; chmod 600 it', file=sys.stderr)
        key = path.read_text().strip()
    return key


def gh_repo_of(url):
    m = re.search(r'github\.com[:/]([\w.-]+/[\w.-]+?)(?:\.git)?/?$', url or '')
    return m.group(1) if m else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', type=int, default=PORT)
    ap.add_argument('--no-browser', action='store_true')
    ap.add_argument('--data', default=str(Path.home() / '.local' / 'share' / 'planwat-dash'))
    ap.add_argument('--cache', default=str(Path.home() / '.cache' / 'planwat-dash' / 'git'))
    args = ap.parse_args(argv)
    remote = subprocess.run(['git', '-C', str(ROOT), 'remote', 'get-url', 'origin'],
                            capture_output=True, text=True).stdout.strip()
    if not remote:
        print('dash: this checkout has no origin remote', file=sys.stderr)
        return 1
    Path(args.data).mkdir(parents=True, exist_ok=True)
    key = load_key()
    if not key:
        print('dash: no key (~/.config/planwat/dash.key): the runners\' telemetry stays sealed', file=sys.stderr)
    collector = Collector(Path(args.data) / 'dash.db', args.cache, key, remote, gh_repo_of(remote))
    halt = threading.Event()
    threading.Thread(target=collector.loop, args=(halt,), daemon=True, name='collector').start()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(collector, args.port))
    server.daemon_threads = True
    url = f'http://127.0.0.1:{args.port}/'
    print(f'dash: {url} (Ctrl+C stops it)')
    if not args.no_browser:
        import webbrowser
        threading.Timer(0.5, webbrowser.open, (url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        halt.set()
        server.server_close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
