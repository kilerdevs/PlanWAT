"""Work stealing within a crawl wave: a runner that has finished its own share helps one that is still crawling.

The plan (fleet.py) splits a pass between the runners up front, by an estimate that pacing and walls easily throw off.
So the runners also talk during the wave, over the board (board.py: one JSON doc per runner, written only by it):

  owner   Every runner's own work is a Pool of slots: a faculty's pass over the running semester (slot "wml") and, while
          the faculties publish the coming one, its pass over that (slot "wml~2027-28-zima"). The lanes start a slot,
          take its groups one by one and finish it; the doc says what is queued, running, blocked or done, and how many
          groups are left. Only the owner decides what leaves its pool: its Coordinator thread answers the requests
          the others put in their docs, under the pool's lock, so a lane never crawls what was given and a helper never
          starts before it has read the grant.
  helper  Once its own lanes are done, a runner looks at the busy peers' docs: first at the faculty a peer is crawling
          right now, then at those it has not started. It lists the faculty itself first (a probe it needs anyway for
          the pages' addresses): a wall there sends it on to the next faculty. Otherwise it asks: for a part of a
          running faculty (the tail of its groups, shared by the runners' speeds) or for a whole queued one.

A grant goes out in this order: the groups (or the slot) are reserved under the lock, the answer is published, and only
a successful push gives them away; a failed one releases them and the request is decided again on the next tick. A
peer whose doc stops changing for STALE seconds (its own heartbeat is HEARTBEAT) counts as gone, on the reader's own
clock, so no runner waits for a dead one. What a helper took and could not finish (a wall in the middle) stays in its
own pool, where a peer can ask for it back, and is reported like any unfinished faculty: the handoff (fleet.py) still
takes it in the next wave. A grant nobody confirmed in its outcome is unfinished too, never silently done. A helper
with nothing to take waits (marked `idle`) while any peer is still at its share, which may yet meet a wall; once every
peer is done or idle too, it stops.
"""
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

SPLIT_MIN_LEFT = 8      # a running slot with fewer groups left is not split
SPLIT_MIN_SHARE = 4     # nor is a smaller share given
WHOLE_MIN_SECONDS = 600  # a helper with less time left asks for no whole faculty
POLL_BUSY = 15          # seconds between board reads while a peer is helping or a request is out
POLL_IDLE = 60
HEARTBEAT = 60          # a doc is pushed at least this often
STALE = 240             # a doc unchanged this long is a runner that is gone
STATES = ('queued', 'running', 'reserving', 'blocked', 'incomplete', 'done', 'given')
MODES = ('own', 'helping', 'done')
SLOT_RE = re.compile(r'^([a-z]{2,8})(~\d{4}-\d{2}-(?:zima|lato))?(#\d{1,3})?$')
NAME_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,38}$')
CODE_RE = re.compile(r'^[A-Za-z0-9_.-]{1,64}$')
GROUP_RE = re.compile(r'^[a-z0-9-]{1,32}$')
MAX_SLOTS, MAX_CODES, MAX_REQUESTS = 64, 2000, 500


def faculty_of(key):
    return SLOT_RE.match(key).group(1)


def term_of(key):
    """The term of an ahead slot ('2027-28-zima'), '' for a slot of the running semester."""
    m = SLOT_RE.match(key)
    return m.group(2)[1:] if m.group(2) else ''


def _codes(value):
    return (isinstance(value, list) and len(value) <= MAX_CODES
            and all(isinstance(c, str) and CODE_RE.match(c) for c in value))


def _int(value, low=0):
    return isinstance(value, int) and not isinstance(value, bool) and value >= low


