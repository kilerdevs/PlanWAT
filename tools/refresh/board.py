#!/usr/bin/env python3
"""The work board of one crawl wave: how runners that crawl side by side see each other (docs/REFRESH.md).

Each runner of a wave keeps one small JSON doc (tools/refresh/steal.py says what is in it) on a git ref of its own in
this repository:

    refs/planwat/pass/<planned>-<run id>/w<wave>/<runner>

Only that runner ever writes its ref, so two writers never race: an update is a parentless commit holding board.json,
force-pushed. The others read it with `git ls-remote` (one cheap round trip tells which docs changed) and fetch only
the changed ones. Git traffic does not count against the REST API's rate limit, the runners already hold push
credentials in their data checkout (.github/actions/refresh), and refs outside heads/ and tags/ trigger no workflow.
The report job sweeps a pass's refs when it ends (`board.py sweep`), and any left over from a pass cut short.

Nothing here decides anything: a board that cannot be reached only means the runners do not help each other.
"""
import argparse
import copy
import json
import re
import subprocess
import sys
import threading
import time

REF_ROOT = 'refs/planwat/pass/'
# <planned Unix seconds>-<run id>/w<wave>
KEY_RE = re.compile(r'^(\d{1,12})-(\d{1,20})/w(\d{1,2})$')
NAME_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,38}$')
MAX_DOC = 256 * 1024
SWEEP_HOURS = 6


class BoardError(Exception):
    pass


def ref_of(key, runner):
    return f'{REF_ROOT}{key}/{runner}'


class GitBoard:
    """The board on git refs of `remote`, through the git repository at `repo` (the runner's data checkout)."""

    def __init__(self, repo, key, runner, remote='origin', timeout=40, run=subprocess.run):
        if not KEY_RE.match(key or '') or not NAME_RE.match(runner or ''):
            raise ValueError(f'bad board key or runner: {key!r} {runner!r}')
        self.repo, self.key, self.runner, self.remote = str(repo), key, runner, remote
        self.timeout, self.run = timeout, run
        self.seen = {}  # peer -> (sha, doc): only a changed sha is fetched again
        self.lock = threading.Lock()

    def _git(self, *args, data=None):
        try:
            done = self.run(['git', '-C', self.repo, '-c', 'user.name=planwat-refresh',
                             '-c', 'user.email=planwat-refresh@users.noreply.github.com', *args],
                            input=data, capture_output=True, timeout=self.timeout)
        except (OSError, subprocess.SubprocessError) as err:
            raise BoardError(f'git {args[0]}: {err}') from err
        if done.returncode != 0:
            raise BoardError(f'git {args[0]}: {done.stderr.decode("utf-8", "replace").strip()[-300:]}')
        return done.stdout.decode('utf-8', 'replace')

    def publish(self, doc):
        """Push `doc` as this runner's board doc; True when the remote has it."""
        body = (json.dumps(doc, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')
        if len(body) > MAX_DOC:
            return False
        with self.lock:
            try:
                blob = self._git('hash-object', '-w', '--stdin', data=body).strip()
                tree = self._git('mktree', data=f'100644 blob {blob}\tboard.json\n'.encode()).strip()
                commit = self._git('commit-tree', tree, '-m', f'board {self.key} {self.runner}').strip()
                self._git('push', '-q', '--force', self.remote, f'{commit}:{ref_of(self.key, self.runner)}')
            except BoardError:
                return False
        return True

    def peers(self):
        """{runner: doc} of every other runner on this board (unchanged docs from memory); None when unreadable."""
        with self.lock:
            try:
                listed = self._git('ls-remote', self.remote, f'{REF_ROOT}{self.key}/*')
            except BoardError:
                return None
            refs = {}
            prefix = f'{REF_ROOT}{self.key}/'
            for line in listed.splitlines():
                sha, _, ref = line.partition('\t')
                name = ref[len(prefix):] if ref.startswith(prefix) else ''
                if NAME_RE.match(name) and name != self.runner and re.match(r'^[0-9a-f]{40,64}$', sha):
                    refs[name] = sha
            changed = [n for n, sha in refs.items() if self.seen.get(n, (None,))[0] != sha]
            if changed:
                try:
                    # FETCH_HEAD stays the data branch's: the push step resets the checkout to it
                    self._git('fetch', '-q', '--no-tags', '--no-write-fetch-head', self.remote,
                              *[ref_of(self.key, n) for n in changed])
                except BoardError:
                    return None
            for name in changed:
                try:
                    text = self._git('cat-file', 'blob', f'{refs[name]}:board.json')
                    doc = json.loads(text) if len(text) <= MAX_DOC else None
                except (BoardError, ValueError):
                    doc = None
                self.seen[name] = (refs[name], doc if isinstance(doc, dict) else None)
            for name in list(self.seen):
                if name not in refs:
                    del self.seen[name]
            return {n: copy.deepcopy(doc) for n, (_, doc) in self.seen.items() if doc is not None}


class MemoryBoard:
    """A board in a dict shared by the runners of a test; `fail` makes the next publishes fail."""

    def __init__(self, store, runner, lock=None):
        self.store, self.runner = store, runner
        self.lock = lock or threading.Lock()
        self.fail = 0
        self.reads_fail = 0

    def publish(self, doc):
        with self.lock:
            if self.fail:
                self.fail -= 1
                return False
            self.store[self.runner] = json.loads(json.dumps(doc))
        return True

    def peers(self):
        with self.lock:
            if self.reads_fail:
                self.reads_fail -= 1
                return None
            return {n: json.loads(json.dumps(d)) for n, d in self.store.items() if n != self.runner}


def sweep(repo, run_id='', hours=SWEEP_HOURS, remote='origin', now=None, run=subprocess.run):
    """Delete the board refs of run `run_id` (the pass that just ended, both its waves) and of every wave planned over
    `hours` ago. Returns the refs deleted."""
    now = time.time() if now is None else now
    board = GitBoard(repo, '0-0/w1', 'sweeper', remote, run=run)
    listed = board._git('ls-remote', remote, f'{REF_ROOT}*')
    doomed = []
    for line in listed.splitlines():
        _, _, ref = line.partition('\t')
        rest = ref[len(REF_ROOT):] if ref.startswith(REF_ROOT) else ''
        key = re.match(r'^(\d{1,12})-(\d{1,20})/', rest)
        if not key:
            continue
        if (run_id and key.group(2) == str(run_id)) or float(key.group(1)) < now - hours * 3600:
            doomed.append(ref)
    for i in range(0, len(doomed), 50):
        board._git('push', '-q', remote, '--delete', *doomed[i:i + 50])
    return doomed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('sweep', help="delete a finished pass's board refs and any older than a few hours")
    p.add_argument('--repo', required=True, help='a checkout of this repository with push credentials')
    p.add_argument('--run-id', default='', help='the run (pass) that just ended')
    p.add_argument('--hours', type=float, default=SWEEP_HOURS)
    args = ap.parse_args(argv)
    try:
        gone = sweep(args.repo, args.run_id, args.hours)
    except BoardError as err:
        print(f'board not swept: {err}')
        return 1
    print(f'board: {len(gone)} refs deleted')
    return 0


if __name__ == '__main__':
    sys.exit(main())
