#!/usr/bin/env python3
"""Read the volunteer registry the only trusted way: from a commit GitHub verifies as signed by a registry editor.

    python tools/volunteer/registry.py --upstream kilerdevs/PlanWAT --editors kilerdevs --out volunteers.json

The registry (volunteers.json) lives alone on the project's `volunteers` branch and is edited with manage.py,
which signs every commit. The coordinator (collect.yml) and every volunteer crawler (entrypoint.sh, the refresh
action in volunteer mode) read it through fetch_verified():

  1. GET /repos/<upstream>/commits/volunteers: the head commit, its signature verdict and its committer;
  2. refuse unless GitHub verified the signature and the committer is one of the editors;
  3. with --after (the commit the reader used last), refuse unless the head is that commit or a descendant of it;
  4. download volunteers.json at exactly that commit (not at the branch, which could move in between);
  5. check it with assign.check_registry.

So a token that can push branches still cannot change who is trusted or who checks what, and the coordinator, which
keeps the commit it used in volunteer-state.json, refuses a force-push back to an older signed registry (one from
before a volunteer was suspended or removed). Exit codes of the CLI: 0 written, 1 GitHub unreachable (try later),
2 refused (unsigned, wrong signer, rolled back, malformed), 3 no registry yet.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import assign  # noqa: E402

API = 'https://api.github.com'
RAW = 'https://raw.githubusercontent.com'
BRANCH = 'volunteers'
MAX_BYTES = 1024 * 1024
DEFAULT_EDITORS = 'kilerdevs'


class Unavailable(RuntimeError):
    """GitHub could not be asked right now; nothing is known about the registry."""


class Missing(LookupError):
    """There is no volunteers branch (yet)."""


def http_get(url, token=None, limit=MAX_BYTES, timeout=30):
    """(status, body bytes) of a GET; raises Unavailable on network trouble, never on an HTTP status."""
    headers = {'User-Agent': 'planwat-volunteer', 'Accept': 'application/vnd.github+json',
               'X-GitHub-Api-Version': '2022-11-28'}
    if token and url.startswith(API):
        headers['Authorization'] = f'Bearer {token}'
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            body = r.read(limit + 1)
            status = r.status
    except urllib.error.HTTPError as err:
        return err.code, b''
    except (urllib.error.URLError, OSError) as err:
        raise Unavailable(f'{url}: {err}')
    if len(body) > limit:
        raise assign.RegistryError(f'{url}: larger than {limit} bytes')
    return status, body


def editor_set(editors):
    return {e.strip().lower() for e in str(editors).replace(',', ' ').split() if e.strip()}


def is_sha(text):
    return isinstance(text, str) and len(text) in (40, 64) and all(c in '0123456789abcdef' for c in text)


def api_get(get, url, token):
    status, body = get(url, token)
    if status == 401 and token:
        # An expired or revoked token must not blind the crawler: the registry is public, so ask anonymously.
        status, body = get(url, None)
    return status, body


def fetch_verified(upstream, editors, token=None, get=http_get, after=None):
    """(registry, raw bytes, commit sha, committer) from a verified commit of an editor; with `after`, only when
    that commit is `after` or a descendant of it. Raises Missing, Unavailable or assign.RegistryError (refused)."""
    allowed = editor_set(editors)
    if not allowed:
        raise assign.RegistryError('no registry editors configured')
    if after and not is_sha(after):
        raise assign.RegistryError(f'the registry commit used last is not a commit id: {after!r}')
    status, body = api_get(get, f'{API}/repos/{upstream}/commits/{BRANCH}', token)
    if status in (404, 422):
        raise Missing(f'{upstream} has no {BRANCH} branch')
    if status != 200:
        raise Unavailable(f'GitHub answered {status} for the {BRANCH} branch')
    try:
        head = json.loads(body)
        sha = head['sha']
        verified = head['commit']['verification']['verified'] is True
        committer = ((head.get('committer') or {}).get('login') or '').lower()
    except (ValueError, KeyError, TypeError):
        raise Unavailable('GitHub answered something that is not a commit')
    if not is_sha(sha):
        raise Unavailable('GitHub answered a malformed commit id')
    if not verified or committer not in allowed:
        raise assign.RegistryError(f'{BRANCH} {sha[:12]} is not a verified commit by a registry editor '
                                   f'(verified={verified}, committer={committer or "-"})')
    if after and after != sha:
        # Every edit (manage.py) is a new commit on top of the last one, so the head only ever moves forward.
        # An older signed commit is still signed: only its place in the history gives a rollback away.
        status, body = api_get(get, f'{API}/repos/{upstream}/compare/{after}...{sha}?per_page=1', token)
        if status == 404:
            raise assign.RegistryError(f'{BRANCH} {sha[:12]} is not related to the registry used last '
                                       f'({after[:12]}): refused as a rollback')
        if status != 200:
            raise Unavailable(f'GitHub answered {status} comparing {after[:12]} with {sha[:12]}')
        try:
            relation = json.loads(body)['status']
        except (ValueError, KeyError, TypeError):
            raise Unavailable('GitHub answered something that is not a comparison')
        if relation != 'ahead':
            raise assign.RegistryError(f'{BRANCH} {sha[:12]} is {relation} the registry used last ({after[:12]}), '
                                       'not ahead of it: refused as a rollback')
    status, raw = get(f'{RAW}/{upstream}/{sha}/volunteers.json', None)
    if status != 200:
        raise Unavailable(f'volunteers.json at {sha[:12]}: HTTP {status}')
    try:
        registry = assign.check_registry(json.loads(raw.decode('utf-8')))
    except (UnicodeDecodeError, ValueError) as err:
        raise assign.RegistryError(f'volunteers.json at {sha[:12]}: {err}')
    return registry, raw, sha, committer


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--upstream', default=os.environ.get('PLANWAT_UPSTREAM', 'kilerdevs/PlanWAT'))
    ap.add_argument('--editors', default=os.environ.get('PLANWAT_REGISTRY_EDITORS', DEFAULT_EDITORS),
                    help='logins whose signed commits may set the registry (comma or space separated)')
    ap.add_argument('--out', required=True, type=Path, help='write the verified volunteers.json here')
    ap.add_argument('--after', default='', help='the registry commit used last: refuse a head that is not it or newer')
    args = ap.parse_args(argv)
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN') or None
    try:
        _, raw, sha, committer = fetch_verified(args.upstream, args.editors, token, after=args.after or None)
    except Missing as err:
        print(f'no registry yet: {err}')
        return 3
    except Unavailable as err:
        print(f'registry unavailable: {err}', file=sys.stderr)
        return 1
    except assign.RegistryError as err:
        print(f'registry refused: {err}', file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix('.tmp')
    tmp.write_bytes(raw)
    tmp.replace(args.out)
    print(f'registry {sha[:12]} signed by {committer}')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as fh:
            fh.write(f'sha={sha}\ncommitter={committer}\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
