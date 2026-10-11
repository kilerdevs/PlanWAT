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

test('maps CATEGORIES, LOCATION, CONTACT and X-PLAN-COLOR onto lesson fields', () => {
  const p = plan(event([
    'UID:e@test',
    'DTSTART;TZID=Europe/Warsaw:20261005T095000',
    'DTEND;TZID=Europe/Warsaw:20261005T112500',
    'SUMMARY:Podstawy grafiki inżynierskiej',
    'CATEGORIES:Laboratorium',
    'LOCATION:108/ 54',
    'CONTACT:Prowadzący',
    'CONTACT:Prowadzący',
    'X-PLAN-COLOR:#6f5ed1',
  ]));
  const [l] = allLessons(p);
  assert.equal(l.type_full, 'Laboratorium');
  assert.equal(l.room, '108/ 54');
  assert.deepEqual(l.teachers_full, ['Prowadzący', 'Prowadzący']);
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

/* ---------- round trip: plan.ics must reproduce the original timetable exactly ---------- */
function originalData() {
  const html = fs.readFileSync(path.join(ROOT, 'tests', 'fixtures', 'v1-page.html'), 'utf8');
  const m = html.match(/<script type="application\/json" id="plan-data">([\s\S]*?)<\/script>/);
  return JSON.parse(m[1]);
}
const ROMAN = { I: 1, II: 2, III: 3, IV: 4, V: 5, VI: 6, VII: 7, VIII: 8, IX: 9, X: 10, XI: 11, XII: 12 };
function oldLabel(label) {
  const pad = (n) => String(n).padStart(2, '0');
  return String(label)
    .replace(/(\d{1,2})\s+(XII|XI|X|IX|VIII|VII|VI|V|IV|III|II|I)\b/g, (m, d, r) => pad(d) + '.' + pad(ROMAN[r]))
    .replace(/\s*[-–]\s*/, '–');
}

test('the WCY26KY3S1 calendar reproduces the original timetable', () => {
  const orig = originalData();
  const p = PlanICS.toPlan(PlanICS.parse(fs.readFileSync(path.join(ROOT, 'timetables', '2026-27-zima', 'WCY26KY3S1.ics'), 'utf8')));

  assert.equal(p.meta.group, orig.meta.group);
  assert.equal(p.meta.generated, orig.meta.generated);
  assert.equal(p.weeks.length, orig.weeks.length);

  let count = 0;
  orig.weeks.forEach((ow, i) => {
    const w = p.weeks[i];
    assert.equal(w.monday, ow.monday, `week ${i + 1} monday`);
    assert.equal(w.label, oldLabel(ow.label), `week ${i + 1} label`);
    assert.deepEqual(Object.keys(w.days).sort(), Object.keys(ow.days).sort(), `week ${i + 1} days`);
    Object.keys(ow.days).forEach((k) => {
      const want = ow.days[k].map((e) => ({
        date: e.date, start: e.start, end: e.end,
        subject_full: e.subject_full, type_full: e.type_full,
        room: e.room === '-' ? '' : e.room, teachers_full: e.teachers_full,
      }));
      assert.deepEqual(w.days[k], want, `week ${i + 1} ${k}`);
      count += want.length;
    });
  });
  assert.equal(count, 216);

  const used = new Set(allLessons(p).map((l) => l.subject_full));
  used.forEach((s) => assert.equal(p.subjectColors[s], orig.subjectColors[s].toLowerCase(), `colour of ${s}`));
});
