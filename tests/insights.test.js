// Tests for src/insights.js (statistics, subject progress, plan changes, group comparison).
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
const WME = PlanICS.toPlan(PlanICS.parse(fs.readFileSync(path.join(ROOT, 'timetables', '2026-27-zima', 'WME24BM1S1.ics'), 'utf8')));

function L(date, start, end, subject, type = 'Wykład', room = '100 S') {
  return { date, start, end, subject_full: subject, type_full: type, room };
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

/* one plan with every kind of block: classes, reservations, breaks, a session period and exams */
const MIX = planOf([
  L('2026-10-20', '08:00', '09:35', 'Fizyka 2', 'Wykład', '108/54'),
  L('2026-10-20', '09:50', '11:25', 'Analiza matematyczna', 'Ćwiczenia', '108/54'),
  L('2026-10-20', '11:40', '13:15', '-', 'Rezerwacja', '-'),
  L('2026-10-20', '13:30', '15:05', 'Biologia', 'Laboratorium', ''),
  L('2026-10-21', '08:00', '09:35', 'Chemia', 'Wykład', '-'),
  L('2026-10-21', '09:50', '11:25', '–', 'Czas do dyspozycji dowódcy', ''),
  L('2026-12-24', '08:00', '09:35', '-', 'przerwa   świąteczna', ''),
  L('2026-12-25', '09:50', '11:25', '-', 'przerwa świąteczna', ''),
  L('2026-12-26', '08:00', '09:35', '-', 'święto', ''),
  L('2027-02-01', '08:00', '09:35', '-', 'Sesja egz. zasadnicza', ''),
  L('2027-02-02', '08:00', '09:35', '-', 'Sesja egz. zasadnicza', ''),
  L('2027-02-15', '08:00', '09:35', '-', 'Sesja egz. poprawkowa', ''),
  L('2026-09-10', '09:50', '11:25', 'Wytrzymałość materiałów', 'Egzamin poprawkowy', '8/62'),
  L('2027-02-01', '09:50', '11:25', 'Systemy wbudowane', 'Egzamin', '15/23A'),
  L('2027-02-02', '11:40', '13:15', 'Grafika w inżynierii biomedycznej', 'Zaliczenie poprawkowe  lab.', '9/54 18/54'),
  L('2027-02-03', '08:00', '09:35', 'Algebra', 'Zaliczenie', '1/1'),
  L('2027-02-03', '10:00', '11:35', 'Fizyka 2', 'Egzamin', '2/2'),
  L('2027-02-04', '08:00', '09:35', '-', 'Egzamin oficerski', ''),
  L('2027-02-04', '09:50', '11:25', 'Ochrona środowiska', 'zaliczenie poprawkowe lab.', '3/3'),
  L('2027-02-10', '08:00', '09:35', '-', 'przerwa międzysemestralna', ''),
  L('2027-02-11', '09:50', '11:25', '-', 'przerwa międzysemestralna', ''),
  L('2027-03-01', '09:50', '11:25', 'Późny przedmiot', 'Egzamin', '9/9'),
]);
MIX.meta = { group: 'WME24BM1S1', semesterStart: '2026-09-28', semesterEnd: '2027-02-22' };

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

test('classifies reservations, breaks, session blocks, exams and credits', () => {
  const lesson = (subject, type) => L('2026-10-20', '08:00', '09:35', subject, type, '100 S');
  const reservation = lesson('-', 'Rezerwacja');
  const officerBlock = lesson('–', 'Czas do dyspozycji dowódcy');
  const breakDay = lesson('-', 'przerwa świąteczna');
  const holiday = lesson('-', 'święto');
  const free = lesson('-', 'Wolne');
  const sessionBlock = lesson('-', 'Sesja egz. zasadnicza');
  const exam = lesson('Systemy wbudowane', 'Egzamin poprawkowy');
  const credit = lesson('Grafika w inżynierii biomedycznej', 'Zaliczenie poprawkowe  lab.');
  const officerExam = lesson('-', 'Egzamin oficerski');

  assert.ok(I.isReservation(reservation) && I.isReservation(officerBlock) && I.isReservation(officerExam));
  assert.ok(!I.isReservation(breakDay) && !I.isReservation(sessionBlock) && !I.isReservation(exam));
  assert.ok(I.isBreak(breakDay) && I.isBreak(holiday) && I.isBreak(free));
  assert.ok(!I.isBreak(reservation) && !I.isBreak(sessionBlock));
  assert.ok(I.isSessionBlock(sessionBlock) && !I.isSessionBlock(exam));
  assert.ok(I.isExam(exam) && !I.isExam(credit) && !I.isExam(sessionBlock) && !I.isExam(officerExam));
  assert.ok(I.isCredit(credit) && !I.isCredit(exam) && !I.isCredit(reservation));
  assert.ok(I.isExam('Zaliczenie') && !I.isExam('Wykład'));  // the old string API still works
});

test('merges consecutive break and session dates by label', () => {
  const br = I.breaks(MIX);
  assert.deepEqual(br, [
    { from: '2026-12-24', to: '2026-12-25', label: 'Przerwa świąteczna', type: 'przerwa świąteczna' },
    { from: '2026-12-26', to: '2026-12-26', label: 'Święto', type: 'święto' },
    { from: '2027-02-10', to: '2027-02-11', label: 'Przerwa międzysemestralna', type: 'przerwa międzysemestralna' },
  ]);
  assert.equal(I.breaksOn(br, '2026-12-25'), br[0]);
  assert.equal(I.breaksOn(br, '2026-12-27'), null);
  assert.equal(I.breaksOn(br, '2027-02-10'), br[2]);
  assert.equal(I.breaksOn(br, '2027-02-12'), null);
  assert.deepEqual(I.sessionRanges(MIX), [
    { from: '2027-02-01', to: '2027-02-02', label: 'Sesja egz. zasadnicza' },
    { from: '2027-02-15', to: '2027-02-15', label: 'Sesja egz. poprawkowa' },
  ]);
});

test('session lists upcoming exams and credits from today, in date and time order', () => {
  const list = I.session(MIX, '2027-02-01');
  assert.deepEqual(list, [
    { date: '2027-02-01', start: '09:50', end: '11:25', subject: 'Systemy wbudowane', type: 'Egzamin', room: '15/23A', kind: 'exam', daysUntil: 0 },
    { date: '2027-02-02', start: '11:40', end: '13:15', subject: 'Grafika w inżynierii biomedycznej', type: 'Zaliczenie poprawkowe  lab.', room: '9/54 18/54', kind: 'credit', daysUntil: 1 },
    { date: '2027-02-03', start: '08:00', end: '09:35', subject: 'Algebra', type: 'Zaliczenie', room: '1/1', kind: 'credit', daysUntil: 2 },
    { date: '2027-02-03', start: '10:00', end: '11:35', subject: 'Fizyka 2', type: 'Egzamin', room: '2/2', kind: 'exam', daysUntil: 2 },
    { date: '2027-02-04', start: '09:50', end: '11:25', subject: 'Ochrona środowiska', type: 'zaliczenie poprawkowe lab.', room: '3/3', kind: 'credit', daysUntil: 3 },
  ]);
  assert.deepEqual(I.session(MIX, '2027-02-01', { from: '2027-02-03', to: '2027-02-03' }).map((x) => x.subject),
    ['Algebra', 'Fizyka 2']);
  assert.deepEqual(I.session(MIX, '2027-02-05'), []);  // the past exam and the blocks are not events
  const later = I.session(MIX, '2027-02-01', { to: '2027-03-31' });
  assert.equal(later.length, 6);
  assert.deepEqual([later[5].subject, later[5].daysUntil], ['Późny przedmiot', 28]);
});

test('statistics split the minutes into teaching, reservations, breaks and sessions', () => {
  const s = I.stats(MIX);
  assert.equal(s.minutes, 22 * 95);
  assert.equal(s.teachingMinutes, 11 * 95);
  assert.equal(s.reservationMinutes, 3 * 95);
  assert.equal(s.breakMinutes, 5 * 95);
  assert.equal(s.sessionMinutes, 3 * 95);
  assert.equal(s.teachingMinutes + s.reservationMinutes + s.breakMinutes + s.sessionMinutes, s.minutes);
  assert.equal(s.subjects, 10);  // "-" reservations are still not subjects
});

test('dayDigest prints the header and one line per class, without breaks or session blocks', () => {
  assert.equal(I.dayDigest(MIX, '2026-10-20'), [
    'Plan WME24BM1S1 · wtorek 20.10',
    '08:00–09:35 Fizyka 2 · 108/54',
    '09:50–11:25 Analiza matematyczna · 108/54',
    '11:40–13:15 Rezerwacja',
    '13:30–15:05 Biologia',
  ].join('\n'));
  const sessionDay = I.dayDigest(MIX, '2027-02-01');
  assert.equal(sessionDay, 'Plan WME24BM1S1 · poniedziałek 01.02\n09:50–11:25 Systemy wbudowane · 15/23A');
  assert.ok(!sessionDay.includes('Sesja egz.'));
  assert.equal(I.dayDigest(MIX, '2026-12-24'), 'Brak zajęć.');
  assert.ok(!I.dayDigest(MIX, '2026-10-20').endsWith('\n'));
});

test('real WME plan: holiday breaks, session ranges and the minute partition', () => {
  assert.deepEqual(I.breaks(WME), [
    { from: '2027-02-10', to: '2027-02-14', label: 'Przerwa międzysemestralna', type: 'przerwa międzysemestralna' },
  ]);
  assert.deepEqual(I.sessionRanges(WME), [
    { from: '2027-02-01', to: '2027-02-04', label: 'Sesja egz. zasadnicza' },
    { from: '2027-02-06', to: '2027-02-09', label: 'Sesja egz. zasadnicza' },
    { from: '2027-02-15', to: '2027-02-21', label: 'Sesja egz. poprawkowa' },
  ]);
  const s = I.stats(WME);
  assert.equal(s.teachingMinutes + s.reservationMinutes + s.breakMinutes + s.sessionMinutes, s.minutes);
  assert.ok(s.teachingMinutes > 0 && s.reservationMinutes > 0 && s.breakMinutes > 0 && s.sessionMinutes > 0);
  const exams = I.session(WME, '2027-02-01');
  assert.ok(exams.length > 0 && exams.every((x) => x.date >= '2027-02-01' && !/^sesja/i.test(x.type)));
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

test('catch-up looks only in peer groups of the same major and matches ordinals', () => {
  assert.equal(I.yearOf('WCY26KY3S1'), 'WCY26');
  assert.equal(I.yearOf('wlo22FO1S0'), 'WLO22');
  assert.equal(I.yearOf('X1'), null);
  assert.deepEqual(I.peersOf('WCY26KY3S1', ['WCY26KY1S1', 'WCY26KY3S1', 'WCY26EL1S1', 'WEL26ELTS6', 'WCY26_Fiz1b']), ['WCY26KY1S1']);
  assert.deepEqual(I.peersOf('X1', ['X1', 'X2']), []);
  const day = I.dayNumber('2026-10-15') - I.dayNumber('2000-01-01');
  const year = {
    epoch: '2000-01-01', groups: ['WCY26KY1S1', 'WCY26KY3S1', 'WCY26EL1S1', 'WCY26ELTS6'],
    names: ['Fizyka', 'Ćwiczenia', '100 S', 'Wykład'],
    // peer of the same major: past class (counts as no. 1), three future ones (no. 4 is beyond my program);
    // other major / other code shape: same classes, never offered
    e: [0, 0, 1, 2, day - 7, 480, 575, 0, 0, 1, 2, day, 480, 575, 0, 0, 1, 2, day + 7, 480, 575, 0, 0, 1, 2, day + 14, 480, 575,
      2, 0, 1, 2, day, 480, 575, 3, 0, 1, 2, day, 480, 575],
  };
  // my group holds three (Fizyka, Ćwiczenia) classes: the peer's 2nd and 3rd are my program
  const mine = {
    '2026-10-01': [L('2026-10-01', '08:00', '09:35', 'Fizyka', 'Ćwiczenia'), L('2026-10-01', '11:40', '13:15', 'Fizyka', 'Ćwiczenia')],
    '2026-10-08': [L('2026-10-08', '08:00', '09:35', 'Fizyka', 'Ćwiczenia')],
    '2026-10-15': [L('2026-10-15', '08:00', '09:35', 'X')],
  };
  const found = I.catchUp(year, 'WCY26KY3S1', mine, 'fizyka', 'Ćwiczenia', '2026-10-15');
  assert.deepEqual(found.map((f) => [f.group, f.n, I.hhmm(f.start), f.clash]),
    [['WCY26KY1S1', 2, '08:00', true], ['WCY26KY1S1', 3, '08:00', false]]);
  assert.equal(found[0].date, '2026-10-15');
  // KY1S1's 08:00 class is left out when it is the very class my group attends with it;
  // the later one is offered as no. 2
  const together = { '2026-10-15': [L('2026-10-15', '08:00', '09:35', 'Fizyka', 'Ćwiczenia', '100 S'), L('2026-10-15', '11:40', '13:15', 'Fizyka', 'Ćwiczenia', '200 S')] };
  const year2 = {
    epoch: '2000-01-01', groups: ['WCY26KY1S1', 'WCY26KY3S1'],
    names: ['Fizyka', 'Ćwiczenia', '100 S'],
    e: [1, 0, 1, 2, day, 480, 575, 1, 0, 1, 2, day + 7, 480, 575],
  };
  assert.deepEqual(I.catchUp(year2, 'WCY26KY1S1', together, 'Fizyka', 'Ćwiczenia', '2026-10-15').map((f) => [f.group, f.n]),
    [['WCY26KY3S1', 2]]);
  assert.equal(I.isoFromDayNumber(I.dayNumber('2027-03-28')), '2027-03-28');
});

test('month grid starts on Monday and pads the edges', () => {
  const oct = I.monthGrid(2026, 9);
  assert.equal(oct.length, 5);
  assert.deepEqual(oct[0], [null, null, null, '2026-10-01', '2026-10-02', '2026-10-03', '2026-10-04']);
  assert.deepEqual(oct[4], ['2026-10-26', '2026-10-27', '2026-10-28', '2026-10-29', '2026-10-30', '2026-10-31', null]);
  assert.equal(I.monthGrid(2027, 1).length, 4); // February 2027 starts on a Monday
});

test('ordinals number each class within its subject and type over the term', () => {
  const plan = planOf([
    L('2026-10-05', '08:00', '09:35', 'Matematyka dyskretna', 'Wykład'),
    L('2026-10-05', '09:50', '11:25', 'Matematyka dyskretna', 'Ćwiczenia'),
    L('2026-10-12', '08:00', '09:35', 'Matematyka dyskretna', 'Wykład'),
    L('2026-10-19', '08:00', '09:35', 'matematyka  dyskretna', 'Wykład'),
    L('2026-10-19', '11:40', '13:15', 'Fizyka', ''),
  ]);
  const o = I.ordinals(plan);
  const of = (l) => o[I.lessonKey(l)];
  const all = plan.weeks.flatMap((w) => Object.values(w.days).flat());
  assert.deepEqual(all.map((l) => [l.date, l.type_full, of(l).n, of(l).of]), [
    ['2026-10-05', 'Wykład', 1, 3], ['2026-10-05', 'Ćwiczenia', 1, 1],
    ['2026-10-12', 'Wykład', 2, 3],
    ['2026-10-19', 'Wykład', 3, 3], ['2026-10-19', '', 1, 1],
  ]);
  const real = I.ordinals(REAL);
  const firstWeek = I.lessons(REAL).slice(0, 5).map((l) => real[I.lessonKey(l)]);
  firstWeek.forEach((x) => assert.ok(x.n >= 1 && x.n <= x.of));
});

/* ---------- free rooms ---------- */
const roomData = (rooms, bookings) => {
  const day = (iso) => I.dayNumber(iso) - I.dayNumber('2000-01-01');
  const b = [];
  bookings.forEach(([room, iso, s, e]) => b.push(room, day(iso), s, e));
  return { epoch: '2000-01-01', rooms, b };
};

test('firstWindow finds the first gap that fits, or runs to the end of the day', () => {
  assert.deepEqual(I.firstWindow([], 600, 60), { start: 600, until: null });
  assert.deepEqual(I.firstWindow([[540, 600]], 570, 60), { start: 600, until: null });
  assert.deepEqual(I.firstWindow([[660, 720]], 600, 60), { start: 600, until: 660 });
  // gaps of 20 and 30 minutes are too short for an hour, so the window opens after the last class
  assert.deepEqual(I.firstWindow([[630, 700], [720, 800], [830, 900]], 600, 60), { start: 900, until: null });
  assert.equal(I.firstWindow([], 24 * 60 - 30, 60), null);
});

test('freeRooms lists rooms free for the whole span, and later ones only on request', () => {
  const d = roomData(['1 S', '2 S', '3 5', '4 5'], [
    [0, '2026-10-15', 480, 570], [0, '2026-10-15', 600, 690],   // 1 S: 8:00-9:30, 10:00-11:30
    [1, '2026-10-15', 960, 1050],                              // 2 S: 16:00-17:30
    [2, '2026-09-01', 480, 570],                               // 3 5: nothing near the date -> unknown
    [3, '2026-10-14', 480, 570]]);                             // 4 5: a class the day before -> known, free today
  const now = I.freeRooms(d, '2026-10-15', 570, 60, false);
  assert.deepEqual(now.list.map((r) => r.room), ['4 5', '2 S']);  // longest stretch first (4 5 is free all day)
  assert.equal(now.skipped, 1);
  const later = I.freeRooms(d, '2026-10-15', 570, 60, true);
  assert.deepEqual(later.list.map((r) => [r.room, r.free, r.start]), [['4 5', true, 570], ['2 S', true, 570], ['1 S', false, 690]]);
  assert.equal(later.list[2].until, null);
  assert.deepEqual(later.list[2].busy, [[480, 570], [600, 690]]);
});

test('freeRooms is null for a date outside the data and building() reads the room text', () => {
  const d = roomData(['1 S'], [[0, '2026-10-15', 480, 570]]);
  assert.equal(I.freeRooms(d, '2026-12-24', 480, 60, false), null);
  assert.deepEqual(I.dataRange(d), { from: '2026-10-15', to: '2026-10-15' });
  assert.equal(I.building('308 S'), 'S');
  assert.equal(I.building('0.24/135'), '135');
  assert.equal(I.building('T3.1W'), '');
});

/* ---------- plan map ---------- */
const profileData = () => {
  const features = [
    { key: 'hours', high: 'dużo zajęć', low: 'mało zajęć', w: 1 },
    { key: 'gaps', high: 'dużo okienek', low: 'prawie bez okienek', w: 0.8 },
    { key: 'span', high: 'długie dni', low: 'krótkie dni', w: 1 },
    { key: 'early', high: 'wczesne starty', low: 'późne starty', w: 0.8 },
    { key: 'fixed', high: 'stałe sale', low: 'wiele sal', w: 0 },
  ];
  // [group, faculty, x, y, percentile, archetype, load, z...] with z in hundredths
  const row = (g, x, y, pct, load, z) => [g, 'WCY', x, y, pct, 0, load, ...z];
  return { features, archetypes: [{ name: 'a', n: 4 }], groups: [
    row('A', 500, 500, 50, 0, [0, 0, 0, 0, 0]),
    row('B', 520, 510, 70, 40, [60, 90, 40, 30, 0]),
    row('C', 480, 480, 20, -40, [-60, -90, -80, -90, 0]),
    row('D', 900, 900, 95, 90, [200, 150, 190, 120, 160]),
  ] };
};

test('traits lists what sets a plan apart, strongest first, and tells heavier from lighter', () => {
  const d = profileData();
  const t = I.traits(d, d.groups[3], 3);
  assert.deepEqual(t.map((x) => x.key), ['hours', 'span', 'fixed']);
  assert.equal(t[0].strength, 'duża różnica');
  assert.equal(t[0].tone, 'heavier');
  assert.equal(t[2].tone, 'plain');  // a feature that does not weigh in the load
  const light = I.traits(d, d.groups[2], 5);
  assert.equal(light.find((x) => x.key === 'early').label, 'późne starty');
  assert.equal(light.find((x) => x.key === 'early').tone, 'lighter');
  assert.deepEqual(I.traits(d, d.groups[0], 5), []);  // an average plan has nothing to say
});

test('similarPlans orders by distance and the modes keep only the plans that are lighter in that respect', () => {
  const d = profileData();
  const a = d.groups[0];
  assert.deepEqual(I.similarPlans(d, a, 'near', 5).map((x) => x.code), ['B', 'C', 'D']);
  assert.deepEqual(I.similarPlans(d, a, 'lighter', 5).map((x) => x.code), ['C']);
  assert.deepEqual(I.similarPlans(d, a, 'gaps', 5).map((x) => x.code), ['C']);
  assert.deepEqual(I.similarPlans(d, a, 'short', 5).map((x) => x.code), ['C']);
  assert.deepEqual(I.similarPlans(d, a, 'late', 5).map((x) => x.code), ['C']);
  assert.deepEqual(I.similarPlans(d, d.groups[3], 'lighter', 2).map((x) => x.code), ['B', 'A']);
});

test('map helpers: row lookup, nearest dot under a tap, and the box around a plan', () => {
  const d = profileData();
  assert.equal(I.profileRow(d, 'C')[0], 'C');
  assert.equal(I.profileRow(d, 'Z'), null);
  assert.equal(I.hitDot(d, 905, 897, 20)[0], 'D');
  assert.equal(I.hitDot(d, 700, 700, 20), null);
  const box = I.neighbourhood(d, d.groups[0], 2);
  assert.equal(box.x, 500);
  assert.ok(box.r >= 40);
});

test('a plan feature reads back as a real value, and is printed with its unit', () => {
  const d = profileData();
  d.features.forEach((f) => { f.mean = 10; f.std = 2; f.unit = 'n'; });
  d.features[0].unit = 'h';
  d.features[1].unit = 'min';
  d.features[3].unit = 'pct';
  const row = d.groups[3];  // z = 2.00, 1.50, 1.90, 1.20, 1.60
  assert.equal(I.featureValue(d, row, 0), 14);
  assert.equal(I.fmtFeature(d.features[0], 14), '14 h');
  assert.equal(I.fmtFeature(d.features[0], 13.45), '13,5 h');
  assert.equal(I.fmtFeature(d.features[1], 200), '3 h 20 min');
  assert.equal(I.fmtFeature(d.features[3], 0.456), '46%');
  assert.equal(I.fmtFeature(d.features[4], 3.25), '3,3');
  assert.equal(I.fmtFeature(d.features[4], 12.4), '12');
  assert.equal(I.fmtTypical([17.5, 4.1, 130, 390]), '17,5 h zajęć · 4,1 dni · okienka 2 h 10 min · dzień 6 h 30 min');
});

test('differences names how another plan is unlike this one, and likeness grades the distance', () => {
  const d = profileData();
  const a = d.groups[0], c = d.groups[2], dd = d.groups[3];
  assert.deepEqual(I.differences(d, a, c, 2), ['późne starty', 'prawie bez okienek']);  // C: early -0.9 and gaps -0.9 tie, so by feature key
  assert.deepEqual(I.differences(d, a, a, 2), []);
  assert.equal(I.differences(d, a, dd, 1).length, 1);
  assert.equal(I.likeness(0.5), 'bardzo podobny');
  assert.equal(I.likeness(1.5), 'podobny');
  assert.equal(I.likeness(3), 'trochę inny');
});
