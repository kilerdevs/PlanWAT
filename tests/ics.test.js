// Tests for src/ics.js (the in-browser iCalendar reader).
// Run: docker run --rm -v "$PWD":/w:ro -w /w node:22-alpine node --test tests/ics.test.js
process.env.TZ = 'Europe/Warsaw';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const PlanICS = require('../src/ics.js');

const ROOT = path.join(__dirname, '..');
const CRLF = '\r\n';

function cal(lines) {
  return ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//test//test//PL'].concat(lines, ['END:VCALENDAR']).join(CRLF) + CRLF;
}
function event(props) {
  return ['BEGIN:VEVENT'].concat(props, ['END:VEVENT']);
}
function plan(lines) {
  return PlanICS.toPlan(PlanICS.parse(cal(lines)));
}
function allLessons(p) {
  const out = [];
  p.weeks.forEach((w) => Object.keys(w.days).forEach((k) => w.days[k].forEach((l) => out.push(l))));
  return out;
}

test('unfolds folded lines and unescapes text values', () => {
  // the SUMMARY is folded in the middle of a two-byte UTF-8 character's neighbourhood
  const p = plan(event([
    'UID:a@test',
    'DTSTART;TZID=Europe/Warsaw:20261002T080000',
    'DTEND;TZID=Europe/Warsaw:20261002T093500',
    'SUMMARY:Ochrona własności inte',
    ' lektualnych',
    'LOCATION:134 K\\, 133 K\\; 131 K',
    'DESCRIPTION:linia 1\\nlinia 2',
  ]));
  const [l] = allLessons(p);
  assert.equal(l.subject_full, 'Ochrona własności intelektualnych');
  assert.equal(l.room, '134 K, 133 K; 131 K');
});

test('alarms inside an event (the reminder feed) do not change the class', () => {
  const p = plan(event([
    'UID:a@test',
    'DTSTART;TZID=Europe/Warsaw:20261002T080000',
    'DTEND;TZID=Europe/Warsaw:20261002T093500',
    'SUMMARY:Matematyka I',
    'LOCATION:314 S',
    'BEGIN:VALARM', 'ACTION:DISPLAY', 'DESCRIPTION:Przypomnienie', 'TRIGGER:-PT15M', 'END:VALARM',
  ]));
  const [l] = allLessons(p);
  assert.equal(allLessons(p).length, 1);
  assert.equal(l.subject_full, 'Matematyka I');
  assert.equal(l.room, '314 S');
  assert.equal(l.start, '08:00');
});

test('decode unfolds raw bytes before UTF-8 decoding, even inside a multi-byte character', () => {
  // "Żywienie" with the fold placed between the two bytes of "Ż" (0xC5 0xBB), plus a UTF-8 BOM
  const head = Buffer.from('﻿BEGIN:VCALENDAR\r\nVERSION:2.0\r\nBEGIN:VEVENT\r\nUID:z@test\r\nDTSTART:20261002T080000\r\nDTEND:20261002T093500\r\nSUMMARY:', 'utf8');
  const tail = Buffer.from('ywienie\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n', 'utf8');
  const bytes = Buffer.concat([head, Buffer.from([0xc5, 0x0d, 0x0a, 0x20, 0xbb]), tail]);
  const buf = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.length);
  const [l] = allLessons(PlanICS.toPlan(PlanICS.parse(PlanICS.decode(buf))));
  assert.equal(l.subject_full, 'Żywienie');
});

test('reads TZID times as wall-clock times', () => {
  const [l] = allLessons(plan(event([
    'UID:b@test',
    'DTSTART;TZID=Europe/Warsaw:20261002T080000',
    'DTEND;TZID=Europe/Warsaw:20261002T093500',
    'SUMMARY:Matematyka I',
  ])));
  assert.deepEqual([l.date, l.start, l.end], ['2026-10-02', '08:00', '09:35']);
});

test('converts UTC times to local time', () => {
  // 06:00Z on 2 Oct 2026 is 08:00 in Warsaw (CEST); 07:00Z on 2 Dec is 08:00 (CET)
  const lessons = allLessons(plan([].concat(
    event(['UID:c1@test', 'DTSTART:20261002T060000Z', 'DTEND:20261002T073500Z', 'SUMMARY:A']),
    event(['UID:c2@test', 'DTSTART:20261202T070000Z', 'DTEND:20261202T083500Z', 'SUMMARY:B'])
  )));
  assert.deepEqual(lessons.map((l) => [l.date, l.start, l.end]), [
    ['2026-10-02', '08:00', '09:35'],
    ['2026-12-02', '08:00', '09:35'],
  ]);
});

