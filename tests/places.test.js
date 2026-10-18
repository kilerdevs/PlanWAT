// Tests for src/places.js (stops, dormitories, shops, parkings, parcel lockers, places to eat around the campus).
// Run: node --test tests/places.test.js
const test = require('node:test');
const assert = require('node:assert/strict');
const C = require('../src/campus.js');
const P = require('../src/places.js');

const WANTED = ['tram', 'bus', 'dorm', 'domki', 'canteen', 'bufet', 'rest', 'bar', 'shop', 'parcel', 'park'];

test('every wanted kind of place has a category with a label, a colour and a zoom', () => {
  assert.deepEqual(P.CATEGORIES.map((c) => c.id), WANTED);
  for (const c of P.CATEGORIES) {
    assert.match(c.color, /^#[0-9a-f]{6}$/i, c.id);
    assert.ok(c.label.length > 2 && c.zoom >= 14 && c.zoom <= 17, c.id);
  }
});

test('places sit inside the map bounds and every category has some', () => {
  const [[w, s], [e, n]] = C.BOUNDS;
  for (const p of P.PLACES) {
    assert.ok(p.lng > w && p.lng < e && p.lat > s && p.lat < n, `${p.cat.id} ${p.name}`);
    assert.ok(p.name.length > 0 && p.name.length <= 48, p.name);
  }
  for (const id of WANTED) assert.ok(P.count(id) >= 1, id);
  assert.ok(P.count('park') > 20 && P.count('shop') > 10 && P.count('dorm') >= 5);
});

test('the Domki place from the maps link is there', () => {
  const d = P.PLACES.find((p) => p.cat.id === 'domki');
  assert.equal(d.name, 'Domki Radiowa');
  assert.ok(Math.abs(d.lat - 52.2617) < 0.001 && Math.abs(d.lng - 20.8939) < 0.001);
});

test('search finds a place by name or by category, ignoring case and Polish letters', () => {
  assert.ok(P.search('akademik').length >= 5);
  assert.ok(P.search('STOLOWKA').every((p) => p.cat.id === 'canteen'));
  assert.equal(P.search('domki')[0].name, 'Domki Radiowa');
  assert.ok(P.search('paczkomat').length >= 1);
  assert.deepEqual(P.search('a'), []);
  assert.deepEqual(P.search('zzzzzz'), []);
  assert.ok(P.search('akademik', 3).length <= 3);
});

test('walking directions go to the place', () => {
  const p = P.PLACES[0];
  assert.equal(P.directionsUrl(p), `https://www.google.com/maps/dir/?api=1&destination=${p.lat},${p.lng}&travelmode=walking`);
});

/* ---- opening hours and accessibility: synthetic tags, so a data refresh cannot weaken the parser ---- */

function at(year, month, day, hour, minute) {
  return new Date(year, month - 1, day, hour, minute || 0, 0, 0);
}
function place(hours, wheelchair) {
  return { hours: hours || null, wheelchair: wheelchair || null };
}
const OPEN = (label) => ({ state: 'open', label });
const CLOSED = (label) => ({ state: 'closed', label: label || 'Zamknięte' });
const UNKNOWN = { state: 'unknown', label: 'Godziny nieznane' };

test('24/7 is open at any time and says so', () => {
  const p = place('24/7');
  assert.deepEqual(P.openState(p, at(2026, 10, 18, 3, 0)), OPEN('Otwarte 24/7'));
  assert.equal(P.isOpenNow(p, at(2026, 10, 18, 3, 0)), true);
});

test('a Monday–Friday range opens and closes on the minute and stays closed at the weekend', () => {
  const p = place('Mo-Fr 07:00-18:00');
  assert.deepEqual(P.openState(p, at(2026, 10, 19, 6, 59)), CLOSED());
  assert.deepEqual(P.openState(p, at(2026, 10, 19, 7, 0)), OPEN('Otwarte do 18:00'));
  assert.deepEqual(P.openState(p, at(2026, 10, 19, 17, 59)), OPEN('Otwarte do 18:00'));
  assert.deepEqual(P.openState(p, at(2026, 10, 19, 18, 0)), CLOSED());
  assert.deepEqual(P.openState(p, at(2026, 10, 24, 10, 0)), CLOSED());  // Saturday
  assert.equal(P.isOpenNow(p, at(2026, 10, 19, 12, 0)), true);
  assert.equal(P.isOpenNow(p, at(2026, 10, 19, 22, 0)), false);
});

test('weekend rules, day lists and later rules overriding earlier ones', () => {
  const weekend = place('Sa-Su 10:00-14:00');
  assert.deepEqual(P.openState(weekend, at(2026, 10, 25, 10, 0)), OPEN('Otwarte do 14:00'));  // Sunday
  assert.deepEqual(P.openState(weekend, at(2026, 10, 19, 10, 0)), CLOSED());  // Monday

  const days = place('Mo,We,Fr 08:00-10:00');
  assert.deepEqual(P.openState(days, at(2026, 10, 21, 9, 0)), OPEN('Otwarte do 10:00'));
  assert.deepEqual(P.openState(days, at(2026, 10, 20, 9, 0)), CLOSED());

  const override = place('Mo-Su 08:00-12:00; Mo off');
  assert.deepEqual(P.openState(override, at(2026, 10, 19, 9, 0)), CLOSED());
  assert.deepEqual(P.openState(override, at(2026, 10, 20, 9, 0)), OPEN('Otwarte do 12:00'));
});

test('a day range may wrap around the week', () => {
  const p = place('Su-Th 10:00-23:00; Fr-Sa 10:00-24:00');
  assert.deepEqual(P.openState(p, at(2026, 10, 18, 12, 0)), OPEN('Otwarte do 23:00'));  // Sunday
  assert.deepEqual(P.openState(p, at(2026, 10, 19, 12, 0)), OPEN('Otwarte do 23:00'));  // Monday
  assert.deepEqual(P.openState(p, at(2026, 10, 23, 23, 30)), OPEN('Otwarte do 24:00'));  // Friday
  assert.deepEqual(P.openState(p, at(2026, 10, 24, 23, 30)), OPEN('Otwarte do 24:00'));  // Saturday
  assert.deepEqual(P.openState(p, at(2026, 10, 25, 23, 30)), CLOSED());  // next Sunday
});

test('off closes the named days and a bare off closes every day', () => {
  const p = place('Mo-Fr 07:00-18:00; Sa-Su off');
  assert.deepEqual(P.openState(p, at(2026, 10, 24, 10, 0)), CLOSED());
  assert.deepEqual(P.openState(p, at(2026, 10, 19, 10, 0)), OPEN('Otwarte do 18:00'));
  assert.deepEqual(P.openState(place('off'), at(2026, 10, 19, 10, 0)), CLOSED());
});

test('several opening ranges in one day, with the midday gap closed', () => {
  const p = place('Mo-Fr 07:00-12:00,13:00-18:00');
  assert.deepEqual(P.openState(p, at(2026, 10, 19, 11, 0)), OPEN('Otwarte do 12:00'));
  assert.deepEqual(P.openState(p, at(2026, 10, 19, 12, 30)), CLOSED());
  assert.deepEqual(P.openState(p, at(2026, 10, 19, 13, 0)), OPEN('Otwarte do 18:00'));
});

test('syntax outside the small subset is unknown, never guessed', () => {
  for (const hours of [
    'sunrise-sunset',
    'Mo-Fr 07:00-18:00 "na zamówienie"',
    'Mo-Fr 07:00-18:00; PH 10:00-12:00',
    'Mo-Fr',
    'week 1-5 08:00-16:00'
  ]) {
    assert.deepEqual(P.openState(place(hours), at(2026, 10, 19, 10, 0)), UNKNOWN, hours);
  }
  assert.deepEqual(P.openState(place(null), at(2026, 10, 19, 10, 0)), UNKNOWN);
});

test('an overnight range stays open after midnight and closes at its end', () => {
  const p = place('Fr 22:00-02:00');
  assert.deepEqual(P.openState(p, at(2026, 10, 23, 21, 59)), CLOSED());
  assert.deepEqual(P.openState(p, at(2026, 10, 23, 23, 0)), OPEN('Otwarte do 02:00'));
  assert.deepEqual(P.openState(p, at(2026, 10, 24, 1, 0)), OPEN('Otwarte do 02:00'));  // Saturday, still Friday's rule
  assert.deepEqual(P.openState(p, at(2026, 10, 24, 2, 0)), CLOSED());
  assert.deepEqual(P.openState(p, at(2026, 10, 24, 3, 0)), CLOSED());

  const daily = place('22:00-02:00');
  assert.deepEqual(P.openState(daily, at(2026, 10, 24, 1, 0)), OPEN('Otwarte do 02:00'));
  assert.deepEqual(P.openState(daily, at(2026, 10, 24, 3, 0)), CLOSED());
});

test("a rule for today overrides the wrapped part of yesterday's rule", () => {
  const p = place('Sa 16:00-03:00; Su 16:00-23:00');
  assert.deepEqual(P.openState(p, at(2026, 10, 24, 17, 0)), OPEN('Otwarte do 03:00'));  // Saturday
  assert.deepEqual(P.openState(p, at(2026, 10, 25, 1, 0)), CLOSED());  // Sunday owns the whole day
  const q = place('Mo-Fr 22:00-02:00; Sa 08:00-14:00');
  assert.deepEqual(P.openState(q, at(2026, 10, 24, 1, 0)), CLOSED());  // Saturday has its own rule
  assert.deepEqual(P.openState(q, at(2026, 10, 24, 9, 0)), OPEN('Otwarte do 14:00'));
});

test('PH off closes on Polish public holidays, including Easter Monday', () => {
  const p = place('Mo-Su 08:00-20:00; PH off');
  assert.deepEqual(P.openState(p, at(2026, 10, 19, 10, 0)), OPEN('Otwarte do 20:00'));
  assert.deepEqual(P.openState(p, at(2026, 11, 11, 10, 0)), CLOSED('Zamknięte · święto'));
  assert.deepEqual(P.openState(p, at(2026, 4, 5, 10, 0)), CLOSED('Zamknięte · święto'));   // Easter Sunday
  assert.deepEqual(P.openState(p, at(2026, 4, 6, 10, 0)), CLOSED('Zamknięte · święto'));   // Easter Monday
  assert.deepEqual(P.openState(place('24/7; PH off'), at(2026, 11, 11, 3, 0)), CLOSED('Zamknięte · święto'));
});

test('wheelchair labels use the OSM values and nothing else', () => {
  assert.equal(P.wheelchairLabel(place(null, 'yes')), 'Dostępne');
  assert.equal(P.wheelchairLabel(place(null, 'limited')), 'Częściowo dostępne');
  assert.equal(P.wheelchairLabel(place(null, 'no')), 'Niedostępne');
  assert.equal(P.wheelchairLabel(place(null, null)), null);
  assert.equal(P.wheelchairLabel(place(null, 'designated')), null);  // not one of the labelled values
  assert.equal(P.wheelchairLabel({}), null);
});

test('every generated place carries nullable hours and a known wheelchair value', () => {
  const allowed = new Set([null, 'yes', 'limited', 'no']);
  for (const p of P.PLACES) {
    assert.ok('hours' in p, p.name);
    assert.ok(p.hours === null || (typeof p.hours === 'string' && p.hours.length > 0), p.name);
    assert.ok(allowed.has(p.wheelchair), `${p.name}: ${p.wheelchair}`);
    assert.ok(['open', 'closed', 'unknown'].includes(P.openState(p, at(2026, 10, 19, 12, 0)).state), p.name);
  }
});
