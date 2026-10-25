#!/usr/bin/env python3
"""Spread one refresh pass over the project's own runners (tools/refresh/fleet.json, docs/REFRESH.md).

The fleet is a fast machine that is often switched off and a slow one that is always up. Each pass:

  plan     (a GitHub-hosted job) asks GitHub which runners are online and splits the policy-group lanes between
           them, weighted by each runner's speed, so both finish at about the same time. A runner that is off gets
           nothing, so no job ever waits in the queue for a machine that is not coming.
  seed     gives a runner that has never crawled its own line state, copied from the data branch.
  merge    folds one runner's refresh-state.json into the data branch's newer one: the runners crawl disjoint
           faculties side by side and push to the same branch, so neither may overwrite what the other learned.
  combine  (a GitHub-hosted job) adds the runners' outcomes up into the one refresh-outcome.json pages.yml reads.

Nothing here touches a faculty site; it is unit-tested offline (tests/test_refresh.py).
"""
import argparse
import copy
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import core  # noqa: E402

FLEET = HERE / 'fleet.json'
SOURCES = HERE / 'sources.json'
# A faculty with no listing on record yet counts as a mid-sized one.
DEFAULT_SIZE = 100
# A pass whose last shard ended this long after the plan (it sat in the queue) no longer files or closes issues:
# newer passes have spoken since.
REPORT_HOURS = 3
NAME_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,38}$')


def log(msg):
    print(msg, flush=True)


def load_json(path, default, kind=dict):
    """The JSON in `path` when it parses to a `kind`, else `default`."""
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default
    return value if isinstance(value, kind) else default


def load_fleet(path=FLEET):
    """The runners from fleet.json, checked: [{name, label, speed, always_on, faculties}]."""
    raw = json.loads(Path(path).read_text(encoding='utf-8'))
    runners = raw.get('runners') if isinstance(raw, dict) else None
    if not isinstance(runners, list):
        raise ValueError('the fleet must be an object with a "runners" list')
    fleet, seen = [], set()
    for r in runners:
        if not isinstance(r, dict):
            raise ValueError(f'a runner must be an object, not {r!r}')
        name, label = r.get('name'), r.get('label')
        if not isinstance(name, str) or not NAME_RE.match(name) or name in seen:
            raise ValueError(f'bad or repeated runner name: {name!r}')
        if not isinstance(label, str) or not label:
            raise ValueError(f'{name}: no label')
        speed = r.get('speed', 1)
        if isinstance(speed, bool) or not isinstance(speed, (int, float)) or not speed > 0:
            raise ValueError(f'{name}: speed must be a positive number')
        only = r.get('faculties')
        if only is not None and not (isinstance(only, list) and all(isinstance(f, str) for f in only)):
            raise ValueError(f'{name}: faculties must be a list of faculty ids')
        seen.add(name)
        fleet.append({'name': name, 'label': label, 'speed': float(speed),
                      'always_on': bool(r.get('always_on')), 'faculties': only})
    if not fleet:
        raise ValueError('the fleet has no runners')
    return fleet


def online_labels(runners):
    """Labels carried by at least one online runner, from GitHub's runner list; None when it is unknown."""
    if runners is None:
        return None
    labels = set()
    for r in runners:
        if isinstance(r, dict) and r.get('status') == 'online':
            labels.update(x for x in r.get('labels', []) if isinstance(x, str))
    return labels


def faculty_cost(state, name):
    """Rough work of one faculty: groups it listed last time times its learned pause multiplier."""
    fac = state.get('faculties', {}).get(name)
    size = fac.get('last_count') if isinstance(fac, dict) else None
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        size = DEFAULT_SIZE
    pace = state.get('pacing', {}).get(core.group_of(name), 1.0)
    if isinstance(pace, bool) or not isinstance(pace, (int, float)):
        pace = 1.0
    return size * min(3.0, max(1.0, float(pace)))


def lanes_of(wanted):
    """Faculties grouped by Incapsula policy, in the order asked (refresh.plan_lanes): a lane never splits, since
    its members share one wall and one wait."""
    lanes = {}
    for name in wanted:
        lanes.setdefault(core.group_of(name), []).append(name)
    return list(lanes.values())