test('accepts DURATION instead of DTEND', () => {
  const [l] = allLessons(plan(event(['UID:d@test', 'DTSTART:20261002T080000', 'DURATION:PT1H35M', 'SUMMARY:A'])));
  assert.equal(l.end, '09:35');
});

test('maps CATEGORIES, LOCATION and X-PLAN-COLOR onto lesson fields, and never reads who teaches', () => {
  const p = plan(event([
    'UID:e@test',
    'DTSTART;TZID=Europe/Warsaw:20261005T095000',
    'DTEND;TZID=Europe/Warsaw:20261005T112500',
    'SUMMARY:Podstawy grafiki inżynierskiej',
    'CATEGORIES:Laboratorium',
    'LOCATION:108/ 54',
    'CONTACT:ignored',
    'X-PLAN-COLOR:#6f5ed1',
  ]));
  const [l] = allLessons(p);
  assert.equal(l.type_full, 'Laboratorium');
  assert.equal(l.room, '108/ 54');
  assert.equal(l.teachers_full, undefined);
  assert.equal(p.subjectColors['Podstawy grafiki inżynierskiej'], '#6f5ed1');
});

test('falls back to a palette colour when X-PLAN-COLOR is missing or not a hex colour', () => {
  const p = plan([].concat(
    event(['UID:f1@test', 'DTSTART:20261005T080000', 'DTEND:20261005T093500', 'SUMMARY:Fizyka']),
    event(['UID:f2@test', 'DTSTART:20261006T080000', 'DTEND:20261006T093500', 'SUMMARY:Chemia', 'X-PLAN-COLOR:red;background:url(x)'])
  ));
  assert.match(p.subjectColors.Fizyka, /^#[0-9a-f]{6}$/i);
  assert.match(p.subjectColors.Chemia, /^#[0-9a-f]{6}$/i);
});

test('expands a weekly RRULE, honouring UNTIL and EXDATE', () => {
  const lessons = allLessons(plan(event([
    'UID:g@test',
    'DTSTART;TZID=Europe/Warsaw:20261005T095000',
    'DTEND;TZID=Europe/Warsaw:20261005T112500',
    'RRULE:FREQ=WEEKLY;UNTIL=20261102T235959Z',
    'EXDATE;TZID=Europe/Warsaw:20261019T095000',
    'SUMMARY:Matematyka I',
  ])));
  assert.deepEqual(lessons.map((l) => l.date), ['2026-10-05', '2026-10-12', '2026-10-26', '2026-11-02']);
});

test('expands a weekly RRULE with COUNT, INTERVAL and several BYDAY days', () => {
  const lessons = allLessons(plan(event([
    'UID:h@test',
    'DTSTART:20261005T080000',
    'DTEND:20261005T093500',
    'RRULE:FREQ=WEEKLY;INTERVAL=2;BYDAY=MO,TH;COUNT=4',
    'SUMMARY:A',
  ])));
  assert.deepEqual(lessons.map((l) => l.date), ['2026-10-05', '2026-10-08', '2026-10-19', '2026-10-22']);
});

test('builds Monday-based weeks over the semester range, keeping weeks without classes', () => {
  const p = plan(['X-PLAN-SEMESTER-START:20260928', 'X-PLAN-SEMESTER-END:20261019'].concat(
    event(['UID:i@test', 'DTSTART:20261007T080000', 'DTEND:20261007T093500', 'SUMMARY:A'])
  ));
  assert.deepEqual(p.weeks.map((w) => [w.monday, w.label]), [
    ['2026-09-28', '28.09–03.10'],
    ['2026-10-05', '05.10–10.10'],
    ['2026-10-12', '12.10–17.10'],
    ['2026-10-19', '19.10–24.10'],
  ]);
  assert.deepEqual(Object.keys(p.weeks[1].days), ['ŚRODA']);
  assert.deepEqual(p.weeks[0].days, {});
});

test('without a semester range, weeks span the first to the last class', () => {
  const p = plan([].concat(
    event(['UID:j1@test', 'DTSTART:20261007T080000', 'DTEND:20261007T093500', 'SUMMARY:A']),
    event(['UID:j2@test', 'DTSTART:20261021T080000', 'DTEND:20261021T093500', 'SUMMARY:A'])
  ));
  assert.deepEqual(p.weeks.map((w) => w.monday), ['2026-10-05', '2026-10-12', '2026-10-19']);
});

test('sorts lessons within a day by start time', () => {
  const p = plan([].concat(
    event(['UID:k1@test', 'DTSTART:20261007T114000', 'DTEND:20261007T131500', 'SUMMARY:Later']),
    event(['UID:k2@test', 'DTSTART:20261007T080000', 'DTEND:20261007T093500', 'SUMMARY:Earlier'])
  ));
  assert.deepEqual(p.weeks[0].days['ŚRODA'].map((l) => l.subject_full), ['Earlier', 'Later']);
});

test('skips all-day, cancelled and malformed events without throwing', () => {
  const p = plan([].concat(
    event(['UID:l1@test', 'DTSTART;VALUE=DATE:20261007', 'SUMMARY:Dzień wolny']),
    event(['UID:l2@test', 'DTSTART:20261007T080000', 'DTEND:20261007T093500', 'STATUS:CANCELLED', 'SUMMARY:Odwołane']),
    event(['UID:l3@test', 'DTSTART:garbage', 'SUMMARY:Zepsute']),
    event(['UID:l4@test', 'DTSTART:20261007T095000', 'DTEND:20261007T112500', 'SUMMARY:OK'])
  ));
  assert.deepEqual(allLessons(p).map((l) => l.subject_full), ['OK']);
});

test('reads calendar metadata, falling back to X-WR-CALNAME for the group', () => {
  const p = plan([
    'X-WR-CALNAME:Plan zajęć WCY26KY3S1',
    'X-PLAN-FACULTY:Cybernetyki',
    'X-PLAN-TERM:semestr zimowy 2026/27',
    'X-PLAN-SEMESTER-START:20260928',
    'X-PLAN-SEMESTER-END:20270222',
    'X-PLAN-GENERATED:20260928',
  ]);
  assert.deepEqual(p.meta, {
    group: 'WCY26KY3S1',
    faculty: 'Cybernetyki',
    term: 'semestr zimowy 2026/27',
    semesterStart: '2026-09-28',
    semesterEnd: '2027-02-22',
    generated: '2026-09-28',
  });
});

test('rejects a file that is not an iCalendar', () => {
  assert.throws(() => PlanICS.parse('<html>not a calendar</html>'), /iCalendar/);
});

test('initialWeekIndex shows the week holding today, rolling over empty weekends', () => {
  const weeks = [
    { monday: '2026-10-05', days: {} },
    { monday: '2026-10-12', days: {} },
    { monday: '2026-10-19', days: {} },
  ];
  // Thursday -> the week holding today
  assert.equal(PlanICS.initialWeekIndex(weeks, '2026-10-15', 4), 1);
  // Saturday with no weekend lessons -> the following week
  assert.equal(PlanICS.initialWeekIndex(weeks, '2026-10-17', 6), 2);
  // Sunday with no weekend lessons -> the following week
  assert.equal(PlanICS.initialWeekIndex(weeks, '2026-10-18', 0), 2);
  // Saturday in the last week has nowhere to roll -> stays
  assert.equal(PlanICS.initialWeekIndex(weeks, '2026-10-24', 6), 2);
  // before the first week -> the first week
  assert.equal(PlanICS.initialWeekIndex(weeks, '2026-09-01', 2), 0);
  // after the last week -> the last week
  assert.equal(PlanICS.initialWeekIndex(weeks, '2027-03-01', 1), 2);
});

test('initialWeekIndex stays on weekends that have lessons', () => {
  const weeks = [
    { monday: '2026-10-12', days: { SOBOTA: [{ subject_full: 'WF' }] } },
    { monday: '2026-10-19', days: {} },
  ];
  assert.equal(PlanICS.initialWeekIndex(weeks, '2026-10-17', 6), 0);
  assert.equal(PlanICS.initialWeekIndex(weeks, '2026-10-18', 0), 0);
});

/* ---------- snapshot: the WCY26KY3S1 calendar must parse into the pinned plan ----------
   The timetables/ files are corrected over time (rooms, times), so the
   frozen v1 export above is no longer byte-identical. This pins the current
   truth instead: any correction fails loudly, then the snapshot is regenerated:
     node -e "process.env.TZ='Europe/Warsaw';
       const fs=require('fs'), P=require('./src/ics.js');
       const p=P.toPlan(P.parse(fs.readFileSync(
         'timetables/2026-27-zima/WCY26KY3S1.ics','utf8')));
       fs.writeFileSync('tests/fixtures/wcy26ky3s1.plan.json',
         JSON.stringify(p,null,2)+'\n')"
   and committed alongside the timetable fix. */
test('the WCY26KY3S1 calendar matches the pinned plan snapshot', () => {
  const p = PlanICS.toPlan(PlanICS.parse(fs.readFileSync(path.join(ROOT, 'timetables', '2026-27-zima', 'WCY26KY3S1.ics'), 'utf8')));
  const snapshot = JSON.parse(fs.readFileSync(path.join(ROOT, 'tests', 'fixtures', 'wcy26ky3s1.plan.json'), 'utf8'));
  assert.equal(p.meta.group, 'WCY26KY3S1');
  assert.equal(p.weeks.length, 22);
  assert.deepEqual(p, snapshot);
});
