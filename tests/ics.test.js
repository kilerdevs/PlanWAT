// Tests for src/ics.js (the in-browser iCalendar reader/writer).
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
  /* the faculties write room codes with a stray space after the slash; both forms are the same room */
  assert.equal(l.room, '108/54');
  assert.equal(l.teachers_full, undefined);
  assert.equal(p.subjectColors['Podstawy grafiki inżynierskiej'], '#6f5ed1');
});

test('normalises the space after a slash in room codes without joining separate rooms', () => {
  const rooms = allLessons(plan([].concat(
    event(['UID:r1@test', 'DTSTART:20261005T080000', 'DTEND:20261005T093500', 'SUMMARY:A', 'LOCATION:54/ 62']),
    event(['UID:r2@test', 'DTSTART:20261005T095000', 'DTEND:20261005T112500', 'SUMMARY:B', 'LOCATION:29/ 54 30/ 54'])
  ))).map((l) => l.room);
  assert.deepEqual(rooms, ['54/62', '29/54 30/54']);
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

test('a class listed twice (same time, subject, type and room) is shown once', () => {
  const ev = (room) => event(['UID:x' + room, 'DTSTART;TZID=Europe/Warsaw:20261015T100000', 'DTEND;TZID=Europe/Warsaw:20261015T113000',
    'SUMMARY:Matematyka', 'CATEGORIES:Wykład', 'LOCATION:' + room]);
  const p = plan([...ev('A1'), ...ev('A1'), ...ev('B2')]);
  assert.equal(allLessons(p).length, 2);
});

test('subjectsOf lists every subject with its count, sorted', () => {
  const ev = (n, s) => event(['UID:' + n, 'DTSTART:20261015T100000', 'DTEND:20261015T113000', 'SUMMARY:' + s, 'X-PLAN-COLOR:#aabbcc']);
  const parsed = PlanICS.parse(cal([...ev(1, 'Fizyka'), ...ev(2, 'Algebra'), ...ev(3, 'Fizyka')]));
  assert.deepEqual(PlanICS.subjectsOf(parsed).map((s) => [s.name, s.count, s.color]), [['Algebra', 1, '#aabbcc'], ['Fizyka', 2, '#aabbcc']]);
});

test('hidden subjects drop out of the plan and out of the calendar text', () => {
  const ev = (n, s) => event(['UID:' + n, 'DTSTART:20261015T100000', 'DTEND:20261015T113000', 'SUMMARY:' + s]);
  const raw = cal([...ev(1, 'Fizyka'), ...ev(2, 'Algebra\, liniowa'), 'X-KEEP:1']);
  const parsed = PlanICS.parse(raw);
  assert.deepEqual(allLessons(PlanICS.toPlan(PlanICS.withoutSubjects(parsed, ['Fizyka']))).map((l) => l.subject_full), ['Algebra, liniowa']);
  const text = PlanICS.filterText(raw, ['Algebra, liniowa']);
  assert.ok(text.includes('SUMMARY:Fizyka') && !text.includes('Algebra'));
  assert.ok(text.includes('X-KEEP:1') && text.trim().endsWith('END:VCALENDAR'));
  assert.equal(PlanICS.parse(text).events.length, 1);
  assert.equal(PlanICS.filterText(raw, []), raw);
});

test('subjectsOf counts each subject per class type, the usual parts first', () => {
  const ev = (n, s, t) => event(['UID:' + n, 'DTSTART:20261015T100000', 'DTEND:20261015T113000', 'SUMMARY:' + s, ...(t ? ['CATEGORIES:' + t] : [])]);
  const parsed = PlanICS.parse(cal([...ev(1, 'Fizyka', 'Zaliczenie'), ...ev(2, 'Fizyka', 'Laboratorium'), ...ev(3, 'Fizyka', 'Wykład'),
    ...ev(4, 'Fizyka', 'Laboratorium'), ...ev(5, 'Fizyka', 'Ćwiczenia'), ...ev(6, 'Algebra', '')]));
  const [algebra, fizyka] = PlanICS.subjectsOf(parsed);
  assert.deepEqual(fizyka.types, [{ type: 'Wykład', count: 1 }, { type: 'Ćwiczenia', count: 1 }, { type: 'Laboratorium', count: 2 }, { type: 'Zaliczenie', count: 1 }]);
  assert.deepEqual(algebra.types, [{ type: '', count: 1 }]);
});

test('a hidden [subject, type] pair drops only those classes, from the plan and from the calendar text', () => {
  const ev = (n, s, t) => event(['UID:' + n, 'DTSTART:20261015T' + (10 + n) + '0000', 'DTEND:20261015T' + (10 + n) + '3000', 'SUMMARY:' + s, 'CATEGORIES:' + t]);
  const raw = cal([...ev(1, 'Fizyka', 'Wykład'), ...ev(2, 'Fizyka', 'Ćwiczenia'), ...ev(3, 'Algebra\, liniowa', 'Wykład'),
    ...ev(4, 'Algebra\, liniowa', 'Lab\\, wyjazd')]);
  const parsed = PlanICS.parse(raw);
  const kept = (hidden) => allLessons(PlanICS.toPlan(PlanICS.withoutSubjects(parsed, hidden))).map((l) => l.subject_full + '/' + l.type_full);
  assert.deepEqual(kept([['Fizyka', 'Ćwiczenia']]), ['Fizyka/Wykład', 'Algebra, liniowa/Wykład', 'Algebra, liniowa/Lab, wyjazd']);
  assert.deepEqual(kept(['Fizyka', ['Algebra, liniowa', 'Lab, wyjazd']]), ['Algebra, liniowa/Wykład']);
  assert.deepEqual(kept([['Fizyka', 'Wykład'], ['Fizyka', 'Ćwiczenia']]), ['Algebra, liniowa/Wykład', 'Algebra, liniowa/Lab, wyjazd']);
  assert.deepEqual(kept([['Fizyka', 'Seminarium'], ['Fizyka'], 'Chemia']).length, 4);  // nothing it names is in the plan
  const text = PlanICS.filterText(raw, [['Fizyka', 'Ćwiczenia'], ['Algebra, liniowa', 'Lab, wyjazd']]);
  assert.deepEqual(PlanICS.parse(text).events.map((e) => e.UID[0].value), ['1', '3']);
  assert.ok(text.trim().endsWith('END:VCALENDAR'));
});

test('physical education without a room is held at the SWF', () => {
  const text = [
    'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//t//t//PL', 'X-PLAN-GROUP:G',
    'BEGIN:VEVENT', 'UID:wf1@t', 'DTSTART:20261014T080000', 'DTEND:20261014T093000', 'SUMMARY:Wychowanie fizyczne', 'END:VEVENT',
    'BEGIN:VEVENT', 'UID:x1@t', 'DTSTART:20261014T100000', 'DTEND:20261014T113000', 'SUMMARY:Analiza', 'LOCATION:314 S', 'END:VEVENT',
    'END:VCALENDAR', ''].join('\r\n');
  const plan = PlanICS.toPlan(PlanICS.parse(text));
  const lessons = plan.weeks.flatMap((w) => Object.values(w.days).flat());
  assert.equal(lessons.find((l) => l.subject_full === 'Wychowanie fizyczne').room, 'SWF');
  assert.equal(lessons.find((l) => l.subject_full === 'Analiza').room, '314 S');
});

/* ---------- writer ---------- */
const NOW = new Date('2026-10-18T12:34:56Z');

function makeLesson(overrides = {}) {
  return Object.assign({
    date: '2026-10-15', start: '08:00', end: '09:35',
    subject_full: 'Matematyka I', type_full: 'Wykład', room: '314 S',
  }, overrides);
}

test('toIcs writes a minimal CRLF calendar with a TZID event and stable output', () => {
  const opts = { name: 'Plan WCY26KY3S1', reminders: [15], colors: { 'Matematyka I': '#2563a8' }, now: NOW };
  const ics = PlanICS.toIcs([makeLesson()], opts);
  assert.ok(ics.startsWith('BEGIN:VCALENDAR\r\n'));
  assert.ok(ics.includes('VERSION:2.0\r\n'));
  assert.ok(ics.includes('PRODID:-//PlanWAT//PlanWAT//PL\r\n'));
  assert.ok(ics.includes('CALSCALE:GREGORIAN\r\n'));
  assert.ok(ics.includes('X-WR-CALNAME:Plan WCY26KY3S1\r\n'));
  assert.match(ics, /DTSTART;TZID=Europe\/Warsaw:20261015T080000\r\n/);
  assert.match(ics, /DTEND;TZID=Europe\/Warsaw:20261015T093500\r\n/);
  assert.ok(ics.includes('DTSTAMP:20261018T123456Z\r\n'));
  assert.ok(ics.includes('SUMMARY:Matematyka I\r\n'));
  assert.ok(ics.includes('CATEGORIES:Wykład\r\n'));
  assert.ok(ics.includes('LOCATION:314 S\r\n'));
  assert.ok(ics.includes('X-PLAN-COLOR:#2563a8\r\n'));
  assert.match(ics, /UID:[^\r\n]+@planwat\r\n/);
  assert.ok(ics.endsWith('END:VCALENDAR\r\n'));
  assert.equal(ics.replace(/\r\n/g, '').includes('\n'), false);
  assert.equal(ics.replace(/\r\n/g, '').includes('\r'), false);

  assert.equal(PlanICS.toIcs([makeLesson()], opts), ics);
  const uid = /UID:([^\r\n]+)/.exec(ics)[1];
  const other = PlanICS.toIcs([makeLesson({ date: '2026-10-16' })], opts);
  assert.notEqual(/UID:([^\r\n]+)/.exec(other)[1], uid);
});

test('toIcs escapes text values', () => {
  const summary = 'A; B, C\\D\nlinia druga';
  const room = 'Sala 12, bud. B; piętro 2';
  const type = 'Ćwiczenia, lab.';
  const ics = PlanICS.toIcs([makeLesson({ subject_full: summary, type_full: type, room })],
    { name: 'Plan; grupa, 1', now: NOW });
  assert.ok(ics.includes('X-WR-CALNAME:Plan\\; grupa\\, 1\r\n'));
  assert.ok(ics.includes('SUMMARY:A\\; B\\, C\\\\D\\nlinia druga\r\n'));
  assert.ok(ics.includes('LOCATION:Sala 12\\, bud. B\\; piętro 2\r\n'));
  assert.ok(ics.includes('CATEGORIES:Ćwiczenia\\, lab.\r\n'));

  const [l] = allLessons(PlanICS.toPlan(PlanICS.parse(ics)));
  assert.equal(l.subject_full, summary);
  assert.equal(l.type_full, type);
  assert.equal(l.room, room);
});

test('toIcs folds long Polish lines at 75 octets and round-trips through parse', () => {
  const summary = 'Zaawansowane przetwarzanie sygnałów i uczenie maszynowe w systemach wbudowanych — laboratorium specjalistyczne';
  const ics = PlanICS.toIcs([makeLesson({ subject_full: summary })], { name: 'Plan', now: NOW });
  const lines = ics.split('\r\n');
  lines.forEach((line) => assert.ok(Buffer.byteLength(line, 'utf8') <= 75, line));
  assert.ok(lines.some((line) => line.startsWith(' ')));
  const [l] = allLessons(PlanICS.toPlan(PlanICS.parse(ics)));
  assert.equal(l.subject_full, summary);
});

test('toIcs writes one DISPLAY VALARM per reminder', () => {
  const ics = PlanICS.toIcs([makeLesson()], { name: 'Plan', reminders: [15, 60], now: NOW });
  assert.equal((ics.match(/BEGIN:VALARM/g) || []).length, 2);
  assert.equal((ics.match(/ACTION:DISPLAY/g) || []).length, 2);
  assert.ok(ics.includes('TRIGGER:-PT15M\r\n'));
  assert.ok(ics.includes('TRIGGER:-PT60M\r\n'));

  const none = PlanICS.toIcs([makeLesson()], { name: 'Plan', reminders: [], now: NOW });
  assert.ok(!none.includes('BEGIN:VALARM'));

  const invalid = PlanICS.toIcs([makeLesson()], { name: 'Plan', reminders: [-15, 'x', NaN, 30], now: NOW });
  assert.equal((invalid.match(/BEGIN:VALARM/g) || []).length, 1);
  assert.ok(invalid.includes('TRIGGER:-PT30M\r\n'));
});

test('toIcs skips breaks and lessons without a valid date or time', () => {
  const ics = PlanICS.toIcs([
    makeLesson({ subject_full: '-' }),
    makeLesson({ subject_full: '–', start: '10:00', end: '11:30' }),
    makeLesson({ date: '2026-02-30' }),
    makeLesson({ date: '2026-13-01' }),
    makeLesson({ start: '24:00', end: '25:00' }),
    makeLesson({ start: '10:00', end: '09:00' }),
    makeLesson({ date: '', start: '', end: '' }),
    makeLesson({ subject_full: 'OK', date: '2026-10-16', start: '10:00', end: '11:30' }),
  ], { name: 'Plan', reminders: [15], now: NOW });
  const parsed = PlanICS.parse(ics);
  assert.equal(parsed.events.length, 1);
  assert.equal(parsed.events[0].SUMMARY[0].value, 'OK');
  assert.equal((ics.match(/BEGIN:VALARM/g) || []).length, 1);
});

test('toIcs includes a minimal Europe/Warsaw VTIMEZONE', () => {
  const ics = PlanICS.toIcs([], { name: 'Plan', now: NOW });
  assert.ok(ics.includes('BEGIN:VTIMEZONE\r\nTZID:Europe/Warsaw\r\n'));
  assert.ok(ics.includes('BEGIN:STANDARD\r\n'));
  assert.ok(ics.includes('BEGIN:DAYLIGHT\r\n'));
  assert.ok(ics.includes('TZOFFSETFROM:+0200\r\nTZOFFSETTO:+0100\r\n'));
  assert.ok(ics.includes('TZOFFSETFROM:+0100\r\nTZOFFSETTO:+0200\r\n'));
  assert.ok(ics.includes('RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU\r\n'));
  assert.ok(ics.includes('RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU\r\n'));
});
