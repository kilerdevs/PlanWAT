#!/usr/bin/env python3
"""Pack a volunteer crawl into a bundle and push it to the `crawl` branch of the volunteer's own fork.

    python tools/volunteer/bundle.py --data <crawled data checkout> --outcomes <outcomes.json>
                                     --fork <login>/PlanWAT [--dry-run] [--keep <dir>]

The bundle is one commit with no history (force-pushed, so the fork never grows):

    manifest.json                       what every check found, see below
    timetables/<term>/<GROUP>.ics       the converted calendars that changed, nothing else

    {"format": 1, "version": "1.2.0", "login": "alice", "seq": 1792000000,
     "started": "...", "ended": "...", "window": 14933,
     "groups": {"WCY26KY3S1@2026-27-zima": {"status": "changed", "plan": "<sha256>", "at": "..."}},
     "faculties": {"wcy": {"blocked": false, "cause": null}}}

`plan` is core.plan_hash of the calendar (volatile lines ignored), so two volunteers who saw the same plan
agree byte-for-byte on it. Raw faculty pages are never bundled: they name teachers, and the fork is public.
The coordinator (collect.py) trusts none of this; it checks everything again. The push authenticates with
PLANWAT_FORK_TOKEN (or GITHUB_TOKEN): a token that can write to the fork and nothing else.
"""
import argparse
import base64
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'refresh'))
import core  # noqa: E402

FORMAT = 1
STATUSES = ('changed', 'unchanged', 'not_ready', 'gone')


def version():
    return json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version']


def build_bundle(data, outcomes, login):
    """(manifest, {relative path: bytes}) for the crawl in `data` described by `outcomes`."""
    data = Path(data)
    groups, files = {}, {}
    for key, found in sorted(outcomes.get('groups', {}).items()):
        status = found.get('status')
        if status not in STATUSES:
            continue
        code, _, tid = key.partition('@')
        rel = f'timetables/{tid}/{code}.ics'
        path = data / rel
        entry = {'status': status, 'at': found.get('at')}
        if status in ('changed', 'unchanged'):
            if not path.is_file():
                continue  # nothing filed to vouch for (a dry run, or a group never published)
            raw = path.read_bytes()
            entry['plan'] = core.plan_hash(raw.decode('utf-8'))
            if status == 'changed':
                files[rel] = raw
        groups[key] = entry
    ended = outcomes.get('ended') or core.now_utc().isoformat()
    manifest = {
        'format': FORMAT, 'version': version(), 'login': login,
        'seq': int(dt.datetime.fromisoformat(ended).replace(tzinfo=dt.timezone.utc).timestamp()),
        'started': outcomes.get('started'), 'ended': ended, 'window': outcomes.get('window'),
        'groups': groups, 'faculties': outcomes.get('faculties', {}),
    }
    return manifest, files


def write_tree(where, manifest, files):
    where = Path(where)
    (where / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + '\n',
                                         encoding='utf-8')
    for rel, raw in files.items():
        (where / rel).parent.mkdir(parents=True, exist_ok=True)
        (where / rel).write_bytes(raw)


def git(*args, cwd, env=None):
    return subprocess.run(['git', *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


def push(tree, fork, login, token, remote=None):
    """Commit `tree` as a single parentless commit and force-push it to <fork>:crawl."""
    url = remote or f'https://github.com/{fork}.git'
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0'}
    git('init', '-q', '-b', 'crawl', cwd=tree)
    git('-c', f'user.name={login}', '-c', f'user.email={login}@users.noreply.github.com',
        'add', '-A', cwd=tree)
    git('-c', f'user.name={login}', '-c', f'user.email={login}@users.noreply.github.com',
        '-c', 'commit.gpgsign=false', 'commit', '-q', '-m', 'PlanWAT volunteer crawl', cwd=tree)
    auth = []
    if token:
        # In a header, never in the URL, so the token cannot end up in a log line or .git/config.
        basic = base64.b64encode(f'x-access-token:{token}'.encode()).decode()
        auth = ['-c', f'http.extraHeader=Authorization: Basic {basic}']
    git(*auth, 'push', '-q', '--force', url, 'HEAD:refs/heads/crawl', cwd=tree, env=env)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--data', required=True, type=Path, help='the data checkout the crawl wrote into')
    ap.add_argument('--outcomes', required=True, type=Path, help='refresh.py --outcomes file')
    ap.add_argument('--fork', required=True, help='<login>/<repository> to push the crawl branch to')
    ap.add_argument('--remote', help='push here instead of https://github.com/<fork>.git (tests)')
    ap.add_argument('--keep', type=Path, help='also leave the bundle in this directory')
    ap.add_argument('--dry-run', action='store_true', help='build the bundle and print it, push nothing')
    args = ap.parse_args(argv)
    login = args.fork.partition('/')[0]
    outcomes = json.loads(args.outcomes.read_text(encoding='utf-8'))
    if outcomes.get('login') and outcomes['login'].lower() != login.lower():
        ap.error(f'the crawl ran as {outcomes["login"]}, not as the owner of {args.fork}')
    if outcomes.get('dry_run'):
        print('the crawl was a dry run: its changed calendars were never written, so they are not bundled')
    manifest, files = build_bundle(args.data, outcomes, login)
    counts = {s: sum(e['status'] == s for e in manifest['groups'].values()) for s in STATUSES}
    print(f'bundle for {login}: ' + ', '.join(f'{n} {s}' for s, n in counts.items()))
    if args.keep:
        args.keep.mkdir(parents=True, exist_ok=True)
        write_tree(args.keep, manifest, files)
    if args.dry_run:
        print(json.dumps(manifest, ensure_ascii=False, indent=1)[:4000])
        return 0
    if not manifest['groups']:
        print('nothing checked this window, nothing to push')
        return 0
    token = os.environ.get('PLANWAT_FORK_TOKEN') or os.environ.get('GITHUB_TOKEN') or ''
    tree = Path(tempfile.mkdtemp(prefix='planwat-bundle-'))
    try:
        write_tree(tree, manifest, files)
        push(tree, args.fork, login, token, args.remote)
    except subprocess.CalledProcessError as err:
        print(f'push to {args.fork} failed: {(err.stderr or "").strip()[-400:]}', file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(tree, ignore_errors=True)
    print(f'pushed to {args.fork}:crawl')
    return 0


if __name__ == '__main__':
    sys.exit(main())
