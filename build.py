#!/usr/bin/env python3
"""Build the static site from the timetables in timetables/<term>/<GROUP>.ics.

Output (default: site/):
    index.html            group list (redirects straight to the group while there is only one)
    <GROUP>/index.html    the timetable page; it fetches ./plan.ics and renders it in the browser
    <GROUP>/plan.ics      the group's current term, byte-for-byte (minus lessons of another semester, see clip_to_term)
    <GROUP>/plan-przypomnienia.ics   the same calendar with a reminder 15 minutes before each class
    mapa/index.html       campus map: MapLibre, OpenFreeMap's style, tiles, glyphs and sprites, all vendored in src/map/
    prywatnosc/index.html privacy notice and terms of use
    assets/               the styles and scripts the pages share (each name carries a hash of its bytes)
    pokrycie-wydzialow.svg  faculty coverage chart for README.md, drawn from the groups of this build
    sw.js, manifest.webmanifest, <GROUP>/manifest.webmanifest, icons/   offline worker and home-screen app
    robots.txt, .well-known/security.txt
    sitemap.xml           every indexable page, written when --site-url gives the absolute address (not for --noindex)
    404.html

Every page carries a hash-pinned Content-Security-Policy in a <meta> tag (GitHub Pages cannot send
headers): inline code by hash, the shared files under assets/ by origin — a meta hash cannot cover an
external file, so each of those is instead pinned by the integrity attribute of the tag that loads it.
For the Docker/nginx deployment, --nginx writes the union of those hashes (plus frame-ancestors, which
only works as a header) into the given nginx.conf; the Dockerfile does this on its own copy of
deploy/nginx.conf, so no tracked file is ever rewritten.

    python3 build.py                                  # site/, terms picked for today
    python3 build.py --base-path /PlanWAT --today 2026-10-15
    python3 build.py --out /site --nginx deploy/nginx.conf   # inside the Docker build
    python3 build.py --base-path /PlanWAT --site-url https://kilerdevs.github.io/PlanWAT   # GitHub Pages

With --site-url the pages also carry a canonical URL, absolute Open Graph links and a sitemap; titles,
descriptions and structured data (JSON-LD) are written either way.
"""
import argparse
import base64
import collections
import dataclasses
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path

import profiles  # plan profiles for data/profiles.json; sits next to this file

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
MARKER = '.planwat-site'
DATA_DIR = 'data'  # site/data/: the JSON files behind the group page's tools
GROUP_RE = re.compile(r'^[A-Za-z0-9_]{2,32}$')
TERM_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,47}$')
# Inter, served from the site's own assets/ (src/fonts/, SIL OFL 1.1) in the two subsets Polish text needs. It sits
# behind SF Pro in every font stack, so the unicode-range rules let a browser fetch only what it actually draws with it,
# and Apple devices nothing at all.
FONTS = (
    ('inter-latin', 'U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, '
                    'U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD'),
    ('inter-latin-ext', 'U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, '
                        'U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C4, U+2113, U+2C60-2C7F, U+A720-A7FF'),
)
MAP_DIR = 'mapa'  # site/mapa/: the campus map
REMINDER_FILE = 'plan-przypomnienia.ics'  # <GROUP>/plan.ics with an alarm before every class
REMINDER_MINUTES = 15
# Extra CSP sources of the map page only: the blob: worker MapLibre renders in and the blob: images it decodes.
# Everything else the map needs (engine, style, tiles, glyphs, sprites) is vendored in src/map/ and served from
# mapa/ on the site's own origin (tools/map/vendor_map.py refreshes it).
MAP_CSP = {
    'img-src': ['blob:'],
    'worker-src': ['blob:'],
    'child-src': ['blob:'],
}
# The index and group pages register the offline service worker (site/sw.js) and link a web app manifest
# with same-origin icons.
APP_CSP = {
    'img-src': ["'self'"],
    'worker-src': ["'self'"],
    'manifest-src': ["'self'"],
}
# The map links the manifest too (so it can be installed from there), but registers no worker of its own.
MAP_APP_CSP = {'manifest-src': ["'self'"]}
ICONS_DIR = 'icons'  # site/icons/: app icons named by the manifests
PRIVACY_DIR = 'prywatnosc'  # site/prywatnosc/: privacy notice and terms of use
ASSETS_DIR = 'assets'  # site/assets/: styles and scripts shared by the pages, named after their content hash
REPO_URL = 'https://github.com/kilerdevs/PlanWAT'
SITE_NAME = 'PlanWAT'  # the name search engines and link previews show
OG_IMAGE = f'{ICONS_DIR}/icon-512.png'  # the link-preview picture
NOINDEX = '<meta name="robots" content="noindex, nofollow">'
SW_FILE = 'sw.js'


def merge_csp(*extras):
    out = {}
    for extra in extras:
        for name, sources in extra.items():
            out[name] = out.get(name, []) + [s for s in sources if s not in out.get(name, [])]
    return out

# Canonical faculties offered on the front page (code -> Polish name).
# A group belongs to the faculty matching the first three letters of its code;
# anything else is listed under "Pozostałe grupy".
FACULTIES = [
    ('IOE', 'Instytut Optoelektroniki'),
    ('WCY', 'Wydział Cybernetyki'),
    ('WEL', 'Wydział Elektroniki'),
    ('WIG', 'Wydział Inżynierii Lądowej i Geodezji'),
    ('WIM', 'Wydział Inżynierii Mechanicznej'),
    ('WLO', 'Wydział Bezpieczeństwa, Logistyki i Zarządzania'),
    ('WML', 'Wydział Mechatroniki, Uzbrojenia i Lotnictwa'),
    ('WTC', 'Wydział Nowych Technologii i Chemii'),
]
FACULTY_CODES = {code for code, _ in FACULTIES}


def faculty_of(group):
    prefix = group[:3].upper()
    if prefix == 'WMT':
        return 'WML'  # WML publishes its plans under WMT group codes
    if prefix == 'WME':
        return 'WIM'  # WIM publishes its plans under WME group codes
    return prefix if prefix in FACULTY_CODES else 'OTHER'


def plural_grup(n):
    if n == 1:
        return '1 grupa'
    m10, m100 = n % 10, n % 100
    if 2 <= m10 <= 4 and not 12 <= m100 <= 14:
        return f'{n} grupy'
    return f'{n} grup'


def plural_wydzialy(n):
    if n == 1:
        return '1 wydział'
    m10, m100 = n % 10, n % 100
    if 2 <= m10 <= 4 and not 12 <= m100 <= 14:
        return f'{n} wydziały'
    return f'{n} wydziałów'


class BuildError(Exception):
    """A timetable or the output directory is not usable; the message says which and why."""


@dataclasses.dataclass
class Term:
    term_id: str
    path: Path | None
    start: dt.date
    end: dt.date
    meta: dict = dataclasses.field(default_factory=dict)
    dates: list = dataclasses.field(default_factory=list)  # the lessons' days inside the term's window
    bad_bounds: bool = False  # X-PLAN-SEMESTER-START/END name another semester (see fix_semester_bounds)

    def data(self):
        """The calendar as published: the file's bytes, minus lessons that belong to another semester, and with
        semester dates that belong to this one."""
        raw = clip_to_term(self.path.read_bytes(), self.term_id)
        if self.bad_bounds:
            raw = with_semester(raw, self.meta['semester_start'], self.meta['semester_end'])
        return raw


# ---------------------------------------------------------------- calendars

def term_window(term_id):
    """(first, last) day, as YYYYMMDD, that lessons of the term `2026-27-zima` / `2026-27-lato` may fall on.

    Wide on purpose (winter: 1 September to the end of February, summer: 1 February to the end of September):
    groups of a higher year start before the official semester date, and sessions run past it."""
    year, _, season = term_id.split('-')
    year = int(year)
    return (f'{year}0901', f'{year + 1}0229') if season == 'zima' else (f'{year + 1}0201', f'{year + 1}0930')


