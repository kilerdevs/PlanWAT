#!/usr/bin/env python3
"""The work stack of one refresh pass: every runner pulls what it crawls, nothing is handed out (docs/REFRESH.md).

A pass is a set of slots: a faculty's pass over the running semester (slot "wml") and, while the faculties publish the
coming one, its pass over that (slot "wml~2027-28-zima"). Each slot is one document on the shared store (board.py),
changed only by compare-and-swap:

  open     The first runner to claim a slot (its leader) lists the faculty, leaves out what is fresh or not ready, and
           cuts the rest, stalest first, into chunks of CHUNK groups: a stack with two ends.
  claim    The leader takes chunks from the front, every other runner (a helper) from the back, so they meet in the
           middle of the faculty's list. Finishing a chunk and taking the next is one swap; a helper first lists the
           faculty from its own address (the pages' links, and its wall probe), and only then takes anything.
  choose   Which slot a runner's lane turns to next is one pure function of what the store says (choose()): a runner
           opens the slots it prefers (fleet.json `prefers`) first, and the others leave those to it while it is up;
           then the slots only it can take, the largest first; then it continues its own; then it helps where the most
           is left, its preferred ones first.

A runner crawls with one lane per policy group (core.POLICY_GROUPS): a lane is the only thing that sends that policy a
request from this runner, listings included, so a site never sees two requests at once from one address. At most
--lanes lanes crawl at a time; a lane doing its own work goes before one helping.

It is built for runners that often fail. Checking a group twice is harmless (a conditional fetch, a hash compare), so a
crash may cost a check twice, never a check lost:

  * a runner that cannot list a faculty (a wall, an error, a page gone) says so on the slot (`cant`) before it takes
    anything there, so it strands nothing; a wall in the middle of a chunk puts the chunk's rest back on the stack;
  * a leader that cannot list its slot lets it go, and the next runner able to opens it;
  * a runner whose heartbeat stops (STALE), or one of whose lanes stops moving (LANE_STALE), loses what it holds:
    another one takes its chunks over;
  * a chunk that keeps failing (a converter crashing on a page) is closed after MAX_FAILS tries, reported, not retried
    forever;
  * a store that cannot be reached at the start sends the runner back to its static share (fleet.py's fallback); one
    that goes away later lets it finish what it leads, then stop.

  hunt     When no runner up can reach a faculty from its own address (plebania off, the others at its wall), a runner
           with an egress (fleet.json `egress`) has it search the pool's public proxies for exits that get through
           (docs/EGRESS.md, "Polowanie na wyjścia"), and crawls the slot through them: `via` on the slot. What it found
           goes on the slot too (`exits`), so another runner checks those with its own egress and helps from the back.
           A runner may also take some faculties only that way (fleet.json `pool`), and help with some of them through
           the pool while another runner leads them (`pool_help`).

Nothing here touches a faculty site: refresh.py hands in what crawls (Ops). Unit-tested offline (tests/test_refresh.py).
"""
import argparse
import copy
import json
import re
import sys
import threading
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import board  # noqa: E402

CHUNK = 8               # groups per chunk
HEARTBEAT = 30          # a runner's doc is pushed at least this often
STALE = 150             # a runner whose doc stood still this long is gone (by the reader's own clock)
JOIN_GRACE = 180        # an expected runner that has not shown up this long after we started is not waited for
LANE_STALE = 600        # a lane holding a chunk without a page checked this long is stuck
POLL = 10               # seconds between reads of the store
STORE_DOWN = 180        # the store unreadable this long: finish what this runner leads, then stop
RETRY_ERROR = 300       # a listing that failed for another reason than a wall is tried once more after this long
MAX_FAILS = 2           # a chunk whose crawl crashed this many times is closed as failed
MAX_EXITS = 8           # proxy exits kept on a slot for the other runners
START_TRIES = 4         # attempts to reach the store at the start before falling back
SHY_PASSES = 3          # passes in a row a runner could not list a faculty before it turns there last
WALL = 'wall'

SLOT_RE = re.compile(r'^([a-z]{2,8})(~\d{4}-\d{2}-(?:zima|lato))?$')
STATES = ('listing', 'open', 'closed', 'unlisted')


def faculty_of(slot):
    return SLOT_RE.match(slot).group(1)


def term_of(slot):
    """The term of an ahead slot ('2027-28-zima'), '' for a slot of the running semester."""
    m = SLOT_RE.match(slot)
    return m.group(2)[1:] if m.group(2) else ''


def doc_name(slot):
    return 's/' + slot.replace('~', '@')


def slot_of(name):
    return name[2:].replace('@', '~') if name.startswith('s/') else None


class Walled(Exception):
    """A faculty's wall refuses this runner."""


class Unlisted(Exception):
    """A faculty's listing page is gone (core.Gone)."""


class StoreUnavailable(Exception):
    """The store could not be reached at the start: the runner crawls its static share instead."""


# -- the documents ---------------------------------------------------------------------------------------------------


