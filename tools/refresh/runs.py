#!/usr/bin/env python3
"""The refresh passes' history: the last few runs, kept on the `data` branch (docs/REFRESH.md).

refresh.yml's report job calls `record` once per pass. It adds the pass to refresh-runs.json (newest first, at most
KEEP runs) and rewrites the branch's README.md from it, so GitHub shows the history at the branch's root; `render
--summary` repeats it in the run's summary. build.py renders the same file as the site's /stan/ page.

A run says which servers (fleet.json) took part and what each did (the faculties it led, those it helped with,
those it could not list), which were off, and per faculty what the pass checked and changed: its leader's `run`
entry in refresh-state.json when that entry is this pass's, and what the work stack says of it (stack.py summary).

Nothing here touches a faculty site; it is unit-tested offline (tests/test_refresh.py).
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fleet  # noqa: E402
import build  # noqa: E402  (fleet's core put the repository root on the path; the site words a run the same way)

KEEP = 10
# A faculty's `run` stamped this long before the plan still belongs to the pass (clocks of two machines).
SLACK = dt.timedelta(minutes=2)
# GitHub Actions names the repository; elsewhere the README links nowhere rather than to a guess.
REPO_URL = (f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}"
            if os.environ.get('GITHUB_SERVER_URL') and os.environ.get('GITHUB_REPOSITORY') else '')


def _iso(moment):
    """A UTC moment the way refresh-state.json writes it: naive, to the second."""
    return moment.astimezone(dt.timezone.utc).replace(microsecond=0, tzinfo=None).isoformat()


def _flag(outcome, key):
    return str(outcome.get(key, '')).lower() == 'true'


def runner_entry(name, faculties, outcome, wave=1, took=None):
    """One server's part in the pass, from its shard outcome (None: it never reported).

    `faculties` are the ones it led (stack.py: it listed them for everyone). One that crawled a part of another
    runner's faculty says which and whose (`helped`: {faculty: leader}); one that ended blocked says on which faculties
    (`blocked_on`). Older passes also had takeovers (wave 2), which said whose faculties they took (`from`)."""
    entry = {'name': name, 'faculties': faculties, 'status': 'missing', 'minutes': None, 'changed': 0, 'wave': wave}
    if took:
        entry['from'] = took
    if not isinstance(outcome, dict):
        return entry
    helped = dict(fleet._pairs(outcome.get('took')))
    if helped:
        entry['helped'] = helped
    via_pool = fleet._names(outcome.get('pool'))
    if via_pool:
        entry['via_pool'] = via_pool  # crawled through proxy exits its egress hunted
    blocked_on = [f for f in str(outcome.get('blocked_faculties') or '').split(',') if f in faculties or f in helped]
    if blocked_on:
        entry['blocked_on'] = blocked_on
    try:
        entry['minutes'] = max(0, round((float(outcome['ended']) - float(outcome['started'])) / 60))
    except (KeyError, TypeError, ValueError):
        pass
    try:
        entry['changed'] = max(0, int(outcome.get('changed') or 0))
    except (TypeError, ValueError):
        pass
    unfinished = [f for f in str(outcome.get('incomplete_faculties') or '').split(',')
                  if f in faculties or f in helped]
    if _flag(outcome, 'skipped'):
        entry['status'] = 'skipped'
    elif _flag(outcome, 'blocked'):
        entry['status'] = 'blocked'
    elif _flag(outcome, 'incomplete') and (unfinished or 'incomplete_faculties' not in outcome
                                           or not _flag(outcome, 'degraded')):
        entry['status'] = 'incomplete'
    elif _flag(outcome, 'degraded'):
        # refresh.py raises "incomplete" for a degraded faculty too; with every faculty finished, that is all it was
        entry['status'] = 'degraded'
    else:
        entry['status'] = 'done'
    return entry


def faculty_entry(name, runner, state, since, handed=None, helpers=(), seen=None):
    """What the pass did on one faculty: its `run` entry in the state (its leader's record), when that is from this
    pass, and what the work stack says of it (`seen`, stack.py summarize): every runner's checks, its verdict.

    `runner` is the leader (or the last runner that had it, in an older pass); `handed` ({'runner', 'why'}) the one
    that let it go to that one in an older pass's takeover; `helpers` the runners that crawled a part of it."""
    fac = state.get('faculties', {}).get(name) if isinstance(state.get('faculties'), dict) else None
    run = fac.get('run') if isinstance(fac, dict) else None
    at = build.utc_moment(run.get('at')) if isinstance(run, dict) else None
    entry = {'id': name, 'runner': runner}
    if handed:
        entry['from'] = handed
    helpers = [h for h in helpers if h != runner]
    if helpers:
        entry['helpers'] = helpers
    if at is not None and at >= since - SLACK:
        entry.update(fresh=True, checked=build.count(run.get('checked')), changed=build.count(run.get('changed')),
                     not_ready=build.count(run.get('not_ready')), skipped=build.count(run.get('skipped')),
                     blocked=bool(run.get('blocked')), degraded=bool(run.get('degraded')),
                     cause=run.get('cause') if isinstance(run.get('cause'), str) else None)
    else:
        entry['fresh'] = False
    if isinstance(seen, dict):
        status = seen.get('status')
        cant = seen.get('cant') if isinstance(seen.get('cant'), dict) else {}
        if not entry['fresh'] and (status in ('blocked', 'failed') or build.count(seen.get('checked'))):
            entry.update(fresh=True, checked=0, changed=0, not_ready=0, skipped=0, blocked=False, degraded=False,
                         cause=None)
        if entry['fresh']:
            # the record counts its leader's checks; the stack counts every runner's
            entry['checked'] = max(entry['checked'], build.count(seen.get('checked')))
            entry['changed'] = max(entry['changed'], build.count(seen.get('changed')))
            entry['blocked'] = status == 'blocked'
            if status == 'blocked':
                entry['cause'] = 'wall'
            elif status == 'failed':
                entry['degraded'] = True
                entry['cause'] = entry.get('cause') or ('listing' if cant else None)
            elif entry.get('cause') in ('wall', 'flaky'):
                entry['cause'] = None  # a wall one runner met, while another got the work done
        if cant:
            entry['cant'] = {r: c for r, c in cant.items() if isinstance(r, str) and isinstance(c, str)}
        via_pool = [r for r in seen.get('via_pool') or () if isinstance(r, str)]
        if via_pool:
            entry['via_pool'] = via_pool
    return entry


def build_run(*, run_id, number, attempt, event, url, planned, ended, matrix, outcomes, plan_info, state,
              summary=None, catchup=''):
    """The record of one pass (see the module docstring): the runners the plan started (`matrix`), what each reported
    (`outcomes`) and what the work stack says of every faculty (`summary`, stack.py summarize; None when unread).
    `catchup` names the runner a catch-up pass was for (refresh-wake.yml), back online after missing passes."""
    got = fleet.latest(outcomes)
    combined = fleet.combine(matrix, outcomes, 0, summary)
    seen = summary.get('faculties') if isinstance(summary, dict) and isinstance(summary.get('faculties'), dict) else {}
    runners, leaders, helpers = [], {}, {}
    for m in matrix:
        names = [f for f in m['faculties'].split(',') if f]
        outcome = got.get(m['runner'])
        led = fleet._names(outcome.get('led')) if isinstance(outcome, dict) and 'led' in outcome else names
        entry = runner_entry(m['runner'], led, outcome)
        cant = dict(fleet._pairs(outcome.get('cant'))) if isinstance(outcome, dict) else {}
        if cant:
            entry['cant'] = cant
            walls = [f for f, c in cant.items() if c == 'wall']
            entry['blocked_on'] = list(dict.fromkeys(entry.get('blocked_on', []) + walls))
            if not entry['blocked_on']:
                entry.pop('blocked_on')
        runners.append(entry)
        for f in led:
            leaders.setdefault(f, m['runner'])
        for f in entry.get('helped', {}):
            helpers.setdefault(f, [])
            if m['runner'] not in helpers[f]:
                helpers[f].append(m['runner'])
    order = list(dict.fromkeys(f for m in matrix for f in m['faculties'].split(',') if f))
    faculties = []
    for f in order:
        info = seen.get(f) if isinstance(seen.get(f), dict) else None
        leader = (info or {}).get('leader') or leaders.get(f) or ''
        helped = list((info or {}).get('helpers') or {}) or helpers.get(f, [])
        faculties.append(faculty_entry(f, leader, state, planned, None, helped, info))
    for r in runners:
        degraded_on = [f['id'] for f in faculties if f.get('degraded') and f['runner'] == r['name']]
        if degraded_on and r['status'] == 'degraded':
            r['degraded_on'] = degraded_on
    changed = int(combined['changed'])
    if not matrix:
        result = 'idle'
    elif combined['blocked'] == 'true':
        result = 'blocked'
    elif combined['incomplete'] == 'true':
        result = 'incomplete'
    elif combined['degraded'] == 'true':
        result = 'degraded'
    else:
        result = 'changed' if changed else 'ok'
    fresh = [f for f in faculties if f['fresh']]
    extra = {'catchup': catchup} if catchup else {}
    return {
        'id': run_id, 'number': number, 'attempt': attempt, 'event': event, **extra, 'url': url,
        'planned': _iso(planned), 'ended': _iso(ended), 'result': result, 'changed': changed,
        'checked': sum(f['checked'] for f in fresh), 'not_ready': sum(f['not_ready'] for f in fresh),
        'runners': runners,
        'offline': [n for n in plan_info.get('down', []) if isinstance(n, str)],
        'unassigned': [n for n in plan_info.get('unassigned', []) if isinstance(n, str)],
        'faculties': faculties,
    }


def load_runs(path):
    return build.load_runs(path)


def outcome_key(run):
    """What a pass looks like from far away: its result and the servers that ran it."""
    return run.get('result'), sorted(r.get('name', '') for r in run.get('runners', []))


def shows_new(runs, run):
    """Whether `run` ended differently from the pass before it, so /stan/ should show it now (pages.yml's gate).

    The first pass on record does; one that fell off the history (a late rerun of an old pass) does not."""
    ids = [r['id'] for r in runs]
    if run['id'] not in ids:
        return False
    i = ids.index(run['id'])
    return i + 1 == len(runs) or outcome_key(runs[i + 1]) != outcome_key(run)


def add_run(runs, run, keep=KEEP):
    """`run` in place of an earlier attempt of the same run, newest first, at most `keep`."""
    rest = [r for r in runs if r.get('id') != run['id']]
    return sorted(rest + [run], key=lambda r: (r['planned'], r['id']), reverse=True)[:keep]


# ---------------------------------------------------------------- the GitHub view

when = build.run_when
result_label = build.run_result_label
runner_state = build.runner_state
faculty_notes = build.faculty_notes
latest = build.latest_label


def duration(run):
    minutes = build.run_minutes(run)
    return build.minutes_label(minutes) if minutes is not None else ''


def _cell(text):
    return str(text).replace('|', '\\|').replace('\n', ' ')


def servers(run, with_faculties=False):
    parts = []
    for name in build.run_servers(run):
        # a faculty the server got back after a short wait shows once, as its second try
        labels = {f: label for r in run['runners'] if r['name'] == name for f, label in build.share_parts(r)}
        facs = ', '.join(labels.values())
        parts.append(f"**{name}**" + (f' ({facs})' if with_faculties and facs else ''))
    parts += [f'~~{n}~~' for n in run.get('offline', [])]
    return ' · '.join(parts) or '–'


ALERT = {'ok': 'TIP', 'changed': 'TIP', 'degraded': 'WARNING', 'incomplete': 'WARNING', 'blocked': 'CAUTION',
         'idle': 'WARNING'}


def markdown(runs, site_url='', repo_url=''):
    """README.md for the data branch (and the run's summary): the history as GitHub renders it."""
    lines = ['# Odświeżanie planów: ostatnie przebiegi', '']
    if not runs:
        return '\n'.join(lines + ['Brak zapisanych przebiegów.', ''])
    last = runs[0]
    lines += [f"> [!{ALERT[last['result']]}]",
              f"> **Ostatni przebieg: {result_label(last).lower()}.** {when(last['planned'], True)} · "
              f"{servers(last)} · {duration(last)} · [przebieg #{last.get('number') or last['id']}]({last.get('url', '')})",
              f"> {build.run_explanation(last)}",
              '',
              f'{latest(len(runs))} workflow „Refresh timetables”, od najnowszego, w czasie warszawskim. '
              'Przekreślony serwer był wtedy wyłączony. Ten plik pisze sam przebieg (`tools/refresh/runs.py`, '
              + (f'opis w [docs/REFRESH.md]({repo_url}/blob/master/docs/REFRESH.md)).' if repo_url else 'opis w docs/REFRESH.md).')
              + (f' Ta sama lista jest na stronie: [{site_url}]({site_url}).' if site_url else ''),
              '',
              '| Kiedy | Wynik | Serwery | Sprawdzono | Czas | Przebieg |',
              '|---|---|---|--:|--:|---|']
    for run in runs:
        lines.append(f"| {when(run['planned'])} | {result_label(run)} | {_cell(servers(run, True))} | "
                     f"{build.count(run.get('checked'))} | {duration(run)} | "
                     f"[#{run.get('number') or run['id']}]({run.get('url', '')}) |")
    lines += ['', '## Szczegóły', '']
    for run in runs:
        lines += ['<details>',
                  f"<summary><b>{when(run['planned'])}</b> · {result_label(run)} · "
                  f"{' · '.join(build.run_servers(run)) or 'bez serwera'}</summary>", '',
                  f"{build.run_explanation(run)} Przebieg {build.run_event(run) or run.get('event') or ''} "
                  f"[#{run.get('number') or run['id']}]({run.get('url', '')})"
                  + (f", próba {run['attempt']}" if build.count(run.get('attempt')) > 1 else '')
                  + f", od planu do raportu {duration(run)}.", '',
                  '| Serwer | Wydziały | Zmienione | Stan |', '|---|---|--:|---|']
        for r in run.get('runners', []):
            role = build.runner_role(r)
            lines.append(f"| **{r['name']}**{f' ({role})' if role else ''} | "
                         f"{_cell(build.runner_share(r))} | "
                         f"{build.count(r.get('changed'))} | {_cell(runner_state(r))} |")
        for n in run.get('offline', []):
            lines.append(f'| {n} | | | wyłączony |')
        if run.get('faculties'):
            lines += ['', '| Wydział | Serwer | Sprawdzono | Zmieniono | Uwagi |', '|---|---|--:|--:|---|']
            for f in run['faculties']:
                lines.append(f"| {f['id'].upper()} | {f.get('runner', '')} | "
                             f"{build.count(f.get('checked')) if f.get('fresh') else '–'} | "
                             f"{build.count(f.get('changed')) if f.get('fresh') else '–'} | "
                             f"{_cell(', '.join(faculty_notes(f)))} |")
        if run.get('unassigned'):
            lines += ['', f"Żaden włączony serwer nie mógł wziąć: {', '.join(u.upper() for u in run['unassigned'])}."]
        lines += ['', '</details>', '']
    return '\n'.join(lines)


# ---------------------------------------------------------------- command line

def _write(path, text):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(text, encoding='utf-8')
    tmp.replace(path)


def _json_arg(text, kind):
    """A JSON argument from the plan job, or an empty `kind` when it is missing or garbled."""
    try:
        value = json.loads(text or 'null')
    except ValueError:
        return kind()
    return value if isinstance(value, kind) else kind()


def cmd_record(args):
    matrix = [m for m in _json_arg(args.matrix, list)
              if isinstance(m, dict) and isinstance(m.get('runner'), str) and isinstance(m.get('faculties'), str)]
    plan_info = _json_arg(args.plan, dict)
    outcomes = [fleet.load_json(p, None) for p in sorted(Path(args.dir).glob('shard-*.json'))] \
        if Path(args.dir).is_dir() else []
    planned = dt.datetime.fromtimestamp(float(args.planned or 0), dt.timezone.utc)
    run = build_run(run_id=args.run_id, number=args.run_number, attempt=args.attempt, event=args.event,
                    url=args.url, planned=planned, ended=dt.datetime.now(dt.timezone.utc), matrix=matrix,
                    outcomes=outcomes, plan_info=plan_info, state=fleet.load_json(args.state, {}),
                    summary=fleet.load_json(args.stack, None) if args.stack else None, catchup=args.catchup)
    runs = add_run(load_runs(args.runs), run)
    _write(args.runs, json.dumps({'version': 1, 'runs': runs}, ensure_ascii=False, indent=1) + '\n')
    text = markdown(runs, args.site_url, args.repo_url)
    if args.readme:
        _write(args.readme, text)
    if args.outcome:
        # refresh-outcome.json, uploaded after this step: "new" lets the Pages gate rebuild for this pass alone
        outcome = fleet.load_json(args.outcome, {})
        outcome['history'] = 'new' if shows_new(runs, run) else 'same'
        _write(args.outcome, json.dumps(outcome) + '\n')
    print(f"run {run['id']}: {run['result']}, {len(runs)} on record")
    return 0


def cmd_render(args):
    text = markdown(load_runs(args.runs), args.site_url, args.repo_url)
    if args.summary:  # under the run summary's other ### sections
        text = '\n' + text.replace('# ', '### ', 1).replace('\n## ', '\n#### ', 1)
    print(text, end='')
    return 0


def parse(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('record', help='add this pass to refresh-runs.json and rewrite README.md')
    p.add_argument('--matrix', default='[]', help="the plan's matrix (JSON)")
    p.add_argument('--handoff', default='[]', help=argparse.SUPPRESS)  # older workflows; nothing reads it
    p.add_argument('--stack', default='', help="the work stack's verdicts (stack.py summary), when it could be read")
    p.add_argument('--plan', default='{}', help="the plan's fleet output (JSON: down, unassigned)")
    p.add_argument('--planned', default='0', help='when the plan was made (Unix seconds)')
    p.add_argument('--dir', required=True, help='where the shard-*.json outcomes are')
    p.add_argument('--state', required=True, help="the data branch's refresh-state.json after the pass")
    p.add_argument('--runs', required=True, help='refresh-runs.json; rewritten')
    p.add_argument('--readme', help='README.md to rewrite from the history')
    p.add_argument('--outcome', help="the pass's refresh-outcome.json, to note whether it ended differently")
    p.add_argument('--run-id', type=int, required=True)
    p.add_argument('--run-number', type=int, default=0)
    p.add_argument('--attempt', type=int, default=1)
    p.add_argument('--event', default='')
    p.add_argument('--catchup', default='', help='the runner a catch-up pass was for (refresh-wake.yml)')
    p.add_argument('--url', default='')
    p.add_argument('--site-url', default='', help="the site's history page, linked from README.md")
    p.add_argument('--repo-url', default=REPO_URL)
    p = sub.add_parser('render', help='print the history as Markdown')
    p.add_argument('--summary', action='store_true', help="headings for a run's step summary")
    p.add_argument('--runs', required=True)
    p.add_argument('--site-url', default='')
    p.add_argument('--repo-url', default=REPO_URL)
    return ap.parse_args(argv)


def main(argv=None):
    args = parse(argv)
    return {'record': cmd_record, 'render': cmd_render}[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())