def clip_to_term(raw, term_id):
    """A calendar (bytes) without the VEVENTs dated outside its term's window.

    The faculties' pages sometimes carry two semesters at once (last semester's lessons below this one's), and the
    page would then show March to July under a winter term. Every byte of what stays is untouched, and the input
    comes back as it is when nothing falls outside. When everything does, the faculty has not published this term
    yet and is still showing the last one: the term goes out with no lessons at all, and the page says so, instead
    of presenting last semester's plan as this one."""
    try:
        first, last = term_window(term_id)
    except ValueError:
        return raw
    text = raw.decode('utf-8')
    lines = text.splitlines(keepends=True)
    out, block, dropped, kept = [], None, 0, 0
    for line in lines:
        bare = line.rstrip('\r\n')
        if block is None:
            if bare.upper() == 'BEGIN:VEVENT':
                block = [line]
            else:
                out.append(line)
            continue
        block.append(line)
        if bare.upper() == 'END:VEVENT':
            unfolded = re.sub(r'\r?\n[ \t]', '', ''.join(block))
            m = re.search(r'^DTSTART[^:\r\n]*:(\d{8})', unfolded, re.M)
            if m and not first <= m.group(1) <= last:
                dropped += 1
            else:
                kept += 1
                out.extend(block)
            block = None
    if block is not None:  # an unterminated event: leave the file alone
        return raw
    if not dropped:
        return raw
    return ''.join(out).encode('utf-8')


def bounds_fit_term(start, end, term_id):
    """Whether declared semester dates can belong to the term: both inside its window, in order."""
    try:
        first, last = term_window(term_id)  # YYYYMMDD strings: the winter window ends on "29 February" every year
    except ValueError:
        return True
    return bool(start and end) and first <= f'{start:%Y%m%d}' <= f'{end:%Y%m%d}' <= last


def with_semester(raw, start, end):
    """A calendar (bytes) with its X-PLAN-SEMESTER-START/END set to `start`/`end`; every other byte untouched."""
    text = raw.decode('utf-8')
    for name, day in (('X-PLAN-SEMESTER-START', start), ('X-PLAN-SEMESTER-END', end)):
        text, n = re.subn(rf'^{name}:[^\r\n]*', f'{name}:{day:%Y%m%d}', text, count=1, flags=re.M)
        if not n:
            text = re.sub(r'^(X-PLAN-GROUP:[^\r\n]*)(\r?\n)', rf'\g<1>\g<2>{name}:{day:%Y%m%d}\g<2>', text, count=1, flags=re.M)
    return text.encode('utf-8')


def fix_semester_bounds(by_group):
    """Give every term whose declared semester belongs to another one the dates its neighbours agree on.

    A converter takes the semester from what the faculty's page shows, and a page that still lists a lesson of the
    last semester (a WCY page with one March class under a winter plan) yields last semester's dates: the page's
    week grid then starts months before the first class, and its semester progress counts those empty months. The
    dates most calendars of the same faculty and term declare replace them, else those of the term as a whole,
    else the span of the lessons themselves (Monday of the first week to the last class)."""
    votes = {}
    for terms in by_group.values():
        for t in terms:
            if not t.bad_bounds:
                bounds = (t.meta['semester_start'], t.meta['semester_end'])
                for key in ((t.term_id, faculty_of(t.meta['group'])), (t.term_id, None)):
                    votes.setdefault(key, collections.Counter())[bounds] += 1
    for terms in by_group.values():
        for t in terms:
            if not t.bad_bounds:
                continue
            agreed = votes.get((t.term_id, faculty_of(t.meta['group']))) or votes.get((t.term_id, None))
            if agreed:
                start, end = agreed.most_common(1)[0][0]
            elif t.dates:
                start, end = min(t.dates) - dt.timedelta(days=min(t.dates).weekday()), max(t.dates)
            else:
                start, end = t.start, t.end
            t.meta['semester_start'], t.meta['semester_end'] = start, end
            t.start = min([start] + t.dates)
            t.end = max([end] + t.dates)
            t.end += dt.timedelta(days=6 - t.end.weekday())


def _unescape(value):
    return re.sub(r'\\([\\;,nN])', lambda m: '\n' if m.group(1) in 'nN' else m.group(1), value).strip()


def _ymd(value):
    m = re.match(r'(\d{4})(\d{2})(\d{2})', value.strip())
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def read_calendar(path):
    """Check a calendar's structure and return its calendar-level properties and event dates."""
    try:
        text = path.read_bytes().decode('utf-8')
    except UnicodeDecodeError as err:
        raise BuildError(f'{path}: not UTF-8 ({err})') from None
    lines = [l for l in re.sub(r'\r?\n[ \t]', '', text.lstrip('\ufeff')).splitlines() if l]
    if not lines or lines[0] != 'BEGIN:VCALENDAR' or lines[-1] != 'END:VCALENDAR':
        raise BuildError(f'{path}: must start with BEGIN:VCALENDAR and end with END:VCALENDAR')

    props, dates, stack, event = {}, [], [], None
    for line in lines:
        name, _, value = line.partition(':')
        key = name.split(';', 1)[0].upper()
        if key == 'BEGIN':
            stack.append(value.upper())
            if value.upper() == 'VEVENT':
                event = set()
        elif key == 'END':
            if not stack or stack[-1] != value.upper():
                raise BuildError(f'{path}: END:{value} does not close {stack[-1] if stack else "anything"}')
            stack.pop()
            if value.upper() == 'VEVENT':
                missing = {'UID', 'DTSTART', 'SUMMARY'} - event
                if missing:
                    raise BuildError(f'{path}: an event has no {", ".join(sorted(missing))}')
                event = None
        elif stack and stack[-1] == 'VEVENT':
            # PlanWAT keeps no personal data of staff: a calendar that names who teaches is refused.
            if key == 'CONTACT' or (key == 'DESCRIPTION' and 'prowadzący:' in value.lower()):
                raise BuildError(f'{path}: calendars must not name staff (remove the {key} line)')
            if key == 'LOCATION' and _names_person(value):
                raise BuildError(f'{path}: a LOCATION names a person (a title such as "dr inż." or an alias such as "AKowalski"): calendars must not name staff')
            event.add(key)
            if key == 'DTSTART' and _ymd(value):
                dates.append(_ymd(value))
        elif stack == ['VCALENDAR']:
            props.setdefault(key, _unescape(value))
    if stack:
        raise BuildError(f'{path}: unclosed {stack[-1]}')
    return props, dates


def load_term(path):
    term_id, group = path.parent.name, path.stem
    if not TERM_RE.match(term_id):
        raise BuildError(f'{path}: term folder "{term_id}" must be lowercase letters, digits and dashes')
    if not GROUP_RE.match(group):
        raise BuildError(f'{path}: group code "{group}" must be 2-32 letters, digits and underscores')
    props, dates = read_calendar(path)
    declared = props.get('X-PLAN-GROUP')
    if declared and declared != group:
        raise BuildError(f'{path}: file is named {group} but X-PLAN-GROUP is {declared}')
    try:  # lessons outside the term's window are not published (clip_to_term), so they do not date the term either
        first, last = term_window(term_id)
        dates = [d for d in dates if first <= f'{d:%Y%m%d}' <= last]
    except ValueError:
        pass
    declared_start = _ymd(props.get('X-PLAN-SEMESTER-START', ''))
    declared_end = _ymd(props.get('X-PLAN-SEMESTER-END', ''))
    bad = bool(declared_start and declared_end) and not bounds_fit_term(declared_start, declared_end, term_id)
    start = (None if bad else declared_start) or (min(dates) if dates else None)
    end = (None if bad else declared_end) or (max(dates) if dates else None)
    if not start or not end:
        if bad:  # nothing of this term in it yet; fix_semester_bounds gives it the term's dates
            start = end = declared_start
        else:
            raise BuildError(f'{path}: no X-PLAN-SEMESTER-START/END and no events to infer the term from')
    if dates:
        start, end = min(start, min(dates)), max(end, max(dates))
    end += dt.timedelta(days=6 - end.weekday())  # a term runs to the Sunday of its last week
    meta = {
        'group': group,
        'faculty': props.get('X-PLAN-FACULTY', ''),
        'term': props.get('X-PLAN-TERM', ''),
        'semester_start': (None if bad else declared_start) or start,
        'semester_end': (None if bad else declared_end) or end - dt.timedelta(days=1),
        'generated': _ymd(props.get('X-PLAN-GENERATED', '')),
    }
    return group, Term(term_id, path, start, end, meta, dates, bad)


