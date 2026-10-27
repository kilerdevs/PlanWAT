"""WTC events -> a PlanWAT calendar (LF text; the refresh turns it into CRLF).

Mirrors the WLO Plansoft import conventions: PRODID -//PlanWAT//WTC//PL,
`@wtc` UIDs (`{date}T{hhmm}-{group}[-n]`), X-PLAN-SOURCE:wtc-plansoft,
VEVENTs without RRULE, per-subject X-PLAN-COLOR sampled from legend boxes,
`wyjazd studyjny` LOCATION for roomless `*/wyj` classes, stable sort.

Staff names are parse intermediates only: they steer the room/teacher split
in parse.py, and neither they nor the teachers' degrees ever reach the
calendar (no CONTACT line, no instructor line in DESCRIPTION). The sort key
still orders by the resolved teacher string, exactly like the one-off
import did — ordering by a name does not publish it, and it keeps the
output stable.

Recovered from the one-off WTC import; vs the recovered script the
hardcoded paths, dates and semester bounds are parameters, pymupdf is
imported lazily, and the per-group loop moved to the driver (one PDF per
refresh item).
"""
import re
from collections import Counter

import core

from . import cells as C
from . import match as M
from .parse import BLOCKS, TYPEMAP, parse_cell, parse_legend_full

VTIMEZONE = """BEGIN:VTIMEZONE
TZID:Europe/Warsaw
X-LIC-LOCATION:Europe/Warsaw
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE""".split('\n')


def esc(text):
    return (str(text).replace('\\', '\\\\').replace(';', '\\;')
            .replace(',', '\\,').replace('\n', '\\n'))


def fold(line):
    if len(line.encode('utf-8')) <= 75:
        return line
    chunks, cur, limit = [], b'', 75
    for ch in line:
        b = ch.encode('utf-8')
        if len(cur) + len(b) > limit:
            chunks.append(cur)
            cur, limit = b'', 74
        cur += b
    chunks.append(cur)
    return '\n '.join(c.decode('utf-8') for c in chunks)


def updated_of(path):
    """YYYYMMDD from the PDF's `Data aktualizacji: DD.MM.YYYY` footer."""
    import pymupdf
    doc = pymupdf.open(path)
    for page in doc:
        m = re.search(r'Data aktualizacji:\s*(\d{2})[.-](\d{2})[.-](\d{4})',
                      page.get_text())
        if m:
            return m.group(3) + m.group(2) + m.group(1)
    return None


def sample_color(path, apos):
    """Robust abbr-box color: first bright-enough pixel around the point."""
    import pymupdf
    if not apos:
        return None
    doc = pymupdf.open(path)
    pix = doc[apos[0]].get_pixmap(dpi=72)
    w, h, n = pix.width, pix.height, pix.n
    buf = bytes(pix.samples)

    def _px(x, y):
        x, y = int(x), int(y)
        if x < 0 or y < 0 or x >= w or y >= h:
            return None
        o = (y * w + x) * n
        return buf[o], buf[o + 1], buf[o + 2]

    x, y = apos[1], apos[2]
    for dx, dy in [(0, 0), (-4, -3), (4, -3), (-4, 3), (4, 3), (0, -4), (0, 4)]:
        px = _px(x + dx, y + dy)
        if px is None:
            continue
        r, g, b = px
        if r + g + b > 90:  # skip dark glyph pixels
            hx = '#%02X%02X%02X' % (r, g, b)
            if not M.is_gray_white(hx):
                return hx
            return None
    return None


