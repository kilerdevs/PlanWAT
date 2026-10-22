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
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
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
SKEW = dt.timedelta(minutes=5)
STRIKES = 3
STRIKE_DAYS = 7
LOG_DAYS = 30
KEY_RE = re.compile(r'^([A-Za-z0-9_]{2,32})@(\d{4}-\d{2}-(?:zima|lato))$')
CAL_RE = re.compile(r'^timetables/(\d{4}-\d{2}-(?:zima|lato))/([A-Za-z0-9_]{2,32})\.ics$')
HASH_RE = re.compile(r'^[0-9a-f]{64}$')


class BundleError(ValueError):
    pass


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
    return {'version': 1, 'groups': {}, 'votes': {}, 'seen': {}, 'strikes': {}, 'benched': {}, 'log': []}


def load_state(path):
    try:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return empty_state()
    if not isinstance(data, dict) or data.get('version') != 1:
        return empty_state()
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

def git(*args, cwd=None, binary=False, timeout=FETCH_TIMEOUT):
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GIT_LFS_SKIP_SMUDGE': '1'}
    out = subprocess.run(['git', *args], cwd=cwd, env=env, check=True, capture_output=True, timeout=timeout)
    return out.stdout if binary else out.stdout.decode('utf-8', errors='replace')


def fetch_bundle(url, scratch):
    """(commit, {path: bytes}) of the crawl branch at `url`, read with plumbing only; None when there is none."""
    repo = Path(scratch)
    git('init', '-q', '--bare', str(repo))
    try:
        git('-C', str(repo), 'fetch', '-q', '--depth=1', '--no-tags', '--no-recurse-submodules',
            url, '+refs/heads/crawl:refs/heads/crawl')
    except subprocess.CalledProcessError:
        return None
    commit = git('-C', str(repo), 'rev-parse', 'refs/heads/crawl').strip()
    entries, total = [], 0
    for line in git('-C', str(repo), 'ls-tree', '-r', '-l', '--full-tree', '-z', commit).split('\0'):
        if not line:
            continue
        meta, _, path = line.partition('\t')
        mode, kind, sha, size = meta.split()
        # Blobs only: a symlink (120000) or a submodule (160000) is refused outright.
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise BundleError(f'{path}: not a plain file (mode {mode})')
        if path != 'manifest.json' and not CAL_RE.match(path):
            raise BundleError(f'{path}: not a manifest or a calendar path')
        size = int(size)
        if size > (MAX_MANIFEST if path == 'manifest.json' else MAX_FILE):
            raise BundleError(f'{path}: too big ({size} bytes)')
        total += size
        entries.append((path, sha))
    if len(entries) > MAX_FILES + 1:
        raise BundleError(f'too many files ({len(entries)})')
    if total > MAX_BUNDLE:
        raise BundleError(f'too big ({total} bytes)')
    files = {path: git('-C', str(repo), 'cat-file', 'blob', sha, binary=True) for path, sha in entries}
    return commit, files


# --- checking ------------------------------------------------------------------------------------------------