def _unfold(source):
    """A calendar's content lines, unfolded; `source` is a path or the bytes of the calendar."""
    text = (source if isinstance(source, bytes) else source.read_bytes()).decode('utf-8')
    return [l for l in re.sub(r'\r?\n[ \t]', '', text.lstrip('﻿')).splitlines() if l]


# Academic and military titles. A room part that is such a title followed by a capitalised name is a person.
_TITLES = {'dr', 'hab', 'prof', 'inż', 'inz', 'mgr', 'lic', 'płk', 'ppłk', 'mjr', 'kpt', 'por', 'ppor', 'gen', 'bryg', 'rez', 'ucz'}


# A lecturer alias left in the room: initial(s) glued to a capitalised surname ('AKowalski'). Real rooms never have
# two capitals followed by lowercase letters ('Teams', '314 S'); U+FFFD stands in for a letter lost to a code page.
_ALIAS = re.compile('[A-ZĄĆĘŁŃÓŚŹŻ�]{1,2}[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż�]{3,}(?:-[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż�]+)?')


def _names_person(location):
    """True when any ';'/','-separated part of a LOCATION value is a title followed by a name, or a bare
    lecturer alias."""
    for part in re.split(r'(?:\\[;,]|[;,])', location):
        if _ALIAS.fullmatch(part.strip()):
            return True
        tokens = [t for t in re.split(r'[\s.()]+', part.strip()) if t]
        i = 0
        while i < len(tokens) and tokens[i].lower() in _TITLES:
            i += 1
        if 0 < i < len(tokens) and tokens[i][0].isalpha() and tokens[i][0].isupper():
            return True
    return False


def _fold(line):
    """An iCalendar content line folded at 75 octets (RFC 5545 3.1), never inside a UTF-8 character."""
    parts, cur, size = [], '', 0
    for ch in line:
        n = len(ch.encode('utf-8'))
        if size + n > 75:
            parts.append(cur)
            cur, size = ' ', 1
        cur += ch
        size += n
    return '\r\n'.join(parts + [cur])


def with_reminders(raw):
    """The calendar with a display alarm REMINDER_MINUTES before each event that has none; CRLF, refolded."""
    text = raw.decode('utf-8').lstrip('\ufeff')
    out, stack, summary, has_alarm = [], [], '', False
    for line in (l for l in re.sub(r'\r?\n[ \t]', '', text).splitlines() if l):
        name, _, value = line.partition(':')
        name = name.split(';', 1)[0].upper()
        kind = value.strip().upper()
        if name == 'BEGIN':
            stack.append(kind)
            if kind == 'VEVENT':
                summary, has_alarm = '', False
            elif kind == 'VALARM':
                has_alarm = True
        elif name == 'END':
            if kind == 'VEVENT' and stack[-1:] == ['VEVENT'] and not has_alarm:
                out += ['BEGIN:VALARM', 'ACTION:DISPLAY', 'DESCRIPTION:' + (summary or 'Zajęcia'),
                        f'TRIGGER:-PT{REMINDER_MINUTES}M', 'END:VALARM']
            if stack:
                stack.pop()
        elif name == 'SUMMARY' and stack[-1:] == ['VEVENT']:
            summary = value
        elif name == 'X-WR-CALNAME' and stack == ['VCALENDAR']:
            line += ' (przypomnienia)'
        out.append(line)
    return ''.join(_fold(l) + '\r\n' for l in out).encode('utf-8')


def _local_dt(value, params, tz):
    """A DTSTART/DTEND value as a naive Warsaw wall-clock datetime; None for all-day or unreadable values."""
    m = re.match(r'(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})?(Z?)$', value.strip())
    if not m or 'VALUE=DATE' in params.upper().replace('VALUE=DATE-TIME', ''):
        return None
    y, mo, d, h, mi = (int(m.group(i)) for i in range(1, 6))
    try:
        when = dt.datetime(y, mo, d, h, mi)
    except ValueError:
        return None
    if m.group(7) and tz:
        when = when.replace(tzinfo=dt.timezone.utc).astimezone(tz).replace(tzinfo=None)
    return when


def _duration(value):
    m = re.match(r'P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$', value.strip())
    if not m:
        return None
    w, d, h, mi, s = (int(g or 0) for g in m.groups())
    return dt.timedelta(weeks=w, days=d, hours=h, minutes=mi, seconds=s)


_BYDAY = {'MO': 0, 'TU': 1, 'WE': 2, 'TH': 3, 'FR': 4, 'SA': 5, 'SU': 6}


def _expand(start, rule, until_limit):
    """Occurrences of a DAILY/WEEKLY RRULE (INTERVAL, COUNT, UNTIL, BYDAY), as the browser reader expands them."""
    parts = dict(p.split('=', 1) for p in rule.split(';') if '=' in p)
    freq = parts.get('FREQ', '').upper()
    if freq not in ('DAILY', 'WEEKLY'):
        return [start]
    interval = max(1, int(parts.get('INTERVAL', '1') or 1))
    count = int(parts['COUNT']) if parts.get('COUNT', '').isdigit() else None
    until = _ymd(parts.get('UNTIL', '')) or until_limit
    days = sorted({_BYDAY[d[-2:].upper()] for d in parts.get('BYDAY', '').split(',') if d[-2:].upper() in _BYDAY})
    out, step = [], 0
    while len(out) < 1000:
        if freq == 'DAILY':
            cands = [start + dt.timedelta(days=step * interval)]
        else:
            monday = start - dt.timedelta(days=start.weekday()) + dt.timedelta(weeks=step * interval)
            cands = [monday + dt.timedelta(days=wd) for wd in (days or [start.weekday()])]
            cands = [c.replace(hour=start.hour, minute=start.minute) for c in cands if c >= start]
        for c in cands:
            if (until and c.date() > until) or (count is not None and len(out) >= count):
                return out
            out.append(c)
        step += 1
        if not until and count is None:
            return out
    return out


def calendar_lessons(path, tz=None, limit=None):
    """Timed events of a calendar as (date, start_min, end_min, summary, category, location) tuples."""
    lessons, ev, depth = [], None, []
    for line in _unfold(path):
        name, _, value = line.partition(':')
        key, _, params = name.partition(';')
        key = key.upper()
        if key == 'BEGIN':
            depth.append(value.upper())
            if value.upper() == 'VEVENT':
                ev = {'EXDATE': []}
        elif key == 'END':
            if depth:
                depth.pop()
            if value.upper() == 'VEVENT' and ev is not None:
                lessons.extend(_event_lessons(ev, tz, limit))
                ev = None
        elif ev is not None and depth and depth[-1] == 'VEVENT':
            if key == 'EXDATE':
                ev['EXDATE'].extend(v for v in value.split(','))
            elif key not in ev:
                ev[key] = (params, value)
    return lessons


def _event_lessons(ev, tz, limit):
    if 'DTSTART' not in ev or 'SUMMARY' not in ev or ev.get('STATUS', ('', ''))[1].strip().upper() == 'CANCELLED':
        return []
    start = _local_dt(ev['DTSTART'][1], ev['DTSTART'][0], tz)
    if not start:
        return []
    end = _local_dt(ev['DTEND'][1], ev['DTEND'][0], tz) if 'DTEND' in ev else None
    if not end and 'DURATION' in ev:
        dur = _duration(ev['DURATION'][1])
        end = start + dur if dur else None
    if not end or end <= start:
        return []
    length = end - start
    starts = _expand(start, ev['RRULE'][1], limit) if 'RRULE' in ev else [start]
    excluded = {_ymd(x) for x in ev['EXDATE']}
    summary = _unescape(ev['SUMMARY'][1])
    category = _unescape(re.split(r'(?<!\\),', ev['CATEGORIES'][1])[0]) if 'CATEGORIES' in ev else ''
    location = _unescape(ev['LOCATION'][1]) if 'LOCATION' in ev else ''
    out = []
    for s in starts:
        if s.date() in excluded:
            continue
        e = s + length
        out.append((s.date(), s.hour * 60 + s.minute, e.hour * 60 + e.minute if e.date() == s.date() else 24 * 60,
                    summary, category, location))
    return out


