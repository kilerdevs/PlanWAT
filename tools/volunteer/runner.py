#!/usr/bin/env python3
"""The volunteer crawler: its loop and its everyday commands (the image's entrypoint runs this).

    runner.py run       one pass per assignment window, forever (the default)
    runner.py once      one pass now, then exit
    runner.py status    what the crawler is doing, and what the coordinator said about its last bundle
    runner.py health    exit 0 while the loop is alive (the image's HEALTHCHECK)
    runner.py setup     the first-run wizard (wizard.py)
    runner.py doctor    every check, each with what to do about it (doctor.py)

Configuration comes from the environment (.env): PLANWAT_LOGIN, PLANWAT_FORK (default <login>/PlanWAT),
PLANWAT_FORK_TOKEN, PLANWAT_UPSTREAM (kilerdevs/PlanWAT), PLANWAT_REGISTRY_EDITORS (kilerdevs), PLANWAT_DRY_RUN=1,
PLANWAT_MAX_MINUTES (75), PLANWAT_WORK (/work).

A pass does only what can end in an accepted bundle, and says plainly why it stops short:
  1. clock     how far this host is off GitHub's clock; more than 30 s is corrected (PLANWAT_CLOCK_OFFSET), so
               a drifting host does not get its bundles refused as stale or from the future;
  2. registry  read only from a commit verified as signed by a registry editor (registry.py); not registered,
               suspended or an outdated crawler: no crawl, look again in a while;
  3. data      the project's data branch, fetched incrementally into the same clone every pass;
  4. verdict   what the coordinator published about this volunteer's last bundle (volunteer-state.json);
               benched: no crawl until the maintainer restores it;
  5. crawl     refresh.py --assign, with this line's own learned pacing and block durations (--faculty-state);
  6. bundle    bundle.py pushes the result (an empty bundle too: it says this crawler is alive).
Passes follow the two-hour assignment windows: one pass per window, starting 5-35 minutes after it opens, so
the volunteers sharing a group crawl in the same window and nobody hits a faculty site twice for one window.
"""
import datetime as dt
import email.utils
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'refresh'))
sys.path.insert(0, str(HERE))
import assign  # noqa: E402
import bundle  # noqa: E402
import core  # noqa: E402
import registry  # noqa: E402

UPSTREAM = 'kilerdevs/PlanWAT'
POLL = 30 * 60           # how soon to look again when there is nothing to crawl yet
STALE = 3 * 3600         # the health check fails when the loop has not written its status for this long
HEARTBEAT = 10 * 60
SKEW_FIX = 30            # seconds of clock error that get corrected
SKEW_WARN = 120
GC_EVERY = 10
JOIN = 'https://github.com/{upstream}/issues/new?template=volunteer.yml'

_child = None


def log(msg):
    print(f'{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S} {msg}', flush=True)


def config(env=None):
    env = os.environ if env is None else env
    login = env.get('PLANWAT_LOGIN', '').strip()
    try:
        minutes = float(env.get('PLANWAT_MAX_MINUTES') or 75)
    except ValueError:
        minutes = 75.0
    return {'login': login, 'fork': (env.get('PLANWAT_FORK') or f'{login}/PlanWAT').strip(),
            'token': env.get('PLANWAT_FORK_TOKEN', '').strip(),
            'upstream': (env.get('PLANWAT_UPSTREAM') or UPSTREAM).strip(),
            'editors': env.get('PLANWAT_REGISTRY_EDITORS') or registry.DEFAULT_EDITORS,
            'dry_run': env.get('PLANWAT_DRY_RUN', '0') == '1', 'max_minutes': max(10.0, min(minutes, 110.0)),
            'work': Path(env.get('PLANWAT_WORK') or '/work')}


# --- status ---------------------------------------------------------------------------------------------------

class Status:
    """/work/status.json: what the loop is doing, for `status`, `health` and the doctor."""

    def __init__(self, work):
        self.path = Path(work) / 'status.json'
        try:
            self.data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(self.data, dict):
                self.data = {}
        except (OSError, ValueError):
            self.data = {}

    def set(self, **values):
        self.data.update(values, updated=core.now_utc().isoformat(), version=bundle.version())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        tmp.replace(self.path)


# --- the steps of a pass --------------------------------------------------------------------------------------