def clean_doc(doc):
    """A peer's doc when it has the expected shape (anything else is ignored whole); None otherwise."""
    try:
        if not (isinstance(doc, dict) and NAME_RE.match(doc.get('runner', '')) and isinstance(doc.get('nonce'), str)
                and len(doc['nonce']) <= 64 and _int(doc.get('beat')) and doc.get('mode') in MODES
                and isinstance(doc.get('idle', False), bool)):
            return None
        slots = doc.get('slots')
        if not isinstance(slots, dict) or len(slots) > MAX_SLOTS:
            return None
        for key, s in slots.items():
            if not (SLOT_RE.match(key) and isinstance(s, dict) and s.get('state') in STATES
                    and isinstance(s.get('group'), str) and GROUP_RE.match(s['group'])
                    and (s.get('left') is None or _int(s['left'])) and s.get('ask') in (None, 'part', 'whole')):
                return None
        requests = doc.get('requests')
        if not isinstance(requests, list) or len(requests) > MAX_REQUESTS:
            return None
        for r in requests:
            if not (isinstance(r, dict) and _int(r.get('id'), 1) and NAME_RE.match(r.get('to', ''))
                    and SLOT_RE.match(r.get('slot', '')) and r.get('kind') in ('part', 'whole')
                    and (r.get('room') is None or _int(r['room']))):
                return None
        cancel = doc.get('cancel', [])
        if not (isinstance(cancel, list) and len(cancel) <= MAX_REQUESTS and all(_int(i, 1) for i in cancel)):
            return None
        answers = doc.get('answers')
        if not isinstance(answers, dict) or len(answers) > 16:
            return None
        for name, mine in answers.items():
            if not (NAME_RE.match(name) and isinstance(mine, dict) and len(mine) <= MAX_REQUESTS):
                return None
            for rid, a in mine.items():
                if not (rid.isdigit() and isinstance(a, dict) and isinstance(a.get('ok'), bool)
                        and isinstance(a.get('n'), str)):
                    return None
                grant = a.get('grant', [])
                if not (isinstance(grant, list) and len(grant) <= 2 and all(
                        isinstance(g, dict) and SLOT_RE.match(g.get('slot', ''))
                        and (g.get('codes') is None or _codes(g['codes'])) for g in grant)):
                    return None
                if a['ok'] and not grant:
                    return None
    except (TypeError, AttributeError):
        return None
    return doc


class Slot:
    def __init__(self, key, group, origin=None, codes=None, sibling=None, rest=False):
        self.key, self.faculty, self.group = key, faculty_of(key), group
        self.origin = origin      # the peer it was taken from; None for the runner's own work
        self.rest = rest          # taken whole or all that was left: its holder publishes the faculty's record
        self.fixed = codes        # a taken part: exactly these groups (None: the whole faculty)
        self.codes = list(codes) if codes is not None else None  # the groups in crawl order, once known
        self.index = {c: i for i, c in enumerate(self.codes or [])}
        self.state = 'queued'
        self.pos = 0              # the next group the lane will take
        self.current = None       # the group the lane took last
        self.given, self.reserved = set(), set()
        self.hold = None          # the state to return to when a whole grant fails
        self.sibling = sibling    # a slot of the running semester names its ahead slot: they go together