# A room is a LOCATION part with a digit in it ("314 S", "0.24/ 135"); anything else ("-", "Teams", "Wyjazd")
# cannot be told apart from a non-room and stays out of the free-rooms list.
ROOM_RE = re.compile(r'\d')
YEAR_RE = re.compile(r'^([A-Za-z]{3}\d{2})')
EPOCH = dt.date(2000, 1, 1)  # day numbers in the data files count from here


def year_of(group):
    """The faculty + intake-year prefix that groups of one year share (WCY26KY3S1 -> WCY26), or None."""
    m = YEAR_RE.match(group)
    return m.group(1).upper() if m else None


def split_rooms(location):
    """The rooms of a LOCATION, normalised: "1.16/ 16;1.17/16" -> ["1.16/16", "1.17/16"]."""
    rooms = []
    for part in location.split(';'):
        part = re.sub(r'\s*/\s*', '/', ' '.join(part.rsplit(',', 1)[-1].split()))
        if ROOM_RE.search(part) and part not in rooms:
            rooms.append(part)
    return rooms


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo('Europe/Warsaw')
    except Exception:  # no tz database: UTC times are kept as they are
        return None


def build_data(current, refreshed=None):
    """The JSON files behind the group page's tools, from every group's current term.

    groups.json            [[group, term label, year prefix], ...]
    profiles.json          every plan's week as numbers, its place on the map and its archetype, for "Mapa planów"
    rooms.json             rooms and every booking [room, day, start, end, ...], for "Wolne sale"; `asof` is the
                           date the crawler last checked the plans (null without a refresh state; the build date would make
                           every build's output differ)
    year/<PREFIX>.json     every class of the groups of one year, for "Odrabianie"
    Days are counted from 2000-01-01 and times are minutes after midnight, to keep the files small.
    """
    tz = _tz()
    groups = sorted(current)
    rooms, booked = {}, set()
    years, by_group = {}, {}
    for group in groups:
        term = current[group]
        lessons = calendar_lessons(term.data(), tz, term.end)
        by_group[group] = lessons
        year = year_of(group)
        if year:
            years.setdefault(year, []).append((group, lessons))
        for day, s, e, _, _, location in lessons:
            for room in split_rooms(location):
                booked.add((rooms.setdefault(room, len(rooms)), (day - EPOCH).days, s, e))
    room_names = sorted(rooms)
    remap = {rooms[name]: i for i, name in enumerate(room_names)}
    bookings = []
    for r, d, s, e in sorted((remap[r], d, s, e) for r, d, s, e in booked):
        bookings.extend((r, d, s, e))
    checked = sorted(str(v.get('checked', ''))[:10] for v in (refreshed or {}).values() if isinstance(v, dict))
    asof = next((c for c in reversed(checked) if re.fullmatch(r'\d{4}-\d{2}-\d{2}', c)), None)
    files = {
        'groups.json': [[g, current[g].meta['term'] or current[g].term_id, year_of(g) or ''] for g in groups],
        'rooms.json': {'epoch': EPOCH.isoformat(), 'asof': asof, 'groups': len(groups), 'rooms': room_names,
                       'b': bookings},
    }
    profile = profiles.build(by_group, faculty_of, asof)
    if profile:
        files['profiles.json'] = profile
    for year, members in sorted(years.items()):
        names, idx, flat = [], {}, []
        def ix(v):  # noqa: E306
            if v not in idx:
                idx[v] = len(names)
                names.append(v)
            return idx[v]
        for gi, (group, lessons) in enumerate(members):
            for day, s, e, summary, category, location in sorted(set(lessons)):
                flat.extend((gi, ix(summary), ix(category), ix(location), (day - EPOCH).days, s, e))
        files[f'year/{year}.json'] = {'epoch': EPOCH.isoformat(), 'groups': [g for g, _ in members],
                                      'names': names, 'e': flat}
    return files


def pick_term(terms, today):
    """The term running today; between terms the next one; after the last term the latest one."""
    running = [t for t in terms if t.start <= today <= t.end]
    if running:
        return max(running, key=lambda t: t.start)
    upcoming = [t for t in terms if t.start > today]
    if upcoming:
        return min(upcoming, key=lambda t: t.start)
    return max(terms, key=lambda t: t.start)


# ---------------------------------------------------------------- pages

def _sha(text):
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode('utf-8')).digest()).decode() + "'"


def inline_hashes(page):
    scripts = [_sha(s) for s in re.findall(r'<script>(.*?)</script>', page, re.S)]
    styles = [_sha(s) for s in re.findall(r'<style>(.*?)</style>', page, re.S)]
    return scripts, styles


class AssetHub:
    """The styles and scripts every page used to carry inline, written once per build under assets/.

    A file's name carries a hash of its bytes, so one name never means two different files: browsers
    and the service worker may cache it forever, and a rebuild that changes the code ships a new name.
    build() hands the hub to the page renderers, then lists what was written for src/sw.js."""

    def __init__(self, out):
        self.dir = Path(out) / ASSETS_DIR
        self.written = {}  # name -> None, in write order

    def put(self, slug, ext, code, prefix=''):
        """Store `code` (text or bytes) as assets/<slug>-<hash8>.<ext>; return its url and the SRI digest of its bytes."""
        data = code if isinstance(code, bytes) else code.encode('utf-8')
        digest = hashlib.sha256(data)
        name = f'{slug}-{digest.hexdigest()[:8]}.{ext}'
        if name not in self.written:
            self.dir.mkdir(parents=True, exist_ok=True)
            (self.dir / name).write_bytes(data)
            self.written[name] = None
        return f'{prefix}{ASSETS_DIR}/{name}', base64.b64encode(digest.digest()).decode()


def externalize(page, assets, prefix):
    """Replace the blocks marked data-asset with shared files under assets/, integrity-pinned in the tag."""
    found = set()

    def style(m):
        url, digest = assets.put(m.group(1), 'css', m.group(2), prefix)
        found.add('style')
        return f'<link rel="stylesheet" href="{url}" integrity="sha256-{digest}">'

    def script(m):
        url, digest = assets.put(m.group(1), 'js', m.group(2), prefix)
        found.add('script')
        return f'<script src="{url}" integrity="sha256-{digest}" defer></script>'

    page = re.sub(r'<style data-asset="([a-z0-9-]+)">(.*?)</style>', style, page, flags=re.S)
    page = re.sub(r'<script data-asset="([a-z0-9-]+)">(.*?)</script>', script, page, flags=re.S)
    return page, found


def csp(scripts, styles, connect, frame_ancestors=False, extra=None):
    extra = extra or {}
    more = lambda name: extra.get(name, [])  # noqa: E731
    parts = [
        "default-src 'none'",
        'script-src ' + (' '.join(scripts + more('script-src')) if scripts else "'none'"),
        'style-src ' + ' '.join(styles + more('style-src')),
        "font-src 'self'",
        'img-src ' + ' '.join(['data:'] + more('img-src')),
        'connect-src ' + (' '.join(["'self'"] + more('connect-src')) if connect else "'none'"),
    ]
    parts += [f'{name} ' + ' '.join(more(name)) for name in ('worker-src', 'child-src', 'manifest-src') if more(name)]
    parts += [
        "base-uri 'none'",
        "form-action 'none'",
    ]
    if frame_ancestors:  # header only
        parts.append("frame-ancestors 'none'")  # browsers ignore it in a meta tag
        # Redundant in the meta CSP (every source is https or 'self'), where WebKit would also apply it to
        # http://127.0.0.1 and break local previews; the header (always served over https) keeps it.
        parts.append('upgrade-insecure-requests')
    return '; '.join(parts)


def themed(page):
    """Fill the theme markers (light tokens, the switch's styles, the early script). Pages without them stay as they are."""
    if '@@THEME_HEAD@@' not in page and '/*@@THEME_CSS@@*/' not in page:
        return page
    light = ''.join('    ' + line + chr(10) for line in (SRC / 'theme-light.css').read_text(encoding='utf-8').splitlines())
    css = (SRC / 'theme.css').read_text(encoding='utf-8').replace('@@LIGHT@@', light.rstrip(chr(10)))
    js = (SRC / 'theme.js').read_text(encoding='utf-8')
    for name, code in (('theme.css', css), ('theme.js', js)):
        if '@@' in code:
            raise BuildError(f'src/{name} must not contain "@@"')
    return page.replace('@@THEME_HEAD@@', '<script>' + js + '</script>').replace('/*@@THEME_CSS@@*/', css)


