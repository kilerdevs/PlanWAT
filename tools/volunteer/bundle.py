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
PLANWAT_FORK_TOKEN (or GITHUB_TOKEN): a token that can write to the fork and nothing else. Before pushing, the
token is asked about itself: a classic or OAuth token (which reaches every repository of the account) is refused,
one that cannot push to the fork is reported plainly, and its expiry date travels in the manifest
(`token_expires`) so the coordinator can warn before the crawler goes quiet. A window with nothing to check still
pushes its (empty) bundle: it tells the coordinator this volunteer is alive.
"""
import argparse
import base64
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'refresh'))
import core  # noqa: E402

FORMAT = 1
STATUSES = ('changed', 'unchanged', 'not_ready', 'gone')
API = 'https://api.github.com'
# Classic personal access tokens and OAuth tokens (what `gh auth login` stores) reach every repository the account
# can write to: one leaked from a crawler's .env would be a disaster, so they are not accepted at all.
BROAD_TOKENS = ('ghp_', 'gho_')
PUSH_TRIES = 3
PUSH_TIMEOUT = 300  # seconds one push attempt may take: a stalled connection counts as a failed attempt


def version():
    return json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version']


def token_report(fork, token, opener=urllib.request.urlopen):
    """(problem or '', expiry 'YYYY-MM-DDTHH:MM:SS' or None) for the token that will push to `fork`.
    A network failure is not a problem: the push itself will tell."""
    if token.startswith(BROAD_TOKENS):
        return ('this is a classic or OAuth token, which reaches all your repositories: create a fine-grained '
                'token limited to your fork (Contents: Read and write)'), None
    if token.startswith('ghs_'):
        return '', None  # the fork's own Actions token (mode B): its job permissions already say contents: write
    req = urllib.request.Request(f'{API}/repos/{fork}', headers={
        'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json', 'User-Agent': 'planwat-volunteer'})
    try:
        with opener(req, timeout=30) as r:
            body = json.loads(r.read(1024 * 1024).decode('utf-8'))
            expires = r.headers.get('github-authentication-token-expiration')
    except urllib.error.HTTPError as err:
        if err.code == 401:
            return 'GitHub does not accept the token (expired or revoked): create a new one', None
        if err.code in (403, 404):
            return f'the token cannot see {fork}: select that repository when creating the token', None
        return '', None
    except (urllib.error.URLError, OSError, ValueError):
        return '', None
    if isinstance(body, dict) and isinstance(body.get('permissions'), dict) and not body['permissions'].get('push'):
        return f'the token cannot write to {fork}: give it Contents: Read and write', None
    # "2026-11-01 12:00:00 UTC"
    found = re.match(r'(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})', expires or '')
    return '', (f'{found.group(1)}T{found.group(2)}' if found else None)


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


def git(*args, cwd, env=None, timeout=120):
    return subprocess.run(['git', *args], cwd=cwd, env=env, check=True, capture_output=True, text=True,
                          timeout=timeout).stdout


def push(tree, fork, login, token, remote=None, tries=1, sleep=time.sleep):
    """Commit `tree` as a single parentless commit and force-push it to <fork>:crawl (retrying a failed push)."""
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
    for attempt in range(1, tries + 1):
        try:
            git(*auth, 'push', '-q', '--force', url, 'HEAD:refs/heads/crawl', cwd=tree, env=env,
                timeout=PUSH_TIMEOUT)
            return
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            if attempt == tries:
                raise
            sleep(15 * attempt)


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
        print('nothing checked this window: pushing an empty bundle so the coordinator knows this crawler is alive')
    token = os.environ.get('PLANWAT_FORK_TOKEN') or os.environ.get('GITHUB_TOKEN') or ''
    if token and not args.remote:
        problem, expires = token_report(args.fork, token)
        if problem:
            print(f'not pushing: {problem}', file=sys.stderr)
            return 1
        if expires:
            manifest['token_expires'] = expires
            left = dt.datetime.fromisoformat(expires) - core.now_utc()
            if left < dt.timedelta(days=14):
                print(f'WARNING: the fork token expires on {expires[:10]}: create a new one before then '
                      f'and run planwat-crawler setup (docs/WOLONTARIUSZE.md, "Szybki start")')
    tree = Path(tempfile.mkdtemp(prefix='planwat-bundle-'))
    try:
        write_tree(tree, manifest, files)
        push(tree, args.fork, login, token, args.remote, tries=PUSH_TRIES)
    except subprocess.CalledProcessError as err:
        # One line: the runner shows the last line of this as the reason in `status` and the doctor.
        print(f'push to {args.fork} failed: {" ".join((err.stderr or "").split())[-400:]}', file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired as err:
        print(f'push to {args.fork} failed: no answer in {err.timeout:.0f} s', file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(tree, ignore_errors=True)
    print(f'pushed to {args.fork}:crawl')
    return 0


if __name__ == '__main__':
    sys.exit(main())
