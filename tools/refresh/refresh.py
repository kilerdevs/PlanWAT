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
schedule (--block-probes), and the whole wait is capped (--max-block-wait-minutes); a wall this runner already
waited out in vain (CHRONIC_MIN_WAIT) is not waited out again until a pass gets through it. A block response is not
taken at face value at once: it is reported to the egress (which demotes the exit that carried it, see
PLANWAT_EGRESS_BLOCK) and retried on a fresh connection (--block-retries), so one flagged exit in the
rotating pool no longer reads as a wall; only a sustained block is one. While it crawls, the run also streams
coarse progress (run/faculty/tick/done/wait events, ticks throttled) to the egress GUI's crawl card — see
PLANWAT_EGRESS_PROGRESS; the GUI turns them into a progress bar and a finish estimate. Nothing half-converted
is published, the old calendars stay. A merely transient fetch (transport error, 408/425/429/500/502/503/504,
an empty 200) is retried a few times with exponential backoff first (--retries/--retry-backoff); exhaustion
raises core.Blocked for HTTP transients (a block response: reported and retried on a fresh connection like
any other, then a wall) and the transport error itself for flakiness, so the run learns the cause.
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
import re
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'volunteer'))
import assign  # noqa: E402
import board as boards  # noqa: E402
import core  # noqa: E402
import drivers  # noqa: E402
import fleet  # noqa: E402
import egress as egress_client  # noqa: E402
import relay  # noqa: E402
import stack  # noqa: E402

# A census (take_census) at most this often: weekly, half a day early so a weekly pass never slips. It only finds new
# programme directories, which come a few times a year, and its Joomla pages are the heaviest load this crawler puts on
# an Incapsula host.
CENSUS_HOURS = 6 * 24 + 12
PROFILES = {'hosted': (4.0, 9.0), 'selfhosted': (1.5, 4.0), 'volunteer': (4.0, 9.0)}  # seconds between pages
# WLO and WEL share one Incapsula policy (cookies for .wat.edu.pl): crawling either too fast blocks both home
# addresses for hours. The ranges above are for the home line with one request at a time per host; a block
# response now costs a reported retry on a fresh exit before it counts as a wall (--block-retries), and the
# AIMD multiplier still stretches the pause after any real wall. The hosted range is for datacenter egress,
# which Incapsula already distrusts. Do not tune these down without a dry run from the crawling machine.


def log(msg):
    print(msg, flush=True)


def egress_headers():
    """JSON + credentials for every report to the egress GUI.

    The proxy accepts `Authorization: Bearer` and `X-Token`; sending both keeps older
    egress builds working while the documented Bearer form is always present.
    """
    headers = {'Content-Type': 'application/json'}
    token = os.environ.get('EGRESS_API_TOKEN', '').strip()
    if token:
        headers['Authorization'] = f'Bearer {token}'
        headers['X-Token'] = token
    return headers


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
                                     headers=egress_headers(), method='POST')
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

    A host fetched through the Worker relay never rode a pool exit, so there is nothing for the
    egress to demote; reporting it would blame whichever exit happened to carry that host last.

    Opt-in: reporting is enabled by setting PLANWAT_EGRESS_BLOCK to the egress' /api/block URL
    (the refresh action does); without it the call is a no-op, keeping offline tests offline.
    """
    url = url or os.environ.get('PLANWAT_EGRESS_BLOCK', '')
    if not url or not host or relay.host_relayed(host):
        return

    import urllib.request
    try:
        req = urllib.request.Request(url, data=json.dumps({'host': host}).encode('utf-8'),
                                     headers=egress_headers(), method='POST')
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
                                     headers=egress_headers(), method='POST')
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

    def tick(self, slot, done, total, **fields):
        """A progress sample for `slot`, sent at most once per `throttle` seconds."""
        if not self.url:
            return False
        now = self.clock()
        with self.lock:
            if now - self.last_sent.get(slot, float('-inf')) < self.throttle:
                return False
            self.last_sent[slot] = now
        return self.send('tick', slot=slot, done=done, total=total, **fields)


def wait_for_recovery(name, probe, model, budget, max_probes=5, sleep=time.sleep, clock=time.monotonic, stop=None):
    """Sleep out a block, probing rarely and late: (recovered, waited_sec, probes).

    `probe()` costs one cheap request (the faculty index) and answers True when the
    wall is gone; any failure means it is still up. Probes land on a quadratic schedule
    — sparse while the block is young, denser near the learned end — over a horizon of
    min(estimate, budget), so every probe still lands inside the budget when the learned
    cooldown overshoots it. `stop()`, asked every half minute at most, ends the wait early (another runner took
    everything that was waiting): not recovered, but nothing is left to recover for.
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
        while pause > 0:
            if stop is not None and stop():
                log(f'[{name}] nothing left to wait for: another runner took it')
                return False, clock() - start, probes
            step = pause if stop is None else min(pause, 30.0)
            sleep(step)
            pause -= step
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


# A wall that outlasted a wait this long (in an earlier pass or this one) is not waited out again: until a pass gets
# through it (its first request each pass is the probe), each pass lets the faculty go at once.
CHRONIC_MIN_WAIT = 15 * 60


def _own_wall(wall, runner):
    """A wall episode on record that this runner met: one another runner met (a state copied from it) is not."""
    return (isinstance(wall, dict) and isinstance(wall.get('since'), str)
            and (not runner or wall.get('by') in (None, runner)))


def note_wall(state, name, cause, runner=''):
    """A wall met here (not a flaky line): the episode starts now, unless this runner's is already open. The record
    names the runner, since a wall stands in front of one address."""
    if cause != 'wall':
        return
    fac = state.faculties.setdefault(name, {})
    if not _own_wall(fac.get('wall'), runner):
        fac['wall'] = {'since': core.now_utc().isoformat(), 'failed': 0}
    if runner:
        fac['wall']['by'] = runner