def font_faces(assets, prefix):
    """The @font-face rules for Inter, its files stored in assets/ and named from the page by `prefix`."""
    rules = []
    for slug, unicode_range in FONTS:
        url, _ = assets.put(slug, 'woff2', (SRC / 'fonts' / f'{slug}.woff2').read_bytes(), prefix)
        rules.append(f'@font-face {{ font-family: "Inter"; font-style: normal; font-weight: 400 700; font-display: swap; '
                     f'src: url("{url}") format("woff2"); unicode-range: {unicode_range}; }}')
    return '<style>' + ' '.join(rules) + '</style>'


def finish(page, connect, extra=None, assets=None, asset_prefix=''):
    """Pin the page's inline code into its meta CSP and sanity-check the result.

    Blocks marked data-asset move out of the page into shared files under assets/ (see AssetHub).
    Those are allowed by origin: a meta CSP hash cannot cover an external file, so each file is
    instead pinned by the integrity attribute of the tag that loads it. Everything left inline is
    pinned by hash, exactly as before. @@FONTS@@ becomes the page's @font-face rules (without a hub,
    for a page rendered on its own, the system font stack simply takes over)."""
    page = page.replace('@@FONTS@@\n', font_faces(assets, asset_prefix) + '\n' if assets is not None else '')
    page = themed(page)
    if 'style="' in page:
        raise BuildError('inline style attributes would be blocked by the CSP')
    found = set()
    if assets is not None:
        page, found = externalize(page, assets, asset_prefix)
    scripts, styles = inline_hashes(page)
    if 'script' in found:
        scripts = ["'self'"] + scripts
    if 'style' in found:
        styles = ["'self'"] + styles
    policy = csp(scripts, styles, connect, extra=extra)
    page = page.replace('@@CSP@@', f'<meta http-equiv="Content-Security-Policy" content="{policy}">')
    left = re.findall(r'@@[A-Z_]+@@', page)
    if left:
        raise BuildError(f'unfilled template placeholders: {sorted(set(left))}')
    return page, scripts, styles


def _date(d):
    return d.strftime('%d.%m.%Y')


def _stamp(iso, with_time=False):
    """A UTC timestamp from refresh-state.json as a Warsaw-time date (and time) for the page, or ''."""
    try:
        moment = dt.datetime.fromisoformat(iso).replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return ''
    tz = _tz()
    if tz:
        moment = moment.astimezone(tz)
    return moment.strftime('%d.%m.%Y %H:%M' if with_time else '%d.%m.%Y')


def load_refresh_state(path):
    """Per-group refresh times written by tools/refresh (refresh-state.json); {} when there is none."""
    try:
        groups = json.loads(Path(path).read_text(encoding='utf-8')).get('groups', {})
    except (OSError, ValueError, AttributeError):
        return {}
    return groups if isinstance(groups, dict) else {}


def term_label(term_id):
    """'2026-27-zima' -> 'Zima 2026/27' (anything else is shown as it is)."""
    m = re.fullmatch(r'(\d{4})-(\d{2})-(zima|lato)', term_id)
    return f'{m.group(3).capitalize()} {m.group(1)}/{m.group(2)}' if m else term_id


def term_switch(term, terms):
    """The Zima/Lato links of a group that has more than one term; empty for the usual single term."""
    if len(terms) < 2:
        return ''
    links = []
    for t in sorted(terms, key=lambda t: t.start):
        href = './' if t.term_id == term.term_id else f'./?t={t.term_id}'
        here = ' aria-current="true"' if t.term_id == term.term_id else ''
        links.append(f'<a href="{html.escape(href, quote=True)}" data-term="{t.term_id}"{here}>{html.escape(term_label(t.term_id))}</a>')
    return '<nav class="termswitch" id="termSwitch" aria-label="Semestr">' + ''.join(links) + '</nav>'


def render_group(template, ics_js, term, refreshed=None, terms=(), assets=None, site_url=''):
    m = term.meta
    e = lambda v: html.escape(v, quote=True)  # noqa: E731
    title, description = group_seo(term)
    crumbs = {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': [
        {'@type': 'ListItem', 'position': 1, 'name': SITE_NAME, **({'item': f'{site_url}/'} if site_url else {})},
        {'@type': 'ListItem', 'position': 2, 'name': f'Plan zajęć {m["group"]}',
         **({'item': f'{site_url}/{m["group"]}/'} if site_url else {})},
    ]}
    refreshed = refreshed or {}
    # Last change of the plan (from the refresh), else the date the calendar says it was generated.
    updated = _stamp(refreshed.get('changed') or refreshed.get('checked')) or (_date(m['generated']) if m['generated'] else '')
    checked = _stamp(refreshed.get('checked'), with_time=True)
    values = {
        '@@SEO@@': seo_head(site_url, f'{m["group"]}/', title, description, [crumbs]),
        '@@TITLE@@': e(title),
        '@@GROUP@@': e(m['group']),
        '@@TERM_SWITCH@@': term_switch(term, terms),
        '@@DESCRIPTION@@': e(description),
        '@@TERM_LINE@@': 'Plan zajęć &middot; ' + e(m['term']) if m['term'] else 'Plan zajęć',
        '@@FACULTY@@': e(m['faculty']),
        '@@HIDE_FACULTY@@': '' if m['faculty'] else ' hidden',
        '@@SEMESTER@@': f'{_date(m["semester_start"])} &ndash; {_date(m["semester_end"])}',
        '@@UPDATED@@': e(updated),
        '@@HIDE_UPDATED@@': '' if updated else ' hidden',
        '@@CHECKED@@': e(checked),
        '@@HIDE_CHECKED@@': '' if checked else ' hidden',
    }
    page = template.replace('@@ICS_JS@@', ics_js)  # first: the scripts' own text is never substituted into
    for key, value in values.items():
        page = page.replace(key, value)
    return finish(page, connect=True, extra=APP_CSP, assets=assets, asset_prefix='../')


def plural_wydzial(n):
    if n == 1:
        return '1 wydział'
    m10, m100 = n % 10, n % 100
    if 2 <= m10 <= 4 and not 12 <= m100 <= 14:
        return f'{n} wydziały'
    return f'{n} wydziałów'


INTAKE_RE = re.compile(r'^[A-Za-z]{3}(\d{2})')
STAR_SVG = ('<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6'
            'L12 17.3l-5.9 3.3 1.3-6.6-4.9-4.6 6.6-.8z"/></svg>')


