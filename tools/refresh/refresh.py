#!/usr/bin/env python3
"""Refresh the timetables from the faculty sites.

    python tools/refresh/refresh.py --out <data checkout> [--faculty wlo,wel] [--profile hosted|selfhosted]
                                    [--limit N] [--dry-run] [--max-minutes M] [--fresh-hours H]

For every enabled faculty it lists the groups, fetches each page politely (one session, sequential, jittered,
conditional revalidation so unchanged pages answer 304), converts pages that changed, validates the calendar the
way the site's build does, and writes <out>/timetables/<term>/<GROUP>.ics only when the plan really changed.
Progress lives in <out>/refresh-state.json, so a stopped run resumes where it stopped.

A block (any status but 200/304/404, an Incapsula incident page) no longer ends the run: that faculty is
deferred while the others are covered, then the run sleeps out the block and resumes. How long to sleep is
learned per policy group from past recoveries (median, 20 min .. 12 h, 2 h without history; wall-caused
episodes count more than flaky ones), recovery is probed with cheap index fetches on a sparse-then-dense
schedule (--block-probes), and the whole wait is capped (--max-block-wait-minutes). A block verdict is never
retried, nothing half-converted is published, the old calendars stay. A merely transient fetch (transport
error, 408/425/429/500/502/503/504, an empty 200) is retried a few times with exponential backoff first
(--retries/--retry-backoff); exhaustion raises core.Blocked for HTTP transients (a wall) and the transport
error itself for flakiness, so the run learns the cause.
Exit codes: 0 done, 3 blocked, 4 incomplete.
With GITHUB_OUTPUT set, `blocked`, `incomplete` and `changed` are exported for the workflow.
"""
import argparse
import datetime as dt
import json
import os
import random
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core  # noqa: E402
import drivers  # noqa: E402