def chronic(state, name, runner=''):
    """Whether this runner already waited out the faculty's current wall in vain (CHRONIC_MIN_WAIT)."""
    wall = state.faculties.get(name, {}).get('wall')
    failed = wall.get('failed') if _own_wall(wall, runner) else None
    return isinstance(failed, int) and not isinstance(failed, bool) and failed >= 1


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
        except core.Gone:
            raise  # the page moved: asking again changes nothing
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


def new_session(proxy=None):
    """A browser-like session; with `proxy` (an egress hunt port, egress.py) every request rides it, the relay
    included: a faculty reached through pool exits is never sent to the Worker instead."""
    from curl_cffi import requests as cr
    # 'chrome' tracks curl_cffi's current Chrome fingerprint (chrome136 in 0.13.0). A pinned old release
    # (chrome131 was kept long after Chrome moved on) is itself a bot signal to Incapsula.
    if proxy:
        s = cr.Session(impersonate='chrome', proxies={'http': proxy, 'https': proxy})
    else:
        s = cr.Session(impersonate='chrome')
    s.headers['Accept-Language'] = 'pl-PL,pl;q=0.9'
    return s if proxy else relay.wrap(s)


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


def noted_not_ready(entry, tid):
    """The page still shows another semester: the group's next ask waits longer (core.not_ready_wait)."""
    mark = entry.get('not_ready')
    streak = mark.get('streak') if isinstance(mark, dict) and mark.get('term') == tid else 0
    if not isinstance(streak, int) or isinstance(streak, bool) or streak < 0:
        streak = 0
    entry['not_ready'] = {'at': core.now_utc().isoformat(), 'term': tid, 'streak': streak + 1}


# A calendar that lost more than core.validate allows is taken once the same plan came back this many times, this many
# hours apart at least: a page broken half-way rarely breaks the same way for half a day.
SHRINK_PASSES = 3
SHRINK_HOURS = 12


def steady_shrink(entry, ics):
    """Note one more sighting of a shrunken plan; whether it has now shown the same way long enough to be the plan."""
    digest, now = core.plan_hash(ics), core.now_utc()
    mark = entry.get('shrink')
    if not (isinstance(mark, dict) and mark.get('hash') == digest and isinstance(mark.get('seen'), int)):
        mark = entry['shrink'] = {'hash': digest, 'seen': 0, 'first': now.isoformat()}
    mark['seen'] += 1
    try:
        hours = (now - dt.datetime.fromisoformat(mark['first'])).total_seconds() / 3600
    except (TypeError, ValueError):
        mark['first'], hours = now.isoformat(), 0
    return mark['seen'] >= SHRINK_PASSES and hours >= SHRINK_HOURS


def accepted_checked(state, code, tid):
    """The coordinator's last accepted check of `code` in term `tid` ('' when none)."""
    entry = state.accepted.get(f'{code}@{tid}')
    stamp = entry.get('checked') if isinstance(entry, dict) else None
    return stamp if isinstance(stamp, str) else ''


LINE_KEYS = core.LINE_KEYS


def load_line_state(state, path):
    try:
        mine = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        mine = {}
    for k in LINE_KEYS:
        state.data[k] = mine[k] if isinstance(mine, dict) and isinstance(mine.get(k), dict) else {}


def save_line_state(state, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps({k: state.data.get(k, {}) for k in LINE_KEYS}, ensure_ascii=False, indent=1) + '\n',
                   encoding='utf-8')
    tmp.replace(path)


def note_outcome(args, code, tid, status):
    """Record what a volunteer's check of `code` found (bundle.py turns these into votes)."""
    outcomes = getattr(args, 'outcomes_log', None)
    if outcomes is not None:
        outcomes[f'{code}@{tid}'] = {'status': status, 'at': core.now_utc().isoformat()}


def partial_outcomes(args):
    """Where the outcomes so far are kept at each checkpoint, so a resumed run still reports them."""
    return args.outcomes.with_name(args.outcomes.name + '.partial')


def save_partial_outcomes(args):
    if getattr(args, 'outcomes', None) and args.outcomes_log is not None:
        path = partial_outcomes(args)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(args.outcomes_log, ensure_ascii=False) + '\n', encoding='utf-8')
        tmp.replace(path)


def noted_change(entry):
    """The plan really moved: the group is hot again and is checked every pass."""
    entry['streak'] = 0


def take_census(names, sources, state, today, session=None, sleep=time.sleep, delay=(1.0, 2.0)):
    """Run the census of each named faculty whose driver has one and whose last census is CENSUS_HOURS old, its pages
    `delay` seconds apart stretched by the faculty's learned pacing, like any crawl.

    A census reads what lists every group (drivers/wig.py: the Joomla tree a datacenter line cannot reach) and
    keeps it in refresh-state.json under `found`, which refresh_faculty hands back to the driver on any runner. It
    never fails the run: a block or an error leaves the last census in place for the next try.
    """
    store = state.data.setdefault('found', {})
    now = core.now_utc()
    for name in names:
        cfg = sources[name]
        driver = drivers.load(cfg['driver'], name, cfg, today)
        if not hasattr(driver, 'census'):
            continue
        last = store.get(name, {}).get('at', '') if isinstance(store.get(name), dict) else ''
        try:
            if now - dt.datetime.fromisoformat(last) < dt.timedelta(hours=CENSUS_HOURS):
                continue
        except ValueError:
            pass
        try:
            mult = min(3.0, max(1.0, float(state.data.get('pacing', {}).get(core.group_of(name), 1.0))))
            driver.sleep = sleep
            found = driver.census(session or new_session(), pause=(delay[0] * mult, delay[1] * mult))
        except Exception as err:  # Blocked included: this line cannot take it today
            log(f'[{name}] census not taken ({err!r}); keeping the last one')
            continue
        known = {d.strip('/') for d in cfg.get('dirs', [])}
        new = sorted(d for d in found.get('dirs', []) if d.split('/', 1)[0] not in known)
        store[name] = dict(found, at=core.now_utc().isoformat())
        log(f"[{name}] census: {found.get('pdfs', 0)} PDFs in {len(found.get('dirs', []))} directories"
            + (f"; not in sources.json (crawled from now on, add them to dirs): {', '.join(new)}" if new else ''))