def convert_pdf(group, pdf_path, today, period):
    """One crawled WTC PDF -> the group's calendar text (LF line endings)."""
    base_year = today.year if today.month >= 9 else today.year - 1
    generated = '%04d%02d%02d' % (today.year, today.month, today.day)
    subs = parse_legend_full(pdf_path, base_year)
    colors = {}
    for abbr, v in subs.items():
        if v.get('apos'):
            c = sample_color(pdf_path, v['apos'])
            if c:
                colors[abbr] = c
    bands, blocks, cc = C.extract_cells(pdf_path, base_year)
    events = []
    skips = Counter()
    for c in cc:
        r = parse_cell(c['lines'], subs)
        if 'skip' in r:
            skips[r['skip']] += 1
            continue
        if c['block'] not in BLOCKS:
            skips['bad-block:' + c['block']] += 1
            continue
        start, end = BLOCKS[c['block']]
        date = c['date'].replace('-', '')
        summary = subs[r['subj']]['name'] if not r.get('raw_subj') else r['subj']
        if not summary:
            skips['empty-summary:' + r['subj']] += 1
            continue
        cat = TYPEMAP.get(r['type'], r['type']) if r.get('type') else None
        room = core.public_room(r['room'].strip())  # a teacher read into the room column is dropped, not published
        if not room and (r.get('type') or '').endswith('/wyj'):
            room = 'wyjazd studyjny'
        desc = []
        if cat:
            desc.append(cat)
        if r['markers']:
            desc.append('Grupy: ' + ', '.join(r['markers']))
        ev = {'date': date, 'start': start, 'end': end,
              'summary': summary, 'cat': cat, 'room': room,
              'teachers': r['teachers'], 'desc': desc,
              'color': colors.get(r['subj'])}
        events.append(ev)
    # stable order + dedup UID collisions (same slot twice)
    events.sort(key=lambda e: (e['date'], e['start'], e['summary'],
                               e['room'], ','.join(e['teachers'])))
    if not events:
        raise ValueError('%s: no events parsed (%s)' % (group, dict(skips)))
    dates = sorted(e['date'] for e in events)
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//PlanWAT//WTC//PL',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
        'X-WR-CALNAME:%s' % esc('Plan zajęć ' + group),
        'X-WR-CALDESC:%s' % esc('Nieoficjalny plan zajęć %s (WTC Plansoft)' % group),
        'X-WR-TIMEZONE:Europe/Warsaw',
        'REFRESH-INTERVAL;VALUE=DURATION:PT12H',
        'X-PUBLISHED-TTL:PT12H',
        'X-PLAN-GROUP:%s' % esc(group),
        'X-PLAN-SOURCE:wtc-plansoft',
        'X-PLAN-PERIOD:%s' % esc(period),
        'X-PLAN-UPDATED:%s' % (updated_of(pdf_path) or generated),
        'X-PLAN-SEMESTER-START:%s' % dates[0],
        'X-PLAN-SEMESTER-END:%s' % dates[-1],
        'X-PLAN-GENERATED:%s' % generated,
    ] + VTIMEZONE
    seen = Counter()
    for e in events:
        key = (e['date'], e['start'])
        seen[key] += 1
        suffix = '-%d' % seen[key] if seen[key] > 1 else ''
        lines += [
            'BEGIN:VEVENT',
            'UID:%sT%s-%s%s@wtc' % (e['date'], e['start'][:4], group.lower(), suffix),
            'DTSTAMP:%sT000000Z' % generated,
            'DTSTART;TZID=Europe/Warsaw:%sT%s00' % (e['date'], e['start']),
            'DTEND;TZID=Europe/Warsaw:%sT%s00' % (e['date'], e['end']),
            'SUMMARY:%s' % esc(e['summary']),
        ]
        if e['cat']:
            lines.append('CATEGORIES:%s' % esc(e['cat']))
        if e['room']:
            lines.append('LOCATION:%s' % esc(e['room']))
        if e['desc']:
            lines.append('DESCRIPTION:%s' % esc('\n'.join(e['desc'])))
        if e['color']:
            lines.append('X-PLAN-COLOR:%s' % e['color'])
        lines.append('END:VEVENT')
    lines.append('END:VCALENDAR')
    return '\n'.join(fold(l) for l in lines) + '\n'