def measure_offset(opener=urllib.request.urlopen):
    """Seconds this host's clock is behind GitHub's (negative: ahead); None when GitHub cannot be asked."""
    req = urllib.request.Request(registry.API, method='HEAD', headers={'User-Agent': 'planwat-volunteer'})
    sent = time.time()
    try:
        with opener(req, timeout=20) as r:
            stamp = r.headers.get('Date')
    except urllib.error.HTTPError as err:
        stamp = err.headers.get('Date') if err.headers else None
    except (urllib.error.URLError, OSError):
        return None
    if not stamp:
        return None
    try:
        server = email.utils.parsedate_to_datetime(stamp).timestamp()
    except (TypeError, ValueError):
        return None
    return server - (sent + time.time()) / 2


def set_clock(offset, warnings):
    """Correct this process and its children by `offset` seconds when the host is off by more than SKEW_FIX."""
    if offset is None:
        return
    os.environ['PLANWAT_CLOCK_OFFSET'] = f'{offset:.0f}' if abs(offset) > SKEW_FIX else '0'
    if abs(offset) > SKEW_WARN:
        warnings.append(f'the host clock is {abs(offset):.0f} s {"behind" if offset > 0 else "ahead"}; corrected '
                        f'for the crawl, but please turn on NTP (timedatectl set-ntp true)')


def git(*args, cwd=None, timeout=600):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'}).stdout


def sync_data(work, upstream, pass_no):
    """The project's data branch in <work>/data, fetched incrementally (a fresh clone only the first time)."""
    data = Path(work) / 'data'
    url = f'https://github.com/{upstream}.git'
    if (data / '.git').is_dir():
        try:
            git('remote', 'set-url', 'origin', url, cwd=data)
            git('fetch', '-q', '--depth=1', 'origin', 'data', cwd=data)
            git('reset', '-q', '--hard', 'FETCH_HEAD', cwd=data)
            git('clean', '-q', '-fdx', cwd=data)
            if pass_no % GC_EVERY == 0:
                git('reflog', 'expire', '--expire=now', '--all', cwd=data)
                git('gc', '-q', '--prune=now', cwd=data)
            return data
        except (subprocess.SubprocessError, OSError) as err:
            log(f'the data clone is unusable ({err}); cloning it again')
    shutil.rmtree(data, ignore_errors=True)
    git('clone', '-q', '--depth=1', '--single-branch', '--branch', 'data', url, str(data))
    return data


