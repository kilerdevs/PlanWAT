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
