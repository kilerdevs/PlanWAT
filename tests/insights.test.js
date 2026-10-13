// Tests for src/insights.js (statistics, subject progress, plan changes, group comparison, free rooms).
// Run: node --test tests/insights.test.js
process.env.TZ = 'Europe/Warsaw';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const PlanICS = require('../src/ics.js');
const I = require('../src/insights.js');

const ROOT = path.join(__dirname, '..');
const REAL = PlanICS.toPlan(PlanICS.parse(fs.readFileSync(path.join(ROOT, 'timetables', '2026-27-zima', 'WCY26KY3S1.ics'), 'utf8')));

function L(date, start, end, subject, type = 'Wykład', room = '100 S') {
  return { date, start, end, subject_full: subject, type_full: type, room, teachers_full: [] };
}
/* a plan model with the lessons placed in their weeks, the way PlanICS.toPlan builds it */
function planOf(list) {
  const keys = ['NIEDZIELA', 'PONIEDZIAŁEK', 'WTOREK', 'ŚRODA', 'CZWARTEK', 'PIĄTEK', 'SOBOTA'];
  const weeks = {};
  list.forEach((l) => {
    const d = new Date(l.date + 'T12:00:00');
    const mon = new Date(d);
    mon.setDate(d.getDate() - ((d.getDay() + 6) % 7));
    const iso = mon.toISOString().slice(0, 10);
    const w = weeks[iso] = weeks[iso] || { monday: iso, label: iso, days: {} };
    (w.days[keys[d.getDay()]] = w.days[keys[d.getDay()]] || []).push(l);
  });
  return { meta: {}, subjectColors: {}, weeks: Object.keys(weeks).sort().map((k) => weeks[k]) };
}

test('formats durations and Polish plurals', () => {
  assert.equal(I.fmtDuration(45), '45 min');
  assert.equal(I.fmtDuration(120), '2 h');
  assert.equal(I.fmtDuration(95), '1 h 35 min');
  assert.deepEqual([1, 2, 5, 12, 22, 25].map((n) => I.plural(n, 'grupa', 'grupy', 'grup')),
    ['grupa', 'grupy', 'grup', 'grup', 'grupy', 'grup']);
  assert.equal(I.hhmm(495), '08:15');
  assert.equal(I.toMin('09:50'), 590);
  assert.equal(I.norm('  Matematyka   I '), 'matematyka i');
});

test('lists every lesson in order and finds breaks of at least the given length', () => {
  const day = [L('2026-10-15', '08:00', '09:35', 'A'), L('2026-10-15', '09:50', '11:25', 'B'),
    L('2026-10-15', '09:50', '11:25', 'B2'), L('2026-10-15', '15:45', '17:20', 'C')];
  assert.deepEqual(I.gaps(day, 30), [{ index: 2, from: 685, to: 945, minutes: 260 }]);
  assert.deepEqual(I.gaps(day, 10).map((g) => g.minutes), [15, 260]);
  assert.equal(I.lessons(REAL).length, 216);
});

test('subject progress counts finished classes and finds the next one', () => {
  const p = planOf([L('2026-10-13', '08:00', '09:35', 'Fizyka'), L('2026-10-15', '08:00', '09:35', 'Fizyka', 'Ćwiczenia'),
    L('2026-10-15', '11:40', '13:15', 'Fizyka', 'Ćwiczenia'), L('2026-10-20', '08:00', '09:35', 'Algebra', '')]);
  const [algebra, fizyka] = I.subjectProgress(p, '2026-10-15', 10 * 60);
  assert.equal(algebra.subject, 'Algebra');
  assert.deepEqual(algebra.byType, { Inne: 1 });
  assert.equal(fizyka.total, 3);
  assert.equal(fizyka.done, 2);
  assert.equal(fizyka.next.start, '11:40');
  assert.deepEqual(fizyka.byType, { Wykład: 1, Ćwiczenia: 2 });
  assert.ok(I.isExam('Zaliczenie') && !I.isExam('Wykład'));
});

test('statistics of the real timetable', () => {
  const s = I.stats(REAL);
  assert.equal(s.lessons, 216);
  assert.equal(s.minutes, I.lessons(REAL).reduce((m, l) => m + I.toMin(l.end) - I.toMin(l.start), 0));
  assert.ok(s.activeWeeks > 10 && s.activeWeeks <= REAL.weeks.length);
  assert.equal(s.byDow.reduce((a, b) => a + b, 0), s.minutes);
  assert.equal(s.byType.reduce((a, t) => a + t.count, 0), 216);
  assert.ok(s.byType[0].minutes >= s.byType[s.byType.length - 1].minutes);
  assert.equal(s.weekly.length, REAL.weeks.length);
  assert.ok(s.earliest.min <= s.latest.min && s.longest.end > s.longest.start);
  assert.ok(s.topRoom.count > 0);
  const empty = I.stats(planOf([]));
  assert.equal(empty.avgWeekMinutes, 0);
  assert.equal(empty.topRoom, null);
  assert.equal(empty.longest, null);
});