def chunks_of(codes, size=CHUNK):
    return [{'id': i, 'codes': codes[i * size:(i + 1) * size], 'state': 'free', 'by': None, 'fails': 0}
            for i in range((len(codes) + size - 1) // size)]


def remaining(doc):
    """Whether a slot still has work: not listed yet, or a chunk not done."""
    if doc is None or doc.get('state') in ('listing', 'unlisted'):
        return True
    if doc.get('state') == 'closed':
        return False
    return any(c.get('state') != 'done' for c in doc.get('chunks', []))


def slot_status(doc, able):
    """A slot's verdict at the end of a pass, from its doc and the runners that could have taken it (`able`).

    done (every chunk done), empty (nothing to do: an ahead semester not published), failed (closed with pages that kept
    failing, or a listing every able runner failed at for another reason than a wall), blocked (work left, and every
    able runner stands at its wall or could not list it, a wall among them), unfinished (work left that a runner could
    have done: a deadline, a runner gone), absent (nobody opened it)."""
    if doc is None:
        return 'absent'
    if doc.get('state') == 'closed':
        if doc.get('note') == 'empty':
            return 'empty'
        if doc.get('note') or any(c.get('failed') for c in doc.get('chunks', [])):
            return 'failed'
        return 'done'
    if not remaining(doc):
        return 'failed' if any(c.get('failed') for c in doc.get('chunks', [])) else 'done'
    cant = doc.get('cant') or {}
    if able and all(r in cant for r in able):
        return 'blocked' if any(cant[r].get('cause') == WALL for r in able) else 'failed'
    return 'unfinished'


# -- what one runner sees of the others ------------------------------------------------------------------------------


class Peers:
    """The runners' docs as this runner saw them change, on its own clock (no two machines' clocks compared)."""

    def __init__(self, me, clock, started=None, stale=STALE, lane_stale=LANE_STALE, join_grace=JOIN_GRACE):
        self.me, self.clock = me, clock
        self.started = clock() if started is None else started
        self.stale, self.lane_stale, self.join_grace = stale, lane_stale, join_grace
        self.docs, self.seen, self.ticks = {}, {}, {}
        self.read_at = self.started

    def observe(self, docs):
        now = self.clock()
        self.read_at = now
        for name, doc in docs.items():
            if name == self.me or not isinstance(doc, dict):
                continue
            mark = (doc.get('nonce'), doc.get('beat'))
            if self.seen.get(name, (None,))[0] != mark:
                self.seen[name] = (mark, now)
            self.docs[name] = doc
            for group, lane in (doc.get('lanes') or {}).items():
                if not isinstance(lane, dict):
                    continue
                tick = (lane.get('slot'), lane.get('chunk'), lane.get('tick'))
                if self.ticks.get((name, group), (None,))[0] != tick:
                    self.ticks[(name, group)] = (tick, now)

    def status(self, name):
        """'me', 'live', 'stale', 'done' or 'absent' (no doc yet)."""
        if name == self.me:
            return 'me'
        doc = self.docs.get(name)
        if doc is None:
            return 'absent'
        if doc.get('mode') == 'done':
            return 'done'
        # measured up to our last good read: a store we could not read makes nobody look gone
        return 'stale' if self.read_at - self.seen[name][1] > self.stale else 'live'

    def snapshot(self):
        """What choose() needs: {name: status}, the lanes that hold a chunk without moving, and our uptime."""
        now = self.clock()
        names = set(self.docs) | {r for r, _ in self.ticks}
        hung = set()
        for (name, group), ((slot, chunk, _), since) in self.ticks.items():
            if chunk is not None and self.status(name) == 'live' and self.read_at - since > self.lane_stale:
                hung.add((name, slot, chunk))
        return {n: self.status(n) for n in names}, hung, now - self.started


class View:
    """One reading of the store, the input of choose(): the slot docs, the runners' statuses, the stuck lanes."""

    def __init__(self, slots, statuses=None, hung=(), uptime=0.0, join_grace=JOIN_GRACE, stale=STALE):
        self.slots = slots
        self.statuses = statuses or {}
        self.hung = set(hung)
        self.uptime, self.join_grace, self.stale = uptime, join_grace, stale

    def status(self, name):
        return self.statuses.get(name, 'absent')

    def gone(self, name):
        """A runner not to wait for: finished, silent, or never seen while we waited long enough for it."""
        status = self.status(name)
        return status in ('stale', 'done') or (status == 'absent' and self.uptime > self.join_grace)

    def holder_dead(self, chunk, slot):
        by = chunk.get('by')
        if by is None:
            return True
        status = self.status(by)
        if status == 'me':
            return False
        if (by, slot, chunk.get('id')) in self.hung:
            return True
        return status in ('stale', 'done') or (status == 'absent' and self.uptime > self.stale)


class Me:
    """What choose() knows of the runner it decides for."""

    def __init__(self, name, slots, groups, expected=(), prefers=(), allow=None, prefers_of=None, costs=None,
                 chronic=(), shy=(), pool=(), pool_help=(), hunter=False, pool_of=None):
        self.name = name
        self.slots = list(slots)                    # the slots this runner may take, in the pass's order
        self.groups = dict(groups)                  # slot -> policy group
        self.expected = [r for r in expected if r != name]
        self.prefers = list(prefers)                # faculties, most preferred first
        self.allow = allow or {}                    # runner -> set of faculties it may take (None: any)
        self.prefers_of = prefers_of or {}          # runner -> its prefers
        self.costs = costs or {}                    # slot -> estimated work
        self.chronic = set(chronic)                 # faculties whose wall here outlasted a full wait lately
        self.shy = set(shy)                         # faculties this runner could not list SHY_PASSES passes in a row
        self.pool = set(pool)                       # faculties this runner takes only through pool exits
        self.pool_help = set(pool_help)             # ... and helps with through them while another runner leads
        self.hunter = bool(hunter)                  # it has an egress that can hunt for exits
        self.pool_of = pool_of or {}                # runner -> faculties it takes only through the pool
        self.cant = {}                              # slot -> {'cause', 'at' (our clock), 'tries'}
        self.waited = set()                         # slots this runner already waited a wall out for
        self.via = {}                               # slot -> 'pool' (reached through exits) or 'lost' (not any more)
        self.hunted = {}                            # slot -> the exits on it when this runner last searched

    def may(self, runner, slot):
        allowed = self.allow.get(runner)
        return allowed is None or faculty_of(slot) in allowed


def _pref_rank(prefers, slot):
    f = faculty_of(slot)
    return prefers.index(f) if f in prefers else len(prefers)


def choose(view, me, group, now=0.0, retry_error=RETRY_ERROR):
    """The next step of `me`'s lane for policy group `group`:

    ('open', slot)            list a slot nobody leads and cut it into chunks
    ('claim', slot, front)    take a chunk (front: the leader's end)
    ('hunt', slot)            search the pool for exits to a slot no runner up reaches directly (or check the
                              exits another runner found for it)
    ('wait', slot)            wait a wall out: work is left there that no runner up can take
    ('linger',)               nothing now, but a runner up holds work this one could get (or a leader is coming)
    ('end',)                  nothing this lane could ever do in this pass
    """
    mine = [s for s in me.slots if me.groups.get(s) == group]

    def doc(s):
        return view.slots.get(s)

    def cant_of(s, r):
        d = doc(s)
        return (d or {}).get('cant', {}).get(r) if d else None

    def via_of(s, r):
        return ((doc(s) or {}).get('via') or {}).get(r)

    def blocked_here(s):
        if me.via.get(s) == 'pool':
            return False  # reached through the exits the hunt found
        if faculty_of(s) in me.pool:
            return True  # never from this runner's own address
        c = me.cant.get(s)
        if c is None:
            return cant_of(s, me.name) is not None
        if c['cause'] != WALL and c.get('tries', 1) < 2 and now - c['at'] >= retry_error:
            return False  # one more try for a listing that failed without a wall
        return True

    def able(r, s):
        """Runner `r` may take slot `s` and nothing stops it there (a runner taking it only through the pool: once
        it found exits)."""
        if not me.may(r, s) or cant_of(s, r) is not None:
            return False
        return faculty_of(s) not in me.pool_of.get(r, ()) or via_of(s, r) == 'pool'

    def direct(r, s):
        """`r` may reach `s` from its own address and has not met its wall there."""
        return me.may(r, s) and cant_of(s, r) is None and faculty_of(s) not in me.pool_of.get(r, ())

    def others_able(s):
        return sum(1 for r in me.expected if able(r, s) and not view.gone(r))

    def openable(s):
        d = doc(s)
        if d is None or d.get('state') == 'unlisted':
            return True
        return d.get('state') == 'listing' and view.status(d.get('leader')) != 'me' and \
            view.holder_dead({'by': d.get('leader')}, s)

    def reserved(s):
        """Left to another runner that prefers it and is (or may soon be) up."""
        f = faculty_of(s)
        if f in me.prefers:
            return False
        return any(f in me.prefers_of.get(r, ()) and able(r, s) and not view.gone(r) for r in me.expected)

    def claimable(s):
        d = doc(s)
        if not d or d.get('state') != 'open':
            return 0
        return sum(1 for c in d.get('chunks', [])
                   if c.get('state') == 'free' or (c.get('state') == 'held' and view.holder_dead(c, s)))

    def hunting_elsewhere(s):
        """Another runner up is searching exits for `s` right now."""
        h = (doc(s) or {}).get('hunting') or {}
        return bool(h.get('runner')) and h['runner'] != me.name and view.status(h['runner']) == 'live'

    def hunt_for(s):
        if not me.hunter or me.via.get(s) == 'pool' or not remaining(doc(s)):
            return False
        exits = set((doc(s) or {}).get('exits') or ())
        if s in me.hunted:
            return bool(exits - me.hunted[s])  # exits found since this runner's own search: worth a check
        f = faculty_of(s)
        mark = me.cant.get(s)
        walled = f in me.pool or (mark is not None and mark['cause'] == WALL)
        if not walled:
            return False
        if exits:
            return True  # another runner found exits: checking them is a few requests, then this one helps
        if hunting_elsewhere(s):
            return False
        if f in me.pool_help and claimable(s) >= 2:
            return True
        return not any(direct(r, s) and not view.gone(r) for r in me.expected)

    # 1. open: what this runner prefers, then what only it can take, the largest first; never what another prefers
    opens = [s for s in mine if openable(s) and not blocked_here(s) and not reserved(s)]
    if opens:
        opens.sort(key=lambda s: (_pref_rank(me.prefers, s), faculty_of(s) in me.shy, others_able(s),
                                  -me.costs.get(s, 0), bool(term_of(s)), s))
        return ('open', opens[0])
    # 2. continue its own slots from the front
    own = [s for s in mine if (doc(s) or {}).get('leader') == me.name and not blocked_here(s) and claimable(s)]
    if own:
        own.sort(key=lambda s: (_pref_rank(me.prefers, s), -claimable(s), s))
        return ('claim', own[0], True)
    # 3. help from the back: its preferred slots first, then where most is left
    helps = [s for s in mine if (doc(s) or {}).get('leader') != me.name and not blocked_here(s) and claimable(s)]
    if helps:
        helps.sort(key=lambda s: (_pref_rank(me.prefers, s), faculty_of(s) in me.shy, -claimable(s), s))
        return ('claim', helps[0], False)
    # 4. nothing to take now. Hunt for exits where no runner up (or still coming) reaches what is left directly, or
    # where another runner already found some; help through the pool where this runner always may (pool_help).
    for s in mine:
        hunt = hunt_for(s)
        if hunt:
            return ('hunt', s)
    # A wall here: wait it out only when no other runner up (or still coming) can take what is left, and not when it
    # already outlasted a full wait lately (chronic); otherwise stay while they may need us.
    for s in mine:
        mark = me.cant.get(s)
        if (remaining(doc(s)) and mark and mark['cause'] == WALL and s not in me.waited
                and faculty_of(s) not in me.chronic
                and not any(able(r, s) and not view.gone(r) for r in me.expected)):
            return ('wait', s)
    for s in mine:
        d = doc(s)
        if not remaining(d):
            continue
        if me.hunter and s not in me.hunted and me.via.get(s) != 'pool' and hunting_elsewhere(s):
            return ('linger',)  # what another runner's hunt finds, this one may use
        if blocked_here(s):
            c = me.cant.get(s)
            if c and c['cause'] != WALL and c.get('tries', 1) < 2:
                return ('linger',)  # its one more try is still to come
            if any(able(r, s) and not view.gone(r) for r in me.expected):
                return ('linger',)  # another runner has it, or may still come for it: should it fail too, we wait
            continue
        if d is None or d.get('state') == 'unlisted':
            if reserved(s):
                return ('linger',)  # its leader is up, or may still come up
            continue
        if d.get('state') == 'listing':
            return ('linger',)
        if any(c.get('state') == 'held' and c.get('by') != me.name for c in d.get('chunks', [])):
            return ('linger',)  # a runner up holds a part: a wall may yet put it back on the stack
    return ('end',)


# -- one runner ------------------------------------------------------------------------------------------------------


class Gate:
    """At most `n` lanes crawl at once; a lower priority number goes first (Runner._rank), and a lane outranked by one
    waiting gives its place up at its next chunk."""

    def __init__(self, n):
        self.n = max(1, n)
        self.cond = threading.Condition()
        self.holders, self.waiting = set(), {}

    def hold(self, lane, prio, until=None, clock=time.monotonic):
        """Take a place (or keep it); False when `until` passed first."""
        with self.cond:
            if lane in self.holders:
                return True
            self.waiting[lane] = prio
            try:
                while len(self.holders) >= self.n or any(p < prio for l, p in self.waiting.items() if l != lane):
                    if until is not None and clock() >= until:
                        return False
                    self.cond.wait(1.0)
                self.holders.add(lane)
                return True
            finally:
                self.waiting.pop(lane, None)

    def outranked(self, prio):
        with self.cond:
            return any(p < prio for p in self.waiting.values())

    def drop(self, lane):
        with self.cond:
            if lane in self.holders:
                self.holders.discard(lane)
                self.cond.notify_all()


class Ops:
    """What a runner does on the sites; refresh.py implements it. Each method may raise; see Runner."""

    def probe(self, slot):
        """List the faculty from here: its items (with .code). Walled for a wall, Unlisted for a page gone."""
        raise NotImplementedError

    def todo(self, slot, items):
        """The leader's cut: (codes to check in order, info {'listed', 'fresh', 'not_ready', 'note'})."""
        raise NotImplementedError

    def crawl(self, slot, codes, items, check, tick):
        """Check `codes`; check() False means stop now (the chunk was taken over, time is up); tick() after each
        page. Returns {'done': [codes checked], 'blocked': bool, 'changed': [codes]}."""
        raise NotImplementedError

    def wait(self, slot, stop):
        """Wait a wall out; True when it is down."""
        return False

    def hunt(self, slot, exits):
        """Find proxy exits that get through to the slot's faculty, the shared `exits` checked first: the ones that
        work (from then on this runner reaches the slot through them), [] for none. May raise."""
        return []


class Runner:
    """One runner's part of a pass: its lanes, its heartbeat and its reading of the store."""

    def __init__(self, store, me, ops, lanes=6, deadline=None, clock=time.monotonic, sleep=time.sleep, log=print,
                 poll=None, heartbeat=None, stale=None, join_grace=None, lane_stale=None, store_down=None,
                 retry_error=None, chunk=None):
        # the module's timings unless given (read now, so a test may shorten them for a whole run)
        poll = POLL if poll is None else poll
        heartbeat = HEARTBEAT if heartbeat is None else heartbeat
        stale = STALE if stale is None else stale
        join_grace = JOIN_GRACE if join_grace is None else join_grace
        lane_stale = LANE_STALE if lane_stale is None else lane_stale
        store_down = STORE_DOWN if store_down is None else store_down
        retry_error = RETRY_ERROR if retry_error is None else retry_error
        chunk = CHUNK if chunk is None else chunk
        self.store, self.me, self.ops, self.log = store, me, ops, log
        self.clock, self.sleep = clock, sleep
        self.deadline = deadline
        self.poll, self.heartbeat, self.store_down, self.retry_error = poll, heartbeat, store_down, retry_error
        self.chunk = chunk
        self.gate = Gate(lanes)
        self.peers = Peers(me.name, clock, stale=stale, lane_stale=lane_stale, join_grace=join_grace)
        self.lock = threading.RLock()
        self.cond = threading.Condition(self.lock)
        self.slots = {}                 # slot -> doc, as last read or written
        self.items = {}                 # slot -> the listing made here
        self.lanes = {}                 # group -> {'slot', 'chunk', 'tick'}
        self.nonce, self.beat = uuid.uuid4().hex[:16], 0
        self.last_ok = clock()
        self.last_push = float('-inf')
        self.halt = threading.Event()
        self.thread = None
        # what this runner did, for its outcome
        self.led, self.helped, self.changed = set(), {}, []
        self.done_here = {}             # slot -> codes this runner checked
        self.solo = set()               # slots finished while the store was away

    # -- the store ----------------------------------------------------------------------------------------------

    def _doc(self, mode='run'):
        with self.lock:
            self.beat += 1
            return {'runner': self.me.name, 'nonce': self.nonce, 'beat': self.beat, 'mode': mode,
                    'lanes': copy.deepcopy(self.lanes)}

    def _read(self):
        docs = self.store.read()
        with self.cond:
            self.peers.observe({n[2:]: d for n, d in docs.items() if n.startswith('r/')})
            for name, d in docs.items():
                slot = slot_of(name)
                if slot is not None and SLOT_RE.match(slot):
                    self.slots[slot] = d
            self.last_ok = self.clock()
            self.cond.notify_all()

    def _push(self, mode='run'):
        self.store.put(f'r/{self.me.name}', self._doc(mode))
        with self.lock:
            self.last_push = self.clock()

    def start(self):
        """Announce this runner and read the store; StoreUnavailable when it cannot be reached."""
        err = None
        for attempt in range(START_TRIES):
            try:
                self._push()
                self._read()
                break
            except board.StoreError as e:
                err = e
                self.sleep(min(15, 2 * (attempt + 1)))
        else:
            raise StoreUnavailable(str(err))
        self.thread = threading.Thread(target=self._loop, name='stack', daemon=True)
        self.thread.start()

    def _loop(self):
        while not self.halt.wait(self.poll):
            # reading and beating apart: a runner that cannot read for a while must still not look gone
            for step in (self._read, self._beat):
                try:
                    step()
                except board.StoreError as err:
                    self.log(f'stack: {err}')
                except Exception as err:  # the store is a help, never a reason to stop crawling
                    self.log(f'stack: {err!r}')

    def _beat(self):
        if self.clock() - self.last_push >= self.heartbeat:
            self._push()

    def store_away(self):
        with self.lock:
            return self.clock() - self.last_ok > self.store_down

    def view(self):
        with self.lock:
            statuses, hung, uptime = self.peers.snapshot()
            return View(copy.deepcopy(self.slots), statuses, hung, uptime, self.peers.join_grace, self.peers.stale)

    def _update(self, slot, fn):
        """A swap on a slot's doc; (doc, written), or (None, False) when the store would not take it."""
        try:
            doc, written = self.store.update(doc_name(slot), fn)
        except board.StoreError as err:
            self.log(f'stack: {slot}: {err}')
            return None, False
        with self.cond:
            self.last_ok = self.clock()
            if doc is not None:
                self.slots[slot] = doc
            self.cond.notify_all()
        return doc, written

    # -- the lanes ----------------------------------------------------------------------------------------------

    def run(self):
        """Crawl until no lane has anything left; returns the report (report())."""
        groups = list(dict.fromkeys(self.me.groups[s] for s in self.me.slots))
        threads = [threading.Thread(target=self._lane_safe, args=(g,), name=f'lane-{g}') for g in groups]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        return self.finish()

    def finish(self):
        """Stop the heartbeat, say done, and read the store a last time for the verdicts."""
        self.halt.set()
        if self.thread is not None:
            self.thread.join(timeout=self.poll + 60)
        try:
            self._read()
        except board.StoreError:
            pass
        for attempt in range(3):
            try:
                self._push('done')
                break
            except board.StoreError:
                self.sleep(1 + attempt)
        return self.report()

    def _lane_safe(self, group):
        try:
            self._lane(group)
        except Exception as err:  # one lane's trouble never ends the others
            self.log(f'stack: lane {group} failed ({err!r})')
        finally:
            self.gate.drop(group)
            with self.lock:
                self.lanes.pop(group, None)

    def _late(self):
        return self.halt.is_set() or (self.deadline is not None and self.clock() >= self.deadline)

    def _nap(self, seconds):
        with self.cond:
            self.cond.wait(seconds)

    def _lane(self, group):
        while not self._late():
            if self.store_away():
                self._solo(group)
                return
            act = choose(self.view(), self.me, group, self.clock(), self.retry_error)
            kind = act[0]
            if kind == 'end':
                return
            if kind == 'linger':
                self.gate.drop(group)
                self._nap(self.poll)
                continue
            if kind == 'wait':
                self.gate.drop(group)
                self._wait(group, act[1])
                continue
            if kind == 'hunt':
                # the search goes out through the pool's exits, not this runner's address: no place in the gate
                self.gate.drop(group)
                if not self._hunt(group, act[1]):
                    self._nap(min(1.0, self.poll))
                continue
            prio = self._rank(act)
            if self.gate.outranked(prio):
                self.gate.drop(group)
            if not self.gate.hold(group, prio, self.deadline, self.clock):
                return
            did = self._open(group, act[1]) if kind == 'open' else self._work(group, act[1], act[2], prio)
            if not did:
                self._nap(min(1.0, self.poll))  # lost a race or the store said no: read again before deciding

    def _rank(self, act):
        """The gate's priority of a step: 0 for own work no other runner up can take (the pass waits for it), 1 for
        other own work, 2 for helping."""
        kind, slot = act[0], act[1]
        if kind == 'claim' and not act[2]:
            return 2
        view = self.view()
        d = view.slots.get(slot) or {}
        others = [r for r in self.me.expected if self.me.may(r, slot) and r not in d.get('cant', {})
                  and not view.gone(r)]
        return 1 if others else 0

    def _cant(self, slot, cause, err):
        """This runner cannot list `slot`: said on the slot, before it takes anything there. Through the pool, any
        failure loses the route (the exits died or the wall met them; the hunt port refuses with 403 once no exit is
        left): no more tries this pass, unless another runner shares new exits on the slot."""
        with self.lock:
            lost = self.me.via.get(slot) == 'pool'
            if lost:
                cause = WALL
                self.me.via[slot] = 'lost'
                self.items.pop(slot, None)
            prior = self.me.cant.get(slot)
            self.me.cant[slot] = {'cause': cause, 'at': self.clock(), 'tries': (prior or {}).get('tries', 0) + 1}
        self.log(f'[{slot}] cannot be listed from here ({cause}: {err}); '
                 + ('the exits do not get through any more' if lost else
                    'leaving it to the others' if cause == WALL else 'the others may'))
        me = self.me.name

        def mark(d):
            if d is None:
                d = {'slot': slot, 'group': self.me.groups[slot], 'state': 'unlisted', 'leader': None, 'chunks': [],
                     'cant': {}, 'next': 0}
            d.setdefault('cant', {})[me] = {'cause': cause, 'at': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())}
            if lost and (d.get('via') or {}).get(me) == 'pool':
                d['via'][me] = 'lost'
            if d.get('state') == 'listing' and d.get('leader') == me:
                d['state'], d['leader'] = 'unlisted', None
            return d
        self._update(slot, mark)

    def _uncant(self, slot):
        with self.lock:
            self.me.cant.pop(slot, None)
        me = self.me.name

        def clear(d):
            if d is None or me not in d.get('cant', {}):
                return None
            del d['cant'][me]
            return d
        self._update(slot, clear)

    def _listing(self, slot):
        """The faculty listed from here (cached for the pass); None when it cannot be (already said on the slot)."""
        if slot in self.items:
            return self.items[slot]
        try:
            items = self.ops.probe(slot)
        except Walled as err:
            self._cant(slot, WALL, err)
            return None
        except Unlisted as err:
            self._cant(slot, 'gone', err)
            return None
        except Exception as err:
            self._cant(slot, 'error', err)
            return None
        self.items[slot] = items
        if slot in self.me.cant:
            self._uncant(slot)
        return items

    def _open(self, group, slot):
        me, view = self.me.name, self.view()

        def claim(d):
            if d is not None:
                if d.get('state') == 'unlisted' and d.get('leader') is None:
                    pass
                elif d.get('state') == 'listing' and d.get('leader') != me and view.holder_dead(
                        {'by': d.get('leader')}, slot):
                    pass
                else:
                    return None
            d = d or {'slot': slot, 'group': group, 'chunks': [], 'cant': {}, 'next': 0}
            d.update(state='listing', leader=me)
            return d
        doc, written = self._update(slot, claim)
        if not written:
            return False
        with self.lock:
            self.lanes[group] = {'slot': slot, 'chunk': None, 'tick': 0}
        if term_of(slot):
            self.log(f'[{slot}] opening it')
        items = self._listing(slot)
        if items is None:
            return True
        try:
            codes, info = self.ops.todo(slot, items)
        except Exception as err:
            self._cant(slot, 'error', err)
            return True
        chunks = chunks_of(list(codes), self.chunk)

        def publish(d):
            if d is None or d.get('leader') != me or d.get('state') != 'listing':
                return None
            d.update(state='open' if chunks else 'closed', chunks=chunks, next=len(chunks),
                     listed=info.get('listed'), fresh=info.get('fresh'), not_ready=info.get('not_ready'))
            if info.get('note'):
                d['note'] = info['note']
                d['state'] = 'closed'
            return d
        doc, written = self._update(slot, publish)
        if written:
            with self.lock:
                self.led.add(slot)
            if chunks:
                self.log(f'[{slot}] leading it: {len(codes)} groups in {len(chunks)} chunks')
        return True

    def _pick(self, d, front, view):
        free = [i for i, c in enumerate(d.get('chunks', []))
                if c.get('state') == 'free' or (c.get('state') == 'held' and view.holder_dead(c, d['slot']))]
        if not free:
            return None
        return free[0] if front else free[-1]

    def _settle(self, d, chunk_id, result, me):
        """Fold a chunk's result into the doc: done, its rest back on the stack, or a failure counted."""
        chunks = d.get('chunks', [])
        at = next((i for i, c in enumerate(chunks) if c.get('id') == chunk_id), None)
        if at is None or chunks[at].get('state') != 'held' or chunks[at].get('by') != me:
            return False  # taken over meanwhile: the taker crawls it (again); what was checked here stays checked
        c = chunks[at]
        if result.get('error') is not None:
            c['fails'] = c.get('fails', 0) + 1
            if c['fails'] >= MAX_FAILS:
                c.update(state='done', by=None, failed=list(c['codes']), done_by=me)
            else:
                c.update(state='free', by=None)
            return True
        done = [code for code in c['codes'] if code in set(result.get('done', ()))]
        rest = [code for code in c['codes'] if code not in set(done)]
        if not rest:
            c.update(state='done', by=None, done_by=me, changed=len(result.get('changed', ())))
        else:
            c.update(state='free', by=None, codes=rest)
            if done:
                chunks.insert(at, {'id': d.get('next', len(chunks)), 'codes': done, 'state': 'done', 'by': None,
                                   'done_by': me, 'fails': 0, 'changed': len(result.get('changed', ()))})
                d['next'] = d.get('next', len(chunks)) + 1
        if result.get('blocked'):
            d.setdefault('cant', {})[me] = {'cause': WALL, 'at': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())}
            if (d.get('via') or {}).get(me) == 'pool':
                d['via'][me] = 'lost'
        if d.get('state') == 'open' and not remaining(d):
            d['state'] = 'closed'
        return True

    def _work(self, group, slot, front, prio):
        items = self._listing(slot)
        if items is None:
            return True
        if not items:  # the leader listed groups, this address sees none (a coming semester not up here yet)
            self.items.pop(slot, None)
            self._cant(slot, 'gone', 'nothing listed from here')
            return True
        me, held = self.me.name, [None]
        view = self.view()

        def take(d):
            if d is None or d.get('state') != 'open' or (me in d.get('cant', {}) and slot in self.me.cant):
                return None
            at = self._pick(d, front, view)
            if at is None:
                return None
            d['chunks'][at].update(state='held', by=me)
            held[0] = d['chunks'][at]['id']
            return d
        doc, written = self._update(slot, take)
        did = bool(written)
        while written and held[0] is not None:
            chunk_id = held[0]
            codes = next(c['codes'] for c in doc['chunks'] if c['id'] == chunk_id)
            result = self._crawl(group, slot, chunk_id, codes, items)
            if result.get('blocked'):
                with self.lock:
                    self.me.cant[slot] = {'cause': WALL, 'at': self.clock(), 'tries': 1}
                    self.items.pop(slot, None)
                    if self.me.via.get(slot) == 'pool':
                        self.me.via[slot] = 'lost'  # the exits met the wall too: no more this pass, unless new ones
                        self.log(f'[{slot}] the exits met its wall too')
            go_on = (not result.get('blocked') and result.get('error') is None and not result.get('cut')
                     and not self._late() and not self.store_away() and not self.gate.outranked(prio))
            held[0] = None
            view = self.view()

            def settle(d):
                if d is None:
                    return None
                ok = self._settle(d, chunk_id, result, me)
                if ok and go_on and d.get('state') == 'open':
                    at = self._pick(d, front, view)
                    if at is not None:
                        d['chunks'][at].update(state='held', by=me)
                        held[0] = d['chunks'][at]['id']
                return d if ok else None
            doc, written = self._update(slot, settle)
            if doc is None:
                # the store would not take the result: the groups stay checked here, the chunk goes back when this
                # runner's lease runs out (the others see it held by a runner that moves on)
                break
        with self.lock:
            self.lanes[group] = {'slot': None, 'chunk': None, 'tick': self.lanes.get(group, {}).get('tick', 0)}
        return did

    def _crawl(self, group, slot, chunk_id, codes, items):
        me = self.me.name
        with self.lock:
            self.lanes[group] = {'slot': slot, 'chunk': chunk_id, 'tick': 0}
        cut = [False]

        def check():
            if self._late():
                cut[0] = True
                return False
            with self.lock:
                d = self.slots.get(slot) or {}
            c = next((c for c in d.get('chunks', []) if c.get('id') == chunk_id), None)
            if c is not None and (c.get('state') != 'held' or c.get('by') != me):
                self.log(f'[{slot}] a chunk was taken over from this runner; stopping it')
                cut[0] = True
                return False
            return True

        def tick():
            with self.lock:
                lane = self.lanes.get(group)
                if lane is not None:
                    lane['tick'] = lane.get('tick', 0) + 1

        if slot not in self.led and slot not in self.helped:
            leader = (self.slots.get(slot) or {}).get('leader')
            with self.lock:
                self.helped[slot] = leader
            self.log(f'[{slot}] helping {leader or "nobody (no leader)"}')
        try:
            result = dict(self.ops.crawl(slot, list(codes), items, check, tick))
        except Exception as err:
            self.log(f'[{slot}] a chunk failed ({err!r}); back on the stack')
            return {'done': [], 'error': repr(err)}
        result['cut'] = cut[0] or (not result.get('blocked') and set(result.get('done', ())) < set(codes)
                                   and self._late())
        with self.lock:
            self.done_here.setdefault(slot, []).extend(result.get('done', ()))
            self.changed.extend(result.get('changed', ()))
        return result

    def _wait(self, group, slot):
        with self.lock:
            self.me.waited.add(slot)

        def stop():
            if self._late():
                return True
            view = self.view()
            d = view.slots.get(slot)
            if not remaining(d):
                return True
            return any(view.status(r) == 'live' and self.me.may(r, slot) and r not in (d or {}).get('cant', {})
                       for r in self.me.expected)
        self.log(f'[{slot}] nobody up can take it; waiting its wall out here')
        try:
            recovered = self.ops.wait(slot, stop)
        except Exception as err:
            self.log(f'[{slot}] the wait failed ({err!r})')
            recovered = False
        if recovered:
            with self.lock:
                self.items.pop(slot, None)
            self._uncant(slot)

    def _hunt(self, group, slot):
        """Search exits for `slot` (or check the ones on it), and say on the slot what came of it. False when the
        store would not take the claim (read again, then decide)."""
        me, view = self.me.name, self.view()
        at = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime())

        def claim(d):
            d = d or {'slot': slot, 'group': group, 'state': 'unlisted', 'leader': None, 'chunks': [], 'cant': {},
                      'next': 0}
            h = d.get('hunting') or {}
            if h.get('runner') not in (None, me) and view.status(h['runner']) == 'live' and not d.get('exits'):
                return None
            d['hunting'] = {'runner': me, 'at': at}
            return d
        doc, written = self._update(slot, claim)
        if not written:
            return False
        exits = [e for e in (doc or {}).get('exits') or [] if isinstance(e, str)]
        with self.lock:
            self.me.hunted[slot] = frozenset(exits)
        leader = (doc or {}).get('leader')
        why = (f'helping {leader} through pool exits' if leader and leader != me and faculty_of(slot) in self.me.pool_help
               else 'no runner up reaches it directly')
        self.log(f'[{slot}] {why}; '
                 + (f'checking the {len(exits)} exits found for it' if exits else 'hunting the pool for exits to it'))
        try:
            found = [e for e in self.ops.hunt(slot, exits) or [] if isinstance(e, str)]
            outcome = 'found' if found else 'none'
        except Exception as err:
            self.log(f'[{slot}] the hunt failed ({err!r})')
            found, outcome = [], 'error'

        def settle(d):
            d = d or {'slot': slot, 'group': group, 'state': 'unlisted', 'leader': None, 'chunks': [], 'cant': {},
                      'next': 0}
            if (d.get('hunting') or {}).get('runner') == me:
                d.pop('hunting')
            d.setdefault('hunted', {})[me] = outcome
            if found:
                d.setdefault('via', {})[me] = 'pool'
                d['exits'] = list(dict.fromkeys(list(d.get('exits') or []) + found))[:MAX_EXITS]
                d.get('cant', {}).pop(me, None)
            elif faculty_of(slot) in self.me.pool and me not in d.get('cant', {}):
                # the only way this runner had there: it ends at the same wall as the others
                d.setdefault('cant', {})[me] = {'cause': WALL if outcome == 'none' else 'error', 'at': at}
            return d
        self._update(slot, settle)
        with self.lock:
            self.me.hunted[slot] = frozenset(exits) | frozenset(found)
            if found:
                self.me.via[slot] = 'pool'
                self.me.cant.pop(slot, None)
                self.items.pop(slot, None)  # listed again, through the exits
        self.log(f'[{slot}] ' + (f'{len(found)} exits get through; crawling it through them' if found
                                 else 'no exit gets through'))
        return True

    def _solo(self, group):
        """The store is away: crawl what is left of the slots this runner leads (as last seen), nothing else."""
        self.log(f'stack: the store has not answered for {self.store_down} s; finishing what this runner leads')
        for slot in [s for s in self.me.slots if self.me.groups.get(s) == group and s in self.led]:
            d = self.slots.get(slot) or {}
            codes = [c for ch in d.get('chunks', []) if ch.get('state') != 'done' for c in ch['codes']]
            items = self.items.get(slot)
            if not codes or items is None or self._late():
                continue
            if not self.gate.hold(group, 0, self.deadline, self.clock):
                return
            result = self._crawl(group, slot, None, codes, items)
            if not result.get('blocked') and result.get('error') is None and not result.get('cut'):
                with self.lock:
                    self.solo.add(slot)

    # -- the outcome --------------------------------------------------------------------------------------------

    def verdicts(self):
        """{slot: status} over this runner's slots, as the store (last read) has them."""
        with self.lock:
            out = {}
            for s in self.me.slots:
                able = [r for r in [self.me.name] + self.me.expected if self.me.may(r, s)]
                out[s] = 'done' if s in self.solo else slot_status(self.slots.get(s), able)
            return out

    def report(self):
        with self.lock:
            cant = {s: c['cause'] for s, c in self.me.cant.items()}
            leaders = {s: (d or {}).get('leader') for s, d in self.slots.items()}
            return {'verdicts': self.verdicts(),
                    'led': sorted(s for s in self.led if leaders.get(s) == self.me.name),
                    'helped': {s: leaders.get(s) or self.helped[s] for s in self.helped if s not in self.led},
                    'gave': {s: sorted({c.get('done_by') for c in (self.slots.get(s) or {}).get('chunks', [])
                                        if c.get('done_by') and c.get('done_by') != self.me.name})
                             for s in self.led if leaders.get(s) == self.me.name},
                    'cant': cant, 'changed': list(self.changed),
                    'checked': {s: len(c) for s, c in self.done_here.items()},
                    # the slots it crawled through pool exits (a hunt's, or another runner's it checked)
                    'pool': sorted(s for s, v in self.me.via.items()
                                   if v in ('pool', 'lost') and self.done_here.get(s)),
                    'failed': sorted(s for s, d in self.slots.items() if s in self.me.slots
                                     and any(c.get('failed') for c in (d or {}).get('chunks', [])))}


