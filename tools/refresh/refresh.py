#!/usr/bin/env python3
"""Refresh the timetables from the faculty sites.

    python tools/refresh/refresh.py --out <data checkout> [--faculty wlo,wel] [--profile hosted|selfhosted]
                                    [--limit N] [--dry-run] [--max-minutes M] [--fresh-hours H]

For every enabled faculty it lists the groups, fetches each page politely (one session, sequential, jittered,
conditional revalidation so unchanged pages answer 304), converts pages that changed, validates the calendar the
way the site's build does, and writes <out>/timetables/<term>/<GROUP>.ics only when the plan really changed.
Progress lives in <out>/refresh-state.json, so a stopped run resumes where it stopped.

A group whose plan keeps coming back unchanged stretches its revalidation gap (doubles per quiet check up to
--adaptive-hours, off with 0), so a quiet semester costs a fraction of the requests; the moment a plan moves,
the group is hot again and rides every pass.

A block (any status but 200/304/404, an Incapsula incident page) no longer ends the run: that faculty is
deferred while the others are covered, then the run sleeps out the block and resumes. How long to sleep is
learned per policy group from past recoveries (median, 20 min .. 12 h, 2 h without history; wall-caused
episodes count more than flaky ones), recovery is probed with cheap index fetches on a sparse-then-dense
schedule (--block-probes), and the whole wait is capped (--max-block-wait-minutes). A block response is not
taken at face value at once: it is reported to the egress (which demotes the exit that carried it, see
PLANWAT_EGRESS_BLOCK) and retried on a fresh connection (--block-retries), so one flagged exit in the
rotating pool no longer reads as a wall; only a sustained block is one. While it crawls, the run also streams
coarse progress (run/faculty/tick/done/wait events, ticks throttled) to the egress GUI's crawl card — see
PLANWAT_EGRESS_PROGRESS; the GUI turns them into a progress bar and a finish estimate. Nothing half-converted
is published, the old calendars stay. A merely transient fetch (transport error, 408/425/429/500/502/503/504,
an empty 200) is retried a few times with exponential backoff first (--retries/--retry-backoff); exhaustion
raises core.Blocked for HTTP transients (a wall) and the transport error itself for flakiness, so the run
learns the cause.
With --assign volunteers.json --as <login> it runs as a volunteer crawler (see docs/WOLONTARIUSZE.md): only the
groups assigned to that login this window are checked, at the volunteer pace, and --outcomes records what each
check found for tools/volunteer/bundle.py.
Exit codes: 0 done, 2 bad arguments, 3 blocked, 4 incomplete.
With GITHUB_OUTPUT set, `blocked`, `incomplete` and `changed` are exported for the workflow.
"""
import argparse
import datetime as dt
import json
import os
import random
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'volunteer'))
import assign  # noqa: E402
import core  # noqa: E402
import drivers  # noqa: E402

PROFILES = {'hosted': (4.0, 9.0), 'selfhosted': (1.5, 4.0), 'volunteer': (4.0, 9.0)}  # seconds between pages
# WLO and WEL share one Incapsula policy (cookies for .wat.edu.pl): crawling either too fast blocks both home
# addresses for hours. The ranges above are for the home line with one request at a time per host; a block
# response now costs a reported retry on a fresh exit before it counts as a wall (--block-retries), and the
# AIMD multiplier still stretches the pause after any real wall. The hosted range is for datacenter egress,
# which Incapsula already distrusts. Do not tune these down without a dry run from the crawling machine.


def log(msg):
    print(msg, flush=True)


# Statuses worth one more try: the host is wobbling, not walling us out.
TRANSIENT_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})


def get_with_retry(session, url, timeout, headers, retries=3, backoff=2.0, sleep=time.sleep):
    """GET that rides out transient trouble: transport errors, TRANSIENT_STATUSES, an empty 200.

    Anything else is a verdict and is returned at once, never retried: a block page,
    an unexpected status, a 404. Raises the last error (core.Blocked for exhausted
    HTTP transients, the transport error itself for exhausted flakiness) when every
    attempt fails, so the caller can tell a wall from a wobble.
    """
    last = None
    for attempt in range(retries + 1):
        try:
            r = session.get(url, timeout=timeout, headers=headers)
        except Exception as err:
            last = err
        else:
            if r.status_code in (200, 304, 404):
                if r.status_code == 200 and not r.content:
                    last = core.Blocked('HTTP 200 with an empty body')
                else:
                    return r
            elif r.status_code in TRANSIENT_STATUSES:
                last = core.Blocked(f'HTTP {r.status_code}')
            else:
                return r  # any other status is a verdict, not a wobble (never retried)
        if attempt < retries:
            sleep(backoff * (2 ** attempt) + random.uniform(0, 1))
    raise last


def post_run_report(report, url=None, timeout=10):
    """Tell the egress GUI how the run went. Best effort: never fails the crawl.

    Uses a proxy-less opener on purpose — the report goes to the egress box over
    the inner network, not through the proxy itself (the job's HTTP_PROXY would
    answer 403 for the egress' own address).
    """
    import urllib.request
    url = url or os.environ.get('PLANWAT_EGRESS_STATUS', 'http://egress:8080/api/run')
    if not url:
        return
    try:
        req = urllib.request.Request(url, data=json.dumps(report).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'}, method='POST')
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout).read()
    except Exception as err:
        log(f'run report not delivered ({err}); continuing')


