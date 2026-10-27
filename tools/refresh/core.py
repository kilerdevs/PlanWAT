"""Shared pieces of the timetable refresh: block detection, change detection, validation and state.

Nothing here touches the network, so it is unit-tested offline (tests/test_refresh.py).
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import build  # noqa: E402  (the site's own validator, so "valid here" means "builds there")

STATE_FILE = 'refresh-state.json'
# Check stamps the volunteer coordinator accepted (tools/volunteer/collect.py), keyed CODE@term.
VOLUNTEER_STATE_FILE = 'volunteer-state.json'
# What a crawl learns about its own line (per-faculty runs, learned block durations, AIMD pacing). A volunteer
# and each project runner keep these in a file of their own (--faculty-state): every line meets its own walls.
LINE_KEYS = ('faculties', 'blocks', 'pacing')
# Lines that change on every run without the plan changing.
VOLATILE = ('X-PLAN-GENERATED', 'DTSTAMP', 'X-PLAN-UPDATED')


class Blocked(Exception):
    """The host answered with a block page or an unexpected status. The run must stop, never retry."""


class Gone(Exception):
    """A listing page answered 404 or 410: the faculty moved or removed it. Not a wall (nothing to wait out): the
    main pass reports the faculty unlisted and degraded, the coming semester's pass reads it as not published yet."""


class NotReady(Exception):
    """A converter found a healthy plan of another semester (a PDF, which page_ok/not_ready cannot read)."""


# How long a faculty stays blocked: learned from history, so the crawler waits out
# the block instead of hammering a wall. Bounds keep a thin history honest.
BLOCK_DEFAULT = 2 * 3600   # no history yet: assume a couple of hours
BLOCK_MIN = 20 * 60        # never wait less than this between recovery probes
BLOCK_MAX = 12 * 3600      # never assume longer than this
BLOCK_KEEP = 10            # remembered recoveries per faculty


# Faculties behind one Incapsula policy share one learned cooldown: a wall tripped
# through either address is the same wall.
POLICY_GROUPS = {'wlo': 'wat-edge', 'wel': 'wat-edge'}


def group_of(name):
    """The policy group a faculty learns its block cooldown with (its own name unless shared)."""
    return POLICY_GROUPS.get(name, name)


class BlockModel:
    """Learned block durations, persisted in refresh-state.json under 'blocks'.

    Every recovery teaches the model how long that policy group's wall usually lasts;
    the estimate (median, clamped) tells the waiter when probing is worth a request.
    Durations remember their cause: a 'wall' (the host said no) predicts the next wall
    better than a 'flaky' (our own network wobbled) episode, so wall-caused durations
    win when any exist. Method arguments stay faculty names; grouping happens inside.
    """

    def __init__(self, data):
        self.data = data.setdefault('blocks', {})

    def _entry(self, name):
        return self.data.setdefault(group_of(name), {'durations': [], 'blocked_at': None, 'cause': None})

    def _pool(self, name):
        pool = []
        for item in self._entry(name)['durations']:
            if isinstance(item, dict):
                dur, cause = item.get('dur'), item.get('cause')
            else:  # pre-cause entries written by older runs
                dur, cause = item, None
            if isinstance(dur, (int, float)):
                pool.append((float(dur), cause))
        walls = [(d, c) for d, c in pool if c == 'wall']
        return walls or pool

    def estimate(self, name):
        """Seconds to wait before the block is probably gone."""
        import statistics
        pool = [dur for dur, _ in self._pool(name)]
        if not pool:
            return BLOCK_DEFAULT
        return min(BLOCK_MAX, max(BLOCK_MIN, statistics.median(pool)))

    def note_blocked(self, name, cause=None, at=None):
        entry = self._entry(name)
        entry['blocked_at'] = (at or now_utc()).isoformat()
        entry['cause'] = cause

    def note_recovered(self, name, at=None):
        """Close the episode: remember how long this block lasted. Returns the duration or None."""
        entry = self._entry(name)
        if not entry['blocked_at']:
            return None
        try:
            start = dt.datetime.fromisoformat(entry['blocked_at'])
        except ValueError:
            start = None
        entry['blocked_at'] = None
        if start is None:
            return None
        now = at or now_utc()
        duration = max(0, (now - start).total_seconds())
        entry['durations'].append({'dur': duration, 'cause': entry.get('cause'), 'at_iso': now.isoformat()})
        del entry['durations'][:-BLOCK_KEEP]
        entry['cause'] = None
        return duration