test('diff reports added and removed classes; a moved class shows as both', () => {
  const before = planOf([L('2026-10-15', '08:00', '09:35', 'A'), L('2026-10-16', '08:00', '09:35', 'B')]);
  const after = planOf([L('2026-10-15', '08:00', '09:35', 'A', 'Wykład', '200 S'), L('2026-10-16', '08:00', '09:35', 'B'),
    L('2026-10-16', '08:00', '09:35', 'B')]);
  const d = I.diff(I.fingerprint(before), I.fingerprint(after));
  assert.deepEqual(d.added.map((l) => l.room), ['200 S', '100 S']);
  assert.deepEqual(d.removed.map((l) => l.room), ['100 S']);
  assert.deepEqual(I.diff(I.fingerprint(REAL), I.fingerprint(REAL)), { added: [], removed: [] });
});

test('free windows shared by several groups', () => {
  const a = [L('d', '08:00', '09:35', 'A'), L('d', '11:40', '13:15', 'A')];
  const b = [L('d', '09:50', '11:25', 'B')];
  assert.deepEqual(I.freeWindows([I.intervals(a), I.intervals(b)], 480, 1200, 30), [{ from: 795, to: 1200 }]);
  assert.deepEqual(I.freeWindows([I.intervals(a)], 480, 1200, 30), [{ from: 575, to: 700 }, { from: 795, to: 1200 }]);
  assert.deepEqual(I.freeWindows([[[400, 1300]]], 480, 1200, 30), []);
  assert.ok(I.overlaps(a, 500, 520) && !I.overlaps(a, 575, 700));
  assert.equal(I.byDate(REAL)['2026-10-15'].length, I.lessons(REAL).filter((l) => l.date === '2026-10-15').length);
});

test('catch-up finds the class in other groups of the year and flags clashes', () => {
  assert.equal(I.yearOf('WCY26KY3S1'), 'WCY26');
  assert.equal(I.yearOf('wlo22FO1S0'), 'WLO22');
  assert.equal(I.yearOf('X1'), null);
  const day = I.dayNumber('2026-10-15') - I.dayNumber('2000-01-01');
  const year = {
    epoch: '2000-01-01', groups: ['G1', 'G2', 'ME'],
    names: ['Fizyka', 'Ćwiczenia', '100 S', 'Wykład', 'Chemia'],
    e: [0, 0, 1, 2, day, 480, 575, 1, 0, 1, 2, day, 700, 795, 1, 0, 3, 2, day, 700, 795,
      2, 0, 1, 2, day, 480, 575, 0, 4, 1, 2, day, 480, 575, 0, 0, 1, 2, day - 1, 480, 575],
  };
  const mine = { '2026-10-15': [L('2026-10-15', '08:00', '09:35', 'X')] };
  const found = I.catchUp(year, 'ME', mine, 'fizyka', 'Ćwiczenia', '2026-10-15');
  assert.deepEqual(found.map((f) => [f.group, I.hhmm(f.start), f.clash]), [['G1', '08:00', true], ['G2', '11:40', false]]);
  assert.equal(found[0].date, '2026-10-15');
  assert.equal(I.catchUp(year, 'ME', mine, 'Fizyka', '', '2026-10-15').length, 3);
  // G1's 08:00 class is left out when it is the very class my group attends with it
  const together = { '2026-10-15': [L('2026-10-15', '08:00', '09:35', 'Fizyka', 'Ćwiczenia', '100 S')] };
  assert.deepEqual(I.catchUp(year, 'ME', together, 'Fizyka', 'Ćwiczenia', '2026-10-15').map((f) => f.group), ['G2']);
  assert.equal(I.isoFromDayNumber(I.dayNumber('2027-03-28')), '2027-03-28');
});

test('free rooms on a date and time, with when each one is next taken', () => {
  const d = I.dayNumber('2026-10-15') - I.dayNumber('2000-01-01');
  const data = { epoch: '2000-01-01', rooms: ['100 S', '200 S', '0.24/135'], b: [0, d, 480, 575, 1, d, 700, 795, 2, d - 7, 480, 575] };
  assert.deepEqual(I.freeRooms(data, '2026-10-15', 500, 560), [{ room: '200 S', until: 700 }, { room: '0.24/135', until: null }]);
  assert.deepEqual(I.freeRooms(data, '2026-10-15', 600, 700).map((r) => r.room), ['100 S', '200 S', '0.24/135']);
  assert.equal(I.freeRooms(data, '2026-10-10', 500, 560).length, 3); // a day inside the data with no classes
  assert.equal(I.freeRooms(data, '2027-06-01', 500, 560), null);
  assert.deepEqual(I.dataRange(data), { from: '2026-10-08', to: '2026-10-15' });
  assert.equal(I.dataRange({ epoch: '2000-01-01', rooms: [], b: [] }), null);
  assert.deepEqual(['308 S', '0.24/135', '124 K', '3/23A', 'T3.1W'].map(I.building), ['S', '135', 'K', '23A', '']);
});

test('month grid starts on Monday and pads the edges', () => {
  const oct = I.monthGrid(2026, 9);
  assert.equal(oct.length, 5);
  assert.deepEqual(oct[0], [null, null, null, '2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04']);
  assert.deepEqual(oct[4], ['2026-10-26', '2026-10-27', '2026-10-28', '2026-10-29', '2026-10-30', '2026-10-31', null]);
  assert.equal(I.monthGrid(2027, 1).length, 4); // February 2027 starts on a Monday
});