def faculty_host(cfg):
    """The destination host of a faculty's config (for egress block reports); '' when unknown."""
    from urllib.parse import urlsplit
    for key in ('base', 'index', 'landing', 'page'):
        url = cfg.get(key)
        if url:
            host = urlsplit(url).hostname
            if host:
                return host
    return ''


def post_block_report(host, url=None, timeout=5):
    """Tell the egress that `host` just answered with a block page, so it can demote the exit that
    carried the response (inside a CONNECT tunnel the egress cannot see the block itself; the
    crawler can, and most recent tunnel is the one to blame). Best effort, never fails the crawl.

    Opt-in: reporting is enabled by setting PLANWAT_EGRESS_BLOCK to the egress' /api/block URL
    (the refresh action does); without it the call is a no-op, keeping offline tests offline.
    """
    url = url or os.environ.get('PLANWAT_EGRESS_BLOCK', '')
    if not url or not host:
        return
    import urllib.request
    try:
        req = urllib.request.Request(url, data=json.dumps({'host': host}).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'}, method='POST')
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=timeout).read()
    except Exception:
        pass  # the demotion is a nice-to-have; the retry path works without it


class Progress:
    """Streams coarse crawl progress to the egress GUI (POST /api/progress), best effort.

    Opt-in: PLANWAT_EGRESS_PROGRESS holds the endpoint (the refresh action sets it); without a
    URL every call is a no-op, so offline tests and plain CLI runs stay silent. Events mirror
    the crawl's structure — run, faculty_start, tick (throttled per slot), faculty_done, wait —
    and each carries enough context (done/total per slot, lane membership, block waits) for the
    GUI to re-derive progress and estimate the finish from its own arrival timestamps: a
    delayed, reordered or lost event costs accuracy, never correctness. Like the block report
    the call is proxy-less (the job's HTTP_PROXY answers 403 for the egress' own address).
    """

    THROTTLE = 4.0

    def __init__(self, url=None, run='', throttle=None, timeout=3.0, post=None, clock=time.monotonic):
        self.url = os.environ.get('PLANWAT_EGRESS_PROGRESS', '') if url is None else url
        self.run = run
        self.throttle = self.THROTTLE if throttle is None else throttle
        self.timeout = timeout
        self.clock = clock
        self.post = post  # injectable for tests; None -> a real proxy-less POST
        self.lock = threading.Lock()
        self.last_sent = {}  # slot -> clock() of the last tick, the throttle's whole memory
        self.quiet = False  # log the first delivery failure of a spell, then stay quiet

    def _deliver(self, payload):
        import urllib.request
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'}, method='POST')
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=self.timeout).read()

    def send(self, event, **fields):
        """Deliver one event; returns whether it went out. Never raises, never blocks the crawl."""
        if not self.url:
            return False
        try:
            (self.post or self._deliver)({'event': event, 'run': self.run, **fields})
            self.quiet = False
            return True
        except Exception as err:
            if not self.quiet:
                log(f'progress report not delivered ({err}); continuing')
                self.quiet = True
            return False

    def tick(self, slot, done, total):
        """A progress sample for `slot`, sent at most once per `throttle` seconds."""
        if not self.url:
            return False
        now = self.clock()
        with self.lock:
            if now - self.last_sent.get(slot, float('-inf')) < self.throttle:
                return False
            self.last_sent[slot] = now
        return self.send('tick', slot=slot, done=done, total=total)


def wait_for_recovery(name, probe, model, budget, max_probes=5, sleep=time.sleep, clock=time.monotonic):
    """Sleep out a block, probing rarely and late: (recovered, waited_sec, probes).

    `probe()` costs one cheap request (the faculty index) and answers True when the
    wall is gone; any failure means it is still up. Probes land on a quadratic schedule
    — sparse while the block is young, denser near the learned end — over a horizon of
    min(estimate, budget), so every probe still lands inside the budget when the learned
    cooldown overshoots it.
    """
    est = model.estimate(name)
    horizon = min(est, budget)
    log(f'[{name}] blocked; learned cooldown is {est / 60:.0f} min, probing up to {max_probes}x')
    waited, probes, start = 0.0, 0, clock()
    for i in range(1, max_probes + 1):
        target = horizon * (i / max_probes) ** 2  # absolute offset of probe i
        remaining = budget - (clock() - start)
        if remaining <= 0:
            break
        pause = min(target - waited, remaining)
        if pause > 0:
            sleep(pause)
        waited = clock() - start
        probes += 1
        try:
            recovered = probe()
        except Exception:
            recovered = False
        if recovered:
            duration = model.note_recovered(name)
            if duration is not None:
                log(f'[{name}] wall is down after {duration / 60:.0f} min; resuming')
            else:
                log(f'[{name}] wall is down; resuming')
            return True, waited, probes
        log(f'[{name}] still blocked ({probes}/{max_probes} probes)')
    return False, waited, probes


