"""Shared pieces of the timetable refresh: block detection, change detection, validation and state.

Nothing here touches the network, so it is unit-tested offline (tests/test_refresh.py).
"""
import datetime as dt
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import build  # noqa: E402  (the site's own validator, so "valid here" means "builds there")

STATE_FILE = 'refresh-state.json'
# Lines that change on every run without the plan changing.
VOLATILE = ('X-PLAN-GENERATED', 'DTSTAMP', 'X-PLAN-UPDATED')


class Blocked(Exception):
    """The host answered with a block page or an unexpected status. The run must stop, never retry."""


def is_blocked(status, text):
    """True for an Incapsula block or any status other than 200.

    Good pages also carry an Incapsula *sensor* script (`_Incapsula_Resource?...`); that alone is not a block.
    """
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
    if previous:
        before, now = event_count(previous), event_count(ics)
        if before >= 5 and now < before * (1 - max_loss):
            return False, f'lost too many events ({before} -> {now})'
    return True, ''


def to_crlf(text):
    return text.replace('\r\n', '\n').replace('\n', '\r\n')


class State:
    """refresh-state.json: what was seen last time, so a run can resume and skip unchanged pages."""

    def __init__(self, path):
        self.path = Path(path)
        self.data = {'version': 1, 'groups': {}, 'faculties': {}}
        if self.path.is_file():
            try:
                loaded = json.loads(self.path.read_text(encoding='utf-8'))
                if loaded.get('version') == 1:
                    self.data = loaded
            except (OSError, ValueError):
                pass

    @property
    def groups(self):
        return self.data['groups']

    @property
    def faculties(self):
        return self.data['faculties']

    def fresh(self, code, now, hours):
        seen = self.groups.get(code, {}).get('checked')
        return bool(seen) and now - dt.datetime.fromisoformat(seen) < dt.timedelta(hours=hours)

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=1, sort_keys=True) + '\n', encoding='utf-8')
        tmp.replace(self.path)


def now_utc():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0, tzinfo=None)