# -- the report job's view of a whole pass ---------------------------------------------------------------------------


def summarize(docs, matrix, allow):
    """What the store says of the whole pass: {'slots': {...}, 'faculties': {...}}.

    `matrix` is the plan's ([{runner, faculties}]): who was expected, and which faculties the pass covered; `allow`
    maps a runner to the faculties it may take (None: any)."""
    expected = [m['runner'] for m in matrix]
    wanted = list(dict.fromkeys(f for m in matrix for f in str(m.get('faculties') or '').split(',') if f))
    slots = {}
    names = {slot_of(n) for n in docs if n.startswith('s/')} | set(wanted)
    for slot in sorted(s for s in names if s and SLOT_RE.match(s)):
        if faculty_of(slot) not in wanted:
            continue
        d = docs.get(doc_name(slot))
        able = [r for r in expected if allow.get(r) is None or faculty_of(slot) in allow[r]]
        by, changed = {}, {}
        for c in (d or {}).get('chunks', []):
            if c.get('state') == 'done' and c.get('done_by'):
                by[c['done_by']] = by.get(c['done_by'], 0) + len(c.get('codes', ()))
                changed[c['done_by']] = changed.get(c['done_by'], 0) + int(c.get('changed') or 0)
        slots[slot] = {'status': slot_status(d, able), 'leader': (d or {}).get('leader'),
                       'groups': sum(len(c.get('codes', ())) for c in (d or {}).get('chunks', [])),
                       'done_by': by, 'changed_by': changed,
                       'cant': {r: c.get('cause') for r, c in ((d or {}).get('cant') or {}).items()},
                       'failed': sum(len(c.get('failed') or ()) for c in (d or {}).get('chunks', [])),
                       'note': (d or {}).get('note'), 'not_ready': (d or {}).get('not_ready'),
                       'via_pool': sorted(r for r, v in ((d or {}).get('via') or {}).items()
                                          if v in ('pool', 'lost') and by.get(r))}
    rank = {'blocked': 0, 'unfinished': 1, 'absent': 1, 'failed': 2, 'done': 3, 'empty': 3}
    faculties = {}
    for f in wanted:
        mine = {s: v for s, v in slots.items() if faculty_of(s) == f}
        main = mine.get(f, {'status': 'absent', 'leader': None, 'done_by': {}, 'changed_by': {}, 'cant': {},
                            'failed': 0, 'groups': 0})
        worst = min((v['status'] for v in mine.values()), key=lambda s: rank.get(s, 1), default='absent')
        helpers = {}
        for v in mine.values():
            for r, n in v['done_by'].items():
                if r != main.get('leader'):
                    helpers[r] = helpers.get(r, 0) + n
        faculties[f] = {'status': 'unfinished' if worst == 'absent' else worst, 'leader': main.get('leader'),
                        'helpers': helpers,
                        'checked': sum(n for v in mine.values() for n in v['done_by'].values()),
                        'changed': sum(n for v in mine.values() for n in v['changed_by'].values()),
                        'cant': {r: c for v in mine.values() for r, c in v['cant'].items()},
                        'failed': sum(v['failed'] for v in mine.values()),
                        'via_pool': sorted({r for v in mine.values() for r in v.get('via_pool', ())})}
    return {'slots': slots, 'faculties': faculties}


