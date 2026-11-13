#!/usr/bin/env python3
"""Start one refresh pass on the project's own runners (tools/refresh/fleet.json, docs/REFRESH.md).

The fleet is a fast home server that is often switched off, a slow always-on VPS and a free container. Each pass:

  plan     (a GitHub-hosted job) asks GitHub which runners are online and starts a crawl on each one that may take
           anything: nothing is handed out, every runner pulls its work from the pass's shared work stack
           (stack.py), its preferred faculties first (`prefers`), within what it may take (`faculties`). Each also gets
           a static share (`fallback`, the old even split: plan()), crawled alone only when the stack cannot be
           reached. A runner that is off gets no crawl, so no share waits in the queue for a machine that is not
           coming; the report queues a tiny catch-up job for it instead (refresh-wake.yml), which starts the moment
           the machine is back.
  owed     what such a runner owes once it is back: the faculties it may take that the passes it missed left undone.
           `plan --catchup` plans a pass of just those.
  seed     gives a runner that has never crawled its own line state, copied from the data branch.
  merge    folds one runner's refresh-state.json into the data branch's newer one: the runners crawl side by side and
           push to the same branch, so neither may overwrite what the other learned. A faculty's record is its
           leader's (the runner that listed it for the stack).
  combine  (a GitHub-hosted job) adds the pass up into the one refresh-outcome.json pages.yml reads: per faculty what
           the stack says of it (stack.py summary), or, when the stack cannot be read, what the runners last saw.

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
# A runner that ended blocked on a faculty in each of its last WALLED_PASSES passes over it (at least WALLED_MIN of
# them) stands at that faculty's wall: the fallback split does not give it the faculty while a runner it lets through
# is up.
WALLED_PASSES = 3
WALLED_MIN = 2
# Every runner of the fleet carries this label besides its own (refresh-crawl.yml's runs-on).
RUNNER_LABEL = 'planwat'
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


EGRESS_KINDS = ('remote', 'local')


def load_fleet(path=FLEET):
    """The runners from fleet.json, checked: [{name, label, speed, always_on, faculties, prefers, census, egress, pool,
    pool_help}]. `egress` says whether the runner can hunt the pool for exits through a wall (stack.py): 'remote' (the
    egress box beside it), 'local' (one it starts itself) or None; `pool` the faculties it may take only through such
    exits, `pool_help` those of them it helps with through the pool even while another runner leads them."""
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
        only, prefers, census = r.get('faculties'), r.get('prefers', []), r.get('census', [])
        pool, pool_help, egress = r.get('pool', []), r.get('pool_help', []), r.get('egress')
        if only is not None and not (isinstance(only, list) and all(isinstance(f, str) for f in only)):
            raise ValueError(f'{name}: faculties must be a list of faculty ids')
        if egress is not None and egress not in EGRESS_KINDS:
            raise ValueError(f'{name}: egress must be one of {", ".join(EGRESS_KINDS)}')
        for key, value in (('prefers', prefers), ('census', census), ('pool', pool), ('pool_help', pool_help)):
            if not (isinstance(value, list) and all(isinstance(f, str) for f in value)):
                raise ValueError(f'{name}: {key} must be a list of faculty ids')
        if pool and egress is None:
            raise ValueError(f'{name}: a pool needs an egress to hunt with')
        if not set(pool_help) <= set(pool):
            raise ValueError(f'{name}: pool_help must be among its pool')
        seen.add(name)
        fleet.append({'name': name, 'label': label, 'speed': float(speed), 'always_on': bool(r.get('always_on')),
                      'faculties': only, 'prefers': prefers, 'census': census, 'egress': egress, 'pool': pool,
                      'pool_help': pool_help})
    if not fleet:
        raise ValueError('the fleet has no runners')
    return fleet


def online_labels(runners):
    """Labels carried by at least one online runner of the fleet, from GitHub's runner list; None when it is unknown.

    Only a runner that also carries the fleet's own label counts: the crawl asks for both (refresh-crawl.yml), so a
    machine with the right name but without RUNNER_LABEL would leave the job queued for nobody."""
    if runners is None:
        return None
    labels = set()
    for r in runners:
        if not isinstance(r, dict) or r.get('status') != 'online' or not isinstance(r.get('labels'), list):
            continue
        mine = {x for x in r['labels'] if isinstance(x, str)}
        if RUNNER_LABEL in mine:
            labels |= mine
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


def may_take(runner, lane, avoid):
    """Whether `runner` may crawl every faculty of `lane`: its allowlist has them and none is to be avoided by it."""
    return all((runner['faculties'] is None or f in runner['faculties']) and runner['name'] not in avoid.get(f, ())
               for f in lane)


def reach(runner):
    """The faculties a runner may take at all, its own address or pool exits (`pool`): a set, None for any."""
    if runner['faculties'] is None:
        return None
    return set(runner['faculties']) | set(runner.get('pool') or ())


def walled_runners(runs):
    """{faculty: {runner}} out of the run history (refresh-runs.json's `runs`, newest first): the runners whose last
    WALLED_PASSES passes over a faculty all ended blocked on it, counting a pass by the runner's last wave there (a wall
    it got through later in the pass is no wall) and only passes that ended done or blocked (a cancelled or cut-short
    one tells nothing)."""
    seen = {}  # (runner, faculty) -> [blocked?] newest pass first
    for run in runs if isinstance(runs, list) else []:
        last = {}  # (runner, faculty) -> (wave, blocked) in this pass
        for x in (run.get('runners') if isinstance(run, dict) else None) or []:
            if not isinstance(x, dict) or x.get('status') not in ('done', 'blocked'):
                continue
            wave = x.get('wave') if isinstance(x.get('wave'), int) else 1
            blocked = set(x.get('blocked_on') or []) | {f for f, c in (x.get('cant') or {}).items() if c == 'wall'}
            for f in list(x.get('faculties') or []) + [f for f in (x.get('cant') or {}) if f not in (x.get('faculties') or [])]:
                key = (x.get('name'), f)
                if key not in last or last[key][0] <= wave:
                    last[key] = (wave, f in blocked)
        for key, (_, blocked) in last.items():
            history = seen.setdefault(key, [])
            if len(history) < WALLED_PASSES:
                history.append(blocked)
    out = {}
    for (runner, f), history in seen.items():
        if len(history) >= WALLED_MIN and all(history):
            out.setdefault(f, set()).add(runner)
    return out


def plan(fleet, wanted, state, online, avoid=None, walled=None):
    """Split the lanes of `wanted` over the runners that are up: the static share each crawls alone should the work
    stack (stack.py) be out of reach, and the runners that are up at all.

    `online` is the set of labels GitHub reports online, or None when it could not be asked: then the always-on
    runners take everything. Lanes go out largest first, each to the runner that would finish it earliest
    (load / speed). A lane a runner up `prefers` (every faculty of it) goes to that runner whatever the load. A lane no
    runner up may take is left for the next pass. `avoid` maps a faculty to runners that must not take it; `walled`
    (walled_runners) to the runners its wall kept out lately: a lane goes to one of them only when no other runner up
    may take it.
    """
    avoid, walled = avoid or {}, walled or {}

    def clear(r, lane):
        return not any(r['name'] in walled.get(f, ()) for f in lane)
    if online is None:
        up = [r for r in fleet if r['always_on']] or fleet
    else:
        up = [r for r in fleet if r['label'] in online]
    load = {r['name']: 0.0 for r in up}
    shards = {r['name']: [] for r in up}
    unassigned = []
    lanes = [(sum(faculty_cost(state, f) for f in lane), lane) for lane in lanes_of(wanted)]
    for cost, lane in sorted(lanes, key=lambda x: (-x[0], x[1])):
        able = [r for r in up if may_take(r, lane, avoid)]
        if not able:
            unassigned += lane
            continue
        able = [r for r in able if clear(r, lane)] or able
        keen = [r for r in able if all(f in r.get('prefers', ()) for f in lane)]
        best = min(keen or able, key=lambda r: ((load[r['name']] + cost) / r['speed'], -r['speed'], r['name']))
        load[best['name']] += cost
        shards[best['name']] += lane
    order = {f: i for i, f in enumerate(wanted)}
    out = [{'runner': r['name'], 'label': r['label'], 'faculties': ','.join(sorted(shards[r['name']], key=order.get)),
            'cost': round(load[r['name']]), 'eta': round(load[r['name']] / r['speed'])}
           for r in up if shards[r['name']]]
    return {'shards': out, 'unassigned': sorted(unassigned, key=order.get), 'known': online is not None,
            'up': [r['name'] for r in up], 'down': [r['name'] for r in fleet if r not in up]}


def matrix_of(fleet, wanted, state, online, walled=None, avoid=None):
    """The pass's crawl jobs: one per runner up that may take any faculty wanted, each with what it may take (in the
    order asked), its census, who else crawls (`expected`) and its fallback share (plan()). Plus the plan itself.
    `avoid` ({faculty: {runner}}) keeps a runner off a faculty altogether (a catch-up's walled helpers)."""
    avoid = avoid or {}
    result = plan(fleet, wanted, state, online, avoid=avoid, walled=walled)
    census = census_of(fleet, wanted)
    fallback = {s['runner']: s['faculties'] for s in result['shards']}
    by = {r['name']: r for r in fleet}
    jobs = []
    for name in result['up']:
        r = by[name]
        pooled = [f for f in wanted if f in (r.get('pool') or ()) and not may_take(r, [f], avoid)
                  and name not in avoid.get(f, ())]
        mine = [f for f in wanted if may_take(r, [f], avoid) or f in pooled]
        if mine:
            jobs.append({'runner': name, 'label': r['label'], 'faculties': ','.join(mine),
                         'census': census.get(name, ''), 'fallback': fallback.get(name, ''),
                         'pool': ','.join(pooled), 'egress': r.get('egress') or ''})
    expected = ','.join(j['runner'] for j in jobs)
    for j in jobs:
        j['expected'] = expected
    taken = {f for j in jobs for f in j['faculties'].split(',')}
    result['unassigned'] = [f for f in wanted if f not in taken]
    return jobs, result


def missed(runner, run):
    """Whether `runner` had no part in `run` (a refresh-runs.json pass): it was off, or its share never ran."""
    if runner in (run.get('offline') or []):
        return True
    entry = next((x for x in run.get('runners') or [] if isinstance(x, dict) and x.get('name') == runner), None)
    return entry is None or entry.get('status') in ('missing', 'skipped')


def owed(fleet, runner, runs, wanted):
    """The faculties of `wanted` that `runner` (a name in the fleet) owes after being away: those it may take whose
    newest pass ran without it and left them undone (nobody could take them, the pass never got to them, or a wall
    stopped whoever tried). A faculty the others got done meanwhile is not owed. With no pass on record that covered a
    faculty, it is owed when the runner missed the newest pass. `runs` is refresh-runs.json's list, newest first."""
    by = {r['name']: r for r in fleet}
    if runner not in by:
        raise ValueError(f'unknown runner: {runner!r}')
    runs = [r for r in runs if isinstance(r, dict)] if isinstance(runs, list) else []
    out = []
    for f in wanted:
        if not may_take(by[runner], [f], {}):
            continue
        for run in runs:
            entry = next((x for x in run.get('faculties') or [] if isinstance(x, dict) and x.get('id') == f), None)
            unassigned = f in (run.get('unassigned') or [])
            if entry is None and not unassigned:
                continue
            undone = unassigned or entry is None or not entry.get('fresh') or bool(entry.get('blocked'))
            if undone and missed(runner, run):
                out.append(f)
            break
        else:
            if runs and missed(runner, runs[0]):
                out.append(f)
    return out


def census_of(fleet, wanted):
    """{runner: 'wig,...'}: the censuses each runner takes this pass (its fleet.json `census` among the faculties
    wanted), whoever crawls those faculties. refresh.py runs each at most once a week, after the crawl."""
    return {r['name']: ','.join(f for f in wanted if f in r.get('census', ())) for r in fleet}


def plan_summary(jobs, result):
    lines = ['### Refresh plan', '']
    if not result['known']:
        lines += ['GitHub was not asked which runners are online (no `PLANWAT_RUNNERS_TOKEN`, or the API failed): '
                  'the always-on runners take everything.', '']
    lines += ['Every runner pulls its work from the shared work stack, its preferred faculties first. The fallback is '
              'what it crawls alone should the stack be out of reach.', '',
              '| runner | may take | prefers | fallback |', '|---|---|---|---|']
    for j in jobs:
        lines.append(f"| {j['runner']} | {j['faculties']} | {j.get('prefers', '')} | {j['fallback'] or '–'} |")
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
    fleet = load_fleet(args.fleet)
    history = load_json(args.runs, {}).get('runs') if args.runs else []
    walled = walled_runners(history)
    for f, names in sorted(walled.items()):
        log(f"{f}: its wall kept {', '.join(sorted(names))} out lately; not in their fallback share")
    online = online_labels(runners)
    avoid = {}
    if args.catchup:
        # A catch-up pass: what the runner that came back owes (owed), helped by the others but not where their
        # own wall would only stop them.
        by = {r['name']: r for r in fleet}
        if args.catchup not in by:
            log(f'unknown runner: {args.catchup}')
            return 2
        wanted = owed(fleet, args.catchup, history, wanted)
        log(f"catch-up for {args.catchup}: it owes {', '.join(wanted) or 'nothing'}")
        if online is not None and by[args.catchup]['label'] not in online:
            log(f'::notice::{args.catchup} is offline again; nothing to catch up now')
            wanted = []
        avoid = {f: names - {args.catchup} for f, names in walled.items()}
    jobs, result = matrix_of(fleet, wanted, load_json(args.state, {}), online, walled, avoid)
    if args.catchup and not any(j['runner'] == args.catchup for j in jobs):
        jobs = []  # the others alone have done what they could already
    prefers = {r['name']: ','.join(f for f in r['prefers'] if f in wanted) for r in fleet}
    for j in jobs:
        j['prefers'] = prefers.get(j['runner'], '')
        log(f"{j['runner']}: may take {j['faculties']}"
            + (f"; leads {j['prefers']}" if j['prefers'] else '') + f"; fallback {j['fallback'] or 'nothing'}")
    for name in result['down']:
        log(f'{name}: offline, nothing')
    if result['unassigned']:
        log(f"::warning::no runner up may take {', '.join(result['unassigned'])}; left for the next pass")
    if not jobs:
        log('::warning::no runner of the fleet is online; this pass crawls nothing')
    matrix = [{k: j[k] for k in ('runner', 'label', 'faculties', 'census', 'expected', 'fallback', 'pool', 'egress')}
              for j in jobs]
    planned = int(dt.datetime.now(dt.timezone.utc).timestamp())
    # runs.py records which servers were off and what nobody could take
    info = {'down': result['down'], 'unassigned': result['unassigned']}
    # the servers GitHub says are off, for the report to queue a catch-up waiting for each (refresh-wake.yml); none
    # when it could not be asked
    by = {r['name']: r for r in fleet}
    asleep = [{'runner': n, 'label': by[n]['label']} for n in result['down']] if result['known'] else []
    github_output(matrix=json.dumps(matrix, separators=(',', ':')), shards=len(matrix), planned=planned,
                  fleet=json.dumps(info, separators=(',', ':')), asleep=json.dumps(asleep, separators=(',', ':')))
    head = (f"Catch-up for **{args.catchup}**, back online: it owes {', '.join(wanted) or 'nothing'}.\n\n"
            if args.catchup else '')
    step_summary(head + plan_summary(jobs, result))
    return 0


def cmd_owed(args):
    fleet = load_fleet(args.fleet)
    if args.runner not in {r['name'] for r in fleet}:
        log(f'unknown runner: {args.runner}')
        return 2
    due = owed(fleet, args.runner, load_json(args.runs, {}).get('runs'), enabled_faculties(args.sources))
    log(f"{args.runner} owes {', '.join(due) or 'nothing'}")
    github_output(owed=','.join(due))
    return 0


# What a faculty's record says about the runner that wrote it: the walls it met and its waits for them. A wall stands
# in front of one address, so a runner seeded from that record must not inherit them.
OWN_WALLS = ('wall', 'wait', 'blocked_at', 'walled_at')


def seed_line(state):
    """A runner's first line state out of the data branch's refresh-state.json: the faculties' records, the learned
    cooldowns and the pacing, without the walls whoever wrote them was standing at."""
    line = {k: copy.deepcopy(state.get(k)) if isinstance(state.get(k), dict) else {} for k in core.LINE_KEYS}
    for fac in line['faculties'].values():
        if isinstance(fac, dict):
            for key in OWN_WALLS:
                fac.pop(key, None)
    for entry in line['blocks'].values():
        if isinstance(entry, dict):
            entry['blocked_at'], entry['cause'] = None, None  # an open episode is that runner's
    return line


def cmd_seed(args):
    """A runner's first line state: the data branch's numbers, the best guess there is."""
    line = seed_line(load_json(args.state, {}))
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
    if args.owned is not None:  # exact, and may be empty: a runner that handed everything on owns no record
        owned = [f.strip() for f in args.owned.split(',') if f.strip()]
    else:
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


def _flag(outcome, key):
    return str(outcome.get(key, '')).lower() == 'true'


def _names(value):
    return [f for f in str(value or '').split(',') if f]


def _pairs(value):
    """[(faculty, runner)] out of 'wel:oracle,wml:plebania' (an outcome's `took`, `gave` or `cant`)."""
    out = []
    for item in _names(value):
        f, _, r = item.partition(':')
        if f and r:
            out.append((f, r))
    return out


def shard_key(shard):
    """A job's identity in a pass: its runner and its wave (always 1 now; older outcomes may say 2)."""
    try:
        wave = int(shard.get('wave') or 1)
    except (TypeError, ValueError):
        wave = 1
    return shard.get('runner'), wave


def latest(outcomes):
    """{runner: its outcome} (a later wave, an older pass's takeover, wins over an earlier one)."""
    got = {}
    for o in outcomes:
        if isinstance(o, dict) and isinstance(o.get('runner'), str):
            if o['runner'] not in got or shard_key(o)[1] >= shard_key(got[o['runner']])[1]:
                got[o['runner']] = o
    return got


RANK = {'blocked': 0, 'unfinished': 1, 'absent': 1, 'failed': 2, 'done': 3, 'empty': 3}


def faculty_views(matrix, outcomes):
    """{faculty: status} when the store cannot be read: what the runners last saw of it. Done when any runner saw it
    done; else blocked when any saw it blocked; else unfinished. An outcome without the per-faculty lists (an older
    crawl) counts its own faculties by its flags."""
    got = latest(outcomes)
    out = {}
    for m in matrix:
        for f in _names(m.get('faculties')):
            out.setdefault(f, 'absent')
    for m in matrix:
        o = got.get(m.get('runner'))
        if not isinstance(o, dict) or _flag(o, 'skipped'):
            continue
        if 'done_faculties' in o or 'blocked_faculties' in o or 'incomplete_faculties' in o:
            done, blocked = set(_names(o.get('done_faculties'))), set(_names(o.get('blocked_faculties')))
            unfinished = set(_names(o.get('incomplete_faculties')))
            if 'done_faculties' not in o:  # an older crawl: its own share, done unless it says otherwise
                done = {f for f in _names(m.get('faculties')) if f not in unfinished and f not in blocked}
        else:
            names = set(_names(m.get('faculties')))
            blocked = names if _flag(o, 'blocked') else set()
            unfinished = names if _flag(o, 'incomplete') else set()
            done = names - blocked - unfinished
        if _flag(o, 'failed'):
            done = set()
        for f in out:
            if f in done:
                out[f] = 'done'
            elif out[f] != 'done' and f in blocked:
                out[f] = 'blocked'
            elif out[f] not in ('done', 'blocked') and f in unfinished:
                out[f] = 'unfinished'
    return out


def read_outcomes(folder):
    return [load_json(p, None) for p in sorted(Path(folder).glob('shard-*.json'))] if Path(folder).is_dir() else []


def combine(matrix, outcomes, age_hours, summary=None):
    """One outcome for the pass (refresh-outcome.json, read by pages.yml's gate).

    Per faculty the store's verdict (`summary`, stack.py summarize) when there is one, else what the runners last saw
    (faculty_views). `pushed` is "true" when any runner pushed and "false" only when every one reported it did not; one
    that never reported leaves it empty, which the gate reads as "rebuild". A faculty left blocked makes the pass
    blocked; one unfinished or failed, or a runner that never reported, makes it incomplete.
    """
    got = latest(outcomes)
    seen = [got[m['runner']] for m in matrix if m['runner'] in got and not _flag(got[m['runner']], 'skipped')]
    missing = [m['runner'] for m in matrix if m['runner'] not in got or _flag(got[m['runner']], 'skipped')]
    if any(_flag(o, 'pushed') for o in seen):
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
    if isinstance(summary, dict) and isinstance(summary.get('faculties'), dict):
        wanted = list(dict.fromkeys(f for m in matrix for f in _names(m.get('faculties'))))
        status = {f: (summary['faculties'].get(f) or {}).get('status', 'absent') for f in wanted}
    else:
        status = faculty_views(matrix, outcomes)
    blocked = [f for f, v in status.items() if v == 'blocked']
    unfinished = [f for f, v in status.items() if v in ('unfinished', 'absent', 'failed')]
    degraded = any(_flag(o, 'degraded') for o in seen) or any(v == 'failed' for v in status.values())
    return {'pushed': pushed, 'changed': str(changed),
            'blocked': str(bool(blocked)).lower(),
            # with the store's verdicts a runner that never reported matters only through what it left undone
            'incomplete': str(bool(blocked or unfinished or (missing and not isinstance(summary, dict)))
                              or not matrix).lower(),
            'degraded': str(degraded).lower(),
            'missing': missing, 'blocked_faculties': blocked, 'status': status, 'current': age_hours < REPORT_HOURS}


def _matrix(text):
    try:
        value = json.loads(text or '[]')
    except ValueError:
        return []
    return [m for m in value if isinstance(m, dict) and isinstance(m.get('runner'), str)] if isinstance(value, list) else []


def cmd_combine(args):
    matrix = _matrix(args.matrix)
    outcomes = read_outcomes(args.dir)
    summary = load_json(args.summary, None) if args.summary else None
    age = (dt.datetime.now(dt.timezone.utc).timestamp() - float(args.planned or 0)) / 3600
    result = combine(matrix, outcomes, age, summary)
    Path(args.out).write_text(json.dumps({k: result[k] for k in ('pushed', 'changed', 'blocked')}) + '\n',
                              encoding='utf-8')
    github_output(blocked=result['blocked'], incomplete=result['incomplete'], degraded=result['degraded'],
                  current=str(result['current']).lower())
    lines = ['### Refresh outcome', '',
             'Per faculty from ' + ('the work stack' if summary else "the runners' own reports (the stack could not be read)")
             + ': ' + ', '.join(f'{f.upper()} {v}' for f, v in result['status'].items()), '',
             '| runner | faculties led | helped | could not list | pushed | changed | minutes |',
             '|---|---|---|---|---|---|---|']
    for o in outcomes:
        if not isinstance(o, dict):
            continue
        try:
            minutes = round((float(o['ended']) - float(o['started'])) / 60)
        except (KeyError, TypeError, ValueError):
            minutes = ''
        state = 'skipped (stale plan)' if _flag(o, 'skipped') else o.get('pushed', '')
        lines.append(f"| {o.get('runner', '?')} | {o.get('led', '') or o.get('faculties', '')} | "
                     f"{o.get('took', '')} | {o.get('cant', '')} | {state} | {o.get('changed', '')} | {minutes} |")
    if result['missing']:
        lines += ['', f"No outcome from: {', '.join(result['missing'])}."]
        log(f"::warning::no outcome from {', '.join(result['missing'])}")
    if result['blocked_faculties']:
        lines += ['', f"Blocked: {', '.join(result['blocked_faculties'])}."]
    if not result['current']:
        lines += ['', f'The plan is over {REPORT_HOURS} h old: issues are left to newer passes.']
    step_summary('\n'.join(lines) + '\n')
    log(json.dumps({k: v for k, v in result.items() if k != 'status'}))
    return 0


def parse(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('plan', help='split a pass over the runners that are online')
    p.add_argument('--state', default='data/refresh-state.json', help="the data branch's refresh-state.json")
    p.add_argument('--runners', help="GitHub's runner list (JSON array); missing = unknown")
    p.add_argument('--runs', help="the data branch's refresh-runs.json: who met which wall lately (walled_runners)")
    p.add_argument('--faculty', default='', help='comma-separated faculties (default: every enabled one)')
    p.add_argument('--catchup', default='', help='a runner back online: plan only what it owes (owed)')
    p.add_argument('--fleet', default=str(FLEET))
    p.add_argument('--sources', default=str(SOURCES))
    p = sub.add_parser('owed', help='what a runner back online owes from the passes it missed')
    p.add_argument('--runner', required=True, help="its name in fleet.json")
    p.add_argument('--runs', required=True, help="the data branch's refresh-runs.json")
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
    p.add_argument('--owned', default=None,
                   help="exactly the faculties whose records this runner publishes (refresh.py's owned_faculties); "
                        'overrides --faculty, may be empty')
    p.add_argument('--sources', default=str(SOURCES))
    p = sub.add_parser('combine', help="add the shards' outcomes up for pages.yml")
    p.add_argument('--matrix', default='[]', help="the plan's matrix (JSON)")
    p.add_argument('--handoff', default='[]', help=argparse.SUPPRESS)  # older workflows; nothing reads it
    p.add_argument('--summary', default='', help="the work stack's verdicts (stack.py summary); missing = the runners'")
    p.add_argument('--planned', default='0', help='when the plan was made (Unix seconds)')
    p.add_argument('--dir', required=True, help='where the shard-*.json outcomes are')
    p.add_argument('--out', required=True)
    return ap.parse_args(argv)


def main(argv=None):
    args = parse(argv)
    return {'plan': cmd_plan, 'owed': cmd_owed, 'seed': cmd_seed, 'merge': cmd_merge, 'combine': cmd_combine}[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())