def load_driver(name, cfg, state, today):
    # what a census found where this runner may not look (drivers/wig.py): the driver lists it too
    found = state.data.get('found', {}).get(name)
    return drivers.load(cfg['driver'], name, dict(cfg, found=found) if isinstance(found, dict) else cfg, today)


def refresh_faculty(name, cfg, args, state, today, session, sleep=time.sleep, clock=time.monotonic,
                    progress=None, ahead=False):
    """Returns (changed codes, blocked, complete). `today` is a date inside the semester to refresh; with `ahead`
    that is the coming semester, tracked under its own state keys so the running one keeps its dates."""
    return _refresh_faculty(name, cfg, args, state, today, session, sleep, clock, progress, ahead)


def todo_of(name, cfg, args, state, today, items, ahead=False, only=None):
    """What of a faculty's listing is to be checked now: (todo items, stalest first; the codes not ready yet and not
    asked again so soon; the term id). `only` keeps to those codes (a chunk of the work stack)."""
    tid = core.term_id(today)
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
    # A page that still showed another semester is asked again later and later (up to core.NOT_READY_CAP_HOURS),
    # except while the faculties publish: it still counts as not ready.
    real_day = getattr(args, 'today', None) or now.date()
    waiting = set() if args.force else {i.code for i in todo if core.still_not_ready(
        state.groups.get(key(i.code), {}), tid, now, fresh_hours, real_day)}
    todo = [i for i in todo if i.code not in waiting]
    # Stalest first: a run cut short by --max-minutes, --limit or a block refreshes the groups
    # unseen the longest. Never-checked ('') sorts before any ISO timestamp; the code breaks ties
    # so the order is deterministic. The limit slices after the sort, keeping the stalest N.
    # A check the volunteer coordinator accepted counts as a sighting too.
    todo.sort(key=lambda i: (max(state.groups.get(key(i.code), {}).get('checked', '') or '',
                                 accepted_checked(state, i.code, tid)), i.code))
    if getattr(args, 'registry', None):
        # A volunteer checks only its own share of this window (tools/volunteer/assign.py), among the volunteers
        # the coordinator last heard from.
        todo = [i for i in todo if assign.is_assigned(args.registry, args.login, name, i.code, tid, args.window,
                                                      getattr(args, 'health', None))]
    if getattr(args, 'resume_since', None):
        # A resumed run (a volunteer pass cut off mid-window): what it checked before the cut is not asked again,
        # even where the faculty's cadence would already call it stale.
        todo = [i for i in todo if (state.groups.get(key(i.code), {}).get('checked') or '') < args.resume_since]
    if only is not None:
        keep = set(only)
        todo = [i for i in todo if i.code in keep]
        waiting &= keep  # a chunk: the leader counts the rest of the faculty's not-ready groups
    if args.limit:
        todo = todo[:args.limit]
    return todo, waiting, tid