def cmd_summary(args):
    import fleet
    try:
        matrix = json.loads(args.matrix or '[]')
    except ValueError:
        matrix = []
    matrix = [m for m in matrix if isinstance(m, dict) and isinstance(m.get('runner'), str)] \
        if isinstance(matrix, list) else []
    key = f'{args.planned}-{args.run_id}'
    try:
        store = board.GitStore(args.repo, key)
        docs = store.read()
        store.forget()
    except (board.StoreError, ValueError) as err:
        print(f'the store of pass {key} cannot be read ({err}); the outcome counts the runners\' own reports')
        return 1
    try:
        allow = {r['name']: fleet.reach(r) for r in fleet.load_fleet(args.fleet)}
    except (OSError, ValueError):
        allow = {}
    result = summarize(docs, matrix, allow)
    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    for f, v in result['faculties'].items():
        helpers = ', '.join(f'{r} {n}' for r, n in v['helpers'].items())
        cant = ', '.join(f'{r} ({c})' for r, c in v['cant'].items())
        print(f"{f}: {v['status']}, led by {v['leader'] or 'nobody'}"
              + (f', helped by {helpers}' if helpers else '') + (f'; could not list it: {cant}' if cant else '')
              + (f"; through pool exits: {', '.join(v['via_pool'])}" if v['via_pool'] else ''))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('summary', help="what a pass's store says of every faculty (the report job, before the sweep)")
    p.add_argument('--repo', required=True, help='a checkout of this repository')
    p.add_argument('--planned', required=True)
    p.add_argument('--run-id', required=True)
    p.add_argument('--matrix', default='[]', help="the plan's matrix (JSON)")
    p.add_argument('--fleet', default=str(HERE / 'fleet.json'))
    p.add_argument('--out', required=True)
    args = ap.parse_args(argv)
    return {'summary': cmd_summary}[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())
