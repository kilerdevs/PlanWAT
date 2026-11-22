#!/usr/bin/env python3
"""The crawl's clock, outside GitHub: starts the scheduled workflows on time.

GitHub's `schedule:` starts these workflows hours late or not at all (refresh.yml ran 3 times a day instead of 12 in
November 2026). So every always-up server runs this ticker in a container of its own (deploy/runner/compose.yml, for
plebania tools/egress/compose.fragment.yml): at each slot of the table below it waits PLANWAT_TICKER_DELAY minutes
(0, 4, 8, 12: one server after another), asks GitHub whether that slot's run has started, and starts it if not. Any
one server up is enough, and GitHub's own cron stays as the last fallback; refresh.yml's plan job lets only the
earliest full pass of a slot crawl.

The token (PLANWAT_TICKER_TOKEN) is a fine-grained one for this repository with Actions read and write only. It lives
in this container alone, never in a runner's, so no crawl job can start workflows.

Environment: PLANWAT_TICKER_TOKEN (required), PLANWAT_TICKER_DELAY (minutes, default 0),
PLANWAT_TICKER_REPO (default kilerdevs/PlanWAT), PLANWAT_TICKER_REF (default master).
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request

# (workflow, period in minutes, first slot in minutes after 00:00 UTC): each mirrors the workflow's own `cron:` line
# (tests/test_ticker.py holds them together).
JOBS = (
    ('refresh.yml', 120, 23),      # '23 */2 * * *'
    ('collect.yml', 30, 7),        # '7,37 * * * *'
    ('pages.yml', 1440, 3 * 60 + 17),  # '17 3 * * *'
)
# Only a full pass takes a refresh slot: a catch-up or a one-faculty run is titled otherwise (refresh.yml run-name).
FULL_PASS = {'refresh.yml': 'Refresh timetables'}
API = 'https://api.github.com'


def log(msg):
    print(f'{dt.datetime.now(dt.timezone.utc):%Y-%m-%dT%H:%M:%SZ} {msg}', flush=True)


def next_slot(now, period, offset):
    """The first slot strictly after `now` (aware, UTC) of a job running every `period` minutes from `offset`."""
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    minutes = (now - day).total_seconds() / 60
    k = int((minutes - offset) // period) + 1
    return day + dt.timedelta(minutes=offset + k * period)


def cron_of(period, offset):
    """The `cron:` string GitHub runs the same job on (for the test that keeps the table and the workflows equal)."""
    if period == 1440:
        return f'{offset % 60} {offset // 60} * * *'
    if period < 60:
        return f'{",".join(str(m) for m in range(offset, 60, period))} * * * *'
    return f'{offset} */{period // 60} * * *'


class GitHub:
    def __init__(self, token, repo):
        self.token, self.repo = token, repo

    def __call__(self, method, path, body=None):
        """(status, parsed JSON or None) of one API call."""
        req = urllib.request.Request(
            f'{API}/repos/{self.repo}{path}', method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization': f'Bearer {self.token}', 'Accept': 'application/vnd.github+json',
                     'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'planwat-ticker'})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read()
                return r.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as err:
            return err.code, None


def tick(api, workflow, slot, ref='master'):
    """One slot of one workflow: 'taken by #N' when its run already started, else start it. Returns what happened."""
    since = f'{slot:%Y-%m-%dT%H:%M:%SZ}'
    status, data = api('GET', f'/actions/workflows/{workflow}/runs?created=%3E%3D{since}&per_page=20')
    if status != 200 or not isinstance(data, dict):
        raise RuntimeError(f'cannot list the runs of {workflow} (HTTP {status})')
    title = FULL_PASS.get(workflow)
    for run in data.get('workflow_runs') or []:
        if title is None or run.get('display_title') == title:
            return f'slot taken by #{run.get("run_number")}'
    body = {'ref': ref}
    if workflow == 'refresh.yml':
        body['inputs'] = {'tick': since}
    status, _ = api('POST', f'/actions/workflows/{workflow}/dispatches', body)
    if status != 204:
        raise RuntimeError(f'GitHub refused to start {workflow} (HTTP {status})')
    return 'started'


def run(api, delay, ref='master', now=lambda: dt.datetime.now(dt.timezone.utc), sleep=time.sleep, rounds=None):
    """Tick forever (or `rounds` times): sleep to the next due slot, tick it, never stop on an error."""
    wait = dt.timedelta(minutes=delay)
    while rounds is None or rounds > 0:
        current = now()
        due = sorted((next_slot(current - wait, period, offset), workflow) for workflow, period, offset in JOBS)
        slot, workflow = due[0]
        sleep(max(0.0, (slot + wait - current).total_seconds()))
        try:
            log(f'{workflow} {slot:%H:%M}: {tick(api, workflow, slot, ref)}')
        except Exception as err:  # noqa: BLE001 (the next slot, or another server, or GitHub's cron takes over)
            log(f'{workflow} {slot:%H:%M}: {err}')
        if rounds is not None:
            rounds -= 1


def main():
    token = os.environ.get('PLANWAT_TICKER_TOKEN', '').strip()
    if not token:
        print('ticker: PLANWAT_TICKER_TOKEN is not set (a fine-grained token, Actions read and write)', file=sys.stderr)
        return 1
    delay = int(os.environ.get('PLANWAT_TICKER_DELAY') or 0)
    if not 0 <= delay < min(period for _, period, _ in JOBS):
        print(f'ticker: PLANWAT_TICKER_DELAY must be 0-{min(p for _, p, _ in JOBS) - 1} minutes', file=sys.stderr)
        return 1
    repo = os.environ.get('PLANWAT_TICKER_REPO') or 'kilerdevs/PlanWAT'
    log(f'ticker for {repo}: {", ".join(w for w, _, _ in JOBS)}, {delay} min after each slot')
    run(GitHub(token, repo), delay, os.environ.get('PLANWAT_TICKER_REF') or 'master')
    return 0


if __name__ == '__main__':
    sys.exit(main())