PROFILES = {'hosted': (4.0, 9.0), 'selfhosted': (2.5, 6.0)}  # seconds between pages
# WLO and WEL share one Incapsula policy (cookies for .wat.edu.pl): crawling either too fast blocks both home
# addresses for hours. The self-hosted range above stays unblocked; the hosted range is for datacenter egress,
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
    the inner network, not through the proxy itself.
    """
    import urllib.request
    url = url or os.environ.get('PLANWAT_EGRESS_STATUS', 'http://egress:8080/api/run')
    if not url:
        return
    try:
        req = urllib.request.Request(url, data=json.dumps(report).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'}, method='POST')
        urllib.request.build_opener().open(req, timeout=timeout).read()
    except Exception as err:
        log(f'run report not delivered ({err}); continuing')


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


def discover_with_retry(driver, session, retries=2, backoff=2.0, sleep=time.sleep):
    """List the groups, riding out flaky transports (a dead pool proxy, a reset).

    A Blocked verdict (wall content, unexpected status) is re-raised at once, never
    retried: only the transport may be flaky. Raises the last error when exhausted.
    """
    last = None
    for attempt in range(retries + 1):
        try:
            return driver.discover(session)
        except core.Blocked:
            raise
        except Exception as err:
            last = err
        if attempt < retries:
            sleep(backoff * (2 ** attempt) + random.uniform(0, 1))
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


def refresh_faculty(name, cfg, args, state, today, session, sleep=time.sleep, clock=time.monotonic, ahead=False):
    """Returns (changed codes, blocked, complete). `today` is a date inside the semester to refresh; with `ahead`
    that is the coming semester, tracked under its own state keys so the running one keeps its dates."""
    driver = drivers.load(cfg['driver'], name, cfg, today)
    tid = core.term_id(today)
    out = Path(args.out)
    fac = state.faculties.setdefault(name, {})
    group = core.group_of(name)
    # AIMD pacing: the policy group's multiplier stretches the pause between pages. It grows on
    # every block verdict and decays on every clean faculty, persisting through state.save.
    mult = state.data.get('pacing', {}).get(group, 1.0)

    def pace(blocked):
        pacing = state.data.setdefault('pacing', {})
        pacing[group] = min(3.0, mult * 1.5) if blocked else max(1.0, mult * 0.9)

    try:
        items = discover_with_retry(driver, session, args.retries, args.retry_backoff, sleep)
    except core.Blocked as err:
        log(f'[{name}] BLOCKED while listing groups: {err}')
        fac['blocked_at'] = core.now_utc().isoformat()
        fac['run'] = {'at': fac['blocked_at'], 'checked': 0, 'changed': 0,
                      'skipped': 0, 'blocked': True, 'ahead': ahead, 'cause': 'wall', 'degraded': False}
        pace(True)
        return [], True, False
    except Exception as err:
        log(f'[{name}] cannot list groups: {err}')
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
            fac['run'] = {'at': core.now_utc().isoformat(), 'term': tid, 'checked': 0,
                          'changed': 0, 'skipped': 0, 'blocked': False, 'ahead': ahead,
                          'cause': None, 'degraded': True}
        return [], False, False
    if not robots_allows(session, items[0].url, state):
        log(f'[{name}] robots.txt disallows the timetable pages; skipping the faculty')
        return [], False, False
    now = core.now_utc()
    key = (lambda code: f'{code}@{tid}') if ahead else (lambda code: code)
    # Twice the cadence while the faculties publish the coming semester; a per-faculty
    # override wins over the default but never drops below one hour.
    fresh_hours = core.effective_fresh_hours(max(1, cfg.get('fresh_hours', args.fresh_hours)), today)
    todo = [i for i in items if args.force or not state.fresh(key(i.code), now, fresh_hours, tid)]
    # Stalest first: a run cut short by --max-minutes, --limit or a block refreshes the groups
    # unseen the longest. Never-checked ('') sorts before any ISO timestamp; the code breaks ties
    # so the order is deterministic. The limit slices after the sort, keeping the stalest N.
    todo.sort(key=lambda i: (state.groups.get(key(i.code), {}).get('checked', ''), i.code))
    if args.limit:
        todo = todo[:args.limit]
    log(f'[{name}] {len(items)} groups, {len(items) - len(todo)} fresh, {len(todo)} to check (term {tid})')
    started, changed, failed, checked = clock(), [], 0, 0
    for n, item in enumerate(todo, 1):
        if args.max_minutes and (clock() - started) / 60 > args.max_minutes:
            log(f'[{name}] time budget used up after {n - 1} groups')
            return changed, False, False
        if n > 1:
            sleep(random.uniform(args.delay[0] * mult, args.delay[1] * mult))
        if n % 25 == 0 and not args.dry_run:
            state.save()  # checkpoint every 25 checks, however they end (a 304 or an unchanged hash included)
        entry = state.groups.setdefault(key(item.code), {})
        try:
            r = get_with_retry(session, item.url, timeout=60, headers=conditional_headers(entry),
                               retries=args.retries, backoff=args.retry_backoff, sleep=sleep)
            checked += 1
        except core.Blocked as err:
            log(f'[{name}] BLOCKED on {item.code}: {err}')
            fac['blocked_at'] = core.now_utc().isoformat()
            fac['run'] = {'at': fac['blocked_at'], 'term': tid, 'checked': checked,
                          'changed': len(changed), 'skipped': failed, 'blocked': True, 'ahead': ahead,
                          'cause': 'wall', 'degraded': degraded}
            pace(True)
            return changed, True, False
        except Exception as err:
            log(f'[{name}] flaky fetch on {item.code}, {checked} responses in: {err}')
            fac['blocked_at'] = core.now_utc().isoformat()
            fac['run'] = {'at': fac['blocked_at'], 'term': tid, 'checked': checked,
                          'changed': len(changed), 'skipped': failed, 'blocked': True, 'ahead': ahead,
                          'cause': 'flaky', 'degraded': degraded}
            pace(True)
            return changed, True, False
        if r.status_code == 304:
            # The server says the page is byte-identical: no download, no conversion, just a fresh check mark.
            remember_validators(entry, r)
            entry['checked'] = core.now_utc().isoformat()
            continue
        raw = r.content
        text = raw.decode('utf-8', errors='replace')
        if r.status_code == 404:
            log(f'[{name}] {item.code}: gone (404), keeping the old calendar')
            continue
        if core.is_blocked(r.status_code, text):
            log(f'[{name}] BLOCKED on {item.code} (HTTP {r.status_code}) after {n - 1} pages')
            fac['blocked_at'] = core.now_utc().isoformat()
            fac['run'] = {'at': fac['blocked_at'], 'term': tid, 'checked': checked,
                          'changed': len(changed), 'skipped': failed, 'blocked': True, 'ahead': ahead,
                          'cause': 'wall', 'degraded': degraded}
            pace(True)
            return changed, True, False
        if not driver.page_ok(text):
            log(f'[{name}] {item.code}: not a timetable page, skipped')
            failed += 1
            continue
        remember_validators(entry, r)
        digest = core.sha256(raw)
        path = out / 'timetables' / tid / f'{item.code}.ics'
        old = path.read_text(encoding='utf-8') if path.is_file() else None
        if old is not None and entry.get('hash') == digest:
            entry['checked'] = core.now_utc().isoformat()
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
        ics, bounds_patched = core.reconcile_term_bounds(ics, old, tid)
        if bounds_patched:
            log(f'[{name}] {item.code}: faculty term label left the filed term; '
                f'keeping the {tid} grid')
        ok, why = core.validate(ics, item.code, tid, old)
        if not ok:
            log(f'[{name}] {item.code}: rejected ({why}), keeping the old calendar')
            failed += 1
            continue
        entry.update(hash=digest, checked=core.now_utc().isoformat(), term=tid)
        if core.same_plan(old, ics):
            continue
        entry['changed'] = entry['checked']
        changed.append(item.code)
        log(f'[{name}] {item.code}: {"new" if old is None else "changed"}')
        if not args.dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(ics.encode('utf-8'))
    # Skips (unreadable pages, failed conversions, rejected calendars) against responses
    # received: too many means the site is half-broken, not the plans half-changed.
    if checked >= 5 and failed / checked > 0.3:
        degraded = True
        log(f'[{name}] DEGRADED: {failed} of {checked} checked groups skipped; flagging the run')
    pace(False)
    if not ahead:
        fac['last_ok'] = core.now_utc().isoformat()
        fac['blocked_at'] = None
    fac['run'] = {'at': core.now_utc().isoformat(), 'term': tid, 'checked': checked,
                  'changed': len(changed), 'skipped': failed, 'blocked': False, 'ahead': ahead,
                  'cause': None, 'degraded': degraded}
    log(f'[{name}] done: {len(changed)} changed, {failed} skipped')
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
    ap.add_argument('--fresh-hours', type=float, default=1.5, help='skip groups checked more recently than this')
    ap.add_argument('--force', action='store_true', help='ignore --fresh-hours')
    ap.add_argument('--dry-run', action='store_true', help='fetch and convert, write nothing')
    ap.add_argument('--retries', type=int, default=3,
                    help='retry a flaky page fetch this many times (blocks are never retried)')
    ap.add_argument('--retry-backoff', type=float, default=2.0,
                    help='base seconds between fetch retries (exponential + jitter)')
    ap.add_argument('--max-block-wait-minutes', type=float, default=30,
                    help='total minutes a run may sleep out blocks before giving up (0 = exit on block)')
    ap.add_argument('--lanes', type=int, default=4,
                    help='policy groups crawled side by side (1 = strictly one faculty at a time)')
    ap.add_argument('--block-probes', type=int, default=5,
                    help='recovery probes per block (one cheap index fetch each)')
    args = ap.parse_args(argv)
    args.delay = PROFILES[args.profile]
    return args


def refresh_ahead(name, sources, args, state, today, session, coming, tallies, sleep, clock):
    """The coming semester's pass for one faculty; folds its results into `tallies`."""
    # The next semester's plans may already be up. Whatever is not published yet is just not there:
    # that never makes the run incomplete, only a block stops it.
    log(f'[{name}] looking for the coming semester ({core.term_id(coming)})')
    done, was_blocked, _ = refresh_faculty(name, sources[name], args, state, coming, session,
                                           sleep=sleep, clock=clock, ahead=True)
    tallies['changed'] += done
    tallies['blocked'] |= was_blocked
    return was_blocked