def render_index(template, current, ics_js='', assets=None, site_url=''):
    names = {code: pl for code, pl in FACULTIES}
    order = {code: i for i, (code, _) in enumerate(FACULTIES)}
    groups = sorted(current.items(), key=lambda kv: (order.get(faculty_of(kv[0]), len(order)), kv[0]))
    labels = {code: term.meta['term'] or term.term_id for code, term in groups}
    uniform = len(set(labels.values())) == 1  # one term for everyone: say it once, not on every row

    def intake(code):
        m = INTAKE_RE.match(code)
        return 2000 + int(m.group(1)) if m else None

    sections, chips, fac, rows = [], [], None, []
    totals = {}
    for code, _ in groups:
        totals[faculty_of(code)] = totals.get(faculty_of(code), 0) + 1

    def flush():
        if rows:
            if fac == 'OTHER':
                title, short = 'Pozostałe grupy', 'Pozostałe'
            else:
                title, short = f'{fac} &middot; {html.escape(names[fac])}', fac
            full = html.escape(names.get(fac, 'Pozostałe grupy'), quote=True)
            chips.append(f'    <button class="chip" type="button" data-fac="{fac}" aria-pressed="false" title="{full}">'
                         f'{short}<span class="n">{totals[fac]}</span></button>')
            lis, last = [], None
            years = {intake(c) for c, _ in rows_src}
            for code, row in rows_src:
                year = intake(code)
                if len(years) > 1 and year != last:
                    lis.append(f'    <li class="yr">Rocznik {year}</li>' if year else '    <li class="yr">Pozostałe</li>')
                    last = year
                lis.append(row)
            sections.append(f'  <details class="fac-sec" data-fac-section="{fac}">\n'
                            f'    <summary><span class="fac-title">{title}</span>'
                            f'<span class="fac-n">{plural_grup(len(rows))}</span>'
                            '<svg class="chev" viewBox="0 0 24 24" aria-hidden="true">'
                            '<path d="m9 18 6-6-6-6"/></svg></summary>\n'
                            '  <ul>\n' + '\n'.join(lis) + '\n  </ul>\n  </details>')

    rows_src = []
    for code, term in groups:
        if faculty_of(code) != fac:
            flush()
            fac, rows, rows_src = faculty_of(code), [], []
        term_html = '' if uniform else f'<span class="term">{html.escape(labels[code])}</span>'
        intake_year = intake(code)
        row = (f'    <li class="row" data-group="{code}" data-fac="{faculty_of(code)}" data-year="{intake_year or ""}">'
               f'<a class="group" href="{code}/"><span><span class="code">{code}</span>{term_html}</span>'
               '<svg class="chev" viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg></a>'
               f'<button class="star" type="button" data-star="{code}" aria-pressed="false" '
               f'aria-label="Dodaj {code} do ulubionych">{STAR_SVG}</button></li>')
        rows.append(row)
        rows_src.append((code, row))
    flush()
    facs = [f for f in totals if f != 'OTHER']
    stats = plural_grup(len(groups)) + ' &middot; ' + plural_wydzial(len(facs))
    if uniform and groups:
        stats += ' &middot; ' + html.escape(next(iter(labels.values())))
    redirect = f'<meta http-equiv="refresh" content="0; url={groups[0][0]}/">' if len(groups) == 1 else ''
    all_chip = (f'    <button class="chip" type="button" data-fac="" aria-pressed="true">Wszystkie'
                f'<span class="n">{len(groups)}</span></button>')
    chips_html = '\n'.join([all_chip] + chips)
    page = template.replace('@@ICS_JS@@', ics_js)  # first: the script's own text is never substituted into
    page = page.replace('@@GROUPS@@', '\n'.join(sections))
    page = page.replace('@@CHIPS@@', chips_html)
    page = page.replace('@@STATS@@', stats)
    page = page.replace('@@REDIRECT@@', redirect)
    title, description = index_seo(current)
    website = {'@context': 'https://schema.org', '@type': 'WebSite', 'name': SITE_NAME,
               'alternateName': ['Plan WAT', 'Plan zajęć WAT'], 'inLanguage': 'pl', 'description': description,
               **({'url': f'{site_url}/'} if site_url else {})}
    page = page.replace('@@SEO@@', seo_head(site_url, '', title, description, [website]))
    page = page.replace('@@TITLE@@', html.escape(title)).replace('@@DESCRIPTION@@', html.escape(description, quote=True))
    return finish(page, connect=True, extra=APP_CSP, assets=assets)


MAP_TITLE = f'Mapa kampusu WAT – budynki, wydziały i sale | {SITE_NAME}'
MAP_DESCRIPTION = ('Mapa kampusu Wojskowej Akademii Technicznej: budynki, wydziały i sale z Twojego planu zajęć, '
                   'a wokół przystanki, akademiki, jedzenie i parkingi.')
PRIVACY_TITLE = f'Prywatność i zasady · {SITE_NAME}'
PRIVACY_DESCRIPTION = 'Jakie dane przetwarza PlanWAT (żadnych kont ani śledzenia), zasady korzystania i kontakt.'


def render_map(template, ics_js, campus_js, places_js, assets=None, site_url=''):
    page = template.replace('@@ICS_JS@@', ics_js).replace('@@CAMPUS_JS@@', campus_js).replace('@@PLACES_JS@@', places_js)
    page = page.replace('@@SEO@@', seo_head(site_url, f'{MAP_DIR}/', MAP_TITLE, MAP_DESCRIPTION))
    page = page.replace('@@TITLE@@', html.escape(MAP_TITLE)).replace('@@DESCRIPTION@@', html.escape(MAP_DESCRIPTION, quote=True))
    return finish(page, connect=True, extra=merge_csp(MAP_APP_CSP, MAP_CSP), assets=assets, asset_prefix='../')


def render_privacy(template, site_url='', assets=None):
    # the notice runs no script at all: it follows the system theme through CSS only (no stored choice)
    page = template.replace('@@SEO@@', seo_head(site_url, f'{PRIVACY_DIR}/', PRIVACY_TITLE, PRIVACY_DESCRIPTION))
    page = page.replace('@@TITLE@@', html.escape(PRIVACY_TITLE)).replace('@@DESCRIPTION@@', html.escape(PRIVACY_DESCRIPTION, quote=True))
    return finish(page.replace('@@THEME_HEAD@@' + chr(10), ''), connect=False, assets=assets, asset_prefix='../')


def robots_txt(base_path, noindex, site_url=''):
    if noindex:  # the dev preview: keep it out of search engines altogether
        return 'User-agent: *\nDisallow: /\n'
    base = base_path.rstrip('/')
    # Crawlers read robots.txt only at the root of a host, so under a base path this file speaks for the site only
    # once it has its own domain; the sitemap line is harmless until then (submit it in Search Console meanwhile).
    return (f'# PlanWAT: nieoficjalne plany zajęć WAT\nUser-agent: *\nAllow: {base}/\n'
            f'Disallow: {base}/{DATA_DIR}/\nDisallow: {base}/dev/\n'
            + (f'\nSitemap: {site_url}/sitemap.xml\n' if site_url else ''))


# ---------------------------------------------------------------- search engines

def faculty_name(group, declared=''):
    """The faculty a group belongs to, by its code, else by its calendar ('Cybernetyki' -> 'Wydział Cybernetyki')."""
    names = dict(FACULTIES)
    if faculty_of(group) in names:
        return names[faculty_of(group)]
    return f'Wydział {declared}' if declared else ''


def _json_ld(data):
    # inside <script>, "</" would end the block early: escape "<" the way JSON allows
    return json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')


def seo_head(site_url, rel, title, description, ld=()):
    """Social cards, the canonical URL and JSON-LD for the page at <site_url>/<rel>.

    Without a site URL (local and Docker builds) the absolute parts are left out: a relative canonical or
    og:url would be wrong for any copy of the site served from somewhere else."""
    e = lambda v: html.escape(v, quote=True)  # noqa: E731
    tags = [
        f'<meta property="og:site_name" content="{SITE_NAME}">',
        '<meta property="og:type" content="website">',
        '<meta property="og:locale" content="pl_PL">',
        f'<meta property="og:title" content="{e(title)}">',
        f'<meta property="og:description" content="{e(description)}">',
        '<meta name="twitter:card" content="summary">',
    ]
    if site_url:
        url = f'{site_url}/{rel}'
        tags[:0] = [f'<link rel="canonical" href="{e(url)}">']
        tags += [f'<meta property="og:url" content="{e(url)}">',
                 f'<meta property="og:image" content="{e(site_url)}/{OG_IMAGE}">',
                 '<meta property="og:image:width" content="512">',
                 '<meta property="og:image:height" content="512">',
                 f'<meta property="og:image:alt" content="Logo {SITE_NAME}">']
    tags += [f'<script type="application/ld+json">{_json_ld(obj)}</script>' for obj in ld]
    return '\n'.join(tags)


def index_seo(current):
    groups = len(current)
    facs = len({faculty_of(g) for g in current} - {'OTHER'})
    title = f'Plan zajęć WAT – plan Twojej grupy na telefonie | {SITE_NAME}'
    description = (f'Plan zajęć WAT dla {groups} {"grupy" if groups == 1 else "grup"} z {facs} '
                   f'{"wydziału" if facs == 1 else "wydziałów"} Wojskowej Akademii Technicznej: zajęcia na dziś '
                   'i na cały tydzień, sale, wolne sale, mapa kampusu i eksport do kalendarza. Za darmo, bez logowania.')
    return title, description


def group_seo(term):
    m = term.meta
    fac = faculty_name(m['group'], m['faculty'])
    title = f'Plan zajęć {m["group"]} – ' + (f'{fac}, WAT' if fac else 'WAT') + f' | {SITE_NAME}'
    description = (f'Plan zajęć grupy {m["group"]} (' + (f'{fac} WAT' if fac else 'WAT') + ')'
                   + (f', {m["term"]}' if m['term'] else '')
                   + ': zajęcia na dziś i na cały tydzień, sale, godziny, wolne sale i eksport do kalendarza.')
    return title, description