def published(data):
    try:
        found = json.loads((Path(data) / core.VOLUNTEER_STATE_FILE).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def verdict(state, login):
    """The coordinator's record of `login` (volunteer-state.json `volunteers`), and whether it is benched."""
    records = state.get('volunteers') if isinstance(state.get('volunteers'), dict) else {}
    record = next((r for k, r in records.items() if k.lower() == login.lower() and isinstance(r, dict)), {})
    benched = any(k.lower() == login.lower() for k in (state.get('benched') or {}))
    return record, benched


def describe_verdict(record):
    """One line about the coordinator's last word on this volunteer, or '' when it has none yet."""
    if record.get('refused'):
        ref = record['refused']
        return f'the coordinator refused the bundle of {ref.get("at", "?")}: {ref.get("reason", "?")}'
    if record.get('read'):
        last = record.get('last') or {}
        accepted = sum(day[2] for day in (record.get('days') or {}).values()
                       if isinstance(day, list) and len(day) == 3)
        line = (f'the coordinator read the bundle of {record.get("ended", "?")}: {last.get("votes", 0)} votes, '
                f'{last.get("rejected", 0)} calendars rejected; {accepted} accepted in 7 days')
        if last.get('reasons'):
            line += f' (rejected: {last["reasons"][0]})'
        return line
    return ''


def outcome_counts(path):
    try:
        groups = json.loads(Path(path).read_text(encoding='utf-8')).get('groups', {})
    except (OSError, ValueError, AttributeError):
        return {}
    counts = {}
    for entry in groups.values():
        if isinstance(entry, dict):
            counts[entry.get('status', '?')] = counts.get(entry.get('status', '?'), 0) + 1
    return counts


def run_child(cmd):
    """Run a step as a child process (so a stop signal can end it cleanly); its exit code."""
    global _child
    _child = subprocess.Popen(cmd)
    try:
        return _child.wait()
    finally:
        _child = None


def run_pass(cfg, status, pass_no=1):
    """One pass. Returns the seconds to wait before the next one, or None to wait for the next window."""
    warnings = []
    login, work = cfg['login'], cfg['work']
    started = core.now_utc()
    status.set(state='starting', message='checking the clock and the registry', warnings=[])
    set_clock(measure_offset(), warnings)
    reg_path = work / 'volunteers.json'
    try:
        reg, raw, sha, _ = registry.fetch_verified(cfg['upstream'], cfg['editors'], cfg['token'] or None)
    except registry.Missing:
        status.set(state='waiting', message='the project has no volunteer registry yet', warnings=warnings)
        return POLL
    except registry.Unavailable as err:
        log(f'GitHub is unreachable ({err}); trying again in {POLL // 60} min')
        status.set(state='waiting', message=f'GitHub is unreachable: {err}', warnings=warnings)
        return POLL
    except assign.RegistryError as err:
        log(f'REGISTRY REFUSED: {err}; not crawling with it')
        status.set(state='waiting', message=f'the registry was refused: {err}', warnings=warnings)
        return POLL
    reg_path.write_bytes(raw)
    me = assign.find(reg, login)
    if me is None or me['trust'] == 'suspended':
        why = 'is not in the registry yet' if me is None else 'is suspended in the registry'
        link = JOIN.format(upstream=cfg['upstream'])
        log(f'{login} {why}; nothing to crawl. Join: {link} (looking again in {POLL // 60} min)')
        status.set(state='not_registered', message=f'{login} {why}', join=link, warnings=warnings)
        return POLL
    if assign.version_tuple(bundle.version()) < assign.version_tuple(reg['min_version']):
        log(f'this crawler is {bundle.version()} and the coordinator wants {reg["min_version"]}: update it '
            f'(planwat-crawler update); not crawling until then')
        status.set(state='update_needed', message=f'crawler {bundle.version()} < required {reg["min_version"]}',
                   warnings=warnings)
        return POLL
    status.set(state='syncing', message=f'registry {sha[:12]}: {login} ({me["trust"]}); fetching the data branch')
    try:
        data = sync_data(work, cfg['upstream'], pass_no)
    except (subprocess.SubprocessError, OSError) as err:
        log(f'could not fetch the data branch ({err}); trying again in {POLL // 60} min')
        status.set(state='waiting', message='could not fetch the data branch', warnings=warnings)
        return POLL
    record, benched = verdict(published(data), login)
    said = describe_verdict(record)
    if said:
        log(said)
    expires = record.get('token_expires')
    if isinstance(expires, str) and expires[:10] <= (core.now_utc() + dt.timedelta(days=14)).date().isoformat():
        warnings.append(f'the fork token expires on {expires[:10]}: create a new one and run planwat-crawler setup')
    if benched:
        log(f'{login} is benched by the coordinator (its votes kept losing); the maintainer has an issue about it. '
            f'Not crawling until restored.')
        status.set(state='benched', message='benched by the coordinator', verdict=said, warnings=warnings)
        return POLL
    window = assign.window_of(core.now_utc())
    status.set(state='crawling', message=f'window {window}', verdict=said, warnings=warnings, window=window)
    outcomes = work / 'outcomes.json'
    outcomes.unlink(missing_ok=True)
    cmd = [sys.executable, str(ROOT / 'tools' / 'refresh' / 'refresh.py'), '--out', str(data),
           '--assign', str(reg_path), '--as', login, '--outcomes', str(outcomes),
           '--faculty-state', str(work / 'faculties.json'), '--max-minutes', f'{cfg["max_minutes"]:g}',
           '--adaptive-hours', '4']
    if cfg['dry_run']:
        cmd.append('--dry-run')
    code = run_child(cmd)
    if code not in (0, 3, 4) or not outcomes.is_file():
        log(f'the crawl failed (exit {code}); nothing pushed')
        status.set(state='failed', message=f'the crawl failed (exit {code})', done_window=window,
                   last_pass={'started': started.isoformat(), 'ended': core.now_utc().isoformat(), 'exit': code})
        return None
    counts = outcome_counts(outcomes)
    cmd = [sys.executable, str(HERE / 'bundle.py'), '--data', str(data), '--outcomes', str(outcomes),
           '--fork', cfg['fork']]
    if cfg['dry_run']:
        cmd.append('--dry-run')
    pushed = run_child(cmd) == 0
    for line in warnings:
        log(f'WARNING: {line}')
    status.set(state='done', done_window=window, warnings=warnings, message='pass finished',
               last_pass={'started': started.isoformat(), 'ended': core.now_utc().isoformat(), 'exit': code,
                          'groups': counts, 'pushed': pushed and not cfg['dry_run'], 'dry_run': cfg['dry_run']})
    return None


def next_wait(now, done_window, rng=random):
    """Seconds until the next pass: now when this window has had none, else 5-35 min into the next window."""
    window = assign.window_of(now)
    if done_window is None or done_window < window:
        return 0
    opens = assign.window_start(window + 1)
    return max(0, (opens - now).total_seconds() + rng.uniform(5 * 60, 35 * 60))


def wait(seconds, status):
    """Sleep, keeping the health check fed."""
    end = time.monotonic() + seconds
    status.set(state=status.data.get('state', 'waiting'),
               next=(core.now_utc() + dt.timedelta(seconds=seconds)).isoformat())
    beat = time.monotonic()
    while time.monotonic() < end:
        time.sleep(min(60, max(0.0, end - time.monotonic())))
        if time.monotonic() - beat >= HEARTBEAT:
            status.set()
            beat = time.monotonic()


def stop(signum, frame):
    if _child is not None and _child.poll() is None:
        _child.terminate()
        try:
            _child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            _child.kill()
    log('stopped')
    sys.exit(0)


def loop(cfg, once=False):
    if not cfg['login']:
        print('PLANWAT_LOGIN is not set: run `planwat-crawler setup` (or fill in .env)', file=sys.stderr)
        return 2
    if not cfg['token'] and not cfg['dry_run']:
        print('PLANWAT_FORK_TOKEN is not set: run `planwat-crawler setup` (or PLANWAT_DRY_RUN=1 for a test run)',
              file=sys.stderr)
        return 2
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    cfg['work'].mkdir(parents=True, exist_ok=True)
    status = Status(cfg['work'])
    log(f'PlanWAT volunteer crawler {bundle.version()} as {cfg["login"]} → {cfg["fork"]}'
        + (' (dry run: nothing is pushed)' if cfg['dry_run'] else ''))
    pass_no = 0
    while True:
        pause = next_wait(core.now_utc(), None if once else status.data.get('done_window'))
        if pause:
            log(f'this window is done; next pass in {pause / 60:.0f} min')
            wait(pause, status)
        pass_no += 1
        try:
            pause = run_pass(cfg, status, pass_no)
        except Exception as err:  # one broken pass must not end the loop
            log(f'the pass failed: {err!r}')
            status.set(state='failed', message=repr(err)[:300])
            pause = POLL
        if once:
            return 0 if status.data.get('state') == 'done' else 1
        if pause:
            wait(pause, status)


# --- the commands ---------------------------------------------------------------------------------------------

STATES = {
    'starting': 'zaczyna przebieg', 'syncing': 'pobiera dane projektu', 'crawling': 'sprawdza plany',
    'done': 'czeka na następne okno', 'failed': 'ostatni przebieg się nie udał', 'waiting': 'czeka',
    'not_registered': 'czeka na wpis do rejestru', 'update_needed': 'wymaga aktualizacji',
    'benched': 'odsunięty przez koordynatora (głosy przegrywały)',
}


def show_status(cfg, out=sys.stdout):
    status = Status(cfg['work']).data
    if not status:
        print('Crawler jeszcze nie wystartował (brak status.json).', file=out)
        return 1
    print(f'PlanWAT crawler {status.get("version", "?")}, login {cfg["login"] or "?"}', file=out)
    print(f'Stan: {STATES.get(status.get("state"), status.get("state"))}'
          + (f' ({status["message"]})' if status.get('message') else ''), file=out)
    if status.get('next'):
        print(f'Następny przebieg: {status["next"][:16].replace("T", " ")} UTC', file=out)
    last = status.get('last_pass')
    if last:
        groups = ', '.join(f'{n} {k}' for k, n in sorted((last.get('groups') or {}).items())) or 'brak grup'
        print(f'Ostatni przebieg: {last.get("started", "?")[:16].replace("T", " ")} UTC, {groups}, '
              + ('wypchnięty' if last.get('pushed') else 'próbny' if last.get('dry_run') else 'niewypchnięty'),
              file=out)
    if status.get('verdict'):
        print(f'Koordynator: {status["verdict"]}', file=out)
    if status.get('join'):
        print(f'Zgłoszenie: {status["join"]}', file=out)
    for line in status.get('warnings') or []:
        print(f'Uwaga: {line}', file=out)
    return 0


def health(cfg, now=None):
    status = Status(cfg['work']).data
    try:
        updated = dt.datetime.fromisoformat(status['updated'])
    except (KeyError, TypeError, ValueError):
        return 1
    return 0 if ((now or core.now_utc()) - updated).total_seconds() < STALE else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = argv.pop(0) if argv else 'run'
    if os.environ.get('PLANWAT_ONCE') == '1' and command == 'run':
        command = 'once'
    cfg = config()
    if command in ('run', 'once'):
        return loop(cfg, once=command == 'once')
    if command == 'status':
        return show_status(cfg)
    if command == 'health':
        return health(cfg)
    if command == 'setup':
        import wizard
        return wizard.main(argv)
    if command == 'doctor':
        import doctor
        return doctor.main(argv)
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == '__main__':
    sys.exit(main())
