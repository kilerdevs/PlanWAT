#!/usr/bin/env python3
"""Build the static site from the timetables in timetables/<term>/<GROUP>.ics.

Output (default: site/):
    index.html            group list (redirects straight to the group while there is only one)
    <GROUP>/index.html    the timetable page; it fetches ./plan.ics and renders it in the browser
    <GROUP>/plan.ics      the group's current term, byte-for-byte
    <GROUP>/plan-przypomnienia.ics   the same calendar with a reminder 15 minutes before each class
    mapa/index.html       campus map (MapLibre from unpkg, tiles from OpenFreeMap: the only page allowed them)
    prywatnosc/index.html privacy notice and terms of use
    sw.js, manifest.webmanifest, <GROUP>/manifest.webmanifest, icons/   offline worker and home-screen app
    robots.txt, .well-known/security.txt
    404.html

Every page carries a hash-pinned Content-Security-Policy in a <meta> tag (GitHub Pages cannot send
headers). For the Docker/nginx deployment, --nginx writes the union of those hashes (plus
frame-ancestors, which only works as a header) into the given nginx.conf; the Dockerfile does this on
its own copy of deploy/nginx.conf, so no tracked file is ever rewritten.

    python3 build.py                                  # site/, terms picked for today
    python3 build.py --base-path /PlanWAT --today 2026-10-15
    python3 build.py --out /site --nginx deploy/nginx.conf   # inside the Docker build
"""
import argparse
import base64
import dataclasses
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
MARKER = '.planwat-site'
DATA_DIR = 'data'  # site/data/: the JSON files behind the group page's tools
GROUP_RE = re.compile(r'^[A-Za-z0-9_]{2,32}$')
TERM_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,47}$')
FONT_CSS = 'https://fonts.googleapis.com'
FONT_FILES = 'https://fonts.gstatic.com'
MAP_DIR = 'mapa'  # site/mapa/: the campus map
REMINDER_FILE = 'plan-przypomnienia.ics'  # <GROUP>/plan.ics with an alarm before every class
REMINDER_MINUTES = 15
# Extra CSP sources of the map page only: the MapLibre engine (SRI-pinned in src/mapa.html), its tiles,
# and the blob: workers it renders with.
MAP_LIB = 'https://unpkg.com'
MAP_TILES = 'https://tiles.openfreemap.org'
MAP_CSP = {
    'script-src': [MAP_LIB],
    'style-src': [MAP_LIB],
    'connect-src': [MAP_TILES],
    'img-src': ['blob:', MAP_TILES],
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
REPO_URL = 'https://github.com/kilerdevs/PlanWAT'
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


class BuildError(Exception):
    """A timetable or the output directory is not usable; the message says which and why."""


@dataclasses.dataclass
class Term:
    term_id: str
    path: Path | None
    start: dt.date
    end: dt.date
    meta: dict = dataclasses.field(default_factory=dict)


# ---------------------------------------------------------------- calendars

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
    start = _ymd(props.get('X-PLAN-SEMESTER-START', '')) or (min(dates) if dates else None)
    end = _ymd(props.get('X-PLAN-SEMESTER-END', '')) or (max(dates) if dates else None)
    if not start or not end:
        raise BuildError(f'{path}: no X-PLAN-SEMESTER-START/END and no events to infer the term from')
    if dates:
        start, end = min(start, min(dates)), max(end, max(dates))
    end += dt.timedelta(days=6 - end.weekday())  # a term runs to the Sunday of its last week
    meta = {
        'group': group,
        'faculty': props.get('X-PLAN-FACULTY', ''),
        'term': props.get('X-PLAN-TERM', ''),
        'semester_start': _ymd(props.get('X-PLAN-SEMESTER-START', '')) or start,
        'semester_end': _ymd(props.get('X-PLAN-SEMESTER-END', '')) or end - dt.timedelta(days=1),
        'generated': _ymd(props.get('X-PLAN-GENERATED', '')),
    }
    return group, Term(term_id, path, start, end, meta)


def _unfold(path):
    text = path.read_bytes().decode('utf-8')
    return [l for l in re.sub(r'\r?\n[ \t]', '', text.lstrip('﻿')).splitlines() if l]


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


YEAR_RE = re.compile(r'^([A-Za-z]{3}\d{2})')
EPOCH = dt.date(2000, 1, 1)  # day numbers in the data files count from here


def year_of(group):
    """The faculty + intake-year prefix that groups of one year share (WCY26KY3S1 -> WCY26), or None."""
    m = YEAR_RE.match(group)
    return m.group(1).upper() if m else None


def _tz():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo('Europe/Warsaw')
    except Exception:  # no tz database: UTC times are kept as they are
        return None


def build_data(current):
    """The JSON files behind the group page's tools, from every group's current term.

    groups.json            [[group, term label, year prefix], ...]
    year/<PREFIX>.json     every class of the groups of one year, for "Odrabianie"
    Days are counted from 2000-01-01 and times are minutes after midnight, to keep the files small.
    """
    tz = _tz()
    groups = sorted(current)
    years = {}
    for group in groups:
        term = current[group]
        lessons = calendar_lessons(term.path, tz, term.end)
        year = year_of(group)
        if year:
            years.setdefault(year, []).append((group, lessons))
    files = {
        'groups.json': [[g, current[g].meta['term'] or current[g].term_id, year_of(g) or ''] for g in groups],
    }
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


def csp(scripts, styles, connect, frame_ancestors=False, extra=None):
    extra = extra or {}
    more = lambda name: extra.get(name, [])  # noqa: E731
    parts = [
        "default-src 'none'",
        'script-src ' + (' '.join(scripts + more('script-src')) if scripts else "'none'"),
        'style-src ' + ' '.join(styles + [FONT_CSS] + more('style-src')),
        f'font-src {FONT_FILES}',
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


def finish(page, connect, extra=None):
    """Pin the page's inline code into its meta CSP and sanity-check the result."""
    page = themed(page)
    if 'style="' in page:
        raise BuildError('inline style attributes would be blocked by the CSP')
    scripts, styles = inline_hashes(page)
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


def render_group(template, ics_js, term, refreshed=None, terms=()):
    m = term.meta
    e = lambda v: html.escape(v, quote=True)  # noqa: E731
    description = f'Plan zajęć grupy {m["group"]}' + (f' — Wydział {m["faculty"]}' if m['faculty'] else '') + \
        (f', {m["term"]}' if m['term'] else '') + '.'
    refreshed = refreshed or {}
    # Last change of the plan (from the refresh), else the date the calendar says it was generated.
    updated = _stamp(refreshed.get('changed') or refreshed.get('checked')) or (_date(m['generated']) if m['generated'] else '')
    checked = _stamp(refreshed.get('checked'), with_time=True)
    values = {
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
    return finish(page, connect=True, extra=APP_CSP)


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


def render_index(template, current, ics_js=''):
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
        row = (f'    <li class="row" data-group="{code}" data-fac="{faculty_of(code)}">'
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
    return finish(page, connect=True, extra=APP_CSP)


def render_map(template, ics_js, campus_js):
    page = template.replace('@@ICS_JS@@', ics_js).replace('@@CAMPUS_JS@@', campus_js)
    return finish(page, connect=True, extra=merge_csp(MAP_APP_CSP, MAP_CSP))


def render_privacy(template):
    # the notice runs no script at all: it follows the system theme through CSS only (no stored choice)
    return finish(template.replace('@@THEME_HEAD@@' + chr(10), ''), connect=False)


def robots_txt(base_path, noindex):
    if noindex:  # the dev preview: keep it out of search engines altogether
        return 'User-agent: *\nDisallow: /\n'
    base = base_path.rstrip('/')
    return (f'# PlanWAT: nieoficjalne plany zajęć WAT\nUser-agent: *\nAllow: {base}/\n'
            f'Disallow: {base}/{DATA_DIR}/\nDisallow: {base}/dev/\n')


def security_txt(today):
    # RFC 9116: Expires must be less than a year away; the site is rebuilt daily, so 180 days stays fresh
    expires = dt.datetime.combine(today + dt.timedelta(days=180), dt.time(), dt.timezone.utc)
    return (f'Contact: {REPO_URL}/security/advisories/new\n'
            f'Expires: {expires.strftime("%Y-%m-%dT%H:%M:%SZ")}\n'
            'Preferred-Languages: pl, en\n'
            f'Policy: {REPO_URL}/blob/master/SECURITY.md\n')


def render_404(template, base_path):
    return finish(template.replace('@@BASE@@', html.escape(base_path.rstrip('/'), quote=True)), connect=False)


def manifest(name, short_name, scope, up):
    """A web app manifest; every URL is relative to the manifest so the site works under any base path."""
    icon = lambda f, size, kind, purpose='any': {'src': f'{up}{ICONS_DIR}/{f}', 'sizes': size, 'type': kind, 'purpose': purpose}  # noqa: E731
    return json.dumps({
        'id': './', 'name': name, 'short_name': short_name, 'lang': 'pl', 'dir': 'ltr',
        'description': 'Nieoficjalny, czytelny na telefonie plan zajęć grup WAT.',
        'start_url': './', 'scope': scope, 'display': 'standalone',
        'background_color': '#000000', 'theme_color': '#000000',
        'icons': [icon('icon-192.png', '192x192', 'image/png'), icon('icon-512.png', '512x512', 'image/png'),
                  icon('maskable-512.png', '512x512', 'image/png', 'maskable'), icon('icon.svg', 'any', 'image/svg+xml')],
    }, ensure_ascii=False, indent=1)


def write_app(out, groups):
    """Icons, manifests and the service worker; written last, so its version covers every other file."""
    (out / ICONS_DIR).mkdir()
    for f in sorted((SRC / 'icons').glob('*')):
        if f.suffix in ('.png', '.svg'):
            shutil.copyfile(f, out / ICONS_DIR / f.name)
    (out / 'manifest.webmanifest').write_text(manifest('PlanWAT', 'PlanWAT', './', ''), encoding='utf-8')
    for group in groups:
        # the app opens at the group; its scope is the whole site so the map and the front page stay inside it
        (out / group / 'manifest.webmanifest').write_text(manifest(f'PlanWAT · {group}', group, '../', '../'), encoding='utf-8')
    digest = hashlib.sha256()
    # .well-known/security.txt changes its expiry date daily; it must not reset everyone's offline copy
    for f in sorted(p for p in out.rglob('*') if p.is_file() and p.relative_to(out).parts[0] != '.well-known'):
        digest.update(f.relative_to(out).as_posix().encode() + b'\0' + f.read_bytes())
    sw = (SRC / SW_FILE).read_text(encoding='utf-8')
    if sw.count('@@VERSION@@') != 1:
        raise BuildError('src/sw.js must contain "@@VERSION@@" exactly once')
    (out / SW_FILE).write_text(sw.replace('@@VERSION@@', digest.hexdigest()[:16]), encoding='utf-8')


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


def build(timetables, out, today, base_path='', nginx_conf=None, state_path=None, noindex=False):
    files = sorted(Path(timetables).glob('*/*.ics'))
    if not files:
        raise BuildError(f'no calendars found in {timetables}/<term>/<GROUP>.ics')
    by_group = {}
    for path in files:
        group, term = load_term(path)
        by_group.setdefault(group, []).append(term)
    clash = [g for g in by_group if g.lower() in (DATA_DIR, MAP_DIR, ICONS_DIR, PRIVACY_DIR)]
    if clash:
        raise BuildError(f'group code "{clash[0]}" is reserved for the site\'s own pages and data files')
    current = {group: pick_term(terms, today) for group, terms in by_group.items()}

    group_tpl = (SRC / 'group.html').read_text(encoding='utf-8')
    ics_js = (SRC / 'ics.js').read_text(encoding='utf-8')
    insights_js = (SRC / 'insights.js').read_text(encoding='utf-8')
    campus_js = (SRC / 'campus.js').read_text(encoding='utf-8')
    for name, code in (('ics.js', ics_js), ('insights.js', insights_js), ('campus.js', campus_js)):
        if '@@' in code:
            raise BuildError(f'src/{name} must not contain "@@"')

    refreshed = load_refresh_state(state_path or ROOT / 'refresh-state.json')

    out = Path(out)
    _prepare_out(out)
    all_scripts, all_styles = [], []

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
                                                  refreshed.get(group), by_group[group]))
        shutil.copyfile(term.path, out / group / 'plan.ics')
        (out / group / REMINDER_FILE).write_bytes(with_reminders(term.path.read_bytes()))
        for other in by_group[group]:  # the group's other terms: plan-<term>.ics, opened by the page's ?t=<term>
            if other.term_id != term.term_id:
                shutil.copyfile(other.path, out / group / f'plan-{other.term_id}.ics')
                (out / group / f'plan-{other.term_id}-przypomnienia.ics').write_bytes(with_reminders(other.path.read_bytes()))
    write('index.html', render_index((SRC / 'index.html').read_text(encoding='utf-8'), current, ics_js))
    write(f'{MAP_DIR}/index.html', render_map((SRC / 'mapa.html').read_text(encoding='utf-8'), ics_js, campus_js))
    write(f'{PRIVACY_DIR}/index.html', render_privacy((SRC / 'prywatnosc.html').read_text(encoding='utf-8')))
    (out / 'robots.txt').write_text(robots_txt(base_path, noindex), encoding='utf-8')
    (out / '.well-known').mkdir()
    (out / '.well-known' / 'security.txt').write_text(security_txt(today), encoding='utf-8')
    write('404.html', render_404((SRC / '404.html').read_text(encoding='utf-8'), base_path))
    for rel, data in build_data(current).items():
        target = out / DATA_DIR / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    write_app(out, sorted(current))
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
    args = ap.parse_args(argv)
    try:
        picked = build(args.timetables, args.out, args.today or _today_in_warsaw(), args.base_path, args.nginx, args.state, args.noindex)
    except BuildError as err:
        print(f'build failed: {err}', file=sys.stderr)
        return 1
    for group, term_id in sorted(picked.items()):
        print(f'{group}: {term_id}')
    print(f'built {len(picked)} group page(s) into {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
