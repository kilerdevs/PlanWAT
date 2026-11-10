#!/usr/bin/env python3
"""The shared store of one refresh pass: the work stack the runners pull from (tools/refresh/stack.py, docs/REFRESH.md).

Every document of a pass is a small JSON file on a git ref of its own in this repository:

    refs/planwat/pass/<planned>-<run id>/r/<runner>   a runner's heartbeat, written only by that runner
    refs/planwat/pass/<planned>-<run id>/s/<slot>     one faculty's pass (its chunks), written by anyone, by CAS

A runner's doc is simply force-pushed. A slot doc changes by compare-and-swap: the new commit is pushed with
`--force-with-lease=<ref>:<the sha it was read at>` (an empty lease for a ref that must not exist yet), which the
remote checks atomically against the ref as it stands. Two runners claiming the same chunk at once therefore cannot
both win: the loser reads the ref again and decides anew. A read is one `git ls-remote` (which docs changed) and a fetch
of only the changed ones. Git traffic does not count against the REST API's rate limit, the runners already hold push
credentials in their data checkout (.github/actions/refresh), and refs outside heads/ and tags/ trigger no workflow.
The report job sweeps a pass's refs when it ends (`board.py sweep`), and any left over from a pass cut short.

Nothing here decides anything; MemoryStore is the same store in memory for the tests, with failures on demand.
"""
import argparse
import copy
import json
import os
import random
import re
import subprocess
import sys
import threading
import time
import uuid

REF_ROOT = 'refs/planwat/pass/'
# where a runner's checkout keeps what it fetched of the store (GitStore.forget drops it)
LOCAL = 'refs/planwat-seen/'
# <planned Unix seconds>-<run id>
KEY_RE = re.compile(r'^(\d{1,12})-(\d{1,20})$')
# r/<runner> or s/<slot> (a slot's '~' is not allowed in a ref name: it is stored as '@')
NAME_RE = re.compile(r'^(?:r/[a-z0-9][a-z0-9-]{0,38}|s/[a-z]{2,8}(?:@\d{4}-\d{2}-(?:zima|lato))?)$')
MAX_DOC = 256 * 1024
SWEEP_HOURS = 6
TRIES = 6
# git's messages in English whatever the machine's locale: a lost race is told apart by them
GIT_ENV = dict(os.environ, LC_ALL='C', LANG='C', LANGUAGE='C')


class StoreError(Exception):
    """The store could not be read or written (network, credentials, a remote that is gone)."""


class Conflict(StoreError):
    """A compare-and-swap lost to other writers every time it tried."""


BoardError = StoreError  # the name older callers know


def ref_of(key, name):
    return f'{REF_ROOT}{key}/{name}'


def _rejected(err):
    text = str(err)
    return any(sign in text for sign in ('[rejected]', '[remote rejected]', 'stale info', 'fetch first',
                                         'non-fast-forward', 'incorrect old value', 'cannot lock ref',
                                         'failed to update ref'))