class Pool:
    """One runner's work, shared by its lanes, its helpers and its Coordinator (one lock for all of it)."""

    def __init__(self, runner, speed=1.0, speeds=None, allowed=None):
        self.runner, self.speed = runner, float(speed)
        self.speeds = speeds or {}            # peer -> speed (fleet.json)
        self.allowed = allowed or (lambda peer, faculty: True)
        self.cond = threading.Condition(threading.RLock())
        self.slots = {}
        self.mode = 'own'
        self.idle = False                     # helping, but finds nothing it can take
        self.version = 0                      # bumped on every change a peer should see
        self.answers = {}                     # peer -> {rid: answer}, kept for the whole wave
        self.gave, self.took = [], []         # [(faculty, peer)], [(faculty, peer, rest)]

    def _changed(self):
        self.version += 1
        self.cond.notify_all()

    def add(self, faculty, group, ahead_term=None):
        """The runner's own faculty, queued (with its ahead slot when the coming semester is being published)."""
        with self.cond:
            sibling = f'{faculty}~{ahead_term}' if ahead_term else None
            self.slots[faculty] = Slot(faculty, group, sibling=sibling)
            if sibling:
                self.slots[sibling] = Slot(sibling, group)
            self._changed()

    # -- the lanes' side ------------------------------------------------------------------------------------------

    def start(self, key):
        """False when the slot was given away (the lane skips it); waits while a whole grant of it is in flight."""
        with self.cond:
            s = self.slots.get(key)
            if s is None:
                return True
            while s.state == 'reserving':
                self.cond.wait(1.0)
            if s.state == 'given':
                return False
            s.state = 'running'
            self._changed()
            return True

    def running(self, key, codes):
        """The groups the lane is about to take, in order (what was given away is left out)."""
        with self.cond:
            s = self.slots.get(key)
            if s is None:
                return
            s.codes = [c for c in codes if c not in s.given]
            s.index = {c: i for i, c in enumerate(s.codes)}
            s.pos, s.current = 0, None
            self._changed()

    def take(self, key, code):
        """Whether the lane may crawl `code` now: never one given away, and not while a grant of it is in flight."""
        with self.cond:
            s = self.slots.get(key)
            if s is None:
                return True
            while code in s.reserved:
                self.cond.wait(1.0)
            if code in s.given:
                return False
            i = s.index.get(code)
            if i is not None:
                s.pos, s.current = max(s.pos, i + 1), code
                self._changed()
            return True

    def finish(self, key, status):
        """The lane is done with the slot for now: 'done', 'blocked' (the group it took last was not checked) or
        'incomplete'."""
        with self.cond:
            s = self.slots.get(key)
            if s is None or s.state == 'given':
                return
            if status == 'blocked' and s.current in s.index:
                s.pos = s.index[s.current]
            s.state = status
            if status == 'blocked' and s.codes is not None and not self._left(s):
                s.state = 'given' if s.given else 'done'
            self._changed()

    def has_work(self, keys):
        """Whether any of `keys` still has something for this runner to do (a wall wait with nothing left ends)."""
        with self.cond:
            for key in keys:
                s = self.slots.get(key)
                if s is None or (s.state != 'given' and (s.codes is None or self._left(s) or s.reserved)):
                    return True
            return False

    # -- the owner's decisions ------------------------------------------------------------------------------------

    @staticmethod
    def _records(s):
        """Whether handing all of `s` on hands on the faculty's record too: a slot of the running semester that is
        this runner's own, or that it took whole."""
        return not term_of(s.key) and (s.origin is None or s.rest)

    @staticmethod
    def _left(s):
        if s.codes is None:
            return None
        return [c for c in s.codes[s.pos:] if c not in s.given and c not in s.reserved]

    def ask(self, s):
        """What a peer may ask of slot `s`: 'whole', 'part' or nothing."""
        left = self._left(s)
        if s.state == 'queued' or (s.state == 'blocked' and s.codes is None):
            return 'whole'
        if s.state == 'blocked' and left:
            return 'part'
        if s.state == 'running' and left is not None and len(left) >= SPLIT_MIN_LEFT:
            return 'part'
        return None

    def decide(self, peer, nonce, req):
        """The answer to one request, and the token that commits or releases it after the push (None: a denial)."""
        with self.cond:
            s = self.slots.get(req['slot'])

            def deny(why):
                return {'ok': False, 'n': nonce, 'why': why}, None
            if s is None:
                return deny('no such faculty here')
            if not self.allowed(peer, s.faculty):
                return deny('not on that runner\'s list')
            ask = self.ask(s)
            if ask is None or ask != req['kind']:
                return deny({'running': 'too little left', 'done': 'finished', 'given': 'given away',
                             'incomplete': 'stopped'}.get(s.state, 'not available'))
            if ask == 'whole':
                items = [(s, None, True)]
                sib = self.slots.get(s.sibling) if s.sibling else None
                if sib is not None and sib.state == 'queued':
                    items.append((sib, None, True))
                for t, _, _ in items:
                    t.hold, t.state = t.state, 'reserving'
                grant = [{'slot': t.key, 'codes': list(t.codes) if t.fixed is not None and t.codes is not None
                          else None} for t, _, _ in items]
                rest = self._records(s)
            else:
                left = self._left(s)
                if s.state == 'blocked':
                    share = left  # the owner cannot go on: all of it
                else:
                    other = float(self.speeds.get(peer, 1.0))
                    n = int(len(left) * other / (other + self.speed))
                    if req.get('room') is not None:
                        n = min(n, req['room'])
                    if n < SPLIT_MIN_SHARE:
                        return deny('too little left')
                    share = left[-n:]
                s.reserved |= set(share)
                items = [(s, share, False)]
                rest = s.state == 'blocked' and self._records(s)
                if rest and s.sibling and self.slots.get(s.sibling) and self.slots[s.sibling].state == 'queued':
                    sib = self.slots[s.sibling]
                    sib.hold, sib.state = sib.state, 'reserving'
                    items.append((sib, None, True))
                grant = [{'slot': t.key, 'codes': list(c) if c is not None else
                          (list(t.codes) if t.fixed is not None and t.codes is not None else None)}
                         for t, c, _ in items]
            self._changed()
            return {'ok': True, 'n': nonce, 'grant': grant, 'rest': rest}, (peer, items)

    def commit(self, token):
        with self.cond:
            peer, items = token
            for s, codes, whole in items:
                if whole:
                    s.state, s.hold = 'given', None
                else:
                    s.reserved -= set(codes)
                    s.given |= set(codes)
                    if s.state == 'blocked' and not self._left(s):
                        s.state = 'given'
            if (items[0][0].faculty, peer) not in self.gave:
                self.gave.append((items[0][0].faculty, peer))
            self._changed()

    def release(self, token):
        with self.cond:
            _, items = token
            for s, codes, whole in items:
                if whole:
                    s.state, s.hold = s.hold or 'queued', None
                else:
                    s.reserved -= set(codes)
            self._changed()

    # -- the helper's side ----------------------------------------------------------------------------------------

    def adopt(self, peer, answer, group):
        """Put what a peer granted into this pool (its own slots, which a peer may ask back); the keys, in order."""
        with self.cond:
            keys, first = [], None
            rest = bool(answer.get('rest'))
            for g in answer['grant']:
                base, n = g['slot'].split('#')[0], 1
                key = base
                while key in self.slots:
                    n += 1
                    key = f'{base}#{n}'
                slot = Slot(key, group, origin=peer, codes=g['codes'], rest=rest and not term_of(key))
                self.slots[key] = slot
                if first is None:
                    first = slot
                elif term_of(key) and not term_of(first.key):
                    first.sibling = key
                keys.append(key)
            pair = (faculty_of(keys[0]), peer, rest)
            if pair not in self.took:
                self.took.append(pair)
            self._changed()
            return keys

    def slot(self, key):
        with self.cond:
            s = self.slots.get(key)
            return None if s is None else {'faculty': s.faculty, 'term': term_of(key), 'fixed': s.fixed,
                                           'group': s.group, 'state': s.state, 'origin': s.origin}

    # -- accounting -----------------------------------------------------------------------------------------------

    def gone(self):
        """The runner's own faculties it holds nothing of any more: their pass over the running semester was given."""
        with self.cond:
            return {s.faculty for s in self.slots.values()
                    if s.origin is None and not term_of(s.key) and s.state == 'given'}

    def set_idle(self, value):
        with self.cond:
            if self.idle != value:
                self.idle = value
                self._changed()

    def taken(self):
        """{faculty: (blocked, unfinished)} over what this runner took from peers and still holds."""
        with self.cond:
            out = {}
            for s in self.slots.values():
                if s.origin is None or s.state == 'given':
                    continue
                blocked, unfinished = out.get(s.faculty, (False, False))
                out[s.faculty] = (blocked or s.state == 'blocked',
                                  unfinished or s.state != 'done')
            return out

    def snapshot(self):
        with self.cond:
            return {'mode': self.mode, 'idle': self.idle,
                    'slots': {k: {'state': s.state, 'group': s.group, 'ask': self.ask(s),
                                  'left': None if s.codes is None else len(self._left(s))}
                              for k, s in self.slots.items()},
                    'answers': {p: dict(a) for p, a in self.answers.items()}}