def discover_with_retry(driver, session, retries=2, backoff=2.0, sleep=time.sleep,
                        block_retries=0, on_block=None):
    """List the groups, riding out flaky transports, then a single flagged exit.

    Transport trouble (a dead pool proxy, a reset) gets `retries` more goes with exponential
    backoff. A Blocked verdict gets `block_retries` more goes, each on a fresh connection —
    with a rotating egress that rides another exit — with `on_block()` called first so the
    caller can report the exit that just answered the block. Raises the last error.
    """
    last = None
    for attempt in range(retries + 1):
        try:
            return driver.discover(session)
        except core.Blocked as err:
            last = err
            if not block_retries:
                raise  # a wall is a verdict: only the caller decides to retry it
            break
        except Exception as err:
            last = err
        if attempt < retries:
            sleep(backoff * (2 ** attempt) + random.uniform(0, 1))
    else:
        raise last
    for attempt in range(block_retries):
        if on_block is not None:
            on_block()
        sleep(backoff * (attempt + 1) + random.uniform(0, 1))
        try:
            return driver.discover(session)
        except Exception as err:  # noqa: BLE001 (Blocked and transport trouble alike)
            last = err
    raise last


def robots_allows(session, url, state=None):
    """False when the host's robots.txt disallows the URL. An unreadable robots.txt does not block.

    With `state`, answers younger than 24 h are reused from state.data['robots']
    (host -> {fetched_iso, text}) and fresh fetches are stored there, so one run
    fetches each host's robots.txt at most once a day; without it every call fetches.
    """
    from urllib import robotparser
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    text = None
    if state is not None:
        entry = state.data.get('robots', {}).get(parts.netloc)
        if entry:
            try:
                fetched = dt.datetime.fromisoformat(entry.get('fetched_iso', ''))
            except ValueError:
                fetched = None
            if fetched is not None and core.now_utc() - fetched < dt.timedelta(hours=24):
                text = entry.get('text')
    if text is None:
        try:
            r = session.get(f'{parts.scheme}://{parts.netloc}/robots.txt', timeout=20)
            if r.status_code != 200 or core.is_blocked(200, r.text[:4000]):
                return True
            text = r.text
        except Exception:
            return True
        if state is not None:
            state.data.setdefault('robots', {})[parts.netloc] = {
                'fetched_iso': core.now_utc().isoformat(), 'text': text}
    if core.is_blocked(200, (text or '')[:4000]):
        return True
    try:
        rp = robotparser.RobotFileParser()
        rp.parse((text or '').splitlines())
        return rp.can_fetch('*', url)
    except Exception:
        return True


def new_session():
    from curl_cffi import requests as cr
    # 'chrome' tracks curl_cffi's current Chrome fingerprint (chrome136 in 0.13.0). A pinned old release
    # (chrome131 was kept long after Chrome moved on) is itself a bot signal to Incapsula.
    s = cr.Session(impersonate='chrome')
    s.headers['Accept-Language'] = 'pl-PL,pl;q=0.9'
    return s


def conditional_headers(entry):
    """Validators for a conditional refresh: the server answers 304 without a body when nothing changed.

    Bandwidth, time and WAF score all drop: a 304 carries no page and looks like a returning visitor's
    revalidation rather than a full crawl.
    """
    headers = {}
    if entry.get('modified'):
        headers['If-Modified-Since'] = entry['modified']
    if entry.get('etag'):
        headers['If-None-Match'] = entry['etag']
    return headers


def remember_validators(entry, response):
    """Keep the server's cache validators for the next conditional refresh (best effort)."""
    get = getattr(response, 'headers', {}).get
    try:
        modified, etag = get('Last-Modified'), get('ETag')
    except Exception:
        return
    if modified:
        entry['modified'] = modified
    if etag:
        entry['etag'] = etag


def noted_quiet(entry):
    """A check finished with the same plan: the group's next revalidation gap doubles.

    core.quiet_interval turns the streak into hours; a change resets it (noted_change),
    so a plan that just moved stays on the full cadence.
    """
    try:
        entry['streak'] = int(entry.get('streak', 0)) + 1
    except (TypeError, ValueError):
        entry['streak'] = 1


def note_outcome(args, code, tid, status):
    """Record what a volunteer's check of `code` found (bundle.py turns these into votes)."""
    outcomes = getattr(args, 'outcomes_log', None)
    if outcomes is not None:
        outcomes[f'{code}@{tid}'] = {'status': status, 'at': core.now_utc().isoformat()}


def noted_change(entry):
    """The plan really moved: the group is hot again and is checked every pass."""
    entry['streak'] = 0


