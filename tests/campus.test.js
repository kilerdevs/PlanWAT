// Tests for src/campus.js (campus buildings, room → building, search, the day's stops).
// Run: node --test tests/campus.test.js
process.env.TZ = 'Europe/Warsaw';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const PlanICS = require('../src/ics.js');
const C = require('../src/campus.js');

const ROOT = path.join(__dirname, '..');
const REAL = PlanICS.toPlan(PlanICS.parse(fs.readFileSync(path.join(ROOT, 'timetables', '2026-27-zima', 'WCY26KY3S1.ics'), 'utf8')));

test('rooms point at their building: "<room> <building>", "<room>/ <building>", S, K and Bibl.', () => {
  const cases = {
    '314 S': '100', 'aula/ 135': '135', 'aula/135': '135', '0.19/ 135': '135', '106 65': '65',
    '106 65 120 65': '65', '1.9/ 16;1.10/ 16': '16', '241 K': 'K', '103 K WYK-1': 'K',
    '7a-b Bibl.': 'BIBL', '23 23A': '23A', '1 55A': '55', '19 36': '36'
  };
  for (const [room, code] of Object.entries(cases)) assert.equal(C.roomBuilding(room), code, room);
});

test('rooms without a known building resolve to null', () => {
  for (const room of ['1002 HILTON', '108 Kpr', '11/', '', '-', 'Teams', 'POLIGON', '1 999', null, undefined]) {
    assert.equal(C.roomBuilding(room), null, String(room));
  }
});

test('buildings have unique codes, sit inside the map bounds and carry valid colours', () => {
  const [[w, s], [e, n]] = C.BOUNDS;
  const codes = C.BUILDINGS.map((b) => b.code).filter(Boolean);
  assert.equal(new Set(codes).size, codes.length);
  for (const b of C.BUILDINGS) {
    assert.ok(b.lng > w && b.lng < e && b.lat > s && b.lat < n, b.name);
    assert.match(b.faculty.color, /^#[0-9a-f]{6}$/);
    assert.ok(b.name && b.desc, b.name);
  }
  for (const f of C.FACULTIES) assert.match(f.color, /^#[0-9a-f]{6}$/);
  assert.equal(C.findBuilding('100').name, 'Budynek główny WAT (Sztab 100)');
  assert.equal(C.findBuilding('65').faculty.code, 'WCY');
  assert.equal(C.findBuilding('63a').code, '63A');
  assert.equal(C.findBuilding('nope'), null);
});

test('search ranks an exact building number first and ignores case and diacritics', () => {
  assert.equal(C.search('65')[0].name, 'Budynek 65');
  assert.equal(C.search('BIBLIOTEKA')[0].code, 'BIBL');
  assert.ok(C.search('ladowej').some((b) => b.code === '53'));
  assert.ok(C.search('stolowka').length >= 3);
  assert.deepEqual(C.search('   '), []);
  assert.ok(C.search('budynek').length <= 15);
});

test('dayStops lists one day in time order with buildings resolved', () => {
  const stops = C.dayStops(REAL, '2026-10-15');
  assert.ok(stops.length > 0);
  for (let i = 1; i < stops.length; i++) assert.ok(stops[i - 1].start <= stops[i].start);
  for (const s of stops) {
    assert.ok(s.subject && s.start && s.end);
    if (s.building) assert.equal(s.building.code, C.roomBuilding(s.room));
  }
  assert.deepEqual(C.dayStops(REAL, '2026-10-18'), []);
});

test('most rooms in the repository timetables resolve to a building', () => {
  const rooms = new Map();
  const dir = path.join(ROOT, 'timetables');
  for (const term of fs.readdirSync(dir)) {
    for (const f of fs.readdirSync(path.join(dir, term))) {
      if (!f.endsWith('.ics')) continue;
      for (const m of fs.readFileSync(path.join(dir, term, f), 'utf8').matchAll(/^LOCATION:(.*)$/gm)) {
        const room = m[1].trim().replace(/\\;/g, ';').replace(/\\,/g, ',');
        rooms.set(room, (rooms.get(room) || 0) + 1);
      }
    }
  }
  let all = 0, hit = 0;
  for (const [room, n] of rooms) { all += n; if (C.roomBuilding(room)) hit += n; }
  assert.ok(all > 0);
  assert.ok(hit / all > 0.85, `only ${(100 * hit / all).toFixed(1)}% of class rooms resolve`);
});

test('helpers: walking directions and readable marker ink', () => {
  const b = C.findBuilding('65');
  assert.equal(C.directionsUrl(b), `https://www.google.com/maps/dir/?api=1&destination=${b.lat},${b.lng}&travelmode=walking`);
  assert.equal(C.inkOn('#ffffff'), '#111');
  assert.equal(C.inkOn('#000000'), '#fff');
});

test('walking time between the buildings of consecutive classes', () => {
  const main = C.findBuilding('100'), wcy = C.findBuilding('65');
  const m = C.walkMinutes(main, wcy);
  assert.ok(m >= 3 && m <= 10, `100 -> 65 takes ${m} min`);
  assert.equal(C.walkMinutes(wcy, main), m);
  assert.equal(C.walkMinutes(main, main), 1);
  const t = C.transfer('307 S', '201 65');
  assert.equal(t.from.code, '100');
  assert.equal(t.to.code, '65');
  assert.equal(t.minutes, m);
  assert.equal(C.transfer('314 S', '1 100'), null);  // the same building
  assert.equal(C.transfer('314 S', '1002 HILTON'), null);  // unknown building
  assert.equal(C.transfer('', '201 65'), null);
});
