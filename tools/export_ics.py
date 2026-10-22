#!/usr/bin/env python3
"""One-time export: the original page's embedded timetable JSON -> timetables/2026-27-zima/WCY26KY3S1.ics.

The timetables/ calendars are the source of truth from now on; this script only records how it was first produced.
Usage: python3 tools/export_ics.py [source.html] [out.ics]
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'tests' / 'fixtures' / 'v1-page.html'
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / 'timetables' / '2026-27-zima' / 'WCY26KY3S1.ics'

# Values the original page showed in its header (not present in the JSON).
FACULTY = 'Cybernetyki'
TERM = 'semestr zimowy 2026/27'
SEMESTER_END = '20270222'
UID_DOMAIN = 'planwat'

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
    """Fold at 75 octets without splitting a UTF-8 character."""
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
    return '\r\n '.join(c.decode('utf-8') for c in chunks)


def local(date, hhmm):
    return date.replace('-', '') + 'T' + hhmm.replace(':', '') + '00'


html = SRC.read_text(encoding='utf-8')
data = json.loads(re.search(r'<script type="application/json" id="plan-data">(.*?)</script>', html, re.S).group(1))
group = data['meta']['group']
generated = data['meta']['generated'].replace('-', '')
colors = {k: v.lower() for k, v in data['subjectColors'].items()}

lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//PlanWAT//Plan zajęć//PL',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    f'X-WR-CALNAME:{esc("Plan zajęć " + group)}',
    f'X-WR-CALDESC:{esc("Nieoficjalny plan zajęć grupy " + group)}',
    'X-WR-TIMEZONE:Europe/Warsaw',
    'REFRESH-INTERVAL;VALUE=DURATION:PT12H',
    'X-PUBLISHED-TTL:PT12H',
    f'X-PLAN-GROUP:{esc(group)}',
    f'X-PLAN-FACULTY:{esc(FACULTY)}',
    f'X-PLAN-TERM:{esc(TERM)}',
    f'X-PLAN-SEMESTER-START:{data["weeks"][0]["monday"].replace("-", "")}',
    f'X-PLAN-SEMESTER-END:{SEMESTER_END}',
    f'X-PLAN-GENERATED:{generated}',
] + VTIMEZONE

count = 0
for week in data['weeks']:
    for day in week['days'].values():
        for ev in day:
            desc = ev['type_full']
            lines += [
                'BEGIN:VEVENT',
                f'UID:{local(ev["date"], ev["start"])[:13]}-{group.lower()}@{UID_DOMAIN}',
                f'DTSTAMP:{generated}T000000Z',
                f'DTSTART;TZID=Europe/Warsaw:{local(ev["date"], ev["start"])}',
                f'DTEND;TZID=Europe/Warsaw:{local(ev["date"], ev["end"])}',
                f'SUMMARY:{esc(ev["subject_full"]) + " (" + esc(desc) + ")"}',
                f'CATEGORIES:{esc(ev["type_full"])}',
            ]
            if ev.get('room') and ev['room'] != '-':
                lines.append(f'LOCATION:{esc(ev["room"])}')
            lines.append(f'DESCRIPTION:{esc(desc)}')
            if ev['subject_full'] in colors:
                lines.append(f'X-PLAN-COLOR:{colors[ev["subject_full"]]}')
            lines.append('END:VEVENT')
            count += 1
lines.append('END:VCALENDAR')

OUT.write_bytes(('\r\n'.join(fold(l) for l in lines) + '\r\n').encode('utf-8'))
print(f'wrote {OUT.name}: {count} events, {OUT.stat().st_size} bytes')
