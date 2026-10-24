#!/usr/bin/env python3
"""Edit who may crawl, and how far they are trusted, in a page in your browser.

    python tools/volunteer/manage.py [--port 8765] [--no-browser]

The registry (volunteers.json) lives alone on the `volunteers` branch. This tool shows it next to what the
coordinator knows about each volunteer (last bundle, online or not, crawler version, refusals, blocked faculties,
token expiry, accepted calendars, strikes, benched; read from the `data` branch) and how well each faculty is
covered (groups nobody checked in a day), lets you change trust levels, faculties and the quorum rules, and saves the result as one commit signed
with your own git signing key, pushed straight to that branch. collect.yml takes a registry only from a commit
that GitHub verifies as signed by a maintainer, so the change is live at the next coordinator pass (within 30
minutes) and nobody else can make one.

The page is served on 127.0.0.1 only, behind a random token in its address, and refuses requests that come
with another Host, so nothing else on the machine or the network can drive it.
"""
import argparse
import datetime as dt
import http.server
import json
import os
import secrets
import shutil
import subprocess
import time
import sys
import threading
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'refresh'))
sys.path.insert(0, str(HERE))
import assign  # noqa: E402
import core  # noqa: E402
import registry  # noqa: E402

BRANCH = 'volunteers'
FILE = 'volunteers.json'
UPSTREAM = 'kilerdevs/PlanWAT'
# A new registry asks for no more than the crawler of this checkout (package.json), never for a release that
# does not exist yet: a higher minimum would stop every running crawler until somebody edited it by hand.
DEFAULT = {'quorum': 2, 'window_hours': 12,
           'min_version': json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version'], 'volunteers': []}
MAX_BODY = 256 * 1024
STALE_HOURS = 24
GIT_TIMEOUT = 120


class SaveError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class Repo:
    """The git side: read the registry and the coordinator's state, write a signed registry commit."""

    def __init__(self, root=ROOT, remote='origin', sign=True, upstream=UPSTREAM, verify=None):
        self.root, self.remote, self.sign, self.upstream = Path(root), remote, sign, upstream
        self.verify = sign if verify is None else verify
        self.editors = os.environ.get('PLANWAT_REGISTRY_EDITORS') or registry.DEFAULT_EDITORS
        self.fetch_errors = {}

    def git(self, *args, stdin=None, check=True, timeout=GIT_TIMEOUT, env=None):
        # Never a credential prompt nobody sees, never a hang: a bad remote becomes an error on the page.
        try:
            out = subprocess.run(['git', '-C', str(self.root), *args], input=stdin, capture_output=True, text=True,
                                 timeout=timeout, env={**os.environ, 'GIT_TERMINAL_PROMPT': '0', **(env or {})})
        except subprocess.TimeoutExpired:
            out = subprocess.CompletedProcess(args, 124, '', f'git {args[0]}: no answer in {timeout} s')
        if check and out.returncode:
            raise SaveError((out.stderr or out.stdout).strip()[-500:] or f'git {args[0]} failed', 500)
        return out

    def fetch(self):
        """Fetch both branches. A branch that does not exist yet is fine; any other failure is kept in
        fetch_errors, so the page says the remote failed instead of showing an empty, brand-new project."""
        self.fetch_errors = {}
        for branch in (BRANCH, 'data'):
            out = self.git('fetch', '-q', self.remote, f'+refs/heads/{branch}:refs/remotes/{self.remote}/{branch}',
                           check=False, env={'LC_ALL': 'C'})  # untranslated, to tell "no such branch" apart
            if out.returncode and "couldn't find remote ref" not in out.stderr:
                self.fetch_errors[branch] = (out.stderr or out.stdout).strip()[-300:] or f'git fetch {branch} failed'

    def head(self):
        out = self.git('rev-parse', '--verify', '-q', f'refs/remotes/{self.remote}/{BRANCH}', check=False)
        return out.stdout.strip() or None

    def show(self, ref, path):
        out = self.git('show', f'{ref}:{path}', check=False)
        return out.stdout if out.returncode == 0 else None

    def registry(self):
        text = self.show(f'refs/remotes/{self.remote}/{BRANCH}', FILE)
        return assign.check_registry(json.loads(text)) if text else assign.check_registry(DEFAULT)

    def data_json(self, path):
        text = self.show(f'refs/remotes/{self.remote}/data', path)
        try:
            found = json.loads(text) if text else {}
        except ValueError:
            found = {}
        return found if isinstance(found, dict) else {}

    def status(self, now=None):
        """What the coordinator knows per login (volunteer-state.json on data)."""
        now = now or core.now_utc()
        state = self.data_json(core.VOLUNTEER_STATE_FILE)
        accepted = {}
        for entry in (state.get('groups') or {}).values():
            for login in entry.get('by', []) if isinstance(entry, dict) else []:
                accepted[login.lower()] = accepted.get(login.lower(), 0) + 1
        seen, strikes, benched = (state.get(k) or {} for k in ('seen', 'strikes', 'benched'))
        health = state.get('volunteers') if isinstance(state.get('volunteers'), dict) else {}
        out = {}
        for login in {*seen, *strikes, *benched, *health, *accepted}:
            record = health.get(login) if isinstance(health.get(login), dict) else {}
            last = record.get('ended') or (seen.get(login) or {}).get('ended')
            ended = assign._stamp(last) if last else None
            days = record.get('days') if isinstance(record.get('days'), dict) else {}
            out.setdefault(login.lower(), {}).update({
                'last': last,
                'online': bool(ended and now - ended < dt.timedelta(hours=assign.LIVE_HOURS)),
                'version': record.get('version'),
                'refused': record.get('refused'),
                'blocked': sorted(record.get('blocked') or {}),
                'token_expires': record.get('token_expires'),
                'week': sum(d[2] for d in days.values() if isinstance(d, list) and len(d) == 3),
                'reasons': (record.get('last') or {}).get('reasons') or [],
                'strikes': len(strikes.get(login, [])),
                'benched': benched.get(login),
                'accepted': accepted.get(login.lower(), 0),
            })
        return out

    def coverage(self, now=None):
        """[{faculty, groups, stale}]: the published groups of the running term per faculty, and how many of them
        nobody trusted (the home runner, or an accepted volunteer check) looked at in the last STALE_HOURS."""
        now = now or core.now_utc()
        tid = core.term_id(now.date())
        listing = self.git('ls-tree', '--name-only', f'refs/remotes/{self.remote}/data', f'timetables/{tid}/',
                           check=False).stdout.split()
        home = self.data_json(core.STATE_FILE).get('groups') or {}
        volunteers = self.data_json(core.VOLUNTEER_STATE_FILE).get('groups') or {}
        cutoff = (now - dt.timedelta(hours=STALE_HOURS)).isoformat()
        labels = {f['label'].upper(): f['label'] for f in faculties()}
        labels.setdefault('WMT', labels.get('WML', 'WML'))
        rows = {}
        for path in listing:
            code = Path(path).stem
            label = next((labels[p] for p in sorted(labels, key=len, reverse=True) if code.upper().startswith(p)), 'WIM')
            marks = [(volunteers.get(f'{code}@{tid}') or {}).get('checked') or '']
            entry = home.get(code) or {}
            if isinstance(entry, dict) and entry.get('term') == tid:
                marks.append(entry.get('checked') or '')
            row = rows.setdefault(label, {'faculty': label, 'groups': 0, 'stale': 0})
            row['groups'] += 1
            row['stale'] += max(marks) < cutoff
        return sorted(rows.values(), key=lambda r: r['faculty'])

    def save(self, registry, base, message):
        """Commit `registry` on top of `base` (None: the branch is new) and push it; returns the commit id."""
        self.fetch()
        if BRANCH in self.fetch_errors:
            raise SaveError(f'Nie udało się pobrać gałęzi {BRANCH}: {self.fetch_errors[BRANCH]}', 502)
        if self.head() != base:
            raise SaveError('Rejestr zmienił się w międzyczasie. Odśwież stronę i wprowadź zmiany jeszcze raz.', 409)
        text = json.dumps(registry, ensure_ascii=False, indent=1) + '\n'
        blob = self.git('hash-object', '-w', '--stdin', stdin=text).stdout.strip()
        tree = self.git('mktree', stdin=f'100644 blob {blob}\t{FILE}\n').stdout.strip()
        args = ['commit-tree', tree, '-m', message]
        if base:
            args += ['-p', base]
        if self.sign:
            args.insert(1, '-S')
        commit = self.git(*args, timeout=None).stdout.strip()  # signing may wait for a passphrase
        self.git('push', '-q', self.remote, f'{commit}:refs/heads/{BRANCH}')
        self.fetch()
        return commit

    def verified(self, commit, tries=6, pause=5, sleep=time.sleep):
        """'' once GitHub verifies `commit` as the branch head signed by a registry editor (what collect.yml and
        every crawler require); otherwise what is wrong, for the person who just saved."""
        if not self.verify:
            return ''
        why = ''
        for attempt in range(tries):
            try:
                _, _, sha, _ = registry.fetch_verified(self.upstream, self.editors)
            except assign.RegistryError as err:
                return (f'GitHub nie uznaje commita {commit[:7]} za podpisany przez opiekuna ({err}), więc koordynator i '
                        f'crawlery go odrzucą. Sprawdź, czy klucz podpisu (git config user.signingkey) i e-mail '
                        f'(user.email) są dodane na GitHubie, i zapisz jeszcze raz.')
            except (registry.Missing, registry.Unavailable) as err:
                why = str(err)
            else:
                if sha == commit:
                    return ''
                why = f'GitHub widzi jeszcze {sha[:7]}'
            if attempt + 1 < tries:
                sleep(pause)
        return f'nie udało się potwierdzić podpisu commita {commit[:7]} na GitHubie ({why}); sprawdź za chwilę.'

    def unbench(self, login):
        if not shutil.which('gh'):
            raise SaveError('Przywracanie uruchamia collect.yml przez GitHub CLI: zainstaluj gh i zaloguj się '
                            '(gh auth login) albo użyj Actions → Collect volunteer crawls → Run workflow z unbench.', 500)
        try:
            out = subprocess.run(['gh', 'workflow', 'run', 'collect.yml', '--repo', self.upstream,
                                  '-f', f'unbench={login}'], cwd=self.root, capture_output=True, text=True,
                                 timeout=GIT_TIMEOUT)
        except (OSError, subprocess.TimeoutExpired) as err:
            raise SaveError(f'gh workflow run: {err}', 500)
        if out.returncode:
            raise SaveError((out.stderr or 'gh workflow run failed').strip()[-500:], 500)


def faculties():
    sources = json.loads((ROOT / 'tools' / 'refresh' / 'sources.json').read_text(encoding='utf-8'))
    return [{'id': k, 'label': v.get('label', k.upper())} for k, v in sources.items() if v.get('enabled')]


def describe(old, new):
    """A one-line summary of what changed between two registries, for the commit message."""
    before = {v['login'].lower(): v for v in old['volunteers']}
    after = {v['login'].lower(): v for v in new['volunteers']}
    names = {'trusted': 'zaufany', 'peer': 'równorzędny', 'suspended': 'wstrzymany'}
    parts = []
    for key, v in after.items():
        was = before.get(key)
        if was is None:
            parts.append(f'+{v["login"]} ({names[v["trust"]]})')
            continue
        if was['trust'] != v['trust']:
            parts.append(f'{v["login"]}: {names[v["trust"]]}')
        if was['faculties'] != v['faculties'] or was['fork'] != v['fork']:
            parts.append(f'{v["login"]}: ' + (', '.join(v['faculties']) or 'wszystkie wydziały'))
    parts += [f'-{was["login"]}' for key, was in before.items() if key not in after]
    for field, label in (('quorum', 'kworum'), ('window_hours', 'okno'), ('min_version', 'min. wersja')):
        if old[field] != new[field]:
            parts.append(f'{label} {new[field]}')
    return 'Volunteers: ' + ('; '.join(parts) if parts else 'no change')


def make_handler(repo, token):
    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = 'planwat-volunteers'

        def log_message(self, fmt, *args):
            pass

        def allowed(self):
            host = (self.headers.get('Host') or '').rsplit(':', 1)[0]
            return host in ('127.0.0.1', 'localhost')

        def reply(self, status, body, kind='application/json; charset=utf-8'):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; "
                             "script-src 'unsafe-inline'; connect-src 'self'; img-src data:; "
                             "frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(data)

        def authorised(self):
            return secrets.compare_digest(self.headers.get('X-Token', ''), token)

        def do_GET(self):
            if not self.allowed():
                return self.reply(403, {'error': 'forbidden'})
            if self.path.split('?')[0] == '/':
                return self.reply(200, PAGE.encode('utf-8'), 'text/html; charset=utf-8')
            if self.path == '/api/state':
                if not self.authorised():
                    return self.reply(403, {'error': 'Zły token: otwórz adres wypisany w terminalu.'})
                repo.fetch()
                try:
                    return self.reply(200, state(repo))
                except (ValueError, SaveError) as err:
                    return self.reply(500, {'error': f'Nie da się odczytać rejestru: {err}'})
            return self.reply(404, {'error': 'not found'})

        def do_POST(self):
            if not self.allowed() or not self.authorised():
                return self.reply(403, {'error': 'Zły token: otwórz adres wypisany w terminalu.'})
            if not (self.headers.get('Content-Type') or '').startswith('application/json'):
                return self.reply(415, {'error': 'JSON only'})
            length = int(self.headers.get('Content-Length') or 0)
            if length > MAX_BODY:
                return self.reply(413, {'error': 'too big'})
            try:
                body = json.loads(self.rfile.read(length) or b'{}')
                if self.path == '/api/save':
                    return self.reply(200, save(repo, body))
                if self.path == '/api/unbench':
                    login = str(body.get('login', ''))
                    if not assign.LOGIN_RE.match(login):
                        raise SaveError('Zły login.')
                    repo.unbench(login)
                    return self.reply(200, {'ok': True})
            except SaveError as err:
                return self.reply(err.status, {'error': str(err)})
            except (ValueError, assign.RegistryError) as err:
                return self.reply(400, {'error': str(err)})
            return self.reply(404, {'error': 'not found'})

    return Handler


def state(repo):
    # An unreadable registry on the branch is shown, not a dead end: the page offers to replace it.
    try:
        current, broken = repo.registry(), ''
    except (ValueError, assign.RegistryError) as err:
        current, broken = assign.check_registry(DEFAULT), str(err)[:300]
    return {'registry': current, 'broken': broken, 'base': repo.head(), 'status': repo.status(),
            'coverage': repo.coverage(), 'faculties': faculties(), 'branch': BRANCH,
            'fetch_errors': repo.fetch_errors}


def save(repo, body):
    if not isinstance(body, dict):
        raise SaveError('Zły format.')
    try:
        new = assign.check_registry(body.get('registry'))
    except assign.RegistryError as err:
        raise SaveError(f'Rejestr się nie zgadza: {err}')
    try:
        old, broken = repo.registry(), False
    except (ValueError, assign.RegistryError):
        old, broken = assign.check_registry(DEFAULT), True
    message = describe(old, new)
    if broken:
        message = 'Volunteers: nieczytelny rejestr zastąpiony' + (
            '' if message.endswith('no change') else '; ' + message.removeprefix('Volunteers: '))
    elif message.endswith('no change'):
        raise SaveError('Nic się nie zmieniło.')
    note = str(body.get('note') or '').strip()[:500]
    commit = repo.save(new, body.get('base'), message + (f'\n\n{note}' if note else ''))
    return {'ok': True, 'commit': commit, 'message': message, 'warning': repo.verified(commit), **state(repo)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--no-browser', action='store_true')
    args = ap.parse_args(argv)
    repo = Repo()
    repo.fetch()
    token = secrets.token_urlsafe(24)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(repo, token))
    url = f'http://127.0.0.1:{server.server_port}/#t={token}'
    print(f'Wolontariusze: {url}\n(Ctrl+C kończy)', flush=True)
    if not args.no_browser:
        threading.Timer(0.3, webbrowser.open, (url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


PAGE = r'''<!doctype html><html lang="pl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark light">
<meta name="referrer" content="no-referrer">
<title>PlanWAT wolontariusze</title>
<style>
  :root {
    --bg:#000; --s2:#1c1c1e; --s3:#2c2c2e; --s4:#3a3a3c;
    --t1:#f5f5f7; --t2:#a1a1a6; --t3:#86868b; --hl:255,255,255;
    --line:rgba(var(--hl),.08); --line-2:rgba(var(--hl),.14); --edge:inset 0 1px 0 rgba(var(--hl),.06);
    --accent:#0a84ff; --accent-text:#4da3ff; --accent-soft:rgba(10,132,255,.14);
    --free:#32d74b; --busy:#ff6b63; --warn:#ffb340;
    --font:-apple-system,BlinkMacSystemFont,"SF Pro Text","Inter",system-ui,sans-serif;
    --r-card:16px; --r-ctl:12px; --r-pill:999px; --ease-out:cubic-bezier(.22,1,.36,1);
    color-scheme:dark;
  }
  @media (prefers-color-scheme: light) {
    :root {
      --bg:#f2f2f7; --s2:#fff; --s3:#e9e9ee; --s4:#d8d8de;
      --t1:#1c1c1e; --t2:#55555a; --t3:#6c6c70; --hl:0,0,0;
      --line:rgba(0,0,0,.12); --line-2:rgba(0,0,0,.2); --edge:inset 0 1px 0 rgba(255,255,255,.8);
      --accent-text:#0059cf; --accent-soft:rgba(10,132,255,.12);
      --free:#17782e; --busy:#c8372f; --warn:#a35200; color-scheme:light;
    }
  }
  *,*::before,*::after { box-sizing:border-box; }
  html,body { background:var(--bg); }
  body { margin:0; color:var(--t1); font:15px/1.45 var(--font); -webkit-font-smoothing:antialiased; }
  main { max-width:1000px; margin:0 auto; padding:36px 16px 140px; }
  h1 { margin:0; font-size:1.75rem; letter-spacing:-.035em; }
  h2 { margin:0 0 12px; font-size:1.0625rem; font-weight:600; }
  .sub { margin:4px 0 24px; color:var(--t2); font-size:.8125rem; }
  .card { padding:16px 20px 20px; border-radius:var(--r-card); background:var(--s2); box-shadow:var(--edge); margin-bottom:16px; }
  .vol { display:grid; grid-template-columns:minmax(130px,.9fr) auto minmax(0,1.5fr) minmax(210px,1.3fr) auto; gap:10px 16px;
         align-items:center; padding:14px 0; border-top:1px solid var(--line); }
  .vol:first-of-type { border-top:0; }
  .vol.changed { box-shadow:-20px 0 0 -16px var(--accent); }
  .vol.removed { opacity:.45; }
  .who b { display:block; font-weight:600; overflow-wrap:anywhere; }
  .who a { color:var(--t3); font-size:.75rem; text-decoration:none; }
  .who a:hover { color:var(--accent-text); }
  .seg { display:inline-flex; padding:3px; gap:2px; border-radius:var(--r-pill); background:var(--s3); }
  .seg button { font:inherit; font-size:.8125rem; font-weight:600; color:var(--t2); background:none; border:0;
                border-radius:var(--r-pill); padding:6px 12px; min-height:32px; cursor:pointer; white-space:nowrap;
                transition:background .15s var(--ease-out), color .15s var(--ease-out); }
  .seg button[aria-pressed="true"] { background:var(--t1); color:var(--bg); }
  .seg button[aria-pressed="true"][data-v="suspended"] { background:var(--busy); color:#fff; }
  .seg button[aria-pressed="true"][data-v="trusted"] { background:var(--accent); color:#fff; }
  button:focus-visible, input:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .chips { display:flex; flex-wrap:wrap; gap:6px; }
  .chip { font:inherit; font-size:.75rem; font-weight:600; color:var(--t2); background:none; cursor:pointer;
          border:1px solid var(--line-2); border-radius:var(--r-pill); padding:4px 10px; min-height:28px; }
  .chip[aria-pressed="true"] { background:var(--accent-soft); border-color:var(--accent); color:var(--accent-text); }
  .chip.all { border-style:dashed; }
  .stat { font-size:.75rem; color:var(--t2); }
  .stat b { color:var(--t1); font-weight:600; }
  .stat .bad { color:var(--busy); font-weight:600; }
  .stat .warn { color:var(--warn); font-weight:600; }
  .link { font:inherit; font-size:.75rem; font-weight:600; color:var(--accent-text); background:none; border:0; padding:0; cursor:pointer; }
  .icon { font:inherit; width:32px; height:32px; border-radius:50%; border:0; background:none; color:var(--t3); cursor:pointer; font-size:1.1rem; }
  .icon:hover { background:var(--s3); color:var(--busy); }
  .add { display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-top:14px; padding-top:14px; border-top:1px solid var(--line); }
  input[type=text], input[type=number] { font:inherit; color:var(--t1); background:var(--s3); border:1px solid transparent;
         border-radius:var(--r-ctl); padding:8px 12px; min-height:36px; min-width:0; }
  input[type=number] { width:90px; }
  .primary { font:inherit; font-weight:600; color:#fff; background:var(--accent); border:0; border-radius:var(--r-pill);
             padding:9px 18px; min-height:38px; cursor:pointer; }
  .primary:disabled { opacity:.4; cursor:default; }
  .ghost { font:inherit; font-weight:600; color:var(--t1); background:var(--s3); border:0; border-radius:var(--r-pill);
           padding:9px 16px; min-height:38px; cursor:pointer; }
  .rules { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:16px; }
  .rules label { display:block; font-size:.8125rem; font-weight:600; margin-bottom:6px; }
  .rules p { margin:6px 0 0; font-size:.75rem; color:var(--t3); }
  .empty { color:var(--t3); font-size:.875rem; padding:8px 0; }
  .bar { position:fixed; left:0; right:0; bottom:0; padding:12px 16px calc(12px + env(safe-area-inset-bottom));
         background:color-mix(in srgb,var(--s2) 88%,transparent); backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px);
         border-top:1px solid var(--line); transform:translateY(100%); visibility:hidden;
         transition:transform .3s var(--ease-out), visibility 0s linear .3s; }
  .bar.on { transform:none; visibility:visible; transition:transform .3s var(--ease-out); }
  .bar .in { max-width:1000px; margin:0 auto; display:flex; flex-wrap:wrap; gap:10px; align-items:center; }
  .bar .what { flex:1 1 260px; font-size:.8125rem; color:var(--t2); min-width:0; overflow-wrap:anywhere; }
  .bar input { flex:1 1 220px; }
  .dot { display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; background:var(--t3); vertical-align:1px; }
  .dot.on { background:var(--free); }
  .cov { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:10px; }
  .cov div { padding:10px 12px; border-radius:var(--r-ctl); background:var(--s3); font-size:.8125rem; color:var(--t2); }
  .cov b { display:block; color:var(--t1); font-size:.9375rem; }
  .cov .warn b { color:var(--warn); }
  .toast { position:fixed; left:50%; top:16px; transform:translate(-50%,-150%); max-width:min(560px,calc(100% - 32px));
           padding:10px 16px; border-radius:var(--r-ctl); background:var(--s3); box-shadow:0 8px 30px rgba(0,0,0,.25);
           font-size:.875rem; visibility:hidden; transition:transform .3s var(--ease-out), visibility 0s linear .3s; z-index:2; }
  .toast.on { transform:translate(-50%,0); visibility:visible; transition:transform .3s var(--ease-out); }
  .toast.err { background:var(--busy); color:#fff; }
  @media (max-width:760px) {
    .vol { grid-template-columns:1fr auto; }
    .vol .seg { grid-column:1 / -1; justify-self:start; }
    .vol .chips, .vol .stat { grid-column:1 / -1; }
    .vol .icon { grid-row:1; grid-column:2; }
  }
  @media (prefers-reduced-motion: reduce) { * { transition:none !important; } }
</style></head><body><main>
<h1>Wolontariusze</h1>
<p class="sub" id="sub">Ładowanie…</p>
<section class="card" aria-labelledby="h-vol">
  <h2 id="h-vol">Kto może crawlować</h2>
  <div id="list"></div>
  <form class="add" id="add">
    <input type="text" id="new-login" placeholder="login GitHub" aria-label="Login GitHub" autocomplete="off" required>
    <input type="text" id="new-fork" placeholder="fork (domyślnie login/PlanWAT)" aria-label="Fork" autocomplete="off">
    <button class="ghost" type="submit">Dodaj</button>
  </form>
</section>
<section class="card" aria-labelledby="h-cov">
  <h2 id="h-cov">Pokrycie</h2>
  <p class="sub" style="margin:-6px 0 12px">Grupy bieżącego semestru, których nikt zaufany (domowy runner ani przyjęci wolontariusze) nie sprawdził od doby.</p>
  <div class="cov" id="cov"></div>
</section>
<section class="card" aria-labelledby="h-rules">
  <h2 id="h-rules">Zasady głosowania</h2>
  <div class="rules">
    <div><label for="quorum">Kworum</label><input type="number" id="quorum" min="2" max="5">
      <p>Ilu wolontariuszy równorzędnych musi się zgodzić, zanim plan trafi na stronę.</p></div>
    <div><label for="window">Ważność głosu (godziny)</label><input type="number" id="window" min="2" max="48">
      <p>Głosy starsze niż to wygasają.</p></div>
    <div><label for="minver">Najstarsza wersja crawlera</label><input type="text" id="minver" placeholder="1.2.0" style="width:110px">
      <p>Paczki ze starszych wersji są odrzucane.</p></div>
  </div>
</section>
</main>
<div class="bar" id="bar" role="region" aria-label="Zapis zmian"><div class="in">
  <div class="what" id="what"></div>
  <input type="text" id="note" placeholder="Powód (opcjonalnie, trafi do commita)" aria-label="Powód">
  <button class="ghost" id="undo" type="button">Cofnij</button>
  <button class="primary" id="save" type="button">Zapisz i opublikuj</button>
</div></div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script>
(function () {
  var token = (location.hash.match(/t=([\w-]+)/) || [])[1] || '';
  var TRUST = [['trusted', 'Zaufany'], ['peer', 'Równorzędny'], ['suspended', 'Wstrzymany']];
  var saved = null, draft = null, base = null, status = {}, facs = [], removed = {}, coverage = [], broken = '';
  function $(id) { return document.getElementById(id); }
  function el(tag, attrs, kids) {
    var n = document.createElement(tag);
    for (var k in attrs || {}) { if (k === 'text') n.textContent = attrs[k]; else n.setAttribute(k, attrs[k]); }
    (kids || []).forEach(function (c) { if (c) n.appendChild(c); });
    return n;
  }
  function copy(o) { return JSON.parse(JSON.stringify(o)); }
  function api(path, body) {
    return fetch(path, { method: body ? 'POST' : 'GET', headers: Object.assign({ 'X-Token': token },
      body ? { 'Content-Type': 'application/json' } : {}), body: body ? JSON.stringify(body) : undefined })
      .then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.error || r.status); return j; }); });
  }
  function toast(msg, err) {
    var t = $('toast'); t.textContent = msg; t.className = 'toast on' + (err ? ' err' : '');
    clearTimeout(toast.t); toast.t = setTimeout(function () { t.className = 'toast' + (err ? ' err' : ''); }, err ? 7000 : 4000);
  }
  function ago(iso) {
    if (!iso) return null;
    var s = (Date.now() - Date.parse(iso + (/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? '' : 'Z'))) / 1000;
    if (s < 90) return 'przed chwilą';
    if (s < 5400) return Math.round(s / 60) + ' min temu';
    if (s < 172800) return Math.round(s / 3600) + ' h temu';
    return Math.round(s / 86400) + ' dni temu';
  }
  function load(j) {
    saved = j.registry; draft = copy(j.registry); base = j.base; status = j.status || {}; facs = j.faculties || []; removed = {};
    coverage = j.coverage || []; broken = j.broken || '';
    var failed = Object.keys(j.fetch_errors || {}).map(function (b) { return b + ': ' + j.fetch_errors[b]; });
    $('sub').textContent = failed.length ? 'Nie udało się pobrać z GitHuba (' + failed.join('; ') + '). Pokazany stan może być nieaktualny: sprawdź remote i dostęp, potem odśwież stronę.'
      : broken ? 'Rejestr na gałęzi ' + j.branch + ' jest nieczytelny (' + broken + '). Zapis zastąpi go tym, co widzisz niżej.'
      : (j.base ? 'Gałąź ' + j.branch + ' · ' + j.base.slice(0, 7) : 'Gałąź ' + j.branch + ' jeszcze nie istnieje: pierwszy zapis ją utworzy')
      + ' · zmiany działają od najbliższego przebiegu koordynatora (do 30 min).';
    render();
  }
  function find(list, login) { for (var i = 0; i < list.length; i++) if (list[i].login.toLowerCase() === login.toLowerCase()) return list[i]; return null; }
  function same(a, b) { return JSON.stringify(a) === JSON.stringify(b); }
  function changes() {
    var out = broken ? ['zastąpienie nieczytelnego rejestru'] : [], names = { trusted: 'zaufany', peer: 'równorzędny', suspended: 'wstrzymany' };
    draft.volunteers.forEach(function (v) {
      var was = find(saved.volunteers, v.login);
      if (removed[v.login.toLowerCase()]) { if (was) out.push('usunięty ' + v.login); return; }
      if (!was) { out.push('nowy ' + v.login + ' (' + names[v.trust] + ')'); return; }
      if (was.trust !== v.trust) out.push(v.login + ': ' + names[v.trust]);
      if (!same(was.faculties, v.faculties) || was.fork !== v.fork) out.push(v.login + ': ' + (v.faculties.join(', ') || 'wszystkie wydziały'));
    });
    if (saved.quorum !== draft.quorum) out.push('kworum ' + draft.quorum);
    if (saved.window_hours !== draft.window_hours) out.push('ważność ' + draft.window_hours + ' h');
    if (saved.min_version !== draft.min_version) out.push('min. wersja ' + draft.min_version);
    return out;
  }
  function seg(v) {
    var box = el('div', { 'class': 'seg', role: 'group', 'aria-label': 'Uprawnienia ' + v.login });
    TRUST.forEach(function (t) {
      var b = el('button', { type: 'button', 'data-v': t[0], 'aria-pressed': String(v.trust === t[0]), text: t[1] });
      b.addEventListener('click', function () { v.trust = t[0]; render(); });
      box.appendChild(b);
    });
    return box;
  }
  function chips(v) {
    var box = el('div', { 'class': 'chips', role: 'group', 'aria-label': 'Wydziały ' + v.login });
    var all = el('button', { type: 'button', 'class': 'chip all', 'aria-pressed': String(!v.faculties.length), text: 'Wszystkie' });
    all.addEventListener('click', function () { v.faculties = []; render(); });
    box.appendChild(all);
    facs.forEach(function (f) {
      var on = v.faculties.indexOf(f.id) >= 0;
      var b = el('button', { type: 'button', 'class': 'chip', 'aria-pressed': String(on), text: f.label });
      b.addEventListener('click', function () {
        v.faculties = on ? v.faculties.filter(function (x) { return x !== f.id; }) : v.faculties.concat([f.id]).sort();
        render();
      });
      box.appendChild(b);
    });
    return box;
  }
  function older(a, b) {
    var x = String(a || '0').split('.'), y = String(b || '0').split('.');
    for (var i = 0; i < 3; i++) { if ((+x[i] || 0) !== (+y[i] || 0)) return (+x[i] || 0) < (+y[i] || 0); }
    return false;
  }
  function stat(v) {
    var s = status[v.login.toLowerCase()] || {}, box = el('div', { 'class': 'stat' });
    var last = ago(s.last);
    box.appendChild(el('div', {}, [el('span', { 'class': 'dot' + (s.online ? ' on' : ''), 'aria-hidden': 'true' }),
      document.createTextNode(last ? (s.online ? 'Działa, paczka ' : 'Cisza od ') : 'Jeszcze bez paczki'), last ? el('b', { text: last }) : null]));
    box.appendChild(el('div', { text: 'Przyjęte w 7 dni: ' + (s.week || 0) + (s.version ? ' · crawler ' + s.version : '') }));
    if (s.version && older(s.version, draft.min_version)) box.appendChild(el('div', { 'class': 'warn', text: 'Wersja starsza niż wymagana: paczki są odrzucane' }));
    if (s.refused) box.appendChild(el('div', { 'class': 'bad', text: 'Ostatnia paczka odrzucona: ' + s.refused.reason }));
    else if (s.reasons && s.reasons.length) box.appendChild(el('div', { 'class': 'warn', text: 'Odrzucone kalendarze: ' + s.reasons[0] }));
    if (s.blocked && s.blocked.length) box.appendChild(el('div', { 'class': 'warn', text: 'Blokady: ' + s.blocked.join(', ').toUpperCase() + ' (przydziały przejmują inni)' }));
    if (s.token_expires) {
      var left = (Date.parse(s.token_expires + 'Z') - Date.now()) / 86400000;
      if (left < 14) box.appendChild(el('div', { 'class': left < 0 ? 'bad' : 'warn', text: left < 0 ? 'Token wygasł' : 'Token wygasa za ' + Math.max(0, Math.round(left)) + ' dni' }));
    }
    if (s.benched) {
      var row = el('div', {}, [el('span', { 'class': 'bad', text: 'Odsunięty przez koordynatora ' }), null]);
      var b = el('button', { type: 'button', 'class': 'link', text: 'Przywróć' });
      b.addEventListener('click', function () {
        b.disabled = true;
        api('/api/unbench', { login: v.login }).then(function () { toast('Przywracanie uruchomione (Actions → Collect volunteer crawls).'); })
          .catch(function (e) { b.disabled = false; toast(e.message, true); });
      });
      row.appendChild(b); box.appendChild(row);
    } else if (s.strikes) {
      box.appendChild(el('div', { 'class': 'warn', text: 'Niezgodności w tym tygodniu: ' + s.strikes + ' / 3' }));
    }
    return box;
  }
  function render() {
    var list = $('list'); list.textContent = '';
    if (!draft.volunteers.length) list.appendChild(el('p', { 'class': 'empty', text: 'Nikogo jeszcze nie ma. Dodaj pierwszą osobę niżej.' }));
    draft.volunteers.forEach(function (v) {
      var was = find(saved.volunteers, v.login), gone = removed[v.login.toLowerCase()];
      var row = el('div', { 'class': 'vol' + (gone ? ' removed' : (!was || !same(was, v) ? ' changed' : '')) });
      row.appendChild(el('div', { 'class': 'who' }, [el('b', { text: v.login }),
        el('a', { href: 'https://github.com/' + v.fork + '/tree/crawl', target: '_blank', rel: 'noopener', text: v.fork })]));
      row.appendChild(seg(v)); row.appendChild(chips(v)); row.appendChild(stat(v));
      var x = el('button', { type: 'button', 'class': 'icon', 'aria-label': (gone ? 'Przywróć ' : 'Usuń ') + v.login, text: gone ? '↺' : '×' });
      x.addEventListener('click', function () {
        if (!gone && was && !confirm('Usunąć ' + v.login + ' z rejestru? Po zapisie przestanie dostawać przydziały.')) return;
        removed[v.login.toLowerCase()] = !gone; render();
      });
      row.appendChild(x);
      list.appendChild(row);
    });
    var cov = $('cov'); cov.textContent = '';
    if (!coverage.length) cov.appendChild(el('p', { 'class': 'empty', text: 'Brak danych o bieżącym semestrze na gałęzi data.' }));
    coverage.forEach(function (c) {
      cov.appendChild(el('div', { 'class': c.stale ? 'warn' : '' }, [el('b', { text: c.faculty }),
        document.createTextNode(c.stale ? 'bez sprawdzenia: ' + c.stale + ' z ' + c.groups : 'sprawdzone wszystkie (' + c.groups + ')')]));
    });
    $('quorum').value = draft.quorum; $('window').value = draft.window_hours; $('minver').value = draft.min_version;
    var c = changes();
    $('what').textContent = c.length ? 'Zmiany: ' + c.join('; ') : '';
    $('bar').className = 'bar' + (c.length ? ' on' : '');
  }
  $('add').addEventListener('submit', function (e) {
    e.preventDefault();
    var login = $('new-login').value.trim(), fork = $('new-fork').value.trim() || login + '/PlanWAT';
    if (!/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$/.test(login)) return toast('To nie wygląda na login GitHub.', true);
    if (fork.split('/')[0].toLowerCase() !== login.toLowerCase()) return toast('Fork musi należeć do tego loginu.', true);
    if (find(draft.volunteers, login)) return toast(login + ' już jest na liście.', true);
    draft.volunteers.push({ login: login, fork: fork, trust: 'peer', faculties: [], added: new Date().toISOString().slice(0, 10) });
    $('new-login').value = ''; $('new-fork').value = ''; render();
  });
  $('quorum').addEventListener('input', function () { draft.quorum = parseInt(this.value, 10) || 2; render(); });
  $('window').addEventListener('input', function () { draft.window_hours = parseFloat(this.value) || 12; render(); });
  $('minver').addEventListener('change', function () { draft.min_version = this.value.trim(); render(); });
  $('undo').addEventListener('click', function () { draft = copy(saved); removed = {}; $('note').value = ''; render(); });
  $('save').addEventListener('click', function () {
    var btn = this; btn.disabled = true; btn.textContent = 'Podpisywanie…';
    var reg = copy(draft); reg.volunteers = reg.volunteers.filter(function (v) { return !removed[v.login.toLowerCase()]; });
    api('/api/save', { registry: reg, base: base, note: $('note').value })
      .then(function (j) {
        $('note').value = ''; load(j);
        if (j.warning) toast('Wypchnięto ' + j.commit.slice(0, 7) + ', ale ' + j.warning, true);
        else toast('Opublikowano ' + j.commit.slice(0, 7) + '. ' + j.message.replace(/^Volunteers: /, ''));
      })
      .catch(function (e) { toast(e.message, true); })
      .then(function () { btn.disabled = false; btn.textContent = 'Zapisz i opublikuj'; });
  });
  api('/api/state').then(load).catch(function (e) { $('sub').textContent = e.message; });
})();
</script></body></html>
'''


if __name__ == '__main__':
    sys.exit(main())