def run_lane(names, sources, args, state, model, today, coming, sleep=time.sleep, clock=time.monotonic,
             session=None, wait_budget=None):
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
                                                           session, sleep=sleep, clock=clock)
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
        if was_blocked:
            model.note_blocked(name, state.faculties.get(name, {}).get('run', {}).get('cause'))
            deferred.append((name, False))
            continue
        if coming and refresh_ahead(name, sources, args, state, today, session, coming,
                                    tallies, sleep, clock):
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

    recovered, waited, probes = wait_for_recovery(group, probe, model, wait_budget,
                                                   args.block_probes, sleep, clock)
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
            refresh_ahead(name, sources, args, state, today, resume, coming, tallies, sleep, clock)
        else:
            done, was_blocked, complete = refresh_faculty(name, sources[name], args, state, today,
                                                          resume, sleep=sleep, clock=clock)
            tallies['changed'] += done
            if complete:
                tallies['incomplete'].discard(name)
            else:
                tallies['incomplete'].add(name)
            if was_blocked:
                model.note_blocked(name, state.faculties.get(name, {}).get('run', {}).get('cause'))
                continue
            if coming:
                refresh_ahead(name, sources, args, state, today, resume, coming, tallies, sleep, clock)
    tallies['blocked'] = any(state.faculties.get(n, {}).get('blocked_at') for n, _ in deferred)
    return tallies


