#!/usr/bin/env python3
"""Rebuild src/places.js: shops, parkings, dormitories, stops, parcel lockers and places to eat around the campus.

The rows come from OpenStreetMap (© OpenStreetMap contributors, ODbL 1.0) through the public Overpass API: a handful of small
queries over the campus box, kept to what lies near the campus buildings in src/campus.js. Run it by hand when the places
should be refreshed; the site itself never calls Overpass.

    python tools/places/make_places.py                  # fetch and write src/places.js
    python tools/places/make_places.py --osm osm.json   # reuse a saved fetch (written with --save)

A place that is not in OpenStreetMap can be added to EXTRA below.
"""
import argparse
import collections
import json
import math
import re
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOX = '(52.232,20.855,52.272,20.95)'
UA = 'PlanWAT-places (+https://github.com/kilerdevs/PlanWAT)'
HOSTS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter']

# one small query per kind: the public servers drop big ones
QUERIES = {
    'shop': 'nwr["shop"]' + BOX + ';',
    'parking': 'nwr["amenity"="parking"]' + BOX + ';',
    'food': 'nwr["amenity"~"^(restaurant|fast_food|cafe|bar|pub|canteen|food_court|ice_cream)$"]' + BOX + ';',
    'parcel': 'nwr["amenity"="parcel_locker"]' + BOX + ';nwr["brand"~"Paczkomat|InPost|Orlen Paczka"]' + BOX + ';',
    'dorm': 'nwr["building"="dormitory"]' + BOX + ';nwr["amenity"="student_accommodation"]' + BOX + ';',
    'bus': 'node["highway"="bus_stop"]' + BOX + ';',
    'tram': 'node["railway"="tram_stop"]' + BOX + ';',
}
# metres from the nearest campus building that still counts as "around the campus"
REACH = {'shop': 450, 'parking': 400, 'food': 500, 'parcel': 600, 'dorm': 600, 'bus': 650, 'tram': 800}
# places OpenStreetMap does not have (or names badly): [category, lng, lat, name, opening_hours, wheelchair]
EXTRA = [
    ['domki', 20.89388, 52.26173, 'Domki Radiowa'],  # https://maps.app.goo.gl/RtHaKcXCXKKYaVmq5
]
CATEGORIES = [  # id, label, colour, first zoom it shows at
    ('tram', 'Tramwaje', '#ff453a', 14.5),
    ('bus', 'Autobusy', '#32ade6', 15),
    ('dorm', 'Akademiki', '#bf5af2', 14.5),
    ('domki', 'Domki', '#2dd4bf', 14.5),
    ('canteen', 'Stołówki', '#ff6b81', 15),
    ('bufet', 'Bufety', '#e0a458', 15),
    ('rest', 'Restauracje i kawiarnie', '#ff7a45', 15.5),
    ('bar', 'Bary', '#7d6bff', 15.5),
    ('shop', 'Sklepy', '#ff9f0a', 15.5),
    ('parcel', 'Paczkomaty', '#ffd60a', 15.5),
    ('park', 'Parkingi', '#5e86e8', 16),
]


def metres(lng1, lat1, lng2, lat2):
    return math.hypot((lng1 - lng2) * 111320 * math.cos(math.radians(52.25)), (lat1 - lat2) * 110540)


def fetch():
    raw = {}
    for kind, body in QUERIES.items():
        query = '[out:json][timeout:40];(' + body + ');out center tags;'
        for attempt in range(6):
            try:
                req = urllib.request.Request(HOSTS[attempt % len(HOSTS)], data=urllib.parse.urlencode({'data': query}).encode(),
                                             headers={'User-Agent': UA})
                raw[kind] = json.loads(urllib.request.urlopen(req, timeout=60).read().decode('utf-8'))['elements']
                print(f'{kind}: {len(raw[kind])}')
                break
            except Exception as exc:  # the public servers are often busy: wait and try the next one
                print(f'{kind}: retry {attempt} ({str(exc)[:50]})')
                time.sleep(8)
        else:
            raise SystemExit(f'could not fetch {kind}')
        time.sleep(4)
    return raw


