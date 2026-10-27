#!/usr/bin/env python3
"""Spread one refresh pass over the project's own runners (tools/refresh/fleet.json, docs/REFRESH.md).

The fleet is a fast machine that is often switched off and a slow one that is always up. Each pass:

  plan     (a GitHub-hosted job) asks GitHub which runners are online and splits the policy-group lanes between
           them, weighted by each runner's speed, so both finish at about the same time. A runner that is off gets
           nothing, so no job ever waits in the queue for a machine that is not coming.
  seed     gives a runner that has never crawled its own line state, copied from the data branch.
  merge    folds one runner's refresh-state.json into the data branch's newer one: the runners crawl disjoint
           faculties side by side and push to the same branch, so neither may overwrite what the other learned.
  help     (steal.py, during the crawl) a runner done with its own share takes work off one still at its: a part of
           the faculty it is crawling, or one it has not started. Each shard reports what it took and gave (`took`,
           `gave`), so the faculty counts as the runners that last held it left it, and a grant nobody confirmed as
           unfinished.
  handoff  (a GitHub-hosted job, after the crawl) gives what a runner left blocked or unfinished to another runner
           that is online now: a wall stands in front of one address, so the other machine often gets through. The
           plan has a runner wait a wall out only briefly when such a takeover is possible; when the other runner is
           gone by then, the runner that was blocked gets the rest of the wait.
  combine  (a GitHub-hosted job) adds the runners' outcomes up into the one refresh-outcome.json pages.yml reads,
           each faculty as the last runner that had it left it.

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
# How long a runner waits out a wall before it lets the faculty go (refresh.py --max-block-wait-minutes): the full wait
# when nobody could take over, a short one when another runner is up, which then takes the faculty in the handoff wave.
BLOCK_WAIT = 30
HANDOFF_WAIT = 5
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


def load_fleet(path=FLEET):
    """The runners from fleet.json, checked: [{name, label, speed, always_on, faculties, prefers, census}]."""
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
        if only is not None and not (isinstance(only, list) and all(isinstance(f, str) for f in only)):
            raise ValueError(f'{name}: faculties must be a list of faculty ids')
        for key, value in (('prefers', prefers), ('census', census)):
            if not (isinstance(value, list) and all(isinstance(f, str) for f in value)):
                raise ValueError(f'{name}: {key} must be a list of faculty ids')
        seen.add(name)
        fleet.append({'name': name, 'label': label, 'speed': float(speed), 'always_on': bool(r.get('always_on')),
                      'faculties': only, 'prefers': prefers, 'census': census})
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


def plan(fleet, wanted, state, online, avoid=None):
    """Split the lanes of `wanted` over the runners that are up.

    `online` is the set of labels GitHub reports online, or None when it could not be asked: then the always-on
    runners take everything (the job waits for them like a single-runner pass would). Lanes go out largest first,
    each to the runner that would finish it earliest (load / speed), so a fast runner takes a lot and a slow one the
    rest. A lane a runner up `prefers` (every faculty of it) goes to that runner whatever the load: a faculty tried
    from both machines that crawls as well from either stays off the fast one's share. A lane no runner up may take
    is left for the next pass. `avoid` maps a faculty to the runners that must not take it (the handoff wave: the
    runner that was blocked on it), so a preferred runner that left a lane behind does not get it back.

    Each shard says how long its runner should wait out a wall (`wait`, minutes): briefly when another runner up could
    take any of its faculties over, else the full wait. The wait is the whole share's, so one faculty nobody else may
    take (a runner limited by `faculties`) keeps the full wait for all of it: letting that one go early would only cost
    a takeover by the same runner for the rest of the wait.
    """
    avoid = avoid or {}
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
        keen = [r for r in able if all(f in r.get('prefers', ()) for f in lane)]
        best = min(keen or able, key=lambda r: ((load[r['name']] + cost) / r['speed'], -r['speed'], r['name']))
        load[best['name']] += cost
        shards[best['name']] += lane
    order = {f: i for i, f in enumerate(wanted)}
    out = [{'runner': r['name'], 'label': r['label'], 'faculties': ','.join(sorted(shards[r['name']], key=order.get)),
            'cost': round(load[r['name']]), 'eta': round(load[r['name']] / r['speed']),
            'wait': HANDOFF_WAIT if all(any(may_take(o, [f], {}) for o in up if o is not r)
                                        for f in shards[r['name']]) else BLOCK_WAIT}
           for r in up if shards[r['name']]]
    return {'shards': out, 'unassigned': sorted(unassigned, key=order.get), 'known': online is not None,
            'up': [r['name'] for r in up], 'down': [r['name'] for r in fleet if r not in up]}


def census_of(fleet, wanted):
    """{runner: 'wig,...'}: the censuses each runner takes this pass (its fleet.json `census` among the faculties
    wanted), whoever crawls those faculties. refresh.py runs each at most once a day; a takeover takes none."""
    return {r['name']: ','.join(f for f in wanted if f in r.get('census', ())) for r in fleet}


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
    fleet = load_fleet(args.fleet)
    result = plan(fleet, wanted, load_json(args.state, {}), online_labels(runners))
    census = census_of(fleet, wanted)
    for s in result['shards']:
        log(f"{s['runner']}: {s['faculties']} (work {s['cost']}, relative time {s['eta']})")
    for name in result['down']:
        log(f'{name}: offline, nothing')
    if result['unassigned']:
        log(f"::warning::no runner up may take {', '.join(result['unassigned'])}; left for the next pass")
    if not result['shards']:
        log('::warning::no runner of the fleet is online; this pass crawls nothing')
    matrix = [{'runner': s['runner'], 'label': s['label'], 'faculties': s['faculties'], 'wave': 1, 'wait': s['wait'],
               'census': census.get(s['runner'], '')} for s in result['shards']]
    planned = int(dt.datetime.now(dt.timezone.utc).timestamp())
    # runs.py records which servers were off and what nobody could take
    info = {'down': result['down'], 'unassigned': result['unassigned']}
    github_output(matrix=json.dumps(matrix, separators=(',', ':')), shards=len(matrix), planned=planned,
                  fleet=json.dumps(info, separators=(',', ':')))
    step_summary(plan_summary(result))
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
    """[(faculty, runner)] out of 'wel:oracle,wml:plebania' (an outcome's `took` or `gave`)."""
    out = []
    for item in _names(value):
        f, _, r = item.partition(':')
        if f and r:
            out.append((f, r))
    return out


def held(shard, outcome):
    """The faculties a shard ended its wave holding: its own and those it took from a peer (steal.py). One it handed
    on whole stays listed; its outcome then counts it neither blocked nor unfinished."""
    names = _names(shard.get('faculties'))
    if isinstance(outcome, dict):
        names += [f for f, _ in _pairs(outcome.get('took'))]
    return list(dict.fromkeys(names))


def unconfirmed(shards, got):
    """What a runner gave a peer that the peer's outcome does not say it took: [(faculty, peer, wave)]. The peer
    crashed, never read the grant or never reported, so the faculty is not done, whatever the giver says."""
    out = []
    for s in shards:
        o = got.get(shard_key(s))
        if not isinstance(o, dict):
            continue
        wave = shard_key(s)[1]
        for f, to in _pairs(o.get('gave')):
            r = got.get((to, wave))
            if not (isinstance(r, dict) and not _flag(r, 'skipped') and (f, s['runner']) in _pairs(r.get('took'))):
                out.append((f, to, wave))
    return out


def shard_key(shard):
    """A shard's identity in a pass: its runner and its wave (1 the plan, 2 the handoff)."""
    try:
        wave = int(shard.get('wave') or 1)
    except (TypeError, ValueError):
        wave = 1
    return shard.get('runner'), wave


def left_over(shard, outcome):
    """The faculties of a shard that another runner should take, and why: [(faculty, 'blocked' | 'unfinished')].

    A shard that never reported, was skipped (stale plan) or crashed leaves all of them; one that reported leaves those
    it ended blocked on and those it did not finish (a time limit, a page it could not read). A report without the
    per-faculty lists (an older crawl) leaves everything when it was blocked or incomplete at all. What the shard took
    from a peer during the wave counts like its own."""
    names = held(shard, outcome)
    if not isinstance(outcome, dict) or _flag(outcome, 'skipped') or _flag(outcome, 'failed'):
        return [(f, 'unfinished') for f in names]
    if 'blocked_faculties' in outcome or 'incomplete_faculties' in outcome:
        blocked = set(_names(outcome.get('blocked_faculties')))
        unfinished = set(_names(outcome.get('incomplete_faculties'))) | blocked
    elif _flag(outcome, 'blocked') or _flag(outcome, 'incomplete'):
        blocked = set(names) if _flag(outcome, 'blocked') else set()
        unfinished = set(names)
    else:
        return []
    return [(f, 'blocked' if f in blocked else 'unfinished') for f in names if f in unfinished]


def _wait(shard):
    """The minutes a plan's shard was told to wait a wall out (the full wait when it does not say)."""
    try:
        wait = float(shard.get('wait'))
    except (TypeError, ValueError):
        return BLOCK_WAIT
    return wait if 0 <= wait <= BLOCK_WAIT else BLOCK_WAIT


def handoff(fleet, shards, outcomes, state, online):
    """The handoff wave: what the plan's runners left blocked or unfinished, for another runner that is up now.

    `online` is asked afresh (a runner may have come up or gone since the plan). A faculty does not go back to the
    runner that left it: a wall is per address, and a runner that crashed or never started may do so again. Lanes stay
    whole, as in the plan, and go out by the same weighting; what no other runner up may take waits for the next pass.

    One exception keeps the plan's promise of a full wait: a lane its runner let go blocked after only the short wait,
    because the plan saw another runner up that has gone since, goes back to that runner (when it is still up) for the
    rest of the wait. The takeover's `from` then names the runner itself.
    """
    got = {shard_key(o): o for o in outcomes if isinstance(o, dict)}
    avoid, origin, wanted, waited = {}, {}, [], {}
    left = [(f, why, s['runner'], _wait(s)) for s in shards for f, why in left_over(s, got.get(shard_key(s)))]
    # a grant the peer never confirmed: that peer may have crashed, so it is avoided like one that left it
    left += [(f, 'unfinished', to, BLOCK_WAIT) for f, to, _ in unconfirmed(shards, got)]
    for f, why, runner, wait in left:
        # two runners may leave one faculty (a part each, steal.py): both are avoided, a wall is what is reported
        avoid.setdefault(f, set()).add(runner)
        if f not in origin or (why == 'blocked' and origin[f]['why'] != 'blocked'):
            origin[f] = {'runner': runner, 'why': why}
            waited[f] = wait
        if f not in wanted:
            wanted.append(f)
    if not wanted:
        return {'shards': [], 'unassigned': [], 'left': {}, 'known': online is not None}
    # a lane's faculties hand off together, in the order the plan had them
    result = plan(fleet, wanted, state, online, avoid)
    for shard in result['shards']:
        shard['wait'] = BLOCK_WAIT  # nobody after this wave: wait the wall out
    by_name = {r['name']: r for r in fleet}
    taking = {s['runner']: s for s in result['shards']}
    order = {f: i for i, f in enumerate(wanted)}
    for lane in lanes_of(result['unassigned']):
        runner = by_name.get(origin[lane[0]]['runner'])
        short = [f for f in lane if origin[f]['why'] == 'blocked' and waited[f] < BLOCK_WAIT]
        if not short or runner is None or runner['name'] not in result['up'] or not may_take(runner, lane, {}):
            continue
        rest = max(1, round(BLOCK_WAIT - max(waited[f] for f in short)))
        shard = taking.get(runner['name'])
        if shard is None:
            shard = taking[runner['name']] = {'runner': runner['name'], 'label': runner['label'], 'faculties': '',
                                              'cost': 0, 'eta': 0, 'wait': rest}
            result['shards'].append(shard)
        else:
            shard['wait'] = max(shard['wait'], rest)
        shard['faculties'] = ','.join(sorted(_names(shard['faculties']) + lane, key=order.get))
        result['unassigned'] = [f for f in result['unassigned'] if f not in lane]
    for shard in result['shards']:
        shard['wave'] = 2
        shard['from'] = ','.join(f"{f}:{origin[f]['runner']}" for f in _names(shard['faculties']))
    result['left'] = origin
    return result


def combine(shards, outcomes, age_hours):
    """One outcome for the pass out of its shards' outcomes (refresh-outcome.json, read by pages.yml's gate).

    `shards` lists the plan's shards and then the handoff's (wave 2). A faculty counts as the last wave that had it left
    it: blocked on oracle and then crawled cleanly by plebania is not blocked. Within that wave every runner that held
    a part of it counts (steal.py), and a grant nobody confirmed leaves it unfinished. `pushed` is "true" when any shard
    pushed and "false" only when every shard reported it did not; a shard that never reported leaves it empty, which the
    gate reads as "rebuild". A faculty whose last shard never reported makes the pass incomplete, so it neither files
    nor closes issues on what it did not see.
    """
    got = {shard_key(o): o for o in outcomes if isinstance(o, dict)}
    last = {}  # faculty -> (its last wave, the shards that held it then)
    for s in sorted(shards, key=lambda s: shard_key(s)[1]):
        wave = shard_key(s)[1]
        for f in held(s, got.get(shard_key(s))):
            if f not in last or last[f][0] < wave:
                last[f] = (wave, [s])
            elif s not in last[f][1]:
                last[f][1].append(s)
    seen = [got[shard_key(s)] for s in shards if shard_key(s) in got and not _flag(got[shard_key(s)], 'skipped')]
    missing = [s['runner'] for s in shards if shard_key(s) not in got or _flag(got[shard_key(s)], 'skipped')]
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
    blocked, unfinished = [], []
    lost = {f for f, _, wave in unconfirmed(shards, got) if f in last and last[f][0] == wave}
    for f, (_, held_by) in last.items():
        whys = {why for s in held_by for g, why in left_over(s, got.get(shard_key(s))) if g == f}
        if 'blocked' in whys:
            blocked.append(f)
        elif whys or f in lost:
            unfinished.append(f)
    finals = [got[k] for k in {shard_key(s) for _, held_by in last.values() for s in held_by} if k in got]
    return {'pushed': pushed, 'changed': str(changed),
            'blocked': str(bool(blocked)).lower(),
            'incomplete': str(bool(blocked or unfinished) or not shards).lower(),
            'degraded': str(any(_flag(o, 'degraded') for o in finals)).lower(),
            'missing': missing, 'blocked_faculties': blocked, 'current': age_hours < REPORT_HOURS}


def _matrix(text):
    try:
        value = json.loads(text or '[]')
    except ValueError:
        return []
    return [m for m in value if isinstance(m, dict) and isinstance(m.get('runner'), str)] if isinstance(value, list) else []


def read_outcomes(folder):
    return [load_json(p, None) for p in sorted(Path(folder).glob('shard-*.json'))] if Path(folder).is_dir() else []


def handoff_summary(result):
    lines = ['### Handoff', '']
    if not result['shards'] and not result['unassigned']:
        return '\n'.join(lines + ['Every faculty of the plan was finished where it was planned: nothing to hand off.']) + '\n'
    lines += ['| runner | takes over | from | waits a wall out |', '|---|---|---|---|']
    for s in result['shards']:
        lines.append(f"| {s['runner']} | {s['faculties']} | {s['from'].replace(',', ', ')} | {s['wait']:g} min |")
    if result['unassigned']:
        lines += ['', f"No other runner up may take: {', '.join(result['unassigned'])} (left for the next pass)."]
    return '\n'.join(lines) + '\n'


def cmd_handoff(args):
    runners = load_json(args.runners, None, list) if args.runners else None
    result = handoff(load_fleet(args.fleet), _matrix(args.matrix), read_outcomes(args.dir), load_json(args.state, {}),
                     online_labels(runners))
    for f, o in result['left'].items():
        log(f"{f}: left {o['why']} by {o['runner']}")
    for s in result['shards']:
        log(f"{s['runner']} takes over {s['faculties']} (waits a wall out up to {s['wait']:g} min)")
    if result['unassigned']:
        log(f"::warning::no other runner up may take {', '.join(result['unassigned'])}; left for the next pass")
    matrix = [{'runner': s['runner'], 'label': s['label'], 'faculties': s['faculties'], 'wave': 2, 'wait': s['wait'],
               'from': s['from']} for s in result['shards']]
    github_output(matrix=json.dumps(matrix, separators=(',', ':')), shards=len(matrix),
                  planned=int(dt.datetime.now(dt.timezone.utc).timestamp()))
    step_summary(handoff_summary(result))
    return 0


def cmd_combine(args):
    shards = _matrix(args.matrix) + [dict(m, wave=2) for m in _matrix(args.handoff)]
    outcomes = read_outcomes(args.dir)
    age = (dt.datetime.now(dt.timezone.utc).timestamp() - float(args.planned or 0)) / 3600
    result = combine(shards, outcomes, age)
    Path(args.out).write_text(json.dumps({k: result[k] for k in ('pushed', 'changed', 'blocked')}) + '\n',
                              encoding='utf-8')
    github_output(blocked=result['blocked'], incomplete=result['incomplete'], degraded=result['degraded'],
                  current=str(result['current']).lower())
    lines = ['### Refresh outcome', '', '| runner | wave | faculties | pushed | changed | blocked on | minutes |',
             '|---|---|---|---|---|---|---|']
    for o in outcomes:
        if not isinstance(o, dict):
            continue
        try:
            minutes = round((float(o['ended']) - float(o['started'])) / 60)
        except (KeyError, TypeError, ValueError):
            minutes = ''
        state = 'skipped (stale plan)' if _flag(o, 'skipped') else o.get('pushed', '')
        lines.append(f"| {o.get('runner', '?')} | {shard_key(o)[1]} | {o.get('faculties', '')} | {state} | "
                     f"{o.get('changed', '')} | {o.get('blocked_faculties', '') or ('yes' if _flag(o, 'blocked') else '')} | "
                     f"{minutes} |")
    if result['missing']:
        lines += ['', f"No outcome from: {', '.join(result['missing'])}."]
        log(f"::warning::no outcome from {', '.join(result['missing'])}")
    if result['blocked_faculties']:
        lines += ['', f"Still blocked after the handoff: {', '.join(result['blocked_faculties'])}."]
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
    p.add_argument('--owned', default=None,
                   help="exactly the faculties whose records this runner publishes (refresh.py's owned_faculties); "
                        'overrides --faculty, may be empty')
    p.add_argument('--sources', default=str(SOURCES))
    p = sub.add_parser('handoff', help='give what one runner left blocked or unfinished to another one that is up')
    p.add_argument('--matrix', default='[]', help="the plan's matrix (JSON)")
    p.add_argument('--dir', required=True, help="where the plan's shard-*.json outcomes are")
    p.add_argument('--state', default='data/refresh-state.json', help="the data branch's refresh-state.json")
    p.add_argument('--runners', help="GitHub's runner list now (JSON array); missing = unknown")
    p.add_argument('--fleet', default=str(FLEET))
    p = sub.add_parser('combine', help="add the shards' outcomes up for pages.yml")
    p.add_argument('--matrix', default='[]', help="the plan's matrix (JSON)")
    p.add_argument('--handoff', default='[]', help="the handoff's matrix (JSON)")
    p.add_argument('--planned', default='0', help='when the plan was made (Unix seconds)')
    p.add_argument('--dir', required=True, help='where the shard-*.json outcomes are')
    p.add_argument('--out', required=True)
    return ap.parse_args(argv)


def main(argv=None):
    args = parse(argv)
    return {'plan': cmd_plan, 'seed': cmd_seed, 'merge': cmd_merge, 'handoff': cmd_handoff,
            'combine': cmd_combine}[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())