def public_room(room):
    """A room text that may be published: every ';'/','-separated part naming a person (build's own rule: a title before
    a name, or a lecturer alias) is dropped, so a cell parsed into the wrong column never puts staff into a calendar
    nor keeps the whole plan out. A room without such a part comes back unchanged."""
    parts = [p.strip() for p in re.split(r'[;,]', room or '')]
    if not any(p and build.names_person(p) for p in parts):
        return room
    return ';'.join(p for p in parts if p and not build.names_person(p))


def check_listing(status, text, what):
    """A listing page's answer: Gone for 404/410 (the page moved), Blocked for a wall (is_blocked), else nothing."""
    if status in (404, 410):
        raise Gone(f'{what}: HTTP {status}, the page is gone')
    if is_blocked(status, text):
        raise Blocked(f'{what}: HTTP {status}')


def is_blocked(status, text):
    """True for an Incapsula block or any status other than 200.

    Good pages also carry an Incapsula *sensor* script (`_Incapsula_Resource?...`); that alone is not a block.
    304 (Not Modified, from a conditional refresh) is a healthy answer: the page is unchanged.
    """
    if status == 304:
        return False
    if status != 200:
        return True
    return (('main-iframe' in text and 'incident_id=' in text)
            or 'Request unsuccessful. Incapsula' in text
            or 'Incapsula incident ID' in text)


def season_of(today):
    """(season, first year) of the semester running on `today`: Sep-Feb winter, Mar-Aug summer."""
    if today.month >= 9:
        return 'zima', today.year
    if today.month <= 2:
        return 'zima', today.year - 1
    return 'lato', today.year - 1


def term_id(today):
    season, year = season_of(today)
    return f'{year}-{(year + 1) % 100:02d}-{season}'


def publishing(today):
    """Whether `today` falls in a publication window: August (winter plans) and January/February (summer plans),
    when the faculties publish the coming semester."""
    return today.month in (1, 2, 8)


def effective_fresh_hours(base, today):
    """The skip threshold actually used: halved during the publication windows (publishing), when pages go stale
    twice as fast.
    """
    if publishing(today):
        return base / 2
    return base


# A group whose page still shows another semester is asked again after fresh hours doubled per such check, at most
# this many hours apart; in a publication window every pass asks it, the plan may appear any time.
NOT_READY_CAP_HOURS = 12


def not_ready_wait(entry, tid, base_hours, today):
    """Hours a group found not ready for `tid` may go unasked (0: ask it now)."""
    mark = entry.get('not_ready') if isinstance(entry, dict) else None
    if publishing(today) or not isinstance(mark, dict) or mark.get('term') != tid:
        return 0
    streak = mark.get('streak')
    if not isinstance(streak, int) or isinstance(streak, bool) or streak < 1:
        return 0
    return min(NOT_READY_CAP_HOURS, base_hours * 2 ** min(streak, 16))


def still_not_ready(entry, tid, now, base_hours, today):
    """Whether a group found not ready for `tid` is still inside its wait (not_ready_wait) at `now`."""
    hours = not_ready_wait(entry, tid, base_hours, today)
    if not hours:
        return False
    try:
        at = dt.datetime.fromisoformat(entry['not_ready']['at'])
    except (KeyError, TypeError, ValueError):
        return False
    return at <= now and now - at < dt.timedelta(hours=hours)


def quiet_interval(entry, base_hours, cap_hours):
    """Hours a group that keeps coming back unchanged may go unchecked.

    Every completed check that found the same plan raises the gap before the
    next one twofold (base) and the `cap_hours` fence stops it (<=0 disables
    the stretching); a change (streak reset to 0) puts the group back on the
    full cadence at once. The result never drops below `base_hours`, so a
    faculty's own --fresh-hours always dominates a too-low cap. An entry
    without a recognised `streak` (a state file written before this existed,
    a hand-edited one) counts as a first check: the old behaviour exactly.
    """
    streak = entry.get('streak') if isinstance(entry, dict) else None
    if cap_hours <= 0 or not isinstance(streak, int) or streak < 0:
        return base_hours
    return max(base_hours, min(cap_hours, base_hours * 2 ** streak))