def _lastmod(term, refreshed):
    """When a group's plan last changed: the refresh's record, else the calendar's own X-PLAN-GENERATED."""
    stamp = str((refreshed or {}).get('changed') or (refreshed or {}).get('checked') or '')
    if re.match(r'\d{4}-\d{2}-\d{2}', stamp):
        return stamp[:10]
    return term.meta['generated'].isoformat() if term.meta['generated'] else None


def sitemap_xml(site_url, current, refreshed):
    """Every page a search engine should index: the front page, the map, the privacy notice and each group."""
    e = lambda v: html.escape(v, quote=False)  # noqa: E731
    stamps = {g: _lastmod(t, refreshed.get(g)) for g, t in current.items()}
    newest = max((d for d in stamps.values() if d), default=None)
    entries = [('', newest), (f'{MAP_DIR}/', None), (f'{PRIVACY_DIR}/', None)]
    entries += [(f'{g}/', stamps[g]) for g in sorted(current)]
    rows = []
    for rel, lastmod in entries:
        row = f'  <url><loc>{e(site_url)}/{e(rel)}</loc>'
        rows.append(row + (f'<lastmod>{lastmod}</lastmod>' if lastmod else '') + '</url>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + '\n'.join(rows) + '\n</urlset>\n')


def security_txt(today):
    # RFC 9116: Expires must be less than a year away; the site is rebuilt daily, so 180 days stays fresh
    expires = dt.datetime.combine(today + dt.timedelta(days=180), dt.time(), dt.timezone.utc)
    return (f'Contact: {REPO_URL}/security/advisories/new\n'
            f'Expires: {expires.strftime("%Y-%m-%dT%H:%M:%SZ")}\n'
            'Preferred-Languages: pl, en\n'
            f'Policy: {REPO_URL}/blob/master/SECURITY.md\n')


def render_404(template, base_path, assets=None):
    # served at any depth, so its font is named from the site root
    base = html.escape(base_path.rstrip('/'), quote=True)
    page = template.replace('@@BASE@@', base).replace('@@BASE_JSON@@', _json_ld(base_path.rstrip('/')))
    return finish(page, connect=True, assets=assets, asset_prefix=base + '/')


# one colour per faculty, taken from the hand-drawn chart this file replaced, so a bar keeps its colour as counts move
COVERAGE_COLORS = {
    'WML': '#0aa5aa', 'WCY': '#ff9f0a', 'WEL': '#b565a7', 'WLO': '#a2845e',
    'WIM': '#68ab40', 'WTC': '#3a6ea5', 'IOE': '#f07a64', 'WIG': '#e5484d',
}


def render_coverage(current):
    """Draw the faculty coverage chart that README.md shows from the deployed site.

    README.md embeds site/pokrycie-wydzialow.svg, so the bars follow every refresh without a hand
    edit; inside the build the file counts as another page asset and joins the worker's version, and
    with no clock in it a quiet rebuild leaves that version (and everyone's offline copy) alone."""
    order = {code: i for i, (code, _) in enumerate(FACULTIES)}
    counts = {}
    for group in current:
        code = faculty_of(group)
        counts[code] = counts.get(code, 0) + 1
    rows = sorted(counts.items(), key=lambda row: (-row[1], order.get(row[0], len(order))))
    total = sum(counts.values())
    top = rows[0][1] if rows else 0
    # a round axis wide enough for the longest bar: 200 maps to 2.2 px per group, like the old drawing
    axis = next((step for step in (50, 100, 150, 200, 250, 300, 400, 500, 750, 1000, 1500, 2000, 3000) if step >= top),
                (top + 499) // 500 * 500)
    scale = 440 / axis
    height = 100 + len(rows) * 40

    def num(value):
        return f'{value:.1f}'.rstrip('0').rstrip('.')

    def label(code):
        return 'Pozostałe' if code == 'OTHER' else code

    ticks = 0, axis // 2, axis
    grid = ''.join(f'<path d="M{num(120 + t * scale)} 64V{height - 42}"/>' for t in ticks)
    axis_line = ''.join(f'<text x="{num(120 + t * scale)}" y="{height - 22}">{t}{" grup" if t == axis else ""}</text>'
                        for t in ticks)
    labels = '\n'.join(f'  <text x="104" y="{88 + i * 40}">{label(code)}</text>' for i, (code, _) in enumerate(rows))
    bars, values = [], []
    for i, (code, n) in enumerate(rows):
        width = n * scale
        y = 70 + i * 40
        bars.append(f'  <rect x="120" y="{y}" width="{num(width)}" height="24" rx="{4 if width < 16 else 7}" '
                    f'fill="{COVERAGE_COLORS.get(code, "#86868b")}"/>')
        values.append(f'    <text x="{num(130 + width)}" y="{y + 18}">{n}</text>')
    faculties = len(rows) - (1 if 'OTHER' in counts else 0)
    listed = ', '.join(f'{label(code)} {n} grup' if i == 0 else f'{label(code)} {n}'
                       for i, (code, n) in enumerate(rows))
    desc = (f'Wykres słupkowy: {listed}. Razem {total} grup.' if rows
            else 'Wykres słupkowy: brak opublikowanych grup.')
    bars_svg, values_svg = '\n'.join(bars), '\n'.join(values)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 {height}" role="img" aria-labelledby="t d" font-family="-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,sans-serif">
  <title id="t">Grupy według wydziału</title>
  <desc id="d">{desc}</desc>
  <rect width="800" height="{height}" rx="18" fill="#0b0f17"/>
  <text x="40" y="42" fill="#f5f5f7" font-size="18" font-weight="700">{plural_grup(total)}, {plural_wydzialy(faculties)}</text>

  <g stroke="#1c1c1e" stroke-width="1">{grid}</g>
  <g fill="#86868b" font-size="11" text-anchor="middle">{axis_line}</g>

  <g font-size="14" font-weight="600" fill="#f5f5f7" text-anchor="end">
{labels}
  </g>

  <g>
{bars_svg}
  </g>

  <g fill="#f5f5f7" font-size="13" font-weight="600">
{values_svg}
  </g>
</svg>
'''


def manifest(name, short_name, scope, up, shortcuts=()):
    """A web app manifest; every URL is relative to the manifest so the site works under any base path.

    `shortcuts` are (label, url) pairs; their urls are relative to the manifest and its scope, like every other url."""
    icon = lambda f, size, kind, purpose='any': {'src': f'{up}{ICONS_DIR}/{f}', 'sizes': size, 'type': kind, 'purpose': purpose}  # noqa: E731
    data = {
        'id': './', 'name': name, 'short_name': short_name, 'lang': 'pl', 'dir': 'ltr',
        'description': 'Nieoficjalny, czytelny na telefonie plan zajęć grup WAT.',
        'start_url': './', 'scope': scope, 'display': 'standalone',
        'background_color': '#000000', 'theme_color': '#000000',
        'icons': [icon('icon-192.png', '192x192', 'image/png'), icon('icon-512.png', '512x512', 'image/png'),
                  icon('maskable-512.png', '512x512', 'image/png', 'maskable'), icon('icon.svg', 'any', 'image/svg+xml')],
    }
    if shortcuts:
        data['shortcuts'] = [
            {'name': label, 'short_name': label, 'url': url,
             'icons': [icon('icon-192.png', '192x192', 'image/png')]}
            for label, url in shortcuts
        ]
    return json.dumps(data, ensure_ascii=False, indent=1)


def write_app(out, groups, assets=()):
    """Icons, manifests and the service worker; written last, so its version covers every other file.

    `assets` lists the shared files from AssetHub: the worker precaches the styles and scripts, so offline
    pages carry their whole style and code with them like the inline versions used to. Fonts are left to the
    first page that draws with them (most phones never do), then kept like the rest of assets/."""
    (out / ICONS_DIR).mkdir()
    for f in sorted((SRC / 'icons').glob('*')):
        if f.suffix in ('.png', '.svg'):
            shutil.copyfile(f, out / ICONS_DIR / f.name)
    (out / 'manifest.webmanifest').write_text(manifest('PlanWAT', 'PlanWAT', './', '', [
        ('Wszystkie plany', './'), ('Mapa kampusu', f'{MAP_DIR}/')]), encoding='utf-8')
    for group in groups:
        # the app opens at the group; its scope is the whole site so the map and the front page stay inside it
        (out / group / 'manifest.webmanifest').write_text(manifest(f'PlanWAT · {group}', group, '../', '../', [
            ('Mój plan', './'), ('Mapa kampusu', f'../{MAP_DIR}/')]), encoding='utf-8')
    digest = hashlib.sha256()
    # .well-known/security.txt changes its expiry date daily; it must not reset everyone's offline copy
    for f in sorted(p for p in out.rglob('*') if p.is_file() and p.relative_to(out).parts[0] != '.well-known'):
        digest.update(f.relative_to(out).as_posix().encode() + b'\0' + f.read_bytes())
    sw = (SRC / SW_FILE).read_text(encoding='utf-8')
    left = ''.join(f", '{ASSETS_DIR}/{name}'" for name in assets if not name.endswith('.woff2'))
    for placeholder in ('@@VERSION@@', '@@ASSETS@@'):
        if sw.count(placeholder) != 1:
            raise BuildError(f'src/sw.js must contain "{placeholder}" exactly once')
    sw = sw.replace('@@VERSION@@', digest.hexdigest()[:16]).replace('@@ASSETS@@', left)
    (out / SW_FILE).write_text(sw, encoding='utf-8')


# ---------------------------------------------------------------- build

def _prepare_out(out):
    if out.exists():
        if any(out.iterdir()) and not (out / MARKER).exists():
            raise BuildError(f'{out} is not empty and was not created by build.py; refusing to delete it')
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / MARKER).write_text('generated by build.py\n')


def update_nginx(conf_path, scripts, styles):
    # One header for every page: the union of their hashes and the map's sources. Each page's meta CSP
    # still applies on top, so the pages other than the map stay as strict as before.
    policy = csp(sorted(set(scripts)), sorted(set(styles)), connect=True, frame_ancestors=True,
                 extra=merge_csp(APP_CSP, MAP_CSP))
    conf, n = re.subn(r'add_header Content-Security-Policy "[^"]*"',
                      f'add_header Content-Security-Policy "{policy}"', conf_path.read_text())
    if n != 1:
        raise BuildError(f'{conf_path}: expected exactly one Content-Security-Policy add_header line, found {n}')
    conf_path.write_text(conf)


def build(timetables, out, today, base_path='', nginx_conf=None, state_path=None, noindex=False, site_url=''):
    files = sorted(Path(timetables).glob('*/*.ics'))
    if not files:
        raise BuildError(f'no calendars found in {timetables}/<term>/<GROUP>.ics')
    by_group = {}
    for path in files:
        group, term = load_term(path)
        by_group.setdefault(group, []).append(term)
    clash = [g for g in by_group if g.lower() in (DATA_DIR, MAP_DIR, ICONS_DIR, PRIVACY_DIR, ASSETS_DIR)]
    if clash:
        raise BuildError(f'group code "{clash[0]}" is reserved for the site\'s own pages and data files')
    fix_semester_bounds(by_group)
    current = {group: pick_term(terms, today) for group, terms in by_group.items()}

    group_tpl = (SRC / 'group.html').read_text(encoding='utf-8')
    ics_js = (SRC / 'ics.js').read_text(encoding='utf-8')
    insights_js = (SRC / 'insights.js').read_text(encoding='utf-8')
    campus_js = (SRC / 'campus.js').read_text(encoding='utf-8')
    places_js = (SRC / 'places.js').read_text(encoding='utf-8')
    for name, code in (('ics.js', ics_js), ('insights.js', insights_js), ('campus.js', campus_js), ('places.js', places_js)):
        if '@@' in code:
            raise BuildError(f'src/{name} must not contain "@@"')

    refreshed = load_refresh_state(state_path or ROOT / 'refresh-state.json')
    site_url = site_url.rstrip('/')
    if site_url and not re.match(r'^https?://[^/\s]+(/[^\s]*)?$', site_url):
        raise BuildError(f'--site-url must be an absolute http(s) URL, not "{site_url}"')

    out = Path(out)
    _prepare_out(out)
    all_scripts, all_styles = [], []
    assets = AssetHub(out)

    def write(rel, page_scripts_styles):
        page, scripts, styles = page_scripts_styles
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if noindex and NOINDEX not in page:
            page = page.replace('<meta charset="utf-8">', '<meta charset="utf-8">\n' + NOINDEX, 1)
        target.write_text(page.replace('\r\n', '\n'), encoding='utf-8')
        all_scripts.extend(scripts)
        all_styles.extend(styles)

    for group, term in sorted(current.items()):
        write(f'{group}/index.html', render_group(group_tpl, '\n'.join((ics_js, insights_js, campus_js)), term,
                                                  refreshed.get(group), by_group[group], assets=assets, site_url=site_url))
        (out / group / 'plan.ics').write_bytes(term.data())
        (out / group / REMINDER_FILE).write_bytes(with_reminders(term.data()))
        for other in by_group[group]:  # the group's other terms: plan-<term>.ics, opened by the page's ?t=<term>
            if other.term_id != term.term_id:
                (out / group / f'plan-{other.term_id}.ics').write_bytes(other.data())
                (out / group / f'plan-{other.term_id}-przypomnienia.ics').write_bytes(with_reminders(other.data()))
    write('index.html', render_index((SRC / 'index.html').read_text(encoding='utf-8'), current, ics_js, assets=assets, site_url=site_url))
    shutil.copytree(SRC / 'map', out / MAP_DIR, dirs_exist_ok=True)
    write(f'{MAP_DIR}/index.html', render_map((SRC / 'mapa.html').read_text(encoding='utf-8'), ics_js, campus_js, places_js, assets=assets, site_url=site_url))
    write(f'{PRIVACY_DIR}/index.html', render_privacy((SRC / 'prywatnosc.html').read_text(encoding='utf-8'), site_url, assets))
    (out / 'robots.txt').write_text(robots_txt(base_path, noindex, site_url), encoding='utf-8')
    if site_url and not noindex:
        (out / 'sitemap.xml').write_text(sitemap_xml(site_url, current, refreshed), encoding='utf-8')
    (out / '.well-known').mkdir()
    (out / '.well-known' / 'security.txt').write_text(security_txt(today), encoding='utf-8')
    write('404.html', render_404((SRC / '404.html').read_text(encoding='utf-8'), base_path, assets))
    for rel, data in build_data(current, refreshed).items():
        target = out / DATA_DIR / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    # the README chart lives among the deployed files: it can never drift from what the build published
    (out / 'pokrycie-wydzialow.svg').write_text(render_coverage(current), encoding='utf-8')

    write_app(out, sorted(current), assets.written)
    if nginx_conf:
        update_nginx(Path(nginx_conf), all_scripts, all_styles)
    return {group: term.term_id for group, term in current.items()}


def _today_in_warsaw():
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo('Europe/Warsaw')).date()
    except Exception:  # no tz database: the UTC date is off by at most one night
        return dt.datetime.now(dt.timezone.utc).date()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--timetables', default=ROOT / 'timetables', type=Path)
    ap.add_argument('--out', default=ROOT / 'site', type=Path)
    ap.add_argument('--today', type=dt.date.fromisoformat, help='pick terms as of this date (YYYY-MM-DD)')
    ap.add_argument('--base-path', default='', help='URL path the site is served under, e.g. /PlanWAT')
    ap.add_argument('--state', type=Path, help='refresh-state.json with per-group refresh times (default: ./refresh-state.json)')
    ap.add_argument('--nginx', type=Path, help='nginx.conf whose CSP header to pin (Docker build only)')
    ap.add_argument('--noindex', action='store_true', help='ask search engines to skip the whole site (the dev preview)')
    ap.add_argument('--site-url', default='', help='absolute address of the site, e.g. https://kilerdevs.github.io/PlanWAT '
                    '(canonical URLs, social cards and sitemap.xml)')
    args = ap.parse_args(argv)
    try:
        picked = build(args.timetables, args.out, args.today or _today_in_warsaw(), args.base_path, args.nginx, args.state, args.noindex,
                       args.site_url)
    except BuildError as err:
        print(f'build failed: {err}', file=sys.stderr)
        return 1
    for group, term_id in sorted(picked.items()):
        print(f'{group}: {term_id}')
    print(f'built {len(picked)} group page(s) into {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