def refresh_faculty(name, cfg, args, state, today, session, sleep=time.sleep, clock=time.monotonic,
                    progress=None, ahead=False):
    """Returns (changed codes, blocked, complete). `today` is a date inside the semester to refresh; with `ahead`
    that is the coming semester, tracked under its own state keys so the running one keeps its dates."""
    driver = drivers.load(cfg['driver'], name, cfg, today)
    tid = core.term_id(today)
    out = Path(args.out)
    fac = state.faculties.setdefault(name, {})
    group = core.group_of(name)
    host = faculty_host(cfg)
    on_block = (lambda: post_block_report(host)) if host else None
    # AIMD pacing: the policy group's multiplier stretches the pause between pages. It grows on
    # every block verdict and decays on every clean faculty, persisting through state.save.
    mult = state.data.get('pacing', {}).get(group, 1.0)

    def pace(blocked):
        pacing = state.data.setdefault('pacing', {})
        pacing[group] = min(3.0, mult * 1.5) if blocked else max(1.0, mult * 0.9)

    try:
        items = discover_with_retry(driver, session, args.retries, args.retry_backoff, sleep,
                                    block_retries=args.block_retries, on_block=on_block)
    except core.Blocked as err:
        log(f'[{name}] BLOCKED while listing groups: {err}')
        fac['blocked_at'] = core.now_utc().isoformat()
        fac['run'] = {'at': fac['blocked_at'], 'checked': 0, 'changed': 0, 'skipped': 0,
                      'not_ready': 0, 'blocked': True, 'ahead': ahead, 'cause': 'wall', 'degraded': False}
        pace(True)
        return [], True, False
    except Exception as err:
        log(f'[{name}] cannot list groups: {err}')
        # The report reads fac['run']: leaving the previous entry here would resend the last
        # run's numbers (and its degraded flag) as if they were this run's verdict.
        fac['run'] = {'at': core.now_utc().isoformat(), 'term': tid, 'checked': 0, 'changed': 0,
                      'skipped': 0, 'not_ready': 0, 'blocked': False, 'ahead': ahead,
                      'cause': 'listing', 'degraded': True}
        return [], False, False
    # The ahead pass must not clear a degraded flag the main pass already raised.
    degraded = fac.get('run', {}).get('degraded', False) if ahead else False
    # Listed-count canary: a site that suddenly lists half its groups is partially broken,
    # not freshly tidy.
    prev_count = fac.get('last_count')
    fac['last_count'] = len(items)
    if prev_count is not None and prev_count >= 10 and len(items) < 0.5 * prev_count:
        degraded = True
        log(f'[{name}] DEGRADED: only {len(items)} groups listed (was {prev_count}); flagging the run')
    if not items:
        log(f'[{name}] no groups listed; leaving the faculty untouched')
        if degraded:
            fac['run'] = {'at': core.now_utc().isoformat(), 'term': tid, 'checked': 0, 'changed': 0,
                          'skipped': 0, 'not_ready': 0, 'blocked': False, 'ahead': ahead,
                          'cause': None, 'degraded': True}
        return [], False, False
    if not robots_allows(session, items[0].url, state):
        log(f'[{name}] robots.txt disallows the timetable pages; skipping the faculty')
        return [], False, False
    now = core.now_utc()
    key = (lambda code: f'{code}@{tid}') if ahead else (lambda code: code)
    # Twice the cadence while the faculties publish the coming semester; a per-faculty
    # override wins over the default but never drops below one hour. On top of that,
    # a group that keeps coming back unchanged stretches its gap (--adaptive-hours),
    # so a quiet semester costs about half of yesterday's requests.
    fresh_hours = core.effective_fresh_hours(max(1, cfg.get('fresh_hours', args.fresh_hours)), today)
    todo = [i for i in items if args.force or not state.fresh(
        key(i.code), now, core.quiet_interval(state.groups.get(key(i.code), {}),
                                              fresh_hours, args.adaptive_hours), tid)]
    # Stalest first: a run cut short by --max-minutes, --limit or a block refreshes the groups
    # unseen the longest. Never-checked ('') sorts before any ISO timestamp; the code breaks ties
    # so the order is deterministic. The limit slices after the sort, keeping the stalest N.
    todo.sort(key=lambda i: (state.groups.get(key(i.code), {}).get('checked', ''), i.code))
    if getattr(args, 'registry', None):
        # A volunteer checks only its own share of this window (tools/volunteer/assign.py).
        todo = [i for i in todo if assign.is_assigned(args.registry, args.login, name, i.code, tid, args.window)]
    if args.limit:
        todo = todo[:args.limit]
    log(f'[{name}] {len(items)} groups, {len(items) - len(todo)} fresh, {len(todo)} to check (term {tid})')
    slot = name if not ahead else f'{name}~{tid}'
    if progress is not None:
        progress.send('faculty_start', slot=slot, faculty=name, lane=group, total=len(todo),
                      fresh=len(items) - len(todo), listed=len(items), ahead=ahead, term=tid)
    started, changed, failed, checked = clock(), [], 0, 0
    not_ready = 0
    for n, item in enumerate(todo, 1):
        if progress is not None:
            progress.tick(slot, n - 1, len(todo))
        if args.max_minutes and (clock() - started) / 60 > args.max_minutes:
            log(f'[{name}] time budget used up after {n - 1} groups')
            return changed, False, False
        if n > 1:
            sleep(random.uniform(args.delay[0] * mult, args.delay[1] * mult))
        if n % 25 == 0 and not args.dry_run:
            state.save()  # checkpoint every 25 checks, however they end (a 304 or an unchanged hash included)
        entry = state.groups.setdefault(key(item.code), {})
        # A block response is reported to the egress (which demotes the exit that carried it) and
        # retried on a fresh connection: with a rotating egress each attempt rides another exit, so
        # one flagged proxy no longer reads as a wall. Only a block that survives every attempt does.
        attempts = max(1, args.block_retries + 1)
        for attempt in range(1, attempts + 1):
            try:
                r = get_with_retry(session, item.url, timeout=60, headers=conditional_headers(entry),
                                   retries=args.retries, backoff=args.retry_backoff, sleep=sleep)
                checked += 1
            except core.Blocked as err:
                log(f'[{name}] BLOCKED on {item.code}: {err}')
                fac['blocked_at'] = core.now_utc().isoformat()
                fac['run'] = {'at': fac['blocked_at'], 'term': tid, 'checked': checked,
                              'changed': len(changed), 'skipped': failed, 'not_ready': not_ready,
                              'blocked': True, 'ahead': ahead, 'cause': 'wall', 'degraded': degraded}
                pace(True)
                return changed, True, False
            except Exception as err:
                log(f'[{name}] flaky fetch on {item.code}, {checked} responses in: {err}')
                fac['blocked_at'] = core.now_utc().isoformat()
                fac['run'] = {'at': fac['blocked_at'], 'term': tid, 'checked': checked,
                              'changed': len(changed), 'skipped': failed, 'not_ready': not_ready,
                              'blocked': True, 'ahead': ahead, 'cause': 'flaky', 'degraded': degraded}
                pace(True)
                return changed, True, False
            if r.status_code in (304, 404):
                break
            text = r.content.decode('utf-8', errors='replace') if r.status_code == 200 else ''
            if not core.is_blocked(r.status_code, text):
                break
            post_block_report(host)
            if attempt >= attempts:
                log(f'[{name}] BLOCKED on {item.code} (HTTP {r.status_code}) after {n - 1} pages')
                fac['blocked_at'] = core.now_utc().isoformat()
                fac['run'] = {'at': fac['blocked_at'], 'term': tid, 'checked': checked,
                              'changed': len(changed), 'skipped': failed, 'not_ready': not_ready,
                              'blocked': True, 'ahead': ahead, 'cause': 'wall', 'degraded': degraded}
                pace(True)
                return changed, True, False
            log(f'[{name}] {item.code}: block response (HTTP {r.status_code}); '
                f'riding a fresh connection ({attempt + 1}/{attempts})')
            sleep(random.uniform(2.0, 4.0) * attempt)
        if r.status_code == 304:
            # The server says the page is byte-identical: no download, no conversion, just a fresh check mark.
            remember_validators(entry, r)
            entry['checked'] = core.now_utc().isoformat()
            noted_quiet(entry)
            note_outcome(args, item.code, tid, 'unchanged')
            continue
        raw = r.content
        text = raw.decode('utf-8', errors='replace')
        if r.status_code == 404:
            log(f'[{name}] {item.code}: gone (404), keeping the old calendar')
            note_outcome(args, item.code, tid, 'gone')
            continue
        if not driver.page_ok(text):
            if getattr(driver, 'not_ready', None) and driver.not_ready(text):
                not_ready += 1
                log(f'[{name}] {item.code}: not ready for {tid} yet (the faculty still shows '
                    f'another semester); keeping the old calendar')
                note_outcome(args, item.code, tid, 'not_ready')
                continue
            log(f'[{name}] {item.code}: not a timetable page, skipped')
            failed += 1
            continue
        remember_validators(entry, r)
        digest = core.sha256(raw)
        path = out / 'timetables' / tid / f'{item.code}.ics'
        old = path.read_text(encoding='utf-8') if path.is_file() else None
        if old is not None and entry.get('hash') == digest:
            entry['checked'] = core.now_utc().isoformat()
            noted_quiet(entry)
            note_outcome(args, item.code, tid, 'unchanged')
            continue
        try:
            ics = core.to_crlf(driver.convert(item, raw))
        except Exception as err:
            log(f'[{name}] {item.code}: conversion failed ({err!r}), keeping the old calendar')
            failed += 1
            continue
        except SystemExit as err:  # the converters exit on a page they cannot read
            log(f'[{name}] {item.code}: conversion stopped ({err}), keeping the old calendar')
            failed += 1
            continue
        clipped = core.clip_to_term(ics, tid)
        if clipped != ics:
            log(f'[{name}] {item.code}: dropped lessons of another semester (the page shows two)')
            ics = clipped
        ics, bounds_patched = core.reconcile_term_bounds(ics, old, tid)
        if bounds_patched:
            log(f'[{name}] {item.code}: faculty term label left the filed term; '
                f'keeping the {tid} grid')
        # The filed calendar may itself still carry another semester's lessons (a file seeded
        # while the faculty was showing the old grid, as WCY's were): clip it first so publishing
        # its cleaned-up version is not read as the page suddenly losing most of its plan.
        previous = core.clip_to_term(old, tid) if old is not None else None
        ok, why = core.validate(ics, item.code, tid, previous)
        if not ok:
            log(f'[{name}] {item.code}: rejected ({why}), keeping the old calendar')
            failed += 1
            continue
        entry.update(hash=digest, checked=core.now_utc().isoformat(), term=tid)
        if core.same_plan(old, ics):
            noted_quiet(entry)
            note_outcome(args, item.code, tid, 'unchanged')
            continue
        entry['changed'] = entry['checked']
        entry['streak'] = 0
        changed.append(item.code)
        log(f'[{name}] {item.code}: {"new" if old is None else "changed"}')
        if not args.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(ics.encode('utf-8'))
            note_outcome(args, item.code, tid, 'changed')
    # Skips (unreadable pages, failed conversions, rejected calendars) against responses
    # received: too many means the site is half-broken, not the plans half-changed. Pages
    # that are merely "not ready" (the faculty still shows another semester) are expected
    # during publication season and never count as skips.
    if checked >= 5 and failed / checked > 0.3:
        degraded = True
        log(f'[{name}] DEGRADED: {failed} of {checked} checked groups skipped; flagging the run')
    pace(False)
    if not ahead:
        fac['last_ok'] = core.now_utc().isoformat()
        fac['blocked_at'] = None
    fac['run'] = {'at': core.now_utc().isoformat(), 'term': tid, 'checked': checked,
                  'changed': len(changed), 'skipped': failed, 'not_ready': not_ready,
                  'blocked': False, 'ahead': ahead, 'cause': None, 'degraded': degraded}
    log(f'[{name}] done: {len(changed)} changed, {failed} skipped'
        + (f', {not_ready} not ready' if not_ready else ''))
    return changed, False, True