class GitStore:
    """The pass's documents on git refs of `remote`, through the git repository at `repo` (the runner's data checkout).

    All git calls of one store run one at a time (a shallow checkout does not like two fetches at once)."""

    def __init__(self, repo, key, remote='origin', timeout=40, run=subprocess.run, sleep=time.sleep):
        if not KEY_RE.match(key or ''):
            raise ValueError(f'bad store key: {key!r}')
        self.repo, self.key, self.remote = str(repo), key, remote
        self.timeout, self.run, self.sleep = timeout, run, sleep
        self.cache = {}  # name -> (sha, doc)
        self.lock = threading.RLock()

    def _git(self, *args, data=None):
        try:
            done = self.run(['git', '-C', self.repo, '-c', 'user.name=planwat-refresh',
                             '-c', 'user.email=planwat-refresh@users.noreply.github.com', *args],
                            input=data, capture_output=True, timeout=self.timeout, env=GIT_ENV)
        except (OSError, subprocess.SubprocessError) as err:
            raise StoreError(f'git {args[0]}: {err}') from err
        if done.returncode != 0:
            raise StoreError(f'git {args[0]}: {done.stderr.decode("utf-8", "replace").strip()[-300:]}')
        return done.stdout.decode('utf-8', 'replace')

    def _listed(self, pattern):
        """{name: sha} of the pass's refs matching `pattern` (relative to the pass)."""
        prefix = f'{REF_ROOT}{self.key}/'
        out = {}
        for line in self._git('ls-remote', self.remote, prefix + pattern).splitlines():
            sha, _, ref = line.partition('\t')
            name = ref[len(prefix):] if ref.startswith(prefix) else ''
            if NAME_RE.match(name) and re.match(r'^[0-9a-f]{40,64}$', sha):
                out[name] = sha
        return out

    def _load(self, refs):
        """Fetch what changed of `refs` ({name: sha}) into the cache. The ref may have moved since it was listed: what
        counts is what the fetch brought (kept on a local ref, LOCAL), never the listed sha."""
        changed = [n for n, sha in refs.items() if self.cache.get(n, (None,))[0] != sha]
        if not changed:
            return
        local = f'{LOCAL}{self.key}/'
        self._git('fetch', '-q', '--no-tags', '--no-write-fetch-head', self.remote,
                  *[f'+{ref_of(self.key, n)}:{local}{n}' for n in changed])
        got = {}
        for line in self._git('for-each-ref', '--format=%(objectname) %(refname)', local).splitlines():
            sha, _, ref = line.partition(' ')
            got[ref[len(local):]] = sha
        for name in changed:
            sha = got.get(name)
            if sha is None:
                continue
            try:
                text = self._git('cat-file', 'blob', f'{sha}:doc.json')
                doc = json.loads(text) if len(text) <= MAX_DOC else None
            except (StoreError, ValueError):
                doc = None
            self.cache[name] = (sha, doc if isinstance(doc, dict) else None)

    def forget(self):
        """Drop the local copies of every pass's docs from the checkout (best effort)."""
        with self.lock:
            try:
                listed = self._git('for-each-ref', '--format=delete %(refname)', LOCAL)
                if listed.strip():
                    self._git('update-ref', '--stdin', data=listed.encode())
            except StoreError:
                pass

    def read(self):
        """{name: doc} of every document of the pass (a fresh copy). Raises StoreError when unreadable."""
        with self.lock:
            refs = self._listed('*')
            self._load(refs)
            for name in list(self.cache):
                if name not in refs:
                    del self.cache[name]
            return {n: copy.deepcopy(doc) for n, (_, doc) in self.cache.items() if doc is not None}

    def _commit(self, name, doc):
        body = (json.dumps(doc, ensure_ascii=False, sort_keys=True) + '\n').encode('utf-8')
        if len(body) > MAX_DOC:
            raise StoreError(f'{name}: the doc is too large ({len(body)} bytes)')
        blob = self._git('hash-object', '-w', '--stdin', data=body).strip()
        tree = self._git('mktree', data=f'100644 blob {blob}\tdoc.json\n'.encode()).strip()
        # a nonce in every commit: two writers making the same doc in the same second would otherwise make the same
        # commit, and a push of what the remote already holds succeeds without its lease ever being checked
        return self._git('commit-tree', tree, '-m', f'{self.key} {name} {uuid.uuid4().hex}').strip()

    def put(self, name, doc):
        """Overwrite `name` (a runner's own doc). Raises StoreError."""
        if not NAME_RE.match(name):
            raise ValueError(f'bad doc name: {name!r}')
        with self.lock:
            commit = self._commit(name, doc)
            self._git('push', '-q', '--force', self.remote, f'{commit}:{ref_of(self.key, name)}')
            self.cache[name] = (commit, copy.deepcopy(doc))

    def update(self, name, fn, tries=TRIES):
        """Compare-and-swap: `fn(doc or None)` returns the new doc, or None for "leave it". Returns (doc, written):
        the doc as it now stands and whether this call wrote it. Raises Conflict after `tries` lost races."""
        if not NAME_RE.match(name):
            raise ValueError(f'bad doc name: {name!r}')
        with self.lock:
            if name not in self.cache:  # never read: ask the remote first rather than lose a race to a known doc
                self._load(self._listed(name))
            sha, doc = self.cache.get(name, (None, None))
            for attempt in range(tries):
                new = fn(copy.deepcopy(doc))
                if new is None:
                    return copy.deepcopy(doc), False
                commit = self._commit(name, new)
                ref = ref_of(self.key, name)
                try:
                    self._git('push', '-q', f'--force-with-lease={ref}:{sha or ""}', self.remote, f'{commit}:{ref}')
                except StoreError as err:
                    if not _rejected(err):
                        raise
                    refs = self._listed(name)
                    self._load(refs)
                    if name not in refs:
                        self.cache.pop(name, None)
                    sha, doc = self.cache.get(name, (None, None))
                    self.sleep(random.uniform(0.05, 0.4) * (attempt + 1))
                    continue
                self.cache[name] = (commit, copy.deepcopy(new))
                return copy.deepcopy(new), True
        raise Conflict(f'{name}: lost {tries} races in a row')