def check_manifest(volunteer, files, registry, seen, now, terms):
    """The manifest of a bundle, after every whole-bundle check; BundleError otherwise."""
    if 'manifest.json' not in files:
        raise BundleError('no manifest.json')
    try:
        manifest = json.loads(files['manifest.json'].decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
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


def tally(state, registry, data, offered, now, dry_run=False):
    """Accept what the votes carry; returns (changed keys, newly benched logins)."""
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
        entry.update(checked=iso(now), plan=plan, by=voters)
        entry.pop('reverted', None)
        # Peers that backed another plan in this window lost: a strike each.
        for other, ballot in ballots.items():
            if other == plan:
                continue
            for login in ballot['voters']:
                if trust.get(login.lower()) == 'peer':
                    state['strikes'].setdefault(login, []).append(iso(now))
        del state['votes'][key]
    cutoff = iso(now - dt.timedelta(days=STRIKE_DAYS))
    for login in list(state['strikes']):
        state['strikes'][login] = [t for t in state['strikes'][login] if t >= cutoff]
        if not state['strikes'][login]:
            del state['strikes'][login]
        elif len(state['strikes'][login]) >= STRIKES and login not in state['benched']:
            state['benched'][login] = iso(now)
            benched.append(login)
            log(f'{login}: benched after {len(state["strikes"][login])} disagreements in {STRIKE_DAYS} days')
    keep = iso(now - dt.timedelta(days=LOG_DAYS))
    state['log'] = [e for e in state['log'] if e.get('at', '') >= keep]
    return changed, benched


# --- the run -------------------------------------------------------------------------------------------------

def collect(registry, data, now, url_of, dry_run=False):
    """One coordinator pass. Returns a summary dict; writes timetables and volunteer-state.json unless dry_run."""
    data = Path(data)
    state_path = data / core.VOLUNTEER_STATE_FILE
    state = load_state(state_path)
    terms = allowed_terms(now.date())
    offered, refused, read = {}, {}, []
    for volunteer in registry['volunteers']:
        login = volunteer['login']
        if volunteer['trust'] == 'suspended' or login in state['benched']:
            continue
        seen = state['seen'].get(login, {})
        scratch = Path(tempfile.mkdtemp(prefix='planwat-collect-'))
        try:
            got = fetch_bundle(url_of(volunteer), scratch / 'repo.git')
            if got is None:
                log(f'{login}: no crawl branch')
                continue
            commit, files = got
            if commit == seen.get('commit'):
                continue
            manifest = check_manifest(volunteer, files, registry, seen, now, terms)
        except (BundleError, subprocess.SubprocessError, OSError, ValueError) as err:
            log(f'{login}: bundle refused: {err}')
            refused[login] = str(err)
            continue
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        votes = rejected = 0
        for key, entry in manifest['groups'].items():
            code, tid = KEY_RE.match(key).groups()
            at = parse_time(entry.get('at'))
            at = iso(min(at, now)) if at else manifest['ended']
            if entry.get('status') == 'unchanged':
                # Only a vote for what is published now counts: "unchanged" never outvotes a change.
                if entry['plan'] == published_plan(data, code, tid):
                    cast(state, key, entry['plan'], login, at)
                    votes += 1
            elif entry.get('status') == 'changed':
                ics, why = check_calendar(code, tid, files[f'timetables/{tid}/{code}.ics'], entry['plan'], data)
                if ics is None:
                    log(f'{login}: {key} rejected ({why})')
                    rejected += 1
                    continue
                offered[(key, entry['plan'])] = ics
                cast(state, key, entry['plan'], login, at)
                votes += 1
        state['seen'][login] = {'seq': manifest['seq'], 'ended': manifest['ended'], 'commit': commit}
        read.append(login)
        log(f'{login}: {votes} votes, {rejected} calendars rejected (crawler {manifest["version"]})')
    expire(state, now, registry['window_hours'])
    changed, benched = tally(state, registry, data, offered, now, dry_run)
    if not dry_run:
        save_state(state_path, state)
    by = sorted({v for key in changed for v in state['groups'][key].get('by', [])})
    return {'read': read, 'refused': refused, 'changed': changed, 'benched': benched, 'by': by}


def revert(state_path, data, login, since, now):
    """Put back every calendar `login` helped accept since `since`; returns the keys restored."""
    state = load_state(state_path)
    restored = []
    hits = [e for e in state['log'] if e.get('at', '') >= since and login.lower() in (b.lower() for b in e['by'])]
    for entry in sorted(hits, key=lambda e: e['at'], reverse=True):
        code, tid = KEY_RE.match(entry['key']).groups()
        path = Path(data) / 'timetables' / tid / f'{code}.ics'
        if entry.get('prior'):
            path.write_bytes(git('-C', str(data), 'cat-file', 'blob', entry['prior'], binary=True))
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--registry', required=True, type=Path)
    ap.add_argument('--data', required=True, type=Path, help='the data branch checkout')
    ap.add_argument('--dry-run', action='store_true', help='check and count, write nothing')
    ap.add_argument('--revert', metavar='LOGIN', help='restore every calendar this volunteer helped accept')
    ap.add_argument('--since', help='with --revert: from this UTC time on (ISO)')
    ap.add_argument('--unbench', metavar='LOGIN', help='let a benched volunteer vote again (clears its strikes)')
    ap.add_argument('--url', default='https://github.com/{fork}.git', help='fork URL template (tests)')
    ap.add_argument('--now', help='pretend it is this UTC time (tests)')
    args = ap.parse_args(argv)
    now = parse_time(args.now) if args.now else core.now_utc()
    state_path = args.data / core.VOLUNTEER_STATE_FILE
    if args.revert:
        if not args.since or parse_time(args.since) is None:
            ap.error('--revert needs --since <ISO time>')
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
                      dry_run=args.dry_run)
    log(f'read {len(summary["read"])} bundles, refused {len(summary["refused"])}, '
        f'accepted {len(summary["changed"])} new calendars' + (' (dry run)' if args.dry_run else ''))
    export(changed=len(summary['changed']), benched=' '.join(summary['benched']),
           volunteers=', '.join(summary['by']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