def plan(fleet, wanted, state, online):
    """Split the lanes of `wanted` over the runners that are up.

    `online` is the set of labels GitHub reports online, or None when it could not be asked: then the always-on
    runners take everything (the job waits for them like a single-runner pass would). Lanes go out largest first,
    each to the runner that would finish it earliest (load / speed), so a fast runner takes a lot and a slow one the
    rest. A lane no runner up may take is left for the next pass.
    """
    if online is None:
        up = [r for r in fleet if r['always_on']] or fleet
    else:
        up = [r for r in fleet if r['label'] in online]
    load = {r['name']: 0.0 for r in up}
    shards = {r['name']: [] for r in up}
    unassigned = []
    lanes = [(sum(faculty_cost(state, f) for f in lane), lane) for lane in lanes_of(wanted)]
    for cost, lane in sorted(lanes, key=lambda x: (-x[0], x[1])):
        able = [r for r in up if r['faculties'] is None or all(f in r['faculties'] for f in lane)]
        if not able:
            unassigned += lane
            continue
        best = min(able, key=lambda r: ((load[r['name']] + cost) / r['speed'], -r['speed'], r['name']))
        load[best['name']] += cost
        shards[best['name']] += lane
    order = {f: i for i, f in enumerate(wanted)}
    out = [{'runner': r['name'], 'label': r['label'], 'faculties': ','.join(sorted(shards[r['name']], key=order.get)),
            'cost': round(load[r['name']]), 'eta': round(load[r['name']] / r['speed'])}
           for r in up if shards[r['name']]]
    return {'shards': out, 'unassigned': sorted(unassigned, key=order.get), 'known': online is not None,
            'up': [r['name'] for r in up], 'down': [r['name'] for r in fleet if r not in up]}


def plan_summary(result):
    lines = ['### Refresh plan', '']
    if not result['known']:
        lines += ['GitHub was not asked which runners are online (no `PLANWAT_RUNNERS_TOKEN`, or the API failed): '
                  'the always-on runners take everything.', '']
    lines += ['| runner | faculties | work | relative time |', '|---|---|---|---|']
    for s in result['shards']:
        lines.append(f"| {s['runner']} | {s['faculties']} | {s['cost']} | {s['eta']} |")
    for name in result['down']:
        lines.append(f'| {name} | offline, nothing |  |  |')
    if result['unassigned']:
        lines += ['', f"No runner up may take: {', '.join(result['unassigned'])} (left for the next pass)."]
    return '\n'.join(lines) + '\n'


def github_output(**values):
    path = os.environ.get('GITHUB_OUTPUT')
    if path:
        with open(path, 'a', encoding='utf-8') as fh:
            for k, v in values.items():
                fh.write(f'{k}={v}\n')


def step_summary(text):
    path = os.environ.get('GITHUB_STEP_SUMMARY')
    if path:
        with open(path, 'a', encoding='utf-8') as fh:
            fh.write(text)


def enabled_faculties(sources=SOURCES):
    return [f for f, c in json.loads(Path(sources).read_text(encoding='utf-8')).items() if c.get('enabled')]


def cmd_plan(args):
    sources = json.loads(Path(args.sources).read_text(encoding='utf-8'))
    named = [f.strip() for f in args.faculty.split(',') if f.strip()]
    unknown = [f for f in named if f not in sources]
    if unknown:
        log(f'unknown faculty: {", ".join(unknown)}')
        return 2
    wanted = named or [f for f, c in sources.items() if c.get('enabled')]
    runners = load_json(args.runners, None, list) if args.runners else None
    result = plan(load_fleet(args.fleet), wanted, load_json(args.state, {}), online_labels(runners))
    for s in result['shards']:
        log(f"{s['runner']}: {s['faculties']} (work {s['cost']}, relative time {s['eta']})")
    for name in result['down']:
        log(f'{name}: offline, nothing')
    if result['unassigned']:
        log(f"::warning::no runner up may take {', '.join(result['unassigned'])}; left for the next pass")
    if not result['shards']:
        log('::warning::no runner of the fleet is online; this pass crawls nothing')
    matrix = [{'runner': s['runner'], 'label': s['label'], 'faculties': s['faculties']} for s in result['shards']]
    planned = int(dt.datetime.now(dt.timezone.utc).timestamp())
    # runs.py records which servers were off and what nobody could take
    info = {'down': result['down'], 'unassigned': result['unassigned']}
    github_output(matrix=json.dumps(matrix, separators=(',', ':')), shards=len(matrix), planned=planned,
                  fleet=json.dumps(info, separators=(',', ':')))
    step_summary(plan_summary(result))
    return 0


