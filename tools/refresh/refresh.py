#!/usr/bin/env python3
"""Refresh the timetables from the faculty sites.

    python tools/refresh/refresh.py --out <data checkout> [--faculty wlo,wel] [--profile hosted|selfhosted]
                                    [--limit N] [--dry-run] [--max-minutes M] [--fresh-hours H]

For every enabled faculty it lists the groups, fetches each page politely (one session, sequential, jittered,
conditional revalidation so unchanged pages answer 304), converts pages that changed, validates the calendar the
way the site's build does, and writes <out>/timetables/<term>/<GROUP>.ics only when the plan really changed.
Progress lives in <out>/refresh-state.json, so a stopped run resumes where it stopped.

The first sign of a block (any status but 200/304, an Incapsula incident page) stops that faculty at once: nothing is
retried, nothing half-converted is published, the old calendars stay. Exit codes: 0 done, 3 blocked, 4 incomplete.
With GITHUB_OUTPUT set, `blocked`, `incomplete` and `changed` are exported for the workflow.
"""
import argparse
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


def robots_allows(session, url):
    """False when the host's robots.txt disallows the URL. An unreadable robots.txt does not block."""
    from urllib import robotparser
    from urllib.parse import urlsplit
    parts = urlsplit(url)
    try:
        r = session.get(f'{parts.scheme}://{parts.netloc}/robots.txt', timeout=20)
        if r.status_code != 200 or core.is_blocked(200, r.text[:4000]):
            return True
        rp = robotparser.RobotFileParser()
        rp.parse(r.text.splitlines())
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
    try:
        items = driver.discover(session)
    except core.Blocked as err:
        log(f'[{name}] BLOCKED while listing groups: {err}')
        fac['blocked_at'] = core.now_utc().isoformat()
        return [], True, False
    except Exception as err:
        log(f'[{name}] cannot list groups: {err}')
        return [], False, False
    if not items:
        log(f'[{name}] no groups listed; leaving the faculty untouched')
        return [], False, False
    if not robots_allows(session, items[0].url):
        log(f'[{name}] robots.txt disallows the timetable pages; skipping the faculty')
        return [], False, False
    now = core.now_utc()
    key = (lambda code: f'{code}@{tid}') if ahead else (lambda code: code)
    todo = [i for i in items if args.force or not state.fresh(key(i.code), now, args.fresh_hours)]
    if args.limit:
        todo = todo[:args.limit]
    log(f'[{name}] {len(items)} groups, {len(items) - len(todo)} fresh, {len(todo)} to check (term {tid})')
    started, changed, failed = clock(), [], 0
    for n, item in enumerate(todo, 1):
        if args.max_minutes and (clock() - started) / 60 > args.max_minutes:
            log(f'[{name}] time budget used up after {n - 1} groups')
            return changed, False, False
        if n > 1:
            sleep(random.uniform(*args.delay))
        entry = state.groups.setdefault(key(item.code), {})
        try:
            r = session.get(item.url, timeout=60, headers=conditional_headers(entry))
        except Exception as err:
            log(f'[{name}] BLOCKED/NETWORK on {item.code}: {err}')
            fac['blocked_at'] = core.now_utc().isoformat()
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
            if n % 25 == 0:
                state.save()
    if not ahead:
        fac['last_ok'] = core.now_utc().isoformat()
        fac['blocked_at'] = None
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
    ap.add_argument('--fresh-hours', type=float, default=20, help='skip groups checked more recently than this')
    ap.add_argument('--force', action='store_true', help='ignore --fresh-hours')
    ap.add_argument('--dry-run', action='store_true', help='fetch and convert, write nothing')
    args = ap.parse_args(argv)
    args.delay = PROFILES[args.profile]
    return args


def main(argv=None, session=None, today=None):
    args = parse(argv)
    today = today or core.now_utc().date()
    sources = json.loads((HERE / 'sources.json').read_text(encoding='utf-8'))
    named = [f for f in args.faculty.split(',') if f]
    wanted = named or [f for f, c in sources.items() if c.get('enabled')]
    unknown = [f for f in wanted if f not in sources]
    if unknown:
        log(f'unknown faculty: {", ".join(unknown)}')
        return 2
    state = core.State(Path(args.out) / core.STATE_FILE)
    session = session or new_session()
    changed, blocked, incomplete = [], False, False
    for name in wanted:
        done, was_blocked, complete = refresh_faculty(name, sources[name], args, state, today, session)
        changed += done
        blocked |= was_blocked
        incomplete |= not complete
        if was_blocked:
            break  # the same egress is probably blocked everywhere: stop, do not probe the other hosts
        coming = core.upcoming_reference(today)
        if coming:
            # The next semester's plans may already be up. Whatever is not published yet is just not there:
            # that never makes the run incomplete, only a block stops it.
            log(f'[{name}] looking for the coming semester ({core.term_id(coming)})')
            done, was_blocked, _ = refresh_faculty(name, sources[name], args, state, coming, session, ahead=True)
            changed += done
            blocked |= was_blocked
            if was_blocked:
                break
    if not args.dry_run:
        state.save()
    export(blocked=blocked, incomplete=incomplete, changed=len(changed))
    log(f'changed: {len(changed)}; blocked: {blocked}; incomplete: {incomplete}')
    return 3 if blocked else 4 if incomplete else 0


if __name__ == '__main__':
    sys.exit(main())