class Coordinator:
    """The runner's link to the board: one thread that publishes the pool and answers the peers' requests."""

    def __init__(self, board, pool, clock=time.monotonic, log=print, busy=None, idle=None, heartbeat=None,
                 stale=None):
        self.board, self.pool, self.clock, self.log = board, pool, clock, log
        self.busy = POLL_BUSY if busy is None else busy
        self.idle = POLL_IDLE if idle is None else idle
        self.heartbeat = HEARTBEAT if heartbeat is None else heartbeat
        self.stale = STALE if stale is None else stale
        self.nonce = uuid.uuid4().hex[:16]
        self.peers, self.seen = {}, {}        # name -> doc; name -> (beat, when it changed, by our clock)
        self.requests, self.cancelled = [], set()
        self.answered = set()                 # (peer, nonce, rid) this runner has answered for good
        self.next_id, self.beat = 1, 0
        self.published, self.last_push = -1, float('-inf')
        self.wake, self.halt = threading.Event(), threading.Event()
        self.thread = None
        self.begun = self.ended = 0           # ticks started and finished (sync() waits for a fresh one)

    # -- the thread -----------------------------------------------------------------------------------------------

    def start(self):
        self.tick()
        self.thread = threading.Thread(target=self._loop, name='board', daemon=True)
        self.thread.start()

    def _loop(self):
        while not self.halt.is_set():
            self.wake.wait(self._interval())
            self.wake.clear()
            if self.halt.is_set():
                break
            try:
                self.tick()
            except Exception as err:  # the board is a help, never a reason to stop crawling
                self.log(f'board: {err!r}')

    def _interval(self):
        with self.pool.cond:
            out = any(r['id'] not in self.cancelled and not self._answer_locked(r['to'], r['id'])
                      for r in self.requests)
            helping = any(d['mode'] == 'helping' and self._status_locked(n) == 'live' for n, d in self.peers.items())
            return self.busy if out or helping else self.idle

    def stop(self):
        """Last word: mode done, every request still open denied. Grants already pushed stand."""
        self.halt.set()
        self.wake.set()
        if self.thread is not None:
            self.thread.join(timeout=120)
        with self.pool.cond:
            self.pool.mode = 'done'
            self.pool._changed()
        for attempt in range(3):
            if self.tick(final=True):
                return
            time.sleep(1 + attempt)

    def tick(self, final=False):
        """Read the peers, answer what is asked of this runner, push the doc when it changed or a heartbeat is due.
        Returns whether the doc on the board is current."""
        with self.pool.cond:
            self.begun += 1
        try:
            return self._tick(final)
        finally:
            with self.pool.cond:
                self.ended += 1
                self.pool.cond.notify_all()

    def sync(self, timeout=None):
        """Wait until a tick that started after this call has finished: the peers as the board has them now."""
        timeout = 4 * self.busy + 30 if timeout is None else timeout
        with self.pool.cond:
            want = self.begun + 1
        self.wake.set()
        end = time.monotonic() + timeout
        with self.pool.cond:
            while self.ended < want and self.thread is not None and self.thread.is_alive():
                left = end - time.monotonic()
                if left <= 0:
                    return False
                self.pool.cond.wait(min(left, 1.0))
                self.wake.set()
            return self.ended >= want

    def _tick(self, final):
        docs = self.board.peers()
        now = self.clock()
        pending = []
        with self.pool.cond:
            if docs is not None:
                for name, doc in docs.items():
                    doc = clean_doc(doc)
                    if doc is None or doc['runner'] != name or name == self.pool.runner:
                        continue
                    old = self.seen.get(name)
                    if old is None or old[0] != (doc['nonce'], doc['beat']):
                        self.seen[name] = ((doc['nonce'], doc['beat']), now)
                    self.peers[name] = doc
            for name, doc in self.peers.items():
                live = self._status_locked(name) == 'live'
                cancel = set(doc.get('cancel', []))
                for req in doc['requests']:
                    mark = (name, doc['nonce'], req['id'])
                    if req['to'] != self.pool.runner or mark in self.answered or req['id'] in cancel:
                        continue
                    if any(p[0] == mark for p in pending):
                        continue
                    if final:
                        answer, token = {'ok': False, 'n': doc['nonce'], 'why': 'finished'}, None
                    elif not live:
                        continue  # a peer that went quiet gets nothing; one that comes back is answered then
                    else:
                        answer, token = self.pool.decide(name, doc['nonce'], req)
                    self.pool.answers.setdefault(name, {})[str(req['id'])] = answer
                    pending.append((mark, answer, token))
            due = pending or self.pool.version != self.published or now - self.last_push >= self.heartbeat
            if not due:
                return True
            self.beat += 1
            version = self.pool.version
            doc = dict(self.pool.snapshot(), runner=self.pool.runner, nonce=self.nonce, beat=self.beat,
                       requests=[dict(r) for r in self.requests], cancel=sorted(self.cancelled))
        ok = False
        try:
            ok = self.board.publish(doc)
        finally:
            with self.pool.cond:
                for mark, answer, token in pending:
                    if ok:
                        self.answered.add(mark)
                        if token is not None:
                            self.pool.commit(token)
                            given = sum(len(g['codes']) if g['codes'] is not None else 0 for g in answer['grant'])
                            what = f'{given} groups of {answer["grant"][0]["slot"]}' if given else \
                                ' and '.join(g['slot'] for g in answer['grant'])
                            self.log(f'board: gave {what} to {mark[0]}')
                    else:
                        if token is not None:
                            self.pool.release(token)
                        self.pool.answers.get(mark[0], {}).pop(str(mark[2]), None)
                if ok:
                    self.published, self.last_push = version, now
                self.pool.cond.notify_all()
        return ok

    # -- what the helpers ask -------------------------------------------------------------------------------------

    def _status_locked(self, name):
        doc = self.peers.get(name)
        if doc is None:
            return 'gone'
        if doc['mode'] == 'done':
            return 'done'
        if self.clock() - self.seen[name][1] > self.stale:
            return 'stale'
        return 'live'

    def status(self, name):
        with self.pool.cond:
            return self._status_locked(name)

    def waited_for(self):
        """Whether a peer is still at work and may yet take what this runner holds: up, and not merely waiting too."""
        with self.pool.cond:
            return any(self._status_locked(n) == 'live' and not d.get('idle') for n, d in self.peers.items())

    def live_peers(self):
        """{name: doc} of the peers that are up and still at it."""
        with self.pool.cond:
            return {n: d for n, d in self.peers.items() if self._status_locked(n) == 'live'}

    def request(self, peer, slot, kind, room=None):
        with self.pool.cond:
            rid = self.next_id
            self.next_id += 1
            self.requests.append({'id': rid, 'to': peer, 'slot': slot, 'kind': kind, 'room': room})
            self.pool._changed()
        self.wake.set()
        return rid

    def cancel(self, rid):
        with self.pool.cond:
            self.cancelled.add(rid)
            self.pool._changed()
        self.wake.set()

    def _answer_locked(self, peer, rid):
        doc = self.peers.get(peer)
        a = doc['answers'].get(self.pool.runner, {}).get(str(rid)) if doc else None
        return a if a is not None and a.get('n') == self.nonce else None

    def answer(self, peer, rid):
        with self.pool.cond:
            return self._answer_locked(peer, rid)

    def await_answer(self, peer, rid, deadline, clock=None):
        """The peer's answer to `rid`; None when the peer finished or went quiet first, or time ran out (`deadline`
        on the caller's `clock`)."""
        clock = clock or self.clock
        while True:
            with self.pool.cond:
                a = self._answer_locked(peer, rid)
                if a is not None:
                    return a
                if self._status_locked(peer) != 'live' or clock() > deadline:
                    return None
                self.pool.cond.wait(min(self.busy, 5.0))

    def late_grants(self, honoured):
        """Grants that came for requests given up on: [(peer, rid, answer)] not yet in `honoured`."""
        with self.pool.cond:
            out = []
            for r in self.requests:
                if r['id'] in self.cancelled and r['id'] not in honoured:
                    a = self._answer_locked(r['to'], r['id'])
                    if a is not None and a['ok']:
                        out.append((r['to'], r['id'], a))
            return out


