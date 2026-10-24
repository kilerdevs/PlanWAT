#!/usr/bin/env python3
"""Collect the volunteers' crawl bundles, check them, count the votes and file what was accepted.

    python tools/volunteer/collect.py --registry volunteers.json --data <data checkout> [--dry-run]
    python tools/volunteer/collect.py --registry volunteers.json --data <data checkout> --revert <login> --since <iso>
    python tools/volunteer/collect.py --registry volunteers.json --data <data checkout> --unbench <login>

Runs on a GitHub-hosted runner (collect.yml) and never talks to a faculty site. For every active volunteer in the
registry it fetches the `crawl` branch of the volunteer's own fork into a bare scratch repository and reads the
blobs with git plumbing: nothing from a fork is ever checked out or executed. A bundle is refused as a whole when
anything about it is off (owner, version, replay, age, paths, sizes, entry types); a calendar inside an accepted
bundle must pass the same gate the crawler uses (core.validate, which runs build.load_term) and hash to the plan
the manifest claims.

Each checked group is a vote for a plan hash. A plan is accepted when a trusted volunteer voted for it, or when
`quorum` distinct peers did within `window_hours`; an "unchanged" vote only counts for the plan that is published
now, so it can never veto a change. Accepted plans are filed under timetables/ and stamped in volunteer-state.json
(the crawler and build.py read the stamps from there; refresh-state.json stays the home runner's own). A peer
whose vote lost to an accepted plan gets a strike; three strikes in a week bench it until the owner unbenches it.

Votes go stale: one cast before somebody trusted last saw the group (the home runner's check in refresh-state.json,
or the newest vote of the plan accepted last) describes a page that has moved on, so it is dropped, never counted
and never struck. A loser is struck only when it voted while the winning plan was already being seen; a vote newer
than every vote of the winner waits for its own quorum instead.

Every volunteer's health is published in volunteer-state.json under `volunteers` (last bundle, version, refusal,
blocked faculties, token expiry, daily counts): the crawler, its doctor, assign.py and the maintainer's panel read
it from the public data branch. A fork is polled with ls-remote first, so an unchanged or already refused bundle
costs one round trip, and the fetch runs with a cap on the size of any file git writes.

A vote's time is the volunteer's own claim, so it is kept inside the bundle's pass (and after the volunteer's
previous bundle), and when a trusted volunteer voted for the winner only the trusted times say when the winner was
seen: one peer cannot backdate a vote to strike somebody else. Work is budgeted: a pass fetches at most PASS_BYTES
and starts no fetch after PASS_SECONDS (the rest wait for the next pass, least recently fetched first), and one
volunteer's fork is fetched at most FETCHES_PER_DAY times a day. A volunteer who leaves the registry is forgotten
(health, strikes, bench, pending votes); a benched one's pending votes are dropped. A volunteer-state.json that
cannot be read stops the run instead of being replaced by an empty one.
"""
import argparse
import concurrent.futures
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'refresh'))
sys.path.insert(0, str(HERE))
import assign  # noqa: E402
import core  # noqa: E402

FORMAT = 1
MAX_FILE = 2 * 1024 * 1024
MAX_MANIFEST = 1024 * 1024
MAX_BUNDLE = 60 * 1024 * 1024
MAX_FILES = 2000
FETCH_TIMEOUT = 90
FETCH_LIMIT = 80 * 1024 * 1024  # the largest file git may write while fetching one bundle (the pack)
WORKERS = 4
PROTOCOLS = ('https',)  # transports a fork URL may use (the tests add 'file')
SKEW = dt.timedelta(minutes=5)
STRIKES = 3
STRIKE_DAYS = 7
LOG_DAYS = 30
KEY_RE = re.compile(r'^([A-Za-z0-9_]{2,32})@(\d{4}-\d{2}-(?:zima|lato))$')
CAL_RE = re.compile(r'^timetables/(\d{4}-\d{2}-(?:zima|lato))/([A-Za-z0-9_]{2,32})\.ics$')
HASH_RE = re.compile(r'^[0-9a-f]{64}$')
FACULTY_RE = re.compile(r'^[a-z]{2,12}$')
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}(?:[T ][0-9:]{5,8})?')
DAYS = 7
PASS_BYTES = 400 * 1024 * 1024  # fetched in one pass; then the remaining forks wait for the next one
PASS_SECONDS = 600  # no fetch starts later than this into a pass (the job has 20 minutes)
FETCHES_PER_DAY = 24  # bundles fetched from one fork a day (an honest crawler pushes one per 2-hour window)
# Faculty names a manifest may report as blocked: the crawler's own list, so the published health stays small.
FACULTIES = frozenset(json.loads((ROOT / 'tools' / 'refresh' / 'sources.json').read_text(encoding='utf-8')))
# ls-remote failures that mean "no such fork (or not one we may read)", not "GitHub could not be reached".
GONE = ('not found', 'not allowed', 'does not appear to be a git repository', 'terminal prompts disabled',
        'could not read username', 'authentication failed')


class BundleError(ValueError):
    def __init__(self, message, commit=None):
        super().__init__(message)
        self.commit = commit


class RemoteError(RuntimeError):
    """A fork could not be asked (network, timeout): nothing is known about its bundle."""