def buildings():
    out = subprocess.run(['node', '-e', "const C=require('./src/campus.js');console.log(JSON.stringify(C.BUILDINGS.map(b=>[b.lng,b.lat])))"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def classify(kind, tags):
    low = (tags.get('name') or '').lower()
    if kind == 'shop':
        return 'shop'
    if kind == 'parking':
        return None if tags.get('parking') == 'underground' or tags.get('access') in ('private', 'no') else 'park'
    if kind == 'food':
        if tags.get('amenity') == 'canteen' or 'stołów' in low or 'stolow' in low:
            return 'canteen'
        if 'bufet' in low or 'buffet' in low:
            return 'bufet'
        return 'bar' if tags.get('amenity') in ('bar', 'pub') else 'rest'
    return {'parcel': 'parcel', 'dorm': 'dorm', 'bus': 'bus', 'tram': 'tram'}[kind]


def rows(raw, near):
    out = []
    for kind, elements in raw.items():
        for e in elements:
            at = (e['lon'], e['lat']) if e['type'] == 'node' else ((e.get('center') or {}).get('lon'), (e.get('center') or {}).get('lat'))
            if at[0] is None or near(*at) > REACH[kind]:
                continue
            tags = e.get('tags', {})
            cat = classify(kind, tags)
            if not cat:
                continue
            name = (tags.get('name') or tags.get('brand') or tags.get('operator') or '').strip()
            if cat in ('bus', 'tram'):
                name = re.sub(r'\s+\d{1,2}$', '', name)  # "WAT 03" and "WAT 04" are the two sides of one stop
            hours = (tags.get('opening_hours') or '').strip() or None
            wheelchair = tags.get('wheelchair')
            if wheelchair not in ('yes', 'limited', 'no'):
                wheelchair = None  # keep only the values the site knows how to label
            row = [cat, round(at[0], 5), round(at[1], 5), name[:48]]
            if wheelchair:  # keep old four-field rows untouched when OSM has no tags
                row += [hours, wheelchair]
            elif hours:
                row.append(hours)
            out.append(row)
    # posts, bays and doubled entries of the same name next to each other become one place
    merged = []
    reach = {'bus': 140, 'tram': 140, 'park': 45, 'parcel': 45, 'shop': 8}
    for r in sorted(out, key=lambda r: (r[0], r[3])):
        for q in merged:
            if q[0] == r[0] and q[3] == r[3] and r[0] in reach and metres(q[1], q[2], r[1], r[2]) < reach[r[0]]:
                # the first entry wins the coordinates, but tags from its twin are just as valid
                if len(r) > 4 and not (len(q) > 4 and q[4]):
                    q += [None] * (5 - len(q))
                    q[4] = r[4]
                if len(r) > 5 and not (len(q) > 5 and q[5]):
                    q += [None] * (6 - len(q))
                    q[5] = r[5]
                break
        else:
            merged.append(r)
    return merged + [list(x) for x in EXTRA]


BODY = r'''  var byId = {};
  CATEGORIES.forEach(function (c) { byId[c.id] = c; });
  var PLACES = ROWS.map(function (r, i) {
    var wheel = r[5];
    if (wheel !== 'yes' && wheel !== 'limited' && wheel !== 'no') wheel = null;
    return {
      id: i, cat: byId[r[0]], lng: r[1], lat: r[2], name: r[3] || byId[r[0]].label,
      hours: typeof r[4] === 'string' && r[4] ? r[4] : null, wheelchair: wheel
    };
  });

  function fold(s) {
    return String(s).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/ł/g, 'l');
  }

  /* places whose name or category matches the query (a prefix of a word in either) */
  function search(query, max) {
    var q = fold(query).trim();
    if (q.length < 2) return [];
    var hits = [];
    PLACES.forEach(function (p) {
      var hay = fold(p.name) + ' ' + fold(p.cat.label);
      if (hay.indexOf(q) >= 0) hits.push(p);
    });
    return hits.slice(0, max || 8);
  }

  function count(id) { return PLACES.filter(function (p) { return p.cat.id === id; }).length; }

  function directionsUrl(p) {
    return 'https://www.google.com/maps/dir/?api=1&destination=' + p.lat + ',' + p.lng + '&travelmode=walking';
  }

  /* ---- opening hours: a deliberately small, conservative reading of OpenStreetMap's opening_hours ----
     Supported: 24/7, day sets (Mo, Mo-Fr, Mo,We,Fr, Sa-Su), several rules separated by ";",
     time ranges (07:00-18:00), several ranges per rule, "off" and "PH off". Overnight ranges such as
     22:00-02:00 are understood. Anything else (seasons, sunrise/sunset, "by appointment", month rules)
     is reported as unknown instead of guessed. */
  var DAY_INDEX = { mo: 0, tu: 1, we: 2, th: 3, fr: 4, sa: 5, su: 6 };
  var DAY_PREFIX = /^((?:[A-Za-z]{2})(?:\s*-\s*[A-Za-z]{2})?(?:\s*,\s*[A-Za-z]{2}(?:\s*-\s*[A-Za-z]{2})?)*)\s+(.+)$/;

  function pad2(n) { return (n < 10 ? '0' : '') + n; }
  function clock(mins) { return pad2(Math.floor(mins / 60)) + ':' + pad2(mins % 60); }

  function parseClock(text) {
    var m = /^(\d{1,2}):(\d{2})$/.exec(text);
    if (!m) return null;
    var h = parseInt(m[1], 10), min = parseInt(m[2], 10);
    if (min > 59 || h > 24 || (h === 24 && min !== 0)) return null;
    return h * 60 + min;
  }

  function parseDays(text) {
    var out = [];
    var parts = text.split(',');
    for (var i = 0; i < parts.length; i++) {
      var m = /^([A-Za-z]{2})(?:\s*-\s*([A-Za-z]{2}))?$/.exec(parts[i].replace(/^\s+|\s+$/g, ''));
      if (!m) return null;
      var a = DAY_INDEX[m[1].toLowerCase()], b = m[2] ? DAY_INDEX[m[2].toLowerCase()] : a;
      if (a == null || b == null) return null;
      /* OSM allows a range that wraps around the week, e.g. "Su-Th" (Sunday through Thursday) */
      for (var d = a; ; d = (d + 1) % 7) {
        if (out.indexOf(d) < 0) out.push(d);
        if (d === b) break;
      }
    }
    return out.length ? out : null;
  }

  function parseRanges(text) {
    var out = [];
    var parts = text.split(',');
    for (var i = 0; i < parts.length; i++) {
      var m = /^(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})$/.exec(parts[i].replace(/^\s+|\s+$/g, ''));
      if (!m) return null;
      var a = parseClock(m[1]), b = parseClock(m[2]);
      if (a == null || b == null || a === b || a >= 1440) return null;
      out.push([a, b]);
    }
    return out.length ? out : null;
  }

  function parseHours(raw) {
    var spec = String(raw == null ? '' : raw).replace(/^\s+|\s+$/g, '');
    if (!spec) return null;
    var rules = [], phOff = false, always = false;
    var parts = spec.split(';');
    for (var i = 0; i < parts.length; i++) {
      var rule = parts[i].replace(/^\s+|\s+$/g, '');
      if (!rule) continue;
      if (/^24\s*\/\s*7$/i.test(rule)) {
        if (rules.length) return null;
        always = true;
        continue;
      }
      if (/^PH\s+off$/i.test(rule)) { phOff = true; continue; }
      if (/^PH\b/i.test(rule)) return null;  // other public-holiday rules are outside the subset
      var m = DAY_PREFIX.exec(rule);
      var days, rest;
      if (m) {
        days = parseDays(m[1]);
        rest = m[2].replace(/^\s+|\s+$/g, '');
        if (!days) return null;
      } else {
        days = [0, 1, 2, 3, 4, 5, 6];
        rest = rule;
      }
      if (/^off$/i.test(rest)) {
        if (always) return null;
        rules.push({ days: days, off: true });
        continue;
      }
      var ranges = parseRanges(rest);
      if (!ranges || always) return null;
      rules.push({ days: days, off: false, ranges: ranges });
    }
    if (always) return { always: true, phOff: phOff, byDay: null };
    if (!rules.length) return null;  // "PH off" alone does not say when the place is open
    var byDay = [null, null, null, null, null, null, null];
    for (i = 0; i < rules.length; i++) {
      for (var j = 0; j < rules[i].days.length; j++) {
        byDay[rules[i].days[j]] = rules[i].off ? [] : rules[i].ranges;  // later rules override earlier ones
      }
    }
    return { always: false, phOff: phOff, byDay: byDay };
  }

  /* Polish public holidays, so "PH off" is not a guess: fixed dates plus Easter, Pentecost and Corpus Christi. */
  function easterSunday(year) {
    var a = year % 19, b = Math.floor(year / 100), c = year % 100;
    var d = Math.floor(b / 4), e = b % 4, f = Math.floor((b + 8) / 25);
    var g = Math.floor((b - f + 1) / 3), h = (19 * a + b - d - g + 15) % 30;
    var i = Math.floor(c / 4), k = c % 4, l = (32 + 2 * e + 2 * i - h - k) % 7;
    var m = Math.floor((a + 11 * h + 22 * l) / 451);
    var month = Math.floor((h + l - 7 * m + 114) / 31);
    var day = ((h + l - 7 * m + 114) % 31) + 1;
    return new Date(year, month - 1, day, 12);
  }

  function sameDate(a, month, day) {
    return a.getMonth() + 1 === month && a.getDate() === day;
  }

  function isPolishHoliday(date) {
    var fixed = [[1, 1], [1, 6], [5, 1], [5, 3], [8, 15], [11, 1], [11, 11], [12, 25], [12, 26]];
    var month = date.getMonth() + 1, day = date.getDate();
    for (var i = 0; i < fixed.length; i++) {
      if (fixed[i][0] === month && fixed[i][1] === day) return true;
    }
    var easter = easterSunday(date.getFullYear());
    var offsets = [0, 1, 49, 60];  // Easter Sunday, Easter Monday, Pentecost, Corpus Christi
    for (i = 0; i < offsets.length; i++) {
      var holiday = new Date(easter.getFullYear(), easter.getMonth(), easter.getDate() + offsets[i], 12);
      if (sameDate(holiday, month, day)) return true;
    }
    return false;
  }

  function unknownState() { return { state: 'unknown', label: 'Godziny nieznane' }; }
  function openLabel(end) {
    return { state: 'open', label: 'Otwarte do ' + clock(end) };
  }
  function sameRanges(a, b) {
    if (a.length !== b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (a[i][0] !== b[i][0] || a[i][1] !== b[i][1]) return false;
    }
    return true;
  }

  function openState(p, date) {
    var now = date instanceof Date ? date : new Date();
    if (isNaN(now.getTime())) return unknownState();
    if (!p || !p.hours) return unknownState();
    var schedule = parseHours(p.hours);
    if (!schedule) return unknownState();
    if (schedule.phOff && isPolishHoliday(now)) return { state: 'closed', label: 'Zamknięte · święto' };
    if (schedule.always) return { state: 'open', label: 'Otwarte 24/7' };

    var day = (now.getDay() + 6) % 7;  // Monday = 0
    var mins = now.getHours() * 60 + now.getMinutes();
    var today = schedule.byDay[day] || [];
    var yesterday = schedule.byDay[(day + 6) % 7] || [];
    var i, r;

    /* an overnight rule that started yesterday is still open early today. A normal rule for today replaces
       earlier rules for the whole day (so "Sa 16:00-03:00; Su 16:00-23:00" is closed early on Sunday), but
       a schedule that repeats the same overnight range every day still covers the early hours. */
    var todaySame = today.length > 0 && yesterday.length > 0 && sameRanges(today, yesterday);
    if (schedule.byDay[day] === null || todaySame) {
      for (i = 0; i < yesterday.length; i++) {
        r = yesterday[i];
        if (r[1] < r[0] && mins < r[1]) return openLabel(r[1]);
      }
    }
    for (i = 0; i < today.length; i++) {
      r = today[i];
      if (r[1] > r[0]) {
        if (mins >= r[0] && mins < r[1]) return openLabel(r[1]);
      } else if (mins >= r[0]) {
        return openLabel(r[1]);
      }
    }
    return { state: 'closed', label: 'Zamknięte' };
  }

  function isOpenNow(p, now) { return openState(p, now).state === 'open'; }

  function wheelchairLabel(p) {
    var w = p && p.wheelchair;
    if (w === 'yes') return 'Dostępne';
    if (w === 'limited') return 'Częściowo dostępne';
    if (w === 'no') return 'Niedostępne';
    return null;
  }

  var Places = {
    CATEGORIES: CATEGORIES, PLACES: PLACES, search: search, count: count, directionsUrl: directionsUrl,
    parseHours: parseHours, openState: openState, isOpenNow: isOpenNow, wheelchairLabel: wheelchairLabel
  };
  if (typeof module === 'object' && module.exports) module.exports = Places;
  else root.Places = Places;
'''


def js(cats, data):
    order = {c[0]: i for i, c in enumerate(CATEGORIES)}
    data = sorted(data, key=lambda r: (order[r[0]], r[3], r[1]))
    lines = ',\n'.join('    ' + json.dumps(r, ensure_ascii=False, separators=(',', ':')) for r in data)
    cat_lines = ',\n'.join('    ' + json.dumps({'id': i, 'label': l, 'color': c, 'zoom': z}, ensure_ascii=False) for i, l, c, z in cats)
    return f'''/* Places around the campus: stops, dormitories, shops, parkings, parcel lockers and somewhere to eat.
   Generated by tools/places/make_places.py. Places: © OpenStreetMap contributors, ODbL 1.0 (see THIRD-PARTY-NOTICES.md).
   Pure (no DOM), so node:test covers it; inlined into the map page only. */
(function (root) {{
  'use strict';

  /* category → label, colour and the zoom it first shows at; the order is the legend's */
  var CATEGORIES = [
{cat_lines}
  ];

  /* [category, longitude, latitude, name] plus, only when OpenStreetMap has them, opening_hours and wheelchair */
  var ROWS = [
{lines}
  ];

''' + BODY + '''})(this);
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--osm', type=Path, help='reuse a fetch saved with --save instead of calling Overpass')
    ap.add_argument('--save', type=Path, help='write the raw fetch here')
    args = ap.parse_args()
    raw = json.loads(args.osm.read_text(encoding='utf-8')) if args.osm else fetch()
    if args.save:
        args.save.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
    bld = buildings()
    data = rows(raw, lambda lng, lat: min(metres(lng, lat, b[0], b[1]) for b in bld))
    (ROOT / 'src' / 'places.js').write_text(js(CATEGORIES, data), encoding='utf-8', newline='\n')
    print(collections.Counter(r[0] for r in data), len(data))


if __name__ == '__main__':
    main()