def upcoming_reference(today):
    """A date inside the semester that is about to start, while the faculties publish its plans ahead of time.

    August -> the winter semester (from 1 September), January and February -> the summer one (from 1 March).
    None the rest of the year. Both semesters are then refreshed side by side, each into its own term folder."""
    if today.month == 8:
        return dt.date(today.year, 9, 1)
    if today.month in (1, 2):
        return dt.date(today.year, 3, 1)
    return None


def term_window(tid):
    """(first, last) day, as YYYYMMDD, that lessons of the term `2026-27-zima` / `2026-27-lato` may fall on."""
    return build.term_window(tid)


def period_label(prefix, today):
    season, year = season_of(today)
    return f'{prefix} {season} {year}/{year + 1}'


def group_code(stem, prefix, keep_prefixes=()):
    """The site's group code for a page named `stem`, or None when it is not a group code.

    Pages such as `1PL26KP` do not carry the faculty prefix the site groups by, so it is added; codes already
    starting with a faculty (or a listed foreign prefix) stay as they are.
    """
    known = tuple(build.FACULTY_CODES) + tuple(keep_prefixes)
    code = stem if (not prefix or stem.upper().startswith(known)) else prefix + stem
    return code if build.GROUP_RE.match(code) else None


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def _stable(ics):
    return [l for l in ics.replace('\r\n', '\n').split('\n') if not l.startswith(VOLATILE)]


def plan_hash(ics):
    """A digest of the plan itself: two calendars with the same plan_hash differ only in volatile lines."""
    return sha256('\n'.join(_stable(ics)).encode('utf-8'))


def same_plan(old, new):
    """True when two calendars differ only in volatile header lines."""
    return old is not None and _stable(old) == _stable(new)


def event_count(ics):
    return ics.count('BEGIN:VEVENT')


def validate(ics, code, tid, previous=None, max_loss=0.4):
    """(ok, reason). The calendar must build, carry its own code, and not shrink suspiciously."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / tid / f'{code}.ics'
        path.parent.mkdir()
        path.write_bytes(ics.encode('utf-8'))
        try:
            build.load_term(path)
        except build.BuildError as err:
            return False, str(err).replace(str(path), f'{tid}/{code}.ics')
    if not event_count(ics):
        return False, 'no events'
    first, last = term_window(tid)
    starts = re.findall(r'BEGIN:VEVENT.*?DTSTART[^:\r\n]*:(\d{8})', ics, re.S)
    inside = sum(first <= d <= last for d in starts)
    if starts and inside * 2 < len(starts):
        return False, f'most lessons fall outside the term ({min(starts)}..{max(starts)}): the faculty shows another semester'
    if previous:
        before, now = event_count(previous), event_count(ics)
        if before >= 5 and now < before * (1 - max_loss):
            return False, f'lost too many events ({before} -> {now})'
    return True, ''


def clip_to_term(ics, tid):
    """The calendar text without lessons dated outside the term's window (see build.clip_to_term)."""
    return build.clip_to_term(ics.encode('utf-8'), tid).decode('utf-8')


def to_crlf(text):
    return text.replace('\r\n', '\n').replace('\n', '\r\n')


def term_season_of_ymd(ymd):
    """'zima' for Sep-Feb dates, 'lato' otherwise (matches season_of())."""
    month = int(ymd[4:6])
    return 'zima' if month >= 9 or month <= 2 else 'lato'


def reconcile_term_bounds(new_ics, old_ics, tid):
    """(ics, patched). Keep the filed term's grid when the faculty flips its term label.

    Converters take the semester bounds from the page's term link. When the faculty moves
    that link to another semester while the lessons still belong to the filed term (e.g.
    WCY pages pointing at lato 2027 with zima lessons on them), publishing the flipped
    bounds would shift the site's week grid away from the lessons and render an empty page.
    In that case the old file's bounds are restored; the lessons (which decide everything
    else) are untouched. No old file, or an old file flipped too, means nothing to restore.
    """
    season = tid.split('-')[-1]
    new_start = re.search(r'X-PLAN-SEMESTER-START:(\d{8})', new_ics or '')
    if not new_start or term_season_of_ymd(new_start.group(1)) == season:
        return new_ics, False
    old_start = re.search(r'X-PLAN-SEMESTER-START:(\d{8})', old_ics or '')
    old_end = re.search(r'X-PLAN-SEMESTER-END:(\d{8})', old_ics or '')
    if not old_start or term_season_of_ymd(old_start.group(1)) != season or not old_end:
        return new_ics, False
    patched = re.sub(r'X-PLAN-SEMESTER-START:\d{8}',
                     f'X-PLAN-SEMESTER-START:{old_start.group(1)}', new_ics)
    patched = re.sub(r'X-PLAN-SEMESTER-END:\d{8}',
                     f'X-PLAN-SEMESTER-END:{old_end.group(1)}', patched)
    return patched, True