def help_peers(coord, pool, probe, crawl, deadline, clock=time.monotonic, workers=2, room_of=None,
               may=None, group_of=None, log=print, poll=None):
    """Help the busy peers until none has anything this runner can take.

    probe(faculty, term) lists the faculty from here: the items, or raises Walled when this runner meets its wall.
    crawl(key, items) crawls one slot of this pool and answers 'done', 'blocked' or 'incomplete'. may(faculty) says
    whether this runner may and should try it at all; room_of(faculty) how many groups it can still do in time."""
    poll = coord.busy if poll is None else poll
    group_of = group_of or (lambda faculty: faculty)
    may = may or (lambda faculty: True)
    room_of = room_of or (lambda faculty: None)
    lock = threading.Lock()
    walled, busy_groups, refused, honoured = set(), set(), set(), set()
    with pool.cond:
        pool.mode = 'helping'
        pool._changed()
    coord.sync()  # the peers as they are now, not as at the last idle read

    def candidates():
        """The peers' slots in the order this runner tries them: running first (the most left first), then the
        ones not started; each with whether it is out of reach for good or only for now."""
        out = []
        for name, doc in coord.live_peers().items():
            slots = list(doc['slots'].items())
            started = [(k, s) for k, s in slots if s['ask'] and s['state'] in ('running', 'blocked')]
            started.sort(key=lambda ks: -(ks[1]['left'] or 0))
            queued = [(k, s) for k, s in slots if s['ask'] and s['state'] not in ('running', 'blocked')]
            for key, s in started + queued:
                out.append((name, key, s))
        return out

    def pick():
        with lock:
            later = False
            for name, key, s in candidates():
                if (name, key, s['ask']) in refused or s['group'] in walled or not may(faculty_of(key)):
                    continue
                if s['group'] in busy_groups:
                    later = True
                    continue
                if s['ask'] == 'whole' and deadline - clock() < WHOLE_MIN_SECONDS:
                    continue
                busy_groups.add(s['group'])
                return (name, key, s), False
            # a faculty a peer is still listing may turn out worth a part once its groups are known
            for name, doc in coord.live_peers().items():
                for key, s in doc['slots'].items():
                    if (s['state'] == 'running' and s['left'] is None and s['group'] not in walled
                            and may(faculty_of(key))):
                        later = True
            return None, later

    def run_grant(peer, answer, group, items=None, term=None):
        keys = pool.adopt(peer, answer, group)
        log(f'help: took {" and ".join(keys)} from {peer}'
            + (f' ({len(answer["grant"][0]["codes"])} groups)' if answer['grant'][0]['codes'] is not None else ''))
        for key in keys:
            try:
                status = crawl(key, items if items is not None and term_of(key) == term else None)
            except Exception as err:  # one slot's trouble never ends the help (nor the run)
                log(f'help: {key} failed ({err!r})')
                status = 'incomplete'
            if status == 'blocked':
                return 'blocked'
        return 'done'

    def late():
        with lock:
            grants = coord.late_grants(honoured)
            honoured.update(rid for _, rid, _ in grants)
        for peer, _, answer in grants:
            log(f'help: {peer} answered late; taking it after all')
            run_grant(peer, answer, group_of(faculty_of(answer['grant'][0]['slot'])))

    def worker():
        synced = False
        while clock() < deadline:
            late()
            found, later = pick()
            if found is None:
                if not later:
                    if not synced:
                        coord.sync()  # nothing to take, as far as this runner knows: make sure that is still so
                        synced = True
                        continue
                    # Nothing to take now, but a peer still at its share may yet meet a wall (all it has left then
                    # comes up for the asking) or take back what this runner could not finish. Waiting costs a board
                    # read now and then, and the wave ends with its busiest runner anyway; once every peer is done or
                    # waiting too, so is this one.
                    if not coord.waited_for():
                        return
                    pool.set_idle(True)
                with pool.cond:
                    pool.cond.wait(poll)
                continue
            pool.set_idle(False)
            synced = False
            peer, key, s = found
            faculty, group = faculty_of(key), s['group']
            try:
                log(f'help: {peer} has {key} {s["state"]}'
                    + (f' ({s["left"]} groups left)' if s['left'] is not None else '') + '; listing it from here')
                try:
                    items = probe(faculty, term_of(key))
                except Walled as err:
                    log(f'help: {faculty} refuses this runner ({err}); trying the next faculty')
                    with lock:
                        walled.add(group)
                    continue
                except Exception as err:
                    log(f'help: cannot list {faculty} ({err!r}); trying the next faculty')
                    with lock:
                        refused.add((peer, key, s['ask']))
                    continue
                room = room_of(faculty) if s['ask'] == 'part' else None
                if room is not None and room < SPLIT_MIN_SHARE:
                    with lock:
                        refused.add((peer, key, s['ask']))
                    continue
                rid = coord.request(peer, key, s['ask'], room)
                answer = coord.await_answer(peer, rid, deadline, clock)
                if answer is None:
                    coord.cancel(rid)
                    log(f'help: no answer from {peer} about {key}; giving up on it')
                    with lock:
                        refused.add((peer, key, s['ask']))
                    continue
                honoured.add(rid)
                if not answer['ok']:
                    log(f'help: {peer} keeps {key} ({answer.get("why", "no reason")})')
                    with lock:
                        refused.add((peer, key, s['ask']))
                    continue
                if any(faculty_of(g['slot']) != faculty for g in answer['grant']):
                    continue  # not what was asked: ignored, and the giver's outcome reports it unconfirmed
                if run_grant(peer, answer, group, items, term_of(key)) == 'blocked':
                    log(f'help: blocked on {faculty} halfway; what is left stays open for {peer} to take back')
                    with lock:
                        walled.add(group)
            finally:
                with lock:
                    busy_groups.discard(group)
                with pool.cond:
                    pool.cond.notify_all()

    n = max(1, workers)
    with ThreadPoolExecutor(max_workers=n) as ex:
        for f in [ex.submit(worker) for _ in range(n)]:
            f.result()
    if clock() < deadline:
        late()


class Walled(Exception):
    """The faculty's wall refuses this runner (help_peers moves on to the next one)."""