def plan_lanes(wanted):
    """Faculties grouped by Incapsula policy, in the order they were asked for: [[name, ...], ...]."""
    lanes = {}
    for name in wanted:
        lanes.setdefault(core.group_of(name), []).append(name)
    return list(lanes.values())


def main(argv=None, session=None, today=None, sleep=time.sleep, clock=time.monotonic):
    args = parse(argv)
    today = today or core.now_utc().date()
    started = core.now_utc().isoformat()
    sources = json.loads((HERE / 'sources.json').read_text(encoding='utf-8'))
    named = [f for f in args.faculty.split(',') if f]
    wanted = named or [f for f, c in sources.items() if c.get('enabled')]
    unknown = [f for f in wanted if f not in sources]
    if unknown:
        log(f'unknown faculty: {", ".join(unknown)}')
        return 2
    state = core.State(Path(args.out) / core.STATE_FILE)
    model = core.BlockModel(state.data)
    coming = core.upcoming_reference(today)
    lanes = plan_lanes(wanted)

    def lane(names, wait_budget=None):
        return run_lane(names, sources, args, state, model, today, coming, sleep, clock,
                        session=session, wait_budget=wait_budget)

    if args.lanes > 1 and len(lanes) > 1 and session is None:
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
    export(blocked=blocked, incomplete=incomplete, changed=len(tallies['changed']),
           degraded=degraded_any)
    log(f'changed: {len(tallies["changed"])}; blocked: {blocked}; incomplete: {incomplete}')
    post_run_report({'started': started, 'ended': core.now_utc().isoformat(), 'exit': exit_code,
                     'profile': args.profile, 'dry_run': args.dry_run,
                     'faculties': {n: {**(state.faculties.get(n, {}).get('run', {})),
                                       **({'wait': state.faculties[n]['wait']}
                                          if 'wait' in state.faculties.get(n, {}) else {})}
                                   for n in wanted if n in sources}})
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