class MemoryStore:
    """The store in a dict shared by the runners of a test (each runner its own MemoryStore on the same `shared`).

    Failures on demand, per runner: `down` (every call raises), `fail_reads`/`fail_writes` (the next N raise),
    `rejects` (the next N writes lose a race first), `delay` (seconds each call takes, through `sleep`)."""

    def __init__(self, shared=None, lock=None, sleep=time.sleep):
        self.shared = shared if shared is not None else {}
        self.lock = lock or threading.Lock()
        self.sleep = sleep
        self.down = False
        self.fail_reads = self.fail_writes = self.rejects = 0
        self.delay = 0.0
        self.writes = 0

    def _check(self, write):
        if self.delay:
            self.sleep(self.delay)
        if self.down:
            raise StoreError('the store is down')
        if write and self.fail_writes:
            self.fail_writes -= 1
            raise StoreError('write failed')
        if not write and self.fail_reads:
            self.fail_reads -= 1
            raise StoreError('read failed')

    def read(self):
        self._check(False)
        with self.lock:
            return {n: json.loads(text) for n, (_, text) in self.shared.items()}

    def put(self, name, doc):
        if not NAME_RE.match(name):
            raise ValueError(f'bad doc name: {name!r}')
        self._check(True)
        with self.lock:
            version = self.shared.get(name, (0, ''))[0]
            self.shared[name] = (version + 1, json.dumps(doc))
            self.writes += 1

    def update(self, name, fn, tries=TRIES):
        if not NAME_RE.match(name):
            raise ValueError(f'bad doc name: {name!r}')
        self._check(True)
        for _ in range(tries):
            with self.lock:
                if self.rejects:
                    self.rejects -= 1
                    continue
                current = self.shared.get(name)
                doc = json.loads(current[1]) if current else None
                new = fn(copy.deepcopy(doc))
                if new is None:
                    return doc, False
                text = json.dumps(new)
                if len(text) > MAX_DOC:
                    raise StoreError(f'{name}: the doc is too large')
                self.shared[name] = ((current[0] if current else 0) + 1, text)
                self.writes += 1
                return json.loads(text), True
        raise Conflict(f'{name}: lost {tries} races in a row')


def sweep(repo, run_id='', hours=SWEEP_HOURS, remote='origin', now=None, run=subprocess.run):
    """Delete the refs of run `run_id` (the pass that just ended) and of every pass planned over `hours` ago. Returns
    the refs deleted. Also takes the older layout (<key>/w<wave>/<runner>), which the same key pattern matches."""
    now = time.time() if now is None else now
    store = GitStore(repo, '0-0', remote, run=run)
    listed = store._git('ls-remote', remote, f'{REF_ROOT}*')
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
        store._git('push', '-q', remote, '--delete', *doomed[i:i + 50])
    return doomed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('sweep', help="delete a finished pass's refs and any older than a few hours")
    p.add_argument('--repo', required=True, help='a checkout of this repository with push credentials')
    p.add_argument('--run-id', default='', help='the run (pass) that just ended')
    p.add_argument('--hours', type=float, default=SWEEP_HOURS)
    args = ap.parse_args(argv)
    try:
        gone = sweep(args.repo, args.run_id, args.hours)
    except StoreError as err:
        print(f'store not swept: {err}')
        return 1
    print(f'board: {len(gone)} refs deleted')
    return 0


if __name__ == '__main__':
    sys.exit(main())