def cmd_seed(args):
    """A runner's first line state: the data branch's numbers, the best guess there is."""
    state = load_json(args.state, {})
    line = {k: state.get(k) if isinstance(state.get(k), dict) else {} for k in core.LINE_KEYS}
    out = Path(args.out)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix('.tmp')
        tmp.write_text(json.dumps(line, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
        tmp.replace(out)
    except OSError as err:
        log(f'cannot keep a line state at {out} ({err}); this runner shares the data branch\'s')
        return 1
    return 0


def merge_state(base, mine, theirs, owned):
    """refresh-state.json for the push: the branch's newest copy (`theirs`) plus what this runner's pass changed.

    `base` is the copy the pass started from and `mine` the copy it ended with. The line keys (per-faculty runs,
    block durations, pacing) are this runner's own line, not the branch's history, so only those of the faculties it
    crawled (`owned`) and their policy groups are taken. Everything else (group stamps, robots answers) is taken
    entry by entry where the pass changed it, so a runner that crawled other faculties meanwhile keeps its entries.
    """
    out = copy.deepcopy(theirs) if isinstance(theirs, dict) and theirs.get('version') == 1 else {}
    out.setdefault('version', 1)
    out.setdefault('groups', {})
    out.setdefault('faculties', {})
    keys = {'faculties': set(owned), 'blocks': {core.group_of(f) for f in owned},
            'pacing': {core.group_of(f) for f in owned}}
    for top, value in mine.items():
        if not isinstance(value, dict):
            continue
        if not isinstance(out.get(top), dict):
            out[top] = {}
        if top in core.LINE_KEYS:
            for k in keys[top]:
                if k in value:
                    out[top][k] = value[k]
            continue
        was = base.get(top) if isinstance(base.get(top), dict) else {}
        for k, v in value.items():
            if was.get(k) != v:
                out[top][k] = v
    return out


def cmd_merge(args):
    owned = [f.strip() for f in args.faculty.split(',') if f.strip()] or enabled_faculties(args.sources)
    mine = load_json(args.mine, None)
    if mine is None:
        log(f'{args.mine} is not a state file; nothing to merge')
        return 1
    merged = merge_state(load_json(args.base, {}), mine, load_json(args.into, {}), owned)
    into = Path(args.into)
    tmp = into.with_suffix('.tmp')
    tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
    tmp.replace(into)
    return 0


def combine(expected, outcomes, age_hours):
    """One outcome for the pass out of its shards' outcomes (refresh-outcome.json, read by pages.yml's gate).

    `pushed` is "true" when any shard pushed and "false" only when every planned shard reported it did not; a
    shard that never reported leaves it empty, which the gate reads as "rebuild". A missing or skipped shard makes
    the pass incomplete, so it neither files nor closes issues on what it did not see.
    """
    got = {o.get('runner'): o for o in outcomes if isinstance(o, dict)}
    flag = lambda o, k: str(o.get(k, '')).lower() == 'true'  # noqa: E731
    seen = [got[r] for r in expected if r in got and not flag(got[r], 'skipped')]
    missing = [r for r in expected if r not in got or flag(got[r], 'skipped')]
    if any(flag(o, 'pushed') for o in seen):
        pushed = 'true'
    elif not missing:
        pushed = 'false'
    else:
        pushed = ''
    changed = 0
    for o in seen:
        try:
            changed += int(o.get('changed') or 0)
        except (TypeError, ValueError):
            pass
    return {'pushed': pushed, 'changed': str(changed),
            'blocked': str(any(flag(o, 'blocked') for o in seen)).lower(),
            'incomplete': str(bool(missing) or not expected or any(flag(o, 'incomplete') for o in seen)).lower(),
            'degraded': str(any(flag(o, 'degraded') for o in seen)).lower(),
            'missing': missing, 'current': age_hours < REPORT_HOURS}


def cmd_combine(args):
    expected = [m.get('runner') for m in json.loads(args.matrix or '[]') if isinstance(m, dict)]
    outcomes = [load_json(p, None) for p in sorted(Path(args.dir).glob('shard-*.json'))] if Path(args.dir).is_dir() else []
    age = (dt.datetime.now(dt.timezone.utc).timestamp() - float(args.planned or 0)) / 3600
    result = combine(expected, outcomes, age)
    Path(args.out).write_text(json.dumps({k: result[k] for k in ('pushed', 'changed', 'blocked')}) + '\n',
                              encoding='utf-8')
    github_output(blocked=result['blocked'], incomplete=result['incomplete'], degraded=result['degraded'],
                  current=str(result['current']).lower())
    lines = ['### Refresh outcome', '', '| runner | faculties | pushed | changed | blocked | incomplete | minutes |',
             '|---|---|---|---|---|---|---|']
    for o in outcomes:
        if not isinstance(o, dict):
            continue
        try:
            minutes = round((float(o['ended']) - float(o['started'])) / 60)
        except (KeyError, TypeError, ValueError):
            minutes = ''
        state = 'skipped (stale plan)' if str(o.get('skipped')).lower() == 'true' else o.get('pushed', '')
        lines.append(f"| {o.get('runner', '?')} | {o.get('faculties', '')} | {state} | {o.get('changed', '')} | "
                     f"{o.get('blocked', '')} | {o.get('incomplete', '')} | {minutes} |")
    if result['missing']:
        lines += ['', f"No outcome from: {', '.join(result['missing'])}."]
        log(f"::warning::no outcome from {', '.join(result['missing'])}; the pass counts as incomplete")
    if not result['current']:
        lines += ['', f'The plan is over {REPORT_HOURS} h old: issues are left to newer passes.']
    step_summary('\n'.join(lines) + '\n')
    log(json.dumps(result))
    return 0


def parse(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('plan', help='split a pass over the runners that are online')
    p.add_argument('--state', default='data/refresh-state.json', help="the data branch's refresh-state.json")
    p.add_argument('--runners', help="GitHub's runner list (JSON array); missing = unknown")
    p.add_argument('--faculty', default='', help='comma-separated faculties (default: every enabled one)')
    p.add_argument('--fleet', default=str(FLEET))
    p.add_argument('--sources', default=str(SOURCES))
    p = sub.add_parser('seed', help="write a runner's first line state from the data branch's")
    p.add_argument('--state', required=True)
    p.add_argument('--out', required=True)
    p = sub.add_parser('merge', help="fold this runner's state into the data branch's newer one")
    p.add_argument('--base', required=True, help='the state the pass started from')
    p.add_argument('--mine', required=True, help='the state the pass ended with')
    p.add_argument('--into', required=True, help="the branch's newest state; overwritten with the merge")
    p.add_argument('--faculty', default='', help='the faculties this pass crawled (default: every enabled one)')
    p.add_argument('--sources', default=str(SOURCES))
    p = sub.add_parser('combine', help="add the shards' outcomes up for pages.yml")
    p.add_argument('--matrix', default='[]', help="the plan's matrix (JSON)")
    p.add_argument('--planned', default='0', help='when the plan was made (Unix seconds)')
    p.add_argument('--dir', required=True, help='where the shard-*.json outcomes are')
    p.add_argument('--out', required=True)
    return ap.parse_args(argv)


def main(argv=None):
    args = parse(argv)
    return {'plan': cmd_plan, 'seed': cmd_seed, 'merge': cmd_merge, 'combine': cmd_combine}[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())