class StateError(ValueError):
    """volunteer-state.json exists but cannot be read; writing over it would lose every vote, strike and log."""


def log(msg):
    print(msg, flush=True)


def iso(moment):
    return moment.replace(microsecond=0).isoformat()


def parse_time(text):
    try:
        moment = dt.datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return moment.astimezone(dt.timezone.utc).replace(tzinfo=None) if moment.tzinfo else moment


def empty_state():
    return {'version': 1, 'groups': {}, 'votes': {}, 'seen': {}, 'strikes': {}, 'benched': {}, 'log': [],
            'volunteers': {}, 'registry': {}}


def load_state(path):
    """The coordinator's state: an empty one when there is none yet, StateError when the file cannot be read."""
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except FileNotFoundError:
        return empty_state()
    except (OSError, ValueError, RecursionError) as err:
        raise StateError(f'{path}: {err}')
    if not isinstance(data, dict) or data.get('version') != 1:
        raise StateError(f'{path}: not a version 1 coordinator state')
    state = empty_state()
    state.update({k: v for k, v in data.items() if k in state and isinstance(v, type(state[k]))})
    return state


def save_state(path, state):
    text = json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + '\n'
    tmp = Path(path).with_suffix('.tmp')
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(path)


def allowed_terms(today):
    terms = {core.term_id(today)}
    coming = core.upcoming_reference(today)
    if coming:
        terms.add(core.term_id(coming))
    return terms


# --- fetching -------------------------------------------------------------------------------------------------

# Runs git with RLIMIT_FSIZE set: a fork serving a huge pack makes index-pack fail, not the runner's disk fill up.
_LIMITED = ('import os, resource, sys; n = int(sys.argv[1]); '
            'resource.setrlimit(resource.RLIMIT_FSIZE, (n, n)); os.execvp(sys.argv[2], sys.argv[2:])')


