# Calendar format

Each timetable is a standard iCalendar file ([RFC 5545](https://www.rfc-editor.org/rfc/rfc5545)) at
`timetables/<term>/<GROUP>.ics`. Any calendar app can read it; PlanWAT reads the properties below.

## File

- UTF-8, **CRLF** line endings, lines folded at 75 octets (continuation lines start with one space).
- `<GROUP>` (the file name) is the WAT group code: 2–32 letters, digits and underscores, e.g. `WCY26KY3S1`.
- `<term>` (the folder) is lowercase letters, digits and dashes, e.g. `2026-27-zima`.

## Calendar properties

| Property | Required | Used for |
|---|---|---|
| `X-PLAN-GROUP` | recommended | Group code shown in the header. Must equal the file name; falls back to `X-WR-CALNAME` minus a leading "Plan zajęć". |
| `X-PLAN-FACULTY` | optional | "Wydział …" in the header, and the section on the group list. Hidden when absent. |
| `X-PLAN-TERM` | optional | "Plan zajęć · semestr zimowy 2026/27". |
| `X-PLAN-SEMESTER-START` | recommended | First day of the term (`YYYYMMDD`). Weeks start on its Monday. Without it, the first class. |
| `X-PLAN-SEMESTER-END` | recommended | Last day shown in the header. Weeks run to its week. Without it, the last class. |
| `X-PLAN-GENERATED` | optional | "Wygenerowano …" in the header. |
| `X-WR-CALNAME`, `X-WR-CALDESC`, `X-WR-TIMEZONE` | optional | For calendar apps. |
| `REFRESH-INTERVAL`, `X-PUBLISHED-TTL` | optional | How often subscribed calendar apps refetch (e.g. `PT12H`). |

Weeks without classes (holidays, exam session) still appear between the semester start and end, with a note pointing to
e-dziekanat.

## Event properties

| Property | Required | Used for |
|---|---|---|
| `UID` | yes | Stable identity for calendar apps. Keep it the same when a class is corrected, e.g. `20261002T0800-wcy26ky3s1@planwat`. |
| `DTSTART`, `DTEND` (or `DURATION`) | yes | Start and end. Local times with `TZID=Europe/Warsaw` are read as wall-clock times; UTC times (`…Z`) are converted. All-day events are ignored. |
| `SUMMARY` | yes | Subject name, e.g. `Matematyka I`. Events with the same summary share a colour and a legend entry. |
| `CATEGORIES` | recommended | Class type: `Wykład`, `Ćwiczenia`, `Laboratorium`, `Zaliczenie`, `Spotkanie organizacyjne`. The first value is used. |
| `LOCATION` | recommended | Room, e.g. `314 S`. |
| `CONTACT` | optional, repeatable | One per teacher, e.g. `dr inż. Janusz Torzewski`. |
| `X-PLAN-COLOR` | optional | Subject colour as `#rrggbb`. Anything else falls back to a fixed palette colour derived from the subject name. |
| `DESCRIPTION` | optional | Shown by calendar apps; not read by PlanWAT. |
| `RRULE` | optional | `FREQ=WEEKLY` or `DAILY` with `INTERVAL`, `COUNT`, `UNTIL` and `BYDAY`. Other rules show only the first occurrence. |
| `EXDATE` | optional | Dates or date-times removed from a repeating event. |
| `STATUS:CANCELLED` | optional | The event is skipped. |

Text values use iCalendar escaping (`\,` `\;` `\\` `\n`).

## Example

```
BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//PlanWAT//Plan zajęć//PL
X-WR-CALNAME:Plan zajęć WCY26KY3S1
X-PLAN-GROUP:WCY26KY3S1
X-PLAN-FACULTY:Cybernetyki
X-PLAN-TERM:semestr zimowy 2026/27
X-PLAN-SEMESTER-START:20260928
X-PLAN-SEMESTER-END:20270222
BEGIN:VTIMEZONE
TZID:Europe/Warsaw
...
END:VTIMEZONE
BEGIN:VEVENT
UID:20261005T0950-wcy26ky3s1@planwat
DTSTAMP:20260928T000000Z
DTSTART;TZID=Europe/Warsaw:20261005T095000
DTEND;TZID=Europe/Warsaw:20261005T112500
SUMMARY:Matematyka I
CATEGORIES:Wykład
LOCATION:314 S
CONTACT:dr Arkadiusz Szymaniec
X-PLAN-COLOR:#c14953
END:VEVENT
END:VCALENDAR
```

`timetables/2026-27-zima/WCY26KY3S1.ics` is a complete real example (216 classes), and
[`tools/export_ics.py`](../tools/export_ics.py) shows how one is written.