class State:
    """refresh-state.json: what was seen last time, so a run can resume and skip unchanged pages."""

    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self.data = {'version': 1, 'groups': {}, 'faculties': {}}
        if self.path.is_file():
            try:
                loaded = json.loads(self.path.read_text(encoding='utf-8'))
                if not isinstance(loaded, dict):
                    raise ValueError(f'holds a JSON {type(loaded).__name__}, not an object')
                if loaded.get('version') == 1:
                    for key in ('groups', 'faculties'):
                        if not isinstance(loaded.setdefault(key, {}), dict):
                            raise ValueError(f'has a "{key}" that is not an object')
                    self.data = loaded
            except ValueError as err:
                # Unparseable JSON, or JSON of the wrong shape (which would only crash the crawl later):
                # quarantine the file so the evidence survives, then start fresh.
                why = 'is not valid JSON' if isinstance(err, json.JSONDecodeError) else str(err)
                stamp = now_utc().strftime('%Y%m%dT%H%M%SZ')
                backup = self.path.with_name(self.path.name + f'.corrupt-{stamp}')
                try:
                    self.path.rename(backup)
                    where = f' (quarantined to {backup.name})'
                except OSError:
                    where = ' (quarantine failed, dropping it)'
                print(f'REFRESH STATE CORRUPT: {self.path} {why}{where}; starting fresh', flush=True)
            except OSError:
                pass
        self.accepted = load_accepted(self.path.with_name(VOLUNTEER_STATE_FILE))

    @property
    def groups(self):
        return self.data['groups']

    @property
    def faculties(self):
        return self.data['faculties']

    def fresh(self, code, now, hours, tid=None):
        """True when the group was checked recently enough to skip. False when the checked
        stamp lies in the future (clock skew: recheck rather than trust it) and, when `tid`
        is given, when the entry belongs to another term (stale-term entries recheck once)."""
        entry = self.groups.get(code, {})
        seen = entry.get('checked')
        if tid is not None and entry.get('term') != tid:
            seen = None
        if tid is not None:
            # A check the volunteer coordinator accepted counts as well, whichever is newer.
            other = self.accepted.get(code if '@' in code else f'{code}@{tid}')
            other = other.get('checked') if isinstance(other, dict) else None
            if isinstance(other, str) and (not seen or other > seen):
                seen = other
        if not seen:
            return False
        try:
            checked = dt.datetime.fromisoformat(seen)
        except ValueError:
            return False
        if checked > now:
            return False
        return now - checked < dt.timedelta(hours=hours)

    def save(self):
        """Atomic write. Safe while other lanes keep mutating the data: serialised under a lock, and a
        dump that races an insert ("dictionary changed size") is simply retried."""
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            for attempt in range(5):
                try:
                    text = json.dumps(self.data, ensure_ascii=False, indent=1, sort_keys=True) + '\n'
                    break
                except RuntimeError:
                    if attempt == 4:
                        raise
            tmp = self.path.with_suffix('.tmp')
            tmp.write_text(text, encoding='utf-8')
            tmp.replace(self.path)


def load_accepted(path):
    """{CODE@term: {checked, changed, ...}} from volunteer-state.json; {} when there is none."""
    try:
        groups = json.loads(Path(path).read_text(encoding='utf-8')).get('groups', {})
    except (OSError, ValueError, AttributeError):
        return {}
    return groups if isinstance(groups, dict) else {}


def clock_offset():
    """Seconds to add to this machine's clock (PLANWAT_CLOCK_OFFSET): a volunteer's crawler measures how far its
    host is off GitHub's clock and corrects its stamps, so a drifting host does not get its bundles refused."""
    try:
        offset = float(os.environ.get('PLANWAT_CLOCK_OFFSET', '0') or 0)
    except ValueError:
        return 0.0
    return offset if abs(offset) <= 86400 else 0.0


def now_utc():
    moment = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=clock_offset())
    return moment.replace(microsecond=0, tzinfo=None)