def _refresh_faculty(name, cfg, args, state, today, session, sleep=time.sleep, clock=time.monotonic,
                     progress=None, ahead=False, part=None, only=None, listed=None, settle=True, report_block=None):
    """refresh_faculty's body. A chunk of the work stack (stack.py) passes `only` (its codes), `listed` (the listing
    this runner made), `part` (asked before each group: False skips it, the chunk is no longer this runner's) and
    `settle` (False: a further chunk of a faculty this runner already crawled cleanly this pass, which does not ease
    the learned pacing again). `report_block` replaces the block report to the egress (a crawl through an egress's
    hunt port tells that one)."""
    driver = load_driver(name, cfg, state, today)
    tid = core.term_id(today)
    out = Path(args.out)
    fac = state.faculties.setdefault(name, {})
    group = core.group_of(name)
    host = faculty_host(cfg)

    def block_report():
        if report_block is not None:
            report_block()
        elif host:
            post_block_report(host)
    on_block = block_report if host or report_block is not None else None
    # AIMD pacing: the policy group's multiplier stretches the pause between pages. It grows on
    # every block verdict and decays on every clean faculty, persisting through state.save.
    mult = state.data.get('pacing', {}).get(group, 1.0)

    def pace(blocked):
        pacing = state.data.setdefault('pacing', {})
        pacing[group] = min(3.0, mult * 1.5) if blocked else max(1.0, mult * 0.9)

    try:
        items = listed if listed is not None else discover_with_retry(
            driver, session, args.retries, args.retry_backoff, sleep, block_retries=args.block_retries,
            on_block=on_block)
    except core.Blocked as err:
        log(f'[{name}] BLOCKED while listing groups: {err}')
        fac['blocked_at'] = core.now_utc().isoformat()
        fac['run'] = {'at': fac['blocked_at'], 'checked': 0, 'changed': 0, 'skipped': 0,
                      'not_ready': 0, 'blocked': True, 'ahead': ahead, 'cause': 'wall', 'degraded': False}
        pace(True)
        return [], True, False
    except core.Gone as err:
        if ahead:
            # the coming semester's listing is not up yet: nothing there, which is no failure
            log(f'[{name}] the coming semester is not published yet ({err})')
            return [], False, True
        log(f'[{name}] cannot list groups, the listing page is gone: {err}; the faculty moved its timetable?')
        fac['run'] = {'at': core.now_utc().isoformat(), 'term': tid, 'checked': 0, 'changed': 0,
                      'skipped': 0, 'not_ready': 0, 'blocked': False, 'ahead': ahead,
                      'cause': 'listing', 'degraded': True}
        return [], False, False
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
    todo, waiting, tid = todo_of(name, cfg, args, state, today, items, ahead, only)
    key = (lambda code: f'{code}@{tid}') if ahead else (lambda code: code)
    log(f'[{name}] {len(items)} groups, {len(items) - len(todo) - len(waiting)} fresh, '
        + (f'{len(waiting)} not ready yet (not asked again so soon), ' if waiting else '')
        + f'{len(todo)} to check (term {tid})' + (f'; a chunk of {len(only)}' if only is not None else ''))
    slot = name if not ahead else f'{name}~{tid}'
    if progress is not None:
        progress.send('faculty_start', slot=slot, faculty=name, lane=group, total=len(todo),
                      fresh=len(items) - len(todo), listed=len(items), ahead=ahead, term=tid)
    started, changed, failed, checked = clock(), [], 0, 0
    not_ready = len(waiting)
    # --max-minutes is the whole run's (main sets the deadline once); a faculty refreshed on its own gets all of it.
    deadline = getattr(args, 'deadline', None)
    if deadline is None and args.max_minutes:
        deadline = started + args.max_minutes * 60
    for n, item in enumerate(todo, 1):
        if progress is not None:
            progress.tick(slot, n - 1, len(todo), faculty=name, lane=group, ahead=ahead, term=tid)
        if deadline is not None and clock() > deadline:
            log(f'[{name}] time budget used up after {n - 1} groups')
            return changed, False, False
        if part is not None and not part(item.code):
            continue  # the chunk is no longer this runner's, or time is up
        if n > 1:
            sleep(random.uniform(args.delay[0] * mult, args.delay[1] * mult))
        if n % 25 == 0 and not args.dry_run:
            state.save()  # checkpoint every 25 checks, however they end (a 304 or an unchanged hash included)
            save_partial_outcomes(args)  # and what they found, which a resumed run still has to report
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
                # Exhausted 429/5xx/empty 200s are a block response too: report the exit that
                # carried them and ride a fresh connection before calling it a wall.
                block_report()
                if attempt < attempts:
                    log(f'[{name}] {item.code}: block response ({err}); '
                        f'riding a fresh connection ({attempt + 1}/{attempts})')
                    sleep(random.uniform(2.0, 4.0) * attempt)
                    continue
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
            block_report()
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
            entry.pop('not_ready', None)
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
                noted_not_ready(entry, tid)
                log(f'[{name}] {item.code}: not ready for {tid} yet (the faculty still shows '
                    f'another semester); keeping the old calendar')
                note_outcome(args, item.code, tid, 'not_ready')
                continue
            log(f'[{name}] {item.code}: not a timetable page, skipped')
            failed += 1
            continue
        remember_validators(entry, r)
        entry.pop('not_ready', None)  # the page reads as a timetable of this semester
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
        except core.NotReady as err:  # a PDF of another semester: what not_ready(text) tells for HTML pages
            not_ready += 1
            noted_not_ready(entry, tid)
            log(f'[{name}] {item.code}: not ready for {tid} yet ({err}); keeping the old calendar')
            note_outcome(args, item.code, tid, 'not_ready')
            continue
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
        if not ok and previous is not None and core.validate(ics, item.code, tid)[0]:
            # Only the shrink guard says no. A half-broken page shrinks once; a faculty that really cut the plan shows the
            # same smaller one pass after pass, and keeping the old one would leave classes on the site that are gone.
            if steady_shrink(entry, ics):
                log(f'[{name}] {item.code}: {why}, the same plan in {SHRINK_PASSES}+ passes over '
                    f'{SHRINK_HOURS} h+; accepted')
                ok = True
            else:
                why += f', seen {entry["shrink"]["seen"]} of {SHRINK_PASSES} times'
        if not ok:
            log(f'[{name}] {item.code}: rejected ({why}), keeping the old calendar')
            failed += 1
            continue
        entry.pop('shrink', None)
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
    if settle:
        pace(False)
    if not ahead:
        fac['last_ok'] = core.now_utc().isoformat()
        fac['blocked_at'] = None
        fac.pop('wall', None)  # the wall this runner met here is down (run_lane: chronic walls)
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
    ap.add_argument('--max-minutes', type=float, default=0,
                    help='stop the whole run gracefully after this long, waits included (0 = no limit)')
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
    ap.add_argument('--faculty-state', type=Path,
                    help="keep this line's learned pacing and block durations here instead of in the data checkout")
    ap.add_argument('--resume-since', default='',
                    help='skip every group checked at or after this UTC time (YYYY-MM-DDTHH:MM:SS): resuming a run')
    ap.add_argument('--census', default='',
                    help='comma-separated faculties whose driver takes a census of the site after the crawl (at most '
                         f'once in {CENSUS_HOURS} h; fleet.json names the runner that can)')
    ap.add_argument('--board', default='',
                    help='<planned>-<run id>: the pass\'s work stack (stack.py, on git refs), which the runners of the '
                         'pass pull their work from; needs --runner and a checkout of this repository in --out')
    ap.add_argument('--expected', default='',
                    help='comma-separated runners the plan started for this pass (the others are not waited for)')
    ap.add_argument('--fallback', default='',
                    help='comma-separated faculties this runner crawls alone when the work stack cannot be reached')
    ap.add_argument('--runner', default='', help="this runner's name in the fleet (fleet.json)")
    ap.add_argument('--fleet', default=str(fleet.FLEET), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    args.registry, args.window, args.health, args.deadline = None, None, None, None
    args.outcomes_log = {} if (args.outcomes or args.assign) else None
    if args.resume_since and args.outcomes and args.outcomes_log is not None:
        # The groups the resumed run skips were checked before the cut: their outcomes come from its checkpoint.
        try:
            kept = json.loads(partial_outcomes(args).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            kept = {}
        args.outcomes_log.update({k: v for k, v in (kept if isinstance(kept, dict) else {}).items()
                                  if isinstance(v, dict) and str(v.get('at') or '') >= args.resume_since})
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
            cause = state.faculties.get(name, {}).get('run', {}).get('cause')
            model.note_blocked(name, cause)
            note_wall(state, name, cause, args.runner)
            deferred.append((name, False))
            continue
        if coming and refresh_ahead(name, sources, args, state, today, session, coming,
                                    tallies, sleep, clock, progress=progress):
            cause = state.faculties.get(name, {}).get('run', {}).get('cause')
            model.note_blocked(name, cause)
            note_wall(state, name, cause, args.runner)
            deferred.append((name, True))
    if wait_budget is None:
        wait_budget = args.max_block_wait_minutes * 60
    if getattr(args, 'deadline', None) is not None:
        # A wait that outlasts the run's time budget would only be cut off by the job's timeout, with nothing pushed.
        wait_budget = min(wait_budget, args.deadline - clock())
    if not deferred or wait_budget <= 0:
        return tallies
    if all(chronic(state, n, args.runner) for n, _ in deferred):
        # Every wall here already outlasted a full wait: another one would only keep the pass from ending.
        for n, _ in deferred:
            wall = state.faculties[n]['wall']
            log(f"[{n}] walled here since {wall['since'][:16].replace('T', ' ')} ({wall['failed']} "
                f"{'wait' if wall['failed'] == 1 else 'waits'} in vain); not waiting this pass")
            state.faculties[n]['wait'] = {'waited': 0, 'probes': 0, 'recovered': False, 'chronic': True}
        return tallies
    # probe through a wall that may still drop, not through one already waited out in vain
    first = next(n for n, _ in deferred if not chronic(state, n, args.runner))
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
        wait_slots = [f'{n}~{core.term_id(coming)}' if (main_ok and coming) else n
                      for n, main_ok in deferred]
        progress.send('wait_start', id=group, lane=group, faculties=[n for n, _ in deferred],
                      slots=wait_slots, budget=round(wait_budget))
    recovered, waited, probes = wait_for_recovery(group, probe, model, wait_budget, args.block_probes, sleep, clock)
    if not recovered and waited >= CHRONIC_MIN_WAIT:
        for n, _ in deferred:
            wall = state.faculties.get(n, {}).get('wall')
            if isinstance(wall, dict) and isinstance(wall.get('failed'), int):
                wall['failed'] += 1
    if progress is not None:
        progress.send('wait_end', id=group, lane=group, faculties=[n for n, _ in deferred],
                      slots=wait_slots, waited=round(waited), probes=probes,
                      recovered=recovered)
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
                cause = state.faculties.get(name, {}).get('run', {}).get('cause')
                model.note_blocked(name, cause)
                note_wall(state, name, cause, args.runner)
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
    partial_outcomes(args).unlink(missing_ok=True)


class FleetOps(stack.Ops):
    """What a fleet runner does on the sites for the work stack (stack.py): list a faculty, cut its work, crawl a chunk,
    wait a wall out. One session per slot, so a faculty's chunks ride the cookies its listing got."""

    def __init__(self, sources, args, state, model, today, coming, sleep, clock, progress, hunter=None):
        self.sources, self.args, self.state, self.model = sources, args, state, model
        self.today, self.coming, self.sleep, self.clock, self.progress = today, coming, sleep, clock, progress
        self.lock = threading.Lock()
        self.sessions, self.settled, self.listed = {}, set(), set()
        self.changed = []
        self.egress = hunter  # egress.Egress that hunts for exits through a wall, or None
        self.routes = {}  # slot -> 'pool': reached through the exits the hunt found (its hunt port)

    def pooled(self, slot):
        with self.lock:
            return self.routes.get(slot) == 'pool' and self.egress is not None

    def reporter(self, slot, host):
        """What tells an egress that a page of `slot` came back as a block page."""
        if self.pooled(slot):
            return lambda: self.egress.report_block(host)
        return (lambda: post_block_report(host)) if host else None

    def day(self, slot):
        """(a date in the slot's semester, whether it is the coming one)."""
        term = stack.term_of(slot)
        if not term:
            return self.today, False
        if self.coming is not None and term == core.term_id(self.coming):
            return self.coming, True
        raise ValueError(f'{slot}: not a semester this pass refreshes')

    def session(self, slot):
        pooled = self.pooled(slot)
        with self.lock:
            if slot not in self.sessions:
                self.sessions[slot] = new_session(self.egress.proxy_url() if pooled else None)
            return self.sessions[slot]

    def walled(self, name, ahead, cause='wall'):
        """A wall met while listing: recorded as _refresh_faculty records one, for this runner's line."""
        state, fac = self.state, self.state.faculties.setdefault(name, {})
        now = core.now_utc().isoformat()
        fac['blocked_at'] = fac['walled_at'] = now
        fac['run'] = {'at': now, 'checked': 0, 'changed': 0, 'skipped': 0, 'not_ready': 0, 'blocked': True,
                      'ahead': ahead, 'cause': cause, 'degraded': False}
        group = core.group_of(name)
        pacing = state.data.setdefault('pacing', {})
        pacing[group] = min(3.0, float(pacing.get(group, 1.0)) * 1.5)
        self.model.note_blocked(name, cause)
        note_wall(state, name, cause, self.args.runner)

    def probe(self, slot):
        name = stack.faculty_of(slot)
        day, ahead = self.day(slot)
        cfg = self.sources[name]
        host = faculty_host(cfg)
        driver = load_driver(name, cfg, self.state, day)
        try:
            items = discover_with_retry(driver, self.session(slot), self.args.retries, self.args.retry_backoff,
                                        self.sleep, block_retries=self.args.block_retries,
                                        on_block=self.reporter(slot, host))
        except core.Blocked as err:
            pooled = self.pooled(slot)
            log(f'[{name}] BLOCKED while listing groups{" through the pool exits" if pooled else ""}: {err}')
            with self.lock:
                self.sessions.pop(slot, None)
            if not pooled:
                self.walled(name, ahead)  # a wall in front of this runner's own address, not the exits'
            raise stack.Walled(str(err)) from err
        except core.Gone as err:
            if ahead:
                log(f'[{name}] the coming semester is not published yet ({err})')
                return []
            log(f'[{name}] cannot list groups, the listing page is gone: {err}; the faculty moved its timetable?')
            raise stack.Unlisted(str(err)) from err
        with self.lock:
            self.listed.add(slot)
        return items

    def todo(self, slot, items):
        name = stack.faculty_of(slot)
        day, ahead = self.day(slot)
        cfg = self.sources[name]
        if not items:
            if ahead:
                return [], {'listed': 0, 'note': 'empty'}
            log(f'[{name}] no groups listed; leaving the faculty untouched')
            return [], {'listed': 0, 'note': 'nothing listed'}
        todo, waiting, tid = todo_of(name, cfg, self.args, self.state, day, items, ahead)
        if not todo:
            # nothing to check: the faculty's usual pass over a listing it already has, records and all
            _refresh_faculty(name, cfg, self.args, self.state, day, self.session(slot), self.sleep, self.clock,
                             self.progress, ahead, listed=items)
            return [], {'listed': len(items), 'fresh': len(items) - len(waiting), 'not_ready': len(waiting)}
        # the record the chunks add up to (refresh-state.json's `run`): the not-ready groups are counted once, here
        self.state.faculties.setdefault(name, {})['run'] = {
            'at': core.now_utc().isoformat(), 'term': tid, 'checked': 0, 'changed': 0, 'skipped': 0,
            'not_ready': len(waiting), 'blocked': False, 'ahead': ahead, 'cause': None, 'degraded': False}
        log(f'[{name}] {len(items)} groups, {len(items) - len(todo) - len(waiting)} fresh, '
            + (f'{len(waiting)} not ready yet (not asked again so soon), ' if waiting else '')
            + f'{len(todo)} to check (term {tid})')
        return [i.code for i in todo], {'listed': len(items), 'fresh': len(items) - len(todo) - len(waiting),
                                        'not_ready': len(waiting)}

    def crawl(self, slot, codes, items, check, tick):
        name = stack.faculty_of(slot)
        day, ahead = self.day(slot)
        cfg = self.sources[name]
        fac = self.state.faculties.setdefault(name, {})
        before = fac.get('run')
        taken, refused = [], [False]

        def part(code):
            if refused[0] or not check():
                refused[0] = True
                return False
            taken.append(code)
            tick()
            return True
        with self.lock:
            settle = slot not in self.settled
        pooled = self.pooled(slot)
        done, blocked, complete = _refresh_faculty(name, cfg, self.args, self.state, day, self.session(slot),
                                                   self.sleep, self.clock, self.progress, ahead, part=part,
                                                   only=codes, listed=items, settle=settle,
                                                   report_block=self.reporter(slot, faculty_host(cfg)))
        run = fac.get('run')
        since = getattr(self.args, 'started', None)
        if (isinstance(before, dict) and isinstance(run, dict) and since and str(before.get('at') or '') >= since
                and before.get('term') == run.get('term') and before.get('ahead') == run.get('ahead')):
            # this pass's record of the faculty counts every chunk this runner crawled of it
            for k in ('checked', 'changed', 'skipped', 'not_ready'):
                run[k] = int(before.get(k) or 0) + int(run.get(k) or 0)
            run['degraded'] = bool(before.get('degraded') or run.get('degraded'))
        with self.lock:
            self.changed.extend(done)
        if blocked:
            cause = (run or {}).get('cause') or 'wall'
            if not pooled:  # the exits' wall says nothing of this runner's own line
                self.model.note_blocked(name, cause)
                note_wall(self.state, name, cause, self.args.runner)
            with self.lock:
                self.sessions.pop(slot, None)  # a fresh jar next time: the old one may be the blocked one
            return {'done': taken[:-1], 'blocked': True, 'changed': done}
        if refused[0] or not complete:
            late = self.args.deadline is not None and self.clock() > self.args.deadline
            if not refused[0] and not late:
                raise RuntimeError(f'{name}: the crawl stopped short of its chunk')
            return {'done': list(taken), 'blocked': False, 'changed': done}
        with self.lock:
            self.settled.add(slot)
        return {'done': list(codes), 'blocked': False, 'changed': done}

    def wait(self, slot, stop):
        name = stack.faculty_of(slot)
        day, ahead = self.day(slot)
        args = self.args
        budget = args.max_block_wait_minutes * 60
        if args.deadline is not None:
            budget = min(budget, args.deadline - self.clock())
        if budget <= 0:
            return False
        driver = load_driver(name, self.sources[name], self.state, day)
        probe_session = new_session()  # probe with a clean jar, like a new visitor

        def probe():
            try:
                driver.discover(probe_session)
                return True
            except Exception:
                return False
        recovered, waited, probes = wait_for_recovery(core.group_of(name), probe, self.model, budget,
                                                       args.block_probes, self.sleep, self.clock, stop)
        fac = self.state.faculties.setdefault(name, {})
        if not recovered and waited >= CHRONIC_MIN_WAIT and not stop():
            wall = fac.get('wall')
            if isinstance(wall, dict) and isinstance(wall.get('failed'), int):
                wall['failed'] += 1
        fac['wait'] = {'waited': round(waited), 'probes': probes, 'recovered': recovered}
        if recovered:
            fac['blocked_at'] = None
            with self.lock:
                self.sessions.pop(slot, None)
        return recovered


    def hunt(self, slot, exits):
        """Exits through the faculty's wall, from this runner's egress (egress.py): from then on the slot's pages
        ride them. Raises when there is no egress that can hunt."""
        if self.egress is None:
            raise egress_client.Unavailable('this runner has no egress')
        host = faculty_host(self.sources[stack.faculty_of(slot)])
        if not host:
            return []
        found = self.egress.hunt(host, exits)
        if found:
            with self.lock:
                self.routes[slot] = 'pool'
                self.sessions.pop(slot, None)  # a fresh jar, through the hunt port
        return found


def fleet_runner(args, wanted, sources, state, model, today, coming, sleep, clock, progress, store=None):
    """This runner's part of the pass on the work stack (stack.py): (Runner, FleetOps), or None when the runners of
    this pass do not share one (no store, a volunteer, a dry run)."""
    if not args.runner or args.dry_run or args.registry or (store is None and not args.board):
        return None
    try:
        runners = {r['name']: r for r in fleet.load_fleet(args.fleet)}
    except (OSError, ValueError) as err:
        log(f'stack: no fleet ({err}); crawling alone')
        return None
    me = runners.get(args.runner)
    if me is None:
        log(f'stack: {args.runner} is not in the fleet; crawling alone')
        return None
    if store is None:
        try:
            store = boards.GitStore(args.out, re.sub(r'/w\d+$', '', args.board))
        except ValueError as err:
            log(f'stack: {err}; crawling alone')
            return None
    term = core.term_id(coming) if coming else None
    slots = []
    reach = fleet.reach(me)
    for name in wanted:
        if name in sources and (reach is None or name in reach):  # `wanted` is already the enabled ones, or named
            slots.append(name)
            if term:
                slots.append(f'{name}~{term}')
    expected = [n for n in args.expected.split(',') if n in runners] or [args.runner]
    line = state.data
    shy = {f for f in wanted if isinstance(state.faculties.get(f, {}).get('cant'), dict)
           and build_count(state.faculties[f]['cant'].get('passes')) >= stack.SHY_PASSES}
    hunter = egress_client.make(me.get('egress'), log)
    if hunter is not None:
        hunter.ensure_async()  # a persistent local egress comes up (or is reused) while the crawl starts
    me_ = stack.Me(args.runner, slots, {s: core.group_of(stack.faculty_of(s)) for s in slots}, expected,
                   me['prefers'], {n: fleet.reach(r) for n, r in runners.items()},
                   {n: r['prefers'] for n, r in runners.items()},
                   {s: fleet.faculty_cost(line, stack.faculty_of(s)) for s in slots},
                   {f for f in wanted if chronic(state, f, args.runner)}, shy,
                   pool=me.get('pool') or (), pool_help=me.get('pool_help') or (), hunter=hunter is not None,
                   pool_of={n: set(r.get('pool') or ()) for n, r in runners.items()})
    ops = FleetOps(sources, args, state, model, today, coming, sleep, clock, progress, hunter)
    runner = stack.Runner(store, me_, ops, lanes=args.lanes, deadline=args.deadline, clock=clock, sleep=sleep, log=log)
    return runner, ops


def build_count(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def note_cant(state, report, ops):
    """Across passes: how many passes in a row this runner could not list a faculty (fac['cant'], its line's own).
    After stack.SHY_PASSES it turns there last; one listing that works forgets it."""
    now = core.now_utc().isoformat()
    for slot, cause in report['cant'].items():
        if stack.term_of(slot):
            continue
        fac = state.faculties.setdefault(stack.faculty_of(slot), {})
        prior = fac.get('cant') if isinstance(fac.get('cant'), dict) else {}
        fac['cant'] = {'since': prior.get('since') or now, 'passes': build_count(prior.get('passes')) + 1,
                       'cause': cause}
    for slot in ops.listed:
        if not stack.term_of(slot) and slot not in report['cant']:
            state.faculties.get(stack.faculty_of(slot), {}).pop('cant', None)


def main(argv=None, session=None, today=None, sleep=time.sleep, clock=time.monotonic, store=None):
    args = parse(argv)
    today = today or core.now_utc().date()
    started = core.now_utc().isoformat()
    args.started = started
    args.today = today
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
        args.health = assign.load_health(Path(args.out) / core.VOLUNTEER_STATE_FILE)
        log(f'volunteer {me["login"]} ({me["trust"]}), window {args.window}: {", ".join(wanted) or "nothing"}')
    unknown = [f for f in wanted if f not in sources]
    if unknown:
        log(f'unknown faculty: {", ".join(unknown)}')
        return 2
    state = core.State(Path(args.out) / core.STATE_FILE)
    if args.faculty_state:
        load_line_state(state, args.faculty_state)
    # One time budget for the whole run, however many faculties and walls it meets: past it, every lane stops after
    # its current page, so the run still saves and pushes inside the job's timeout.
    args.deadline = clock() + args.max_minutes * 60 if args.max_minutes else None
    model = core.BlockModel(state.data)
    coming = core.upcoming_reference(today)
    progress = Progress(run=started, clock=clock)
    lanes = plan_lanes(wanted)
    found = fleet_runner(args, wanted, sources, state, model, today, coming, sleep, clock, progress, store)
    report = ops = None
    if found is not None:
        runner, ops = found
        try:
            runner.start()
        except stack.StoreUnavailable as err:
            # The store is out of reach: the static share the plan made for this case, crawled the old way.
            wanted = [f for f in args.fallback.split(',') if f in sources]
            lanes = plan_lanes(wanted)
            log(f'stack: the work stack cannot be reached ({err}); crawling the fallback share alone: '
                f'{", ".join(wanted) or "nothing"}')
        else:
            if progress.url:
                progress.send('run_start', profile=args.profile, parallel=True,
                              lanes=[{'lane': core.group_of(ns[0]), 'faculties': list(ns)} for ns in lanes])
            try:
                report = runner.run()
            finally:
                if ops.egress is not None:
                    ops.egress.close()  # a local egress started for a hunt goes with the crawl
            forget = getattr(runner.store, 'forget', None)
            if forget is not None:
                forget()  # the copies of the store's docs this checkout fetched: the pass is over
    tallies = {'changed': [], 'blocked': False, 'incomplete': set()}
    if report is None:
        parallel = bool(args.lanes > 1 and len(lanes) > 1 and session is None)
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
            with ThreadPoolExecutor(max_workers=min(args.lanes, len(lanes))) as ex:
                results = list(ex.map(lane, lanes))
        else:
            # One after another the waits add up, so they share the budget: each wait is capped to its fair share
            # of what is left (but always gets a real chance: at least 15 minutes).
            results, left = [], args.max_block_wait_minutes * 60
            for pos, names in enumerate(lanes):
                res = lane(names, min(left, max(900.0, left / (len(lanes) - pos))) if left > 0 else 0)
                left -= res['waited']
                results.append(res)
        for res in results:
            tallies['changed'] += res['changed']
            tallies['blocked'] |= res['blocked']
            tallies['incomplete'] |= res['incomplete']
    else:
        tallies['changed'] = list(ops.changed)
        note_cant(state, report, ops)
    # The census comes last: the WAT sites behind Incapsula share one wall per address, and on 2026-10-27 plebania met
    # it on WLO, WEL, WML and WTC four seconds after a census. After the crawl it can cost the census at most, and a
    # pass that met a wall leaves it to a later one rather than lean on that wall.
    census = [f for f in args.census.split(',') if f in sources and sources[f].get('enabled')]
    walled = sorted(n for n in sources
                    if state.faculties.get(n, {}).get('run', {}).get('cause') == 'wall'
                    and str(state.faculties[n]['run'].get('at') or '') >= started)
    if census and not args.dry_run:
        if walled:
            log(f'census left for a later pass: this one met a wall ({", ".join(walled)})')
        elif args.deadline is not None and clock() > args.deadline:
            log('census left for a later pass: the time budget is used up')
        else:
            take_census(census, sources, state, today, session, sleep, args.delay)
    if report is not None:
        outcome = stack_outcome(report, state, sources, started)
    else:
        outcome = solo_outcome(wanted, tallies, state, sources, started)
    if outcome['degraded']:
        log('DEGRADED: one or more faculties checked out degraded (skips or a shrunken listing); '
            'forcing incomplete so the run gets attention')
    if not args.dry_run:
        state.save()
    if args.faculty_state:
        save_line_state(state, args.faculty_state)
    exit_code = 3 if outcome['blocked'] else 4 if outcome['incomplete'] else 0
    if args.outcomes:
        write_outcomes(args, started, wanted, sources, state)
    export(blocked=outcome['blocked'], incomplete=outcome['incomplete'], changed=len(tallies['changed']),
           degraded=outcome['degraded'], blocked_faculties=','.join(outcome['blocked_faculties']),
           incomplete_faculties=','.join(outcome['incomplete_faculties']),
           done_faculties=','.join(outcome['done_faculties']),
           took_faculties=','.join(outcome['took']), gave_faculties=','.join(outcome['gave']),
           led_faculties=','.join(outcome['led']), cant_faculties=','.join(outcome['cant']),
           pool_faculties=','.join(outcome.get('pool', [])),
           owned_faculties=','.join(outcome['owned']), owned_known=True)
    log(f'changed: {len(tallies["changed"])}; blocked: {outcome["blocked"]}; incomplete: {outcome["incomplete"]}')
    if progress.url:
        progress.send('run_done', exit=exit_code, blocked=outcome['blocked'], incomplete=outcome['incomplete'],
                      degraded=outcome['degraded'], changed=len(tallies['changed']))
    post_run_report({'started': started, 'ended': core.now_utc().isoformat(), 'exit': exit_code,
                     'profile': args.profile, 'dry_run': args.dry_run,
                     'faculties': {n: {**(state.faculties.get(n, {}).get('run', {})),
                                       **({'wait': state.faculties[n]['wait']}
                                          if 'wait' in state.faculties.get(n, {}) else {})}
                                   for n in wanted if n in sources}})
    return exit_code


def _fresh_degraded(state, names, started):
    return any(state.faculties.get(n, {}).get('run', {}).get('degraded')
               and str(state.faculties[n]['run'].get('at') or '') >= started for n in names)


def solo_outcome(wanted, tallies, state, sources, started):
    """A runner that crawled its faculties alone (no work stack): per faculty, for the fleet's report."""
    own = [n for n in wanted if n in sources]
    ran = {n: state.faculties.get(n, {}).get('run', {}) for n in own}
    this_pass = {n for n, r in ran.items() if str(r.get('at') or '') >= started}
    blocked = [n for n in own if n in this_pass and ran[n].get('blocked')]
    unfinished = [n for n in own if n in tallies['incomplete'] or n not in this_pass or n in blocked]
    degraded = any(ran[n].get('degraded') for n in own)
    return {'blocked': bool(tallies['blocked']), 'incomplete': bool(tallies['incomplete']) or degraded,
            'degraded': degraded, 'blocked_faculties': blocked, 'incomplete_faculties': unfinished,
            'done_faculties': [n for n in own if n not in unfinished], 'took': [], 'gave': [], 'led': own,
            'cant': [], 'owned': own}


def stack_outcome(report, state, sources, started):
    """A stack runner's outcome, per faculty, from its last reading of the store (stack.slot_status): the report job
    reads the store itself and only falls back on these when it cannot."""
    rank = {'blocked': 0, 'unfinished': 1, 'absent': 1, 'failed': 2, 'done': 3, 'empty': 3}
    worst = {}
    for slot, status in report['verdicts'].items():
        f = stack.faculty_of(slot)
        if f not in worst or rank.get(status, 1) < rank.get(worst[f], 1):
            worst[f] = status
    blocked = [f for f, v in worst.items() if v == 'blocked']
    unfinished = [f for f, v in worst.items() if v in ('blocked', 'unfinished', 'absent', 'failed')]
    led = list(dict.fromkeys(stack.faculty_of(s) for s in report['led']))
    owned = [stack.faculty_of(s) for s in report['led'] if not stack.term_of(s)]
    helped = list(dict.fromkeys(stack.faculty_of(s) for s in report['helped']))
    degraded = (any(v == 'failed' for v in worst.values())
                or _fresh_degraded(state, [f for f in dict.fromkeys(owned + helped) if f in sources], started))
    return {'blocked': bool(blocked), 'incomplete': bool(unfinished) or degraded, 'degraded': degraded,
            'blocked_faculties': blocked, 'incomplete_faculties': unfinished,
            'done_faculties': [f for f, v in worst.items() if v in ('done', 'empty')],
            'took': list(dict.fromkeys(f'{stack.faculty_of(s)}:{leader}' for s, leader in report['helped'].items()
                                       if leader)),
            'gave': list(dict.fromkeys(f'{stack.faculty_of(s)}:{h}' for s, hs in report['gave'].items() for h in hs)),
            'led': led, 'cant': list(dict.fromkeys(f'{stack.faculty_of(s)}:{c}' for s, c in report['cant'].items())),
            'owned': owned, 'pool': list(dict.fromkeys(stack.faculty_of(s) for s in report.get('pool', ())))}


if __name__ == '__main__':
    sys.exit(main())