def export(**values):
    path = os.environ.get('GITHUB_OUTPUT')
    if path:
        with open(path, 'a', encoding='utf-8') as fh:
            for k, v in values.items():
                fh.write(f'{k}={str(v).lower()}\n')


def parse(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', required=True, help='the data checkout (holds timetables/ and refresh-state.json)')
    ap.add_argument('--faculty', default='', help='comma-separated faculties (default: every enabled one)')
    ap.add_argument('--profile', choices=sorted(PROFILES), default='hosted')
    ap.add_argument('--limit', type=int, default=0, help='check at most N groups per faculty')
    ap.add_argument('--max-minutes', type=float, default=0, help='stop gracefully after this long (0 = no limit)')
    ap.add_argument('--fresh-hours', type=float, default=1.0, help='skip groups checked more recently than this')
    ap.add_argument('--adaptive-hours', type=float, default=4.0,
                    help='a group answering unchanged doubles its revalidation gap (1 h, 2 h, 4 h, ...) '
                         'up to this many hours; 0 disables the stretching')
    ap.add_argument('--force', action='store_true', help='ignore --fresh-hours')
    ap.add_argument('--dry-run', action='store_true', help='fetch and convert, write nothing')
    ap.add_argument('--retries', type=int, default=3,
                    help='retry a flaky page fetch this many times (block responses are the exception)')
    ap.add_argument('--retry-backoff', type=float, default=2.0,
                    help='base seconds between fetch retries (exponential + jitter)')
    ap.add_argument('--block-retries', type=int, default=2,
                    help='after a block response, retry on a fresh connection this many times before '
                         'calling it a wall (each retry rides another exit of a rotating egress)')
    ap.add_argument('--max-block-wait-minutes', type=float, default=30,
                    help='total minutes a run may sleep out blocks before giving up (0 = exit on block)')
    ap.add_argument('--lanes', type=int, default=6,
                    help='policy groups crawled side by side (1 = strictly one faculty at a time)')
    ap.add_argument('--block-probes', type=int, default=5,
                    help='recovery probes per block (one cheap index fetch each)')
    ap.add_argument('--assign', type=Path, help='volunteer mode: the registry (volunteers.json)')
    ap.add_argument('--as', dest='login', default='', help='volunteer mode: your GitHub login in the registry')
    ap.add_argument('--outcomes', type=Path, help='write what each check found here (JSON, for bundle.py)')
    args = ap.parse_args(argv)
    args.registry, args.window = None, None
    args.outcomes_log = {} if (args.outcomes or args.assign) else None
    if args.assign:
        if not args.login:
            ap.error('--assign needs --as <login>')
        try:
            args.registry = assign.load_registry(args.assign)
        except (OSError, ValueError) as err:
            ap.error(f'cannot read the registry {args.assign}: {err}')
        # Volunteers crawl at the gentle pace, whatever profile was asked for: many lines add up.
        args.profile = 'volunteer'
    args.delay = PROFILES[args.profile]
    return args


def refresh_ahead(name, sources, args, state, today, session, coming, tallies, sleep, clock, progress=None):
    """The coming semester's pass for one faculty; folds its results into `tallies`."""
    # The next semester's plans may already be up. Whatever is not published yet is just not there:
    # that never makes the run incomplete, only a block stops it.
    log(f'[{name}] looking for the coming semester ({core.term_id(coming)})')
    done, was_blocked, complete = refresh_faculty(name, sources[name], args, state, coming, session,
                                                  sleep=sleep, clock=clock, progress=progress, ahead=True)
    tallies['changed'] += done
    tallies['blocked'] |= was_blocked
    if progress is not None:
        progress.send('faculty_done', slot=f'{name}~{core.term_id(coming)}', faculty=name,
                      lane=core.group_of(name), changed=len(done), blocked=was_blocked,
                      complete=complete, ahead=True)
    return was_blocked


def run_lane(names, sources, args, state, model, today, coming, sleep=time.sleep, clock=time.monotonic,
             session=None, wait_budget=None, progress=None):
    """Refresh the faculties of one policy group, one after another, on a session of their own.

    Returns {'changed': [...], 'blocked': bool, 'incomplete': set(names), 'waited': seconds slept}. A blocked faculty no longer stops
    the others: each is deferred while the rest of the lane is covered, then the lane sleeps out the shared wall
    (one wait per lane: its members stand behind the same Incapsula policy) and every member resumes.
    """
    session = session or new_session()
    tallies = {'changed': [], 'blocked': False, 'incomplete': set(), 'waited': 0.0}
    deferred = []  # (name, main_ok): main_ok says the main pass finished cleanly
    for name in names:
        # Drivers may tune the shared session (WTC sets Referer): never leak that into the next faculty.
        saved_headers = dict(session.headers) if getattr(session, 'headers', None) is not None else None
        try:
            done, was_blocked, complete = refresh_faculty(name, sources[name], args, state, today,
                                                           session, sleep=sleep, clock=clock,
                                                           progress=progress)
        finally:
            if saved_headers is not None:
                try:
                    session.headers.clear()
                    session.headers.update(saved_headers)
                except Exception:
                    pass
        tallies['changed'] += done
        tallies['blocked'] |= was_blocked
        if complete:
            tallies['incomplete'].discard(name)  # a clean rerun clears the earlier mark
        else:
            tallies['incomplete'].add(name)
        if progress is not None:
            # One done-event per faculty however its pass ended (a wall, a flaky fetch, no groups
            # listed): the slot's ticks stay truthful, this closes them out.
            progress.send('faculty_done', slot=name, faculty=name, lane=core.group_of(name),
                          changed=len(done), blocked=was_blocked, complete=complete)
        if was_blocked:
            model.note_blocked(name, state.faculties.get(name, {}).get('run', {}).get('cause'))
            deferred.append((name, False))
            continue
        if coming and refresh_ahead(name, sources, args, state, today, session, coming,
                                    tallies, sleep, clock, progress=progress):
            model.note_blocked(name, state.faculties.get(name, {}).get('run', {}).get('cause'))
            deferred.append((name, True))
    if wait_budget is None:
        wait_budget = args.max_block_wait_minutes * 60
    if not deferred or wait_budget <= 0:
        return tallies
    first = deferred[0][0]
    group = core.group_of(first)
    driver = drivers.load(sources[first]['driver'], first, sources[first], today)
    probe_session = new_session()  # probe with a clean jar, like a new visitor

    def probe():
        try:
            driver.discover(probe_session)
            return True
        except Exception:
            return False

    if progress is not None:
        progress.send('wait_start', lane=group, faculties=[n for n, _ in deferred],
                      budget=round(wait_budget))
    recovered, waited, probes = wait_for_recovery(group, probe, model, wait_budget,
                                                   args.block_probes, sleep, clock)
    if progress is not None:
        progress.send('wait_end', lane=group, faculties=[n for n, _ in deferred],
                      waited=round(waited), probes=probes, recovered=recovered)
    tallies['waited'] = waited
    for name, main_ok in deferred:
        fac = state.faculties.setdefault(name, {})
        fac['wait'] = {'waited': round(waited), 'probes': probes, 'recovered': recovered}
        if not recovered:
            continue
        fac['blocked_at'] = None  # the wall is down; the rerun re-decides from scratch
        resume = new_session()  # fresh cookies/jar: the old ones may be the blocked ones
        if main_ok and coming:
            # The main pass already finished: only the coming semester is still missing.
            refresh_ahead(name, sources, args, state, today, resume, coming, tallies, sleep, clock,
                          progress=progress)
        else:
            done, was_blocked, complete = refresh_faculty(name, sources[name], args, state, today,
                                                          resume, sleep=sleep, clock=clock,
                                                          progress=progress)
            tallies['changed'] += done
            if complete:
                tallies['incomplete'].discard(name)
            else:
                tallies['incomplete'].add(name)
            if progress is not None:
                progress.send('faculty_done', slot=name, faculty=name, lane=core.group_of(name),
                              changed=len(done), blocked=was_blocked, complete=complete)
            if was_blocked:
                model.note_blocked(name, state.faculties.get(name, {}).get('run', {}).get('cause'))
                continue
            if coming:
                refresh_ahead(name, sources, args, state, today, resume, coming, tallies, sleep, clock,
                              progress=progress)
    tallies['blocked'] = any(state.faculties.get(n, {}).get('blocked_at') for n, _ in deferred)
    return tallies


def plan_lanes(wanted):
    """Faculties grouped by Incapsula policy, in the order they were asked for: [[name, ...], ...]."""
    lanes = {}
    for name in wanted:
        lanes.setdefault(core.group_of(name), []).append(name)
    return list(lanes.values())


def write_outcomes(args, started, wanted, sources, state):
    """What this run found, group by group, for tools/volunteer/bundle.py."""
    faculties = {}
    for n in wanted:
        run = state.faculties.get(n, {}).get('run', {}) if n in sources else {}
        faculties[n] = {'blocked': bool(run.get('blocked')), 'cause': run.get('cause')}
    report = {'started': started, 'ended': core.now_utc().isoformat(), 'login': args.login,
              'window': args.window, 'dry_run': args.dry_run,
              'groups': dict(sorted((args.outcomes_log or {}).items())),
              'faculties': faculties}
    args.outcomes.parent.mkdir(parents=True, exist_ok=True)
    args.outcomes.write_text(json.dumps(report, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')


def main(argv=None, session=None, today=None, sleep=time.sleep, clock=time.monotonic):
    args = parse(argv)
    today = today or core.now_utc().date()
    started = core.now_utc().isoformat()
    sources = json.loads((HERE / 'sources.json').read_text(encoding='utf-8'))
    named = [f for f in args.faculty.split(',') if f]
    wanted = named or [f for f, c in sources.items() if c.get('enabled')]
    if args.registry:
        me = assign.find(args.registry, args.login)
        if me is None or me['trust'] == 'suspended':
            log(f'{args.login} is not an active volunteer in {args.assign}')
            return 2
        if me['faculties']:
            wanted = [f for f in wanted if f in me['faculties']]
        args.window = assign.window_of(core.now_utc())
        log(f'volunteer {me["login"]} ({me["trust"]}), window {args.window}: {", ".join(wanted) or "nothing"}')
    unknown = [f for f in wanted if f not in sources]
    if unknown:
        log(f'unknown faculty: {", ".join(unknown)}')
        return 2
    state = core.State(Path(args.out) / core.STATE_FILE)
    model = core.BlockModel(state.data)
    coming = core.upcoming_reference(today)
    lanes = plan_lanes(wanted)
    parallel = bool(args.lanes > 1 and len(lanes) > 1 and session is None)
    progress = Progress(run=started, clock=clock)
    if progress.url:
        # The GUI seeds one queued slot per faculty from this layout, so an untouched lane still
        # shows up (and an ETA covers it) long before its first faculty reports in.
        progress.send('run_start', profile=args.profile, parallel=parallel,
                      lanes=[{'lane': core.group_of(ns[0]), 'faculties': list(ns)} for ns in lanes])

    def lane(names, wait_budget=None):
        return run_lane(names, sources, args, state, model, today, coming, sleep, clock,
                        session=session, wait_budget=wait_budget, progress=progress)

    if parallel:
        # Different policy groups are different walls, so they crawl side by side: the pause between pages
        # is per host and unchanged, only the wall-clock time of a full pass shrinks. Each lane waits out
        # its own wall concurrently, so each may spend the whole wait budget.
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=min(args.lanes, len(lanes))) as pool:
            results = list(pool.map(lane, lanes))
    else:
        # One after another the waits add up, so they share the budget: each wait is capped to its fair share
        # of what is left (but always gets a real chance: at least 15 minutes).
        results, left = [], args.max_block_wait_minutes * 60
        for pos, names in enumerate(lanes):
            res = lane(names, min(left, max(900.0, left / (len(lanes) - pos))) if left > 0 else 0)
            left -= res['waited']
            results.append(res)
    tallies = {'changed': [], 'blocked': False, 'incomplete': set()}
    for res in results:
        tallies['changed'] += res['changed']
        tallies['blocked'] |= res['blocked']
        tallies['incomplete'] |= res['incomplete']
    blocked = tallies['blocked']
    degraded_any = any(state.faculties.get(n, {}).get('run', {}).get('degraded')
                       for n in wanted if n in sources)
    incomplete = bool(tallies['incomplete']) or degraded_any
    if degraded_any:
        log('DEGRADED: one or more faculties checked out degraded (skips or a shrunken listing); '
            'forcing incomplete so the run gets attention')
    if not args.dry_run:
        state.save()
    exit_code = 3 if blocked else 4 if incomplete else 0
    if args.outcomes:
        write_outcomes(args, started, wanted, sources, state)
    export(blocked=blocked, incomplete=incomplete, changed=len(tallies['changed']),
           degraded=degraded_any)
    log(f'changed: {len(tallies["changed"])}; blocked: {blocked}; incomplete: {incomplete}')
    if progress.url:
        progress.send('run_done', exit=exit_code, blocked=blocked, incomplete=incomplete,
                      degraded=degraded_any, changed=len(tallies['changed']))
    post_run_report({'started': started, 'ended': core.now_utc().isoformat(), 'exit': exit_code,
                     'profile': args.profile, 'dry_run': args.dry_run,
                     'faculties': {n: {**(state.faculties.get(n, {}).get('run', {})),
                                       **({'wait': state.faculties[n]['wait']}
                                          if 'wait' in state.faculties.get(n, {}) else {})}
                                   for n in wanted if n in sources}})
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
