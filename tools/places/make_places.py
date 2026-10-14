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
# places OpenStreetMap does not have (or names badly): [category, lng, lat, name]
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
            out.append([cat, round(at[0], 5), round(at[1], 5), name[:48]])
    # posts, bays and doubled entries of the same name next to each other become one place
    merged = []
    reach = {'bus': 140, 'tram': 140, 'park': 45, 'parcel': 45, 'shop': 8}
    for r in sorted(out, key=lambda r: (r[0], r[3])):
        for q in merged:
            if q[0] == r[0] and q[3] == r[3] and r[0] in reach and metres(q[1], q[2], r[1], r[2]) < reach[r[0]]:
                break
        else:
            merged.append(r)
    return merged + [list(x) for x in EXTRA]


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

  /* [category, longitude, latitude, name] */
  var ROWS = [
{lines}
  ];

  var byId = {{}};
  CATEGORIES.forEach(function (c) {{ byId[c.id] = c; }});
  var PLACES = ROWS.map(function (r, i) {{
    return {{ id: i, cat: byId[r[0]], lng: r[1], lat: r[2], name: r[3] || byId[r[0]].label }};
  }});

  function fold(s) {{
    return String(s).toLowerCase().normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').replace(/ł/g, 'l');
  }}

  /* places whose name or category matches the query (a prefix of a word in either) */
  function search(query, max) {{
    var q = fold(query).trim();
    if (q.length < 2) return [];
    var hits = [];
    PLACES.forEach(function (p) {{
      var hay = fold(p.name) + ' ' + fold(p.cat.label);
      if (hay.indexOf(q) >= 0) hits.push(p);
    }});
    return hits.slice(0, max || 8);
  }}

  function count(id) {{ return PLACES.filter(function (p) {{ return p.cat.id === id; }}).length; }}

  function directionsUrl(p) {{
    return 'https://www.google.com/maps/dir/?api=1&destination=' + p.lat + ',' + p.lng + '&travelmode=walking';
  }}

  var Places = {{ CATEGORIES: CATEGORIES, PLACES: PLACES, search: search, count: count, directionsUrl: directionsUrl }};
  if (typeof module === 'object' && module.exports) module.exports = Places;
  else root.Places = Places;
}})(this);
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