def git_env():
    return {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_LFS_SKIP_SMUDGE': '1', 'LC_ALL': 'C', 'LANGUAGE': 'C'}


def git(*args, cwd=None, binary=False, timeout=FETCH_TIMEOUT, limit=None):
    cmd = ['git', *args]
    if limit:
        cmd = [sys.executable, '-c', _LIMITED, str(limit), *cmd]
    out = subprocess.run(cmd, cwd=cwd, env=git_env(), check=True, capture_output=True, timeout=timeout)
    return out.stdout if binary else out.stdout.decode('utf-8', errors='replace')


def remote_config():
    """Config for every command that talks to a fork: no hooks, only the allowed transports, one pack file."""
    cfg = ['-c', 'core.hooksPath=/dev/null', '-c', 'protocol.allow=never',
           '-c', 'fetch.unpackLimit=1', '-c', 'transfer.unpackLimit=1']
    for proto in PROTOCOLS:
        cfg += ['-c', f'protocol.{proto}.allow=always']
    return cfg


def remote_head(url):
    """The commit the fork's crawl branch points at, or None when there is no such fork or branch. RemoteError when
    the fork could not be asked at all, so an outage is not mistaken for volunteers who never set up."""
    try:
        out = git(*remote_config(), 'ls-remote', '--', url, 'refs/heads/crawl', timeout=30)
    except subprocess.CalledProcessError as err:
        why = (err.stderr or b'').decode('utf-8', errors='replace').strip()
        if any(sign in why.lower() for sign in GONE):
            return None
        raise RemoteError(why.splitlines()[-1][:200] if why else f'ls-remote exited {err.returncode}')
    except (subprocess.SubprocessError, OSError) as err:
        raise RemoteError(str(err)[:200] or type(err).__name__)
    head = out.split()[0] if out.split() else ''
    return head if re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', head) else None


def fetch_bundle(url, scratch, limit=None):
    """(commit, {path: bytes}) of the crawl branch at `url`, read with plumbing only; None when there is none.
    A bundle that breaks a rule raises BundleError carrying its commit, so the refusal can be remembered."""
    repo = Path(scratch)
    git('init', '-q', '--bare', str(repo))
    try:
        git('-C', str(repo), *remote_config(), 'fetch', '-q', '--depth=1', '--no-tags', '--no-recurse-submodules',
            url, '+refs/heads/crawl:refs/heads/crawl', limit=limit or FETCH_LIMIT)
    except subprocess.CalledProcessError as err:
        why = (err.stderr or b'').decode('utf-8', errors='replace')
        # Python leaves SIGXFSZ ignored across exec, so the capped write fails with EFBIG instead of a signal.
        if 'file too large' in why.lower() or 'signal 25' in why:
            raise BundleError(f'the fetch grew past {(limit or FETCH_LIMIT) // 2**20} MB')
        return None
    commit = git('-C', str(repo), 'rev-parse', 'refs/heads/crawl').strip()
    entries, total = [], 0
    with closing(tree_lines(repo, commit)) as lines:
        for line in lines:
            meta, _, path = line.partition('\t')
            mode, kind, sha, size = meta.split()
            # Blobs only: a symlink (120000) or a submodule (160000) is refused outright.
            if kind != 'blob' or mode not in ('100644', '100755'):
                raise BundleError(f'{path}: not a plain file (mode {mode})', commit)
            if path != 'manifest.json' and not CAL_RE.match(path):
                raise BundleError(f'{path}: not a manifest or a calendar path', commit)
            size = int(size)
            if size > (MAX_MANIFEST if path == 'manifest.json' else MAX_FILE):
                raise BundleError(f'{path}: too big ({size} bytes)', commit)
            total += size
            entries.append((path, sha))
            if len(entries) > MAX_FILES + 1:
                raise BundleError(f'too many files (over {MAX_FILES + 1})', commit)
            if total > MAX_BUNDLE:
                raise BundleError(f'too big (over {total} bytes)', commit)
    files = {path: git('-C', str(repo), 'cat-file', 'blob', sha, binary=True) for path, sha in entries}
    return commit, files


def tree_lines(repo, commit):
    """The `ls-tree -r -l` entries of `commit`, read as they are written: the caller stops at its limits, so a
    tree of millions of entries is never held whole."""
    cmd = ['git', '-C', str(repo), 'ls-tree', '-r', '-l', '--full-tree', '-z', commit]
    proc = subprocess.Popen(cmd, env=git_env(), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        rest = b''
        while chunk := proc.stdout.read(65536):
            *lines, rest = (rest + chunk).split(b'\0')
            if len(rest) > 8192:
                raise BundleError('a tree entry is too long', commit)
            for line in lines:
                if line:
                    yield line.decode('utf-8', errors='replace')
        if proc.wait(timeout=FETCH_TIMEOUT):
            raise subprocess.CalledProcessError(proc.returncode, cmd)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
        proc.stdout.close()


def gather(url, seen, may_fetch=True):
    """What one fork offers, fetched off the main thread: (kind, commit, files or reason, bytes fetched). kind is
    'none' (no branch), 'same' (nothing new since the last read or refusal), 'later' (new, but the fork used up
    today's fetches), 'refused', 'error' (transient) or 'ok'. It never raises: one odd fork must not stop the pass."""
    try:
        head = remote_head(url)
    except RemoteError as err:
        return 'error', None, f'the fork could not be asked: {err}', 0
    except Exception as err:  # noqa: BLE001 - see the docstring
        return 'error', None, f'{type(err).__name__}: {str(err)[:150]}', 0
    if head is None:
        return 'none', None, None, 0
    if head in (seen.get('commit'), seen.get('refused_commit')):
        return 'same', head, None, 0
    if not may_fetch:
        return 'later', head, f'already fetched {FETCHES_PER_DAY} bundles today', 0
    scratch = Path(tempfile.mkdtemp(prefix='planwat-collect-'))
    try:
        got = fetch_bundle(url, scratch / 'repo.git')
        if got is None:
            return 'error', head, 'the fetch failed', disk_use(scratch)
        return 'ok', got[0], got[1], disk_use(scratch)
    except BundleError as err:
        return 'refused', err.commit or head, str(err), disk_use(scratch)
    except Exception as err:  # noqa: BLE001 - see the docstring
        return 'error', head, f'{type(err).__name__}: {str(err)[:150]}', disk_use(scratch)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def disk_use(folder):
    """Bytes under `folder`: what a fetch actually downloaded, for the pass's budget."""
    return sum(f.stat().st_size for f in Path(folder).rglob('*') if f.is_file() and not f.is_symlink())


# --- checking ------------------------------------------------------------------------------------------------

def check_manifest(volunteer, files, registry, seen, now, terms):
    """The manifest of a bundle, after every whole-bundle check; BundleError otherwise."""
    if 'manifest.json' not in files:
        raise BundleError('no manifest.json')
    try:
        manifest = json.loads(files['manifest.json'].decode('utf-8'))
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise BundleError('manifest.json is not JSON')
    if not isinstance(manifest, dict) or manifest.get('format') != FORMAT:
        raise BundleError(f'unknown bundle format {manifest.get("format") if isinstance(manifest, dict) else None!r}')
    if str(manifest.get('login', '')).lower() != volunteer['login'].lower():
        raise BundleError(f'the manifest is signed {manifest.get("login")!r}, not {volunteer["login"]}')
    try:
        if assign.version_tuple(manifest.get('version')) < assign.version_tuple(registry['min_version']):
            raise BundleError(f'crawler {manifest.get("version")} is older than {registry["min_version"]}')
    except assign.RegistryError as err:
        raise BundleError(str(err))
    seq = manifest.get('seq')
    if not isinstance(seq, int) or isinstance(seq, bool):
        raise BundleError('no sequence number')
    if seq <= seen.get('seq', -1):
        raise BundleError(f'replayed or out of order (seq {seq} after {seen.get("seq")})')
    ended = parse_time(manifest.get('ended'))
    if ended is None or ended > now + SKEW:
        raise BundleError(f'bad end time {manifest.get("ended")!r}')
    if now - ended > dt.timedelta(hours=registry['window_hours']):
        raise BundleError(f'stale: ended {iso(ended)}')
    before = parse_time(seen.get('ended'))
    if before and ended < before - SKEW:
        raise BundleError(f'ends {iso(ended)}, before the previous bundle ({iso(before)})')
    started = manifest.get('started')
    if started is not None and (parse_time(started) is None or parse_time(started) > ended):
        raise BundleError(f'bad start time {started!r}')
    groups = manifest.get('groups')
    if not isinstance(groups, dict):
        raise BundleError('no groups')
    wanted = set()
    for key, entry in groups.items():
        m = KEY_RE.match(str(key))
        if not m or not isinstance(entry, dict):
            raise BundleError(f'bad group entry {key!r}')
        if m.group(2) not in terms:
            raise BundleError(f'{key}: term {m.group(2)} is neither the current nor the coming one')
        if entry.get('status') in ('changed', 'unchanged') and not HASH_RE.match(str(entry.get('plan', ''))):
            raise BundleError(f'{key}: bad plan hash')
        if entry.get('status') == 'changed':
            wanted.add(f'timetables/{m.group(2)}/{m.group(1)}.ics')
    expires = manifest.get('token_expires')
    if expires is not None and not (isinstance(expires, str) and DATE_RE.match(expires) and len(expires) <= 40):
        raise BundleError('bad token_expires')
    if not isinstance(manifest.get('faculties', {}), dict):
        raise BundleError('bad faculties')
    calendars = {p for p in files if p != 'manifest.json'}
    if calendars != wanted:
        stray = sorted(calendars ^ wanted)[:3]
        raise BundleError(f'calendars and manifest disagree ({", ".join(stray)})')
    return manifest


def check_calendar(code, tid, raw, claimed, data):
    """(ics, '') when the calendar passes the crawler's own gate and hashes to `claimed`; (None, why) otherwise."""
    try:
        ics = raw.decode('utf-8')
    except UnicodeDecodeError:
        return None, 'not UTF-8'
    declared = re.search(r'^X-PLAN-GROUP:(.*?)\r?$', ics, re.M)
    if not declared or declared.group(1).strip() != code:
        return None, 'does not carry its own X-PLAN-GROUP'
    path = Path(data) / 'timetables' / tid / f'{code}.ics'
    old = path.read_text(encoding='utf-8') if path.is_file() else None
    if core.clip_to_term(ics, tid) != ics:
        return None, 'holds lessons outside the term'
    ok, why = core.validate(ics, code, tid, core.clip_to_term(old, tid) if old is not None else None)
    if not ok:
        return None, why
    if core.plan_hash(ics) != claimed:
        return None, 'does not hash to the plan the manifest claims'
    return ics, ''


def published_plan(data, code, tid):
    path = Path(data) / 'timetables' / tid / f'{code}.ics'
    return core.plan_hash(path.read_text(encoding='utf-8')) if path.is_file() else None


# --- voting --------------------------------------------------------------------------------------------------

def vote_time(entry, manifest, seen, now):
    """When a vote was cast, as far as the coordinator can bound the volunteer's claim: inside the bundle's own pass
    (started..ended, never in the future) and not before the volunteer's previous bundle ended."""
    ended = min(parse_time(manifest['ended']), now)
    floor = [t for t in (parse_time(manifest.get('started')), parse_time(seen.get('ended'))) if t]
    at = max(parse_time(entry.get('at')) or ended, *floor)
    return iso(min(at, ended))


def drop_votes(state, logins):
    """Take every pending vote of `logins` (any case) off the ballots."""
    gone = {str(login).lower() for login in logins}
    for key in list(state['votes']):
        for plan in list(state['votes'][key]):
            ballot = state['votes'][key][plan]
            ballot['voters'] = {v: t for v, t in ballot['voters'].items() if v.lower() not in gone}
            if not ballot['voters']:
                del state['votes'][key][plan]
        if not state['votes'][key]:
            del state['votes'][key]


def align(state, registry):
    """Key every volunteer's records by the login as the registry spells it now (GitHub logins ignore case, so a
    respelt login keeps its bench, strikes and replay guard), and forget volunteers who left the registry: their
    health, strikes, bench and pending votes. Their login stays in the `by` of groups they helped accept and in
    the log (for --revert) until those are overwritten or expire."""
    names = {v['login'].lower(): v['login'] for v in registry['volunteers']}
    for field in ('seen', 'volunteers', 'strikes', 'benched'):
        records = {}
        # The registry's own spelling goes last, so it wins over an older one.
        for login, record in sorted(state[field].items(), key=lambda kv: names.get(kv[0].lower()) == kv[0]):
            name = names.get(login.lower())
            if name is None:
                continue
            if field == 'strikes' and isinstance(records.get(name), list) and isinstance(record, list):
                record = records[name] + record
            records[name] = record
        state[field] = records
    voters = {v for ballots in state['votes'].values() for ballot in ballots.values() for v in ballot['voters']}
    drop_votes(state, {v for v in voters if v.lower() not in names})
    for ballots in state['votes'].values():
        for ballot in ballots.values():
            ballot['voters'] = {names[v.lower()]: t for v, t in ballot['voters'].items()}


def cast(state, key, plan, login, at):
    ballot = state['votes'].setdefault(key, {}).setdefault(plan, {'voters': {}, 'first': at})
    ballot['voters'][login] = at


def expire(state, now, hours):
    cutoff = iso(now - dt.timedelta(hours=hours))
    for key in list(state['votes']):
        for plan in list(state['votes'][key]):
            voters = {v: t for v, t in state['votes'][key][plan]['voters'].items() if t >= cutoff}
            if voters:
                state['votes'][key][plan]['voters'] = voters
            else:
                del state['votes'][key][plan]
        if not state['votes'][key]:
            del state['votes'][key]


def winner(ballots, trust, quorum):
    """The accepted plan of one group, or None: a trusted voter, or `quorum` peers; the latest vote breaks ties."""
    best = None
    for plan, ballot in ballots.items():
        voters = ballot['voters']
        trusted = [v for v in voters if trust.get(v.lower()) == 'trusted']
        peers = [v for v in voters if trust.get(v.lower()) == 'peer']
        if trusted or len(peers) >= quorum:
            latest = max(voters.values())
            if best is None or latest > best[1]:
                best = (plan, latest)
    return best[0] if best else None


def blob_of(data, rel):
    """The git blob id of a file in the data checkout (to restore it on --revert), or None when absent."""
    path = Path(data) / rel
    if not path.is_file():
        return None
    try:
        return git('-C', str(data), 'hash-object', '--', rel).strip()
    except (subprocess.CalledProcessError, OSError):
        return None


def load_home(data):
    """The home runner's group entries (refresh-state.json): its checks are trusted sightings of each page."""
    try:
        groups = json.loads((Path(data) / core.STATE_FILE).read_text(encoding='utf-8')).get('groups', {})
    except (OSError, ValueError, AttributeError):
        return {}
    return groups if isinstance(groups, dict) else {}


def last_seen(state, home, key):
    """When somebody trusted last saw `key`'s page: the home runner's check (same term) or the newest vote of the
    plan accepted last. A vote older than that describes a page that has since been looked at again."""
    code, tid = KEY_RE.match(key).groups()
    marks = [state['groups'].get(key, {}).get('observed')]
    entry = home.get(code)
    if isinstance(entry, dict) and entry.get('term') == tid:
        moment = parse_time(entry.get('checked'))
        marks.append(iso(moment) if moment else None)
    marks = [m for m in marks if isinstance(m, str)]
    return max(marks) if marks else ''


def void_stale(state, home):
    """Drop every vote cast before the group was last seen by somebody trusted (no strike: it was simply old)."""
    for key in list(state['votes']):
        cutoff = last_seen(state, home, key)
        if not cutoff:
            continue
        for plan in list(state['votes'][key]):
            voters = {v: t for v, t in state['votes'][key][plan]['voters'].items() if t >= cutoff}
            if voters:
                state['votes'][key][plan]['voters'] = voters
            else:
                del state['votes'][key][plan]
        if not state['votes'][key]:
            del state['votes'][key]


def health(state, login):
    return state['volunteers'].setdefault(login, {})


def count(state, login, now, field):
    """Bump one of a volunteer's daily counters: [votes, rejected, accepted], kept for DAYS days."""
    days = health(state, login).setdefault('days', {})
    day = days.setdefault(now.date().isoformat(), [0, 0, 0])
    day[('votes', 'rejected', 'accepted').index(field)] += 1


def tally(state, registry, data, offered, now, dry_run=False):
    """Accept what the votes carry; returns (changed keys, newly benched logins)."""
    # A benched volunteer's votes stop counting everywhere, not only for the bundles it can no longer send.
    drop_votes(state, state['benched'])
    trust = {v['login'].lower(): v['trust'] for v in registry['volunteers']}
    changed, benched = [], []
    for key in sorted(state['votes']):
        ballots = state['votes'][key]
        plan = winner(ballots, trust, registry['quorum'])
        if plan is None:
            continue
        code, tid = KEY_RE.match(key).groups()
        rel = f'timetables/{tid}/{code}.ics'
        voters = sorted(ballots[plan]['voters'])
        # When the winner was seen: by the trusted voters alone when there are any, so a peer's claimed time
        # can neither backdate the first sighting nor stretch the last one to strike somebody else.
        times = ballots[plan]['voters']
        times = {v: t for v, t in times.items() if trust.get(v.lower()) == 'trusted'} or times
        first, latest = min(times.values()), max(times.values())
        entry = state['groups'].setdefault(key, {})
        if plan != published_plan(data, code, tid):
            ics = offered.get((key, plan))
            if ics is None:
                continue  # the content arrives with the vote that completes it; keep waiting
            prior = blob_of(data, rel)
            if not dry_run:
                (Path(data) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(data) / rel).write_bytes(ics.encode('utf-8'))
            entry['changed'] = iso(now)
            state['log'].append({'key': key, 'plan': plan, 'by': voters, 'at': iso(now), 'prior': prior})
            changed.append(key)
            log(f'{key}: accepted a new plan from {", ".join(voters)}')
        entry.update(checked=iso(now), plan=plan, by=voters, observed=latest)
        entry.pop('reverted', None)
        for login in voters:
            count(state, login, now, 'accepted')
        del ballots[plan]
        # The other plans: a vote cast while the winner was being seen lost (a strike for a peer); one newer
        # than every vote of the winner may be the next plan and waits for its own quorum; older ones were stale.
        for other in list(ballots):
            keep = {}
            for login, at in ballots[other]['voters'].items():
                if at > latest:
                    keep[login] = at
                elif at >= first and trust.get(login.lower()) == 'peer':
                    state['strikes'].setdefault(login, []).append(iso(now))
            if keep:
                ballots[other]['voters'] = keep
            else:
                del ballots[other]
        if not ballots:
            del state['votes'][key]
    cutoff = iso(now - dt.timedelta(days=STRIKE_DAYS))
    for login in list(state['strikes']):
        state['strikes'][login] = [t for t in state['strikes'][login] if t >= cutoff]
        if not state['strikes'][login]:
            del state['strikes'][login]
        elif len(state['strikes'][login]) >= STRIKES and login.lower() not in {b.lower() for b in state['benched']}:
            state['benched'][login] = iso(now)
            benched.append(login)
            log(f'{login}: benched after {len(state["strikes"][login])} disagreements in {STRIKE_DAYS} days')
    drop_votes(state, benched)
    keep = iso(now - dt.timedelta(days=LOG_DAYS))
    state['log'] = [e for e in state['log'] if e.get('at', '') >= keep]
    oldest = (now - dt.timedelta(days=DAYS - 1)).date().isoformat()
    for record in state['volunteers'].values():
        if isinstance(record.get('days'), dict):
            record['days'] = {d: n for d, n in record['days'].items() if d >= oldest}
    return changed, benched


# --- the run -------------------------------------------------------------------------------------------------

def note_bundle(state, login, manifest, commit, now, votes, rejected, reasons):
    """What the coordinator learned about a volunteer from a bundle it read (published in volunteer-state.json)."""
    old = state['seen'].get(login, {})
    state['seen'][login] = {'seq': manifest['seq'], 'ended': manifest['ended'], 'commit': commit,
                            **{k: old[k] for k in ('fetches', 'fetched') if k in old}}
    record = health(state, login)
    record.pop('refused', None)
    record.update(read=iso(now), ended=manifest['ended'], version=manifest['version'],
                  last={'votes': votes, 'rejected': rejected, 'reasons': reasons[:3]})
    if manifest.get('token_expires'):
        record['token_expires'] = manifest['token_expires']
    blocked = record.setdefault('blocked', {})
    for name in [n for n in blocked if n not in FACULTIES]:
        del blocked[name]
    for name, found in manifest.get('faculties', {}).items():
        if not FACULTY_RE.match(str(name)) or name not in FACULTIES or not isinstance(found, dict):
            continue
        if found.get('blocked'):
            blocked[name] = manifest['ended']
        else:
            blocked.pop(name, None)


def note_refusal(state, login, commit, why, now):
    """Remember a refused bundle, so the same commit is not fetched again, and tell its author why."""
    if commit:
        state['seen'].setdefault(login, {})['refused_commit'] = commit
    health(state, login)['refused'] = {'reason': why[:200], 'at': iso(now), 'commit': commit}


def note_fetch(state, login, now):
    """Count a bundle fetched from `login`'s fork, for FETCHES_PER_DAY and the least-recently-fetched order."""
    seen = state['seen'].setdefault(login, {})
    day = now.date().isoformat()
    fetches = seen.get('fetches') if isinstance(seen.get('fetches'), list) and len(seen['fetches']) == 2 else []
    seen['fetches'] = [day, (fetches[1] if fetches[:1] == [day] else 0) + 1]
    seen['fetched'] = iso(now)


def may_fetch(seen, now):
    fetches = seen.get('fetches')
    return not (isinstance(fetches, list) and fetches[:1] == [now.date().isoformat()]
                and fetches[1:] and fetches[1] >= FETCHES_PER_DAY)


def collect(registry, data, now, url_of, dry_run=False, registry_sha=None):
    """One coordinator pass. Returns a summary dict; writes timetables and volunteer-state.json unless dry_run.
    `registry_sha` is the registry commit in use, kept so that the next pass can refuse a rollback to an older one."""
    data = Path(data)
    state_path = data / core.VOLUNTEER_STATE_FILE
    state = load_state(state_path)
    align(state, registry)
    if registry_sha:
        state['registry'] = {'sha': registry_sha, 'read': iso(now)}
    run = {'terms': allowed_terms(now.date()), 'offered': {}, 'refused': {}, 'read': [], 'rows': []}
    active = [v for v in registry['volunteers'] if v['trust'] != 'suspended' and v['login'] not in state['benched']]
    # Least recently fetched first, so the forks a spent budget leaves out are first in line next pass.
    active.sort(key=lambda v: state['seen'].get(v['login'], {}).get('fetched', ''))
    spent, clock = 0, time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as pool:
        # A batch at a time: at most WORKERS bundles are held in memory, and the budget is checked in between.
        for start in range(0, len(active), WORKERS):
            batch = active[start:start + WORKERS]
            if spent >= PASS_BYTES or time.monotonic() - clock >= PASS_SECONDS:
                found = [('later', None, 'this pass used up its budget', 0)] * len(batch)
            else:
                found = list(pool.map(lambda v: gather(url_of(v), state['seen'].get(v['login'], {}),
                                                       may_fetch(state['seen'].get(v['login'], {}), now)), batch))
                spent += sum(size for *_, size in found)
            for volunteer, (kind, commit, payload, _) in zip(batch, found):
                read_bundle(state, registry, data, now, run, volunteer, kind, commit, payload)
    order = [v['login'] for v in registry['volunteers']]
    rows = sorted(run['rows'], key=lambda row: order.index(row['login']))
    expire(state, now, registry['window_hours'])
    void_stale(state, load_home(data))
    changed, benched = tally(state, registry, data, run['offered'], now, dry_run)
    if not dry_run:
        save_state(state_path, state)
    by = sorted({v for key in changed for v in state['groups'][key].get('by', [])})
    for row in rows:
        record = state['volunteers'].get(row['login'], {})
        row['accepted'] = sum(n[2] for n in record.get('days', {}).values())
        row['blocked'] = sorted(record.get('blocked', {}))
        row['token_expires'] = record.get('token_expires', '')
    # A dry run benches nobody for real, so it must not report (and file an issue about) a bench it never wrote.
    return {'read': run['read'], 'refused': run['refused'], 'changed': changed, 'benched': [] if dry_run else benched,
            'by': by, 'rows': rows}


def read_bundle(state, registry, data, now, run, volunteer, kind, commit, payload):
    """Check what gather() brought from one fork and cast its votes; the outcome goes into `run`."""
    login = volunteer['login']
    row = {'login': login, 'trust': volunteer['trust'], 'result': kind, 'votes': 0, 'rejected': 0, 'why': ''}
    run['rows'].append(row)
    if kind == 'none':
        log(f'{login}: no crawl branch')
        return
    if kind == 'same':
        return
    if kind in ('error', 'later'):
        log(f'{login}: could not fetch the bundle ({payload}); trying again next pass')
        row['why'] = payload
        return
    seen = dict(state['seen'].get(login, {}))
    note_fetch(state, login, now)
    try:
        if kind == 'refused':
            raise BundleError(payload, commit)
        try:
            manifest = check_manifest(volunteer, payload, registry, seen, now, run['terms'])
        except BundleError:
            raise
        except Exception as err:  # noqa: BLE001 - a manifest that trips a check is refused, it never ends the pass
            raise BundleError(f'unreadable manifest ({type(err).__name__})')
    except BundleError as err:
        log(f'{login}: bundle refused: {err}')
        run['refused'][login] = str(err)
        row.update(result='refused', why=str(err))
        note_refusal(state, login, commit, str(err), now)
        return
    files = payload
    votes = rejected = 0
    reasons = []
    for key, entry in manifest['groups'].items():
        code, tid = KEY_RE.match(key).groups()
        at = vote_time(entry, manifest, seen, now)
        if entry.get('status') == 'unchanged':
            # Only a vote for what is published now counts: "unchanged" never outvotes a change.
            if entry['plan'] == published_plan(data, code, tid):
                cast(state, key, entry['plan'], login, at)
                votes += 1
        elif entry.get('status') == 'changed':
            try:
                ics, why = check_calendar(code, tid, files[f'timetables/{tid}/{code}.ics'], entry['plan'], data)
            except Exception as err:  # noqa: BLE001 - one odd calendar is rejected, the pass goes on
                ics, why = None, f'unreadable ({type(err).__name__})'
            if ics is None:
                log(f'{login}: {key} rejected ({why})')
                rejected += 1
                if why not in reasons:
                    reasons.append(why[:160])
                continue
            run['offered'][(key, entry['plan'])] = ics
            cast(state, key, entry['plan'], login, at)
            votes += 1
    for _ in range(votes):
        count(state, login, now, 'votes')
    for _ in range(rejected):
        count(state, login, now, 'rejected')
    note_bundle(state, login, manifest, commit, now, votes, rejected, reasons)
    run['read'].append(login)
    row.update(votes=votes, rejected=rejected, why='; '.join(reasons[:1]))
    log(f'{login}: {votes} votes, {rejected} calendars rejected (crawler {manifest["version"]})')


def prior_blob(data, sha):
    """The bytes of an earlier calendar version. collect.yml checks the data branch out shallow, so a blob from an
    older commit may be missing: then the checkout's history is fetched whole, once, and the blob read again."""
    try:
        return git('-C', str(data), 'cat-file', 'blob', sha, binary=True)
    except subprocess.CalledProcessError:
        if git('-C', str(data), 'rev-parse', '--is-shallow-repository').strip() != 'true':
            raise
    log('the data checkout is shallow: fetching its history to find the earlier calendars')
    git('-C', str(data), 'fetch', '-q', '--unshallow', 'origin', timeout=900)
    return git('-C', str(data), 'cat-file', 'blob', sha, binary=True)


def revert(state_path, data, login, since, now):
    """Put back every calendar `login` helped accept since `since`; returns the keys restored."""
    state = load_state(state_path)
    restored = []
    hits = [e for e in state['log'] if e.get('at', '') >= since and login.lower() in (b.lower() for b in e['by'])]
    # Every earlier version is read before anything is written, so a revert happens whole or not at all.
    priors = {e['prior']: prior_blob(data, e['prior']) for e in hits if e.get('prior')}
    for entry in sorted(hits, key=lambda e: e['at'], reverse=True):
        code, tid = KEY_RE.match(entry['key']).groups()
        path = Path(data) / 'timetables' / tid / f'{code}.ics'
        if entry.get('prior'):
            path.write_bytes(priors[entry['prior']])
        elif path.is_file():
            path.unlink()
        group = state['groups'].setdefault(entry['key'], {})
        group.pop('checked', None)  # make every crawler look again
        group['reverted'] = iso(now)
        restored.append(entry['key'])
    state['log'] = [e for e in state['log'] if e not in hits]
    for key in {e['key'] for e in hits}:
        state['votes'].pop(key, None)
    save_state(state_path, state)
    return sorted(set(restored))


def export(**values):
    path = os.environ.get('GITHUB_OUTPUT')
    if path:
        with open(path, 'a', encoding='utf-8') as fh:
            for k, v in values.items():
                fh.write(f'{k}={v}\n')


RESULTS = {'ok': 'przeczytana', 'refused': 'odrzucona', 'same': 'bez nowej paczki', 'none': 'brak gałęzi crawl',
           'error': 'błąd pobierania', 'later': 'odłożona (limit)'}


def summary_table(summary, now, dry_run):
    """The pass as a Markdown table for the run page (public, so volunteers can read their own row)."""
    lines = [f'### Paczki wolontariuszy{" (przebieg próbny)" if dry_run else ""}', '',
             f'Przyjęto {len(summary["changed"])} nowych kalendarzy.', '',
             '| Wolontariusz | Paczka | Głosy | Odrzucone kalendarze | Przyjęte (7 dni) | Blokady | Token | Uwagi |',
             '|---|---|---|---|---|---|---|---|']
    soon = (now + dt.timedelta(days=14)).date().isoformat()
    for row in summary['rows']:
        token = row['token_expires'][:10]
        if token and token <= soon:
            token = f'⚠️ wygasa {token}'
        why = str(row['why']).replace('|', '\\|')[:120]
        lines.append(f'| {row["login"]} ({row["trust"]}) | {RESULTS.get(row["result"], row["result"])} | '
                     f'{row["votes"]} | {row["rejected"]} | {row["accepted"]} | {", ".join(row["blocked"]) or "–"} | '
                     f'{token or "–"} | {why or "–"} |')
    return '\n'.join(lines) + '\n'


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--registry', required=True, type=Path)
    ap.add_argument('--data', required=True, type=Path, help='the data branch checkout')
    ap.add_argument('--dry-run', action='store_true', help='check and count, write nothing')
    ap.add_argument('--revert', metavar='LOGIN', help='restore every calendar this volunteer helped accept')
    ap.add_argument('--since', help='with --revert: from this UTC time on (ISO)')
    ap.add_argument('--unbench', metavar='LOGIN', help='let a benched volunteer vote again (clears its strikes)')
    ap.add_argument('--registry-sha', help='the registry commit in use (registry.py), kept to refuse a rollback')
    ap.add_argument('--url', default='https://github.com/{fork}.git', help='fork URL template (tests)')
    ap.add_argument('--now', help='pretend it is this UTC time (tests)')
    args = ap.parse_args(argv)
    if args.revert and (not args.since or parse_time(args.since) is None):
        ap.error('--revert needs --since <ISO time>')
    try:
        return run_command(args)
    except StateError as err:
        log(f'the coordinator state cannot be read, so nothing was written: {err}. Restore '
            f'{core.VOLUNTEER_STATE_FILE} from the history of the data branch (or delete it to start afresh).')
        return 2
    except subprocess.CalledProcessError as err:
        log(f'git failed, nothing was written: {(err.stderr or b"").decode("utf-8", errors="replace").strip()[:300]}')
        return 2


def run_command(args):
    now = parse_time(args.now) if args.now else core.now_utc()
    state_path = args.data / core.VOLUNTEER_STATE_FILE
    # revert and unbench are the owner's own commands: they write even while PLANWAT_COLLECT_LIVE is off.
    if args.revert:
        keys = revert(state_path, args.data, args.revert, iso(parse_time(args.since)), now)
        log(f'restored {len(keys)} calendars: {", ".join(keys) or "none"}')
        export(changed=len(keys))
        return 0
    if args.unbench:
        state = load_state(state_path)
        state['benched'] = {k: v for k, v in state['benched'].items() if k.lower() != args.unbench.lower()}
        state['strikes'] = {k: v for k, v in state['strikes'].items() if k.lower() != args.unbench.lower()}
        save_state(state_path, state)
        log(f'{args.unbench} may vote again')
        export(changed=0)
        return 0
    try:
        registry = assign.load_registry(args.registry)
    except (OSError, ValueError) as err:
        log(f'cannot read the registry: {err}')
        return 2
    summary = collect(registry, args.data, now, lambda v: args.url.format(fork=v['fork'], login=v['login']),
                      dry_run=args.dry_run, registry_sha=args.registry_sha)
    log(f'read {len(summary["read"])} bundles, refused {len(summary["refused"])}, '
        f'accepted {len(summary["changed"])} new calendars' + (' (dry run)' if args.dry_run else ''))
    export(changed=len(summary['changed']), benched=' '.join(summary['benched']),
           volunteers=', '.join(summary['by']))
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as fh:
            fh.write(summary_table(summary, now, args.dry_run))
    return 0


if __name__ == '__main__':
    sys.exit(main())
