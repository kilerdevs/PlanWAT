#!/usr/bin/env python3
"""Rebuild src/map/: everything the campus map (/mapa/) draws with, so the page needs no host but the site's own.

    lib/        MapLibre GL JS and its stylesheet, checked against the integrity hashes in src/mapa.html
    style.json  OpenFreeMap's "dark" style, its addresses pointed at the files below
    tiles/      the OpenMapTiles vector tiles of every view the map allows (tools/map/coverage.json)
    glyphs/     the label glyph ranges those tiles and src/places.js actually use
    sprites/    the style's icons
    LICENSE-openfreemap.md  the licences of the style, its icons and glyphs (the engine's is in lib/)

The tiles come from OpenFreeMap (© OpenMapTiles, data © OpenStreetMap contributors, ODbL 1.0) and are stored byte for
byte. .github/workflows/map.yml runs it monthly and publishes the result to the `map` branch, which pages.yml lays over
src/map/; run it by hand when the committed snapshot should change too. The site itself never calls OpenFreeMap or unpkg.

    python tools/map/vendor_map.py

tools/map/coverage.json lists the tiles. It comes from tools/map/coverage.js, which asks MapLibre itself which tiles
every reachable view covers; run that first whenever the map's bounds (src/campus.js) or zoom limits change.
"""
import base64
import hashlib
import json
import re
import shutil
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'src' / 'map'
COVERAGE = Path(__file__).resolve().parent / 'coverage.json'
UA = 'PlanWAT-map (+https://github.com/kilerdevs/PlanWAT)'
ENGINE = 'https://unpkg.com/maplibre-gl@{version}/{path}'
STYLE = 'https://tiles.openfreemap.org/styles/dark'
STYLE_LICENSE = 'https://raw.githubusercontent.com/hyperknot/openfreemap-styles/main/LICENSE.md'
# the tile attributes a label can be drawn from (the style's text-field expressions and src/mapa.html's own layers)
LABEL_KEYS = {'name', 'name:latin', 'name:nonlatin', 'name_en', 'ref'}


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as res:
                return res.read()
        except OSError:
            if attempt == 3:
                raise
            time.sleep(2 ** attempt)


# ---------------------------------------------------------------- vector tiles: just enough protobuf to read labels

def _varint(buf, i):
    shift = result = 0
    while True:
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if b < 0x80:
            return result, i
        shift += 7


def _fields(buf):
    i = 0
    while i < len(buf):
        key, i = _varint(buf, i)
        num, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _varint(buf, i)
        elif wire == 1:
            value, i = buf[i:i + 8], i + 8
        elif wire == 2:
            size, i = _varint(buf, i)
            value, i = buf[i:i + size], i + size
        elif wire == 5:
            value, i = buf[i:i + 4], i + 4
        else:
            raise ValueError(f'unsupported protobuf wire type {wire}')
        yield num, value


def tile_labels(data, wanted=LABEL_KEYS):
    """Every string a tile holds under one of the `wanted` attribute keys."""
    found = set()
    for num, layer in _fields(data):
        if num != 3:
            continue
        keys, values, features = [], [], []
        for lnum, value in _fields(layer):
            if lnum == 2:
                features.append(value)
            elif lnum == 3:
                keys.append(value.decode('utf-8'))
            elif lnum == 4:
                values.append(value)
        for feature in features:
            for fnum, tags in _fields(feature):
                if fnum != 2:
                    continue
                i, packed = 0, []
                while i < len(tags):
                    v, i = _varint(tags, i)
                    packed.append(v)
                for k, v in zip(packed[0::2], packed[1::2]):
                    if keys[k] in wanted:
                        found.update(s.decode('utf-8') for n, s in _fields(values[v]) if n == 1)
    return found


# ---------------------------------------------------------------- the pieces

def vendor_engine(page):
    """MapLibre's script and stylesheet, as pinned by the integrity attributes in src/mapa.html."""
    pinned = re.findall(r'(?:href|src)="lib/maplibre-gl-([\d.]+)\.(js|css)" integrity="sha384-([^"]+)"', page)
    if len(pinned) != 2:
        raise SystemExit('src/mapa.html must load lib/maplibre-gl-<version>.js and .css with an integrity hash')
    (OUT / 'lib').mkdir(parents=True)
    for version, ext, digest in pinned:
        data = fetch(ENGINE.format(version=version, path=f'dist/maplibre-gl.{ext}'))
        got = base64.b64encode(hashlib.sha384(data).digest()).decode()
        if got != digest:
            raise SystemExit(f'maplibre-gl {version} .{ext} does not match the hash pinned in src/mapa.html')
        (OUT / 'lib' / f'maplibre-gl-{version}.{ext}').write_bytes(data)
    (OUT / 'lib' / 'LICENSE.txt').write_bytes(fetch(ENGINE.format(version=pinned[0][0], path='LICENSE.txt')))
    return pinned[0][0]


def vendor_tiles(template, cover):
    labels = set()
    for n, tile in enumerate(cover, 1):
        z, x, y = tile.split('/')
        data = fetch(template.replace('{z}', z).replace('{x}', x).replace('{y}', y))
        path = OUT / 'tiles' / z / x / f'{y}.pbf'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        labels |= tile_labels(data)
        if n % 50 == 0:
            print(f'  {n}/{len(cover)} tiles')
        time.sleep(0.05)
    return labels


def bounds_of(cover):
    """The [west, south, east, north] box of a list of z/x/y tiles."""
    import math

    def lon(x, z):
        return x / 2 ** z * 360 - 180

    def lat(y, z):
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2 ** z))))

    boxes = [(lon(int(x), int(z)), lat(int(y) + 1, int(z)), lon(int(x) + 1, int(z)), lat(int(y), int(z)))
             for z, x, y in (t.split('/') for t in cover)]
    return [round(min(b[0] for b in boxes), 6), round(min(b[1] for b in boxes), 6),
            round(max(b[2] for b in boxes), 6), round(max(b[3] for b in boxes), 6)]


def main():
    page = (ROOT / 'src' / 'mapa.html').read_text(encoding='utf-8')
    cover = json.loads(COVERAGE.read_text(encoding='utf-8'))
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    version = vendor_engine(page)
    print(f'engine: maplibre-gl {version}')

    style = json.loads(fetch(STYLE))
    used = {layer.get('source') for layer in style['layers']}
    vector = [k for k, s in style['sources'].items() if s['type'] == 'vector']
    if len(vector) != 1:
        raise SystemExit(f'expected one vector source in the style, found {vector}')
    tilejson = json.loads(fetch(style['sources'][vector[0]]['url']))
    print(f'tiles: {tilejson["tiles"][0]}')
    labels = vendor_tiles(tilejson['tiles'][0], cover)

    # glyphs: every 256-codepoint range a label can need, for every font stack a layer names
    places = (ROOT / 'src' / 'places.js').read_text(encoding='utf-8') + (ROOT / 'src' / 'campus.js').read_text(encoding='utf-8')
    text = ''.join(labels) + places + ''.join(chr(c) for c in range(0x20, 0x17F))
    ranges = sorted({ord(ch) // 256 for ch in text if ord(ch) <= 0xFFFF})
    stacks = {json.dumps(layer['layout']['text-font']) for layer in style['layers'] if 'text-font' in layer.get('layout', {})}
    stacks |= {json.dumps(json.loads(f'[{m}]')) for m in re.findall(r"'text-font': \[([^\]]+)\]", page.replace("'", '"').replace('"text-font"', "'text-font'"))}
    for stack in sorted(stacks):
        fontstack = ','.join(json.loads(stack))
        for r in ranges:
            name = f'{r * 256}-{r * 256 + 255}'
            url = style['glyphs'].replace('{fontstack}', urllib.request.quote(fontstack)).replace('{range}', name)
            path = OUT / 'glyphs' / fontstack / f'{name}.pbf'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(fetch(url))
    print(f'glyphs: {len(stacks)} font stack(s) x {len(ranges)} ranges')

    (OUT / 'LICENSE-openfreemap.md').write_bytes(fetch(STYLE_LICENSE))

    sprite = style['sprite']
    (OUT / 'sprites').mkdir()
    name = sprite.rsplit('/', 1)[1]
    for suffix in ('.json', '.png', '@2x.json', '@2x.png'):
        (OUT / 'sprites' / f'{name}{suffix}').write_bytes(fetch(sprite + suffix))

    # sources no layer draws from (the low-zoom shaded relief) are dropped: MapLibre would never request them
    style['sources'] = {vector[0]: {
        'type': 'vector',
        'tiles': ['tiles/{z}/{x}/{y}.pbf'],
        'minzoom': tilejson.get('minzoom', 0),
        'maxzoom': tilejson['maxzoom'],
        'bounds': bounds_of(cover),
        'attribution': tilejson['attribution'],
    }}
    if used - {None} - set(style['sources']):
        raise SystemExit(f'layers draw from sources that were dropped: {sorted(used - {None} - set(style["sources"]))}')
    style['sprite'] = f'sprites/{name}'
    style['glyphs'] = 'glyphs/{fontstack}/{range}.pbf'
    style['metadata'] = {**style.get('metadata', {}), 'planwat:vendored': {
        'style': STYLE, 'tiles': tilejson['tiles'][0], 'sprite': sprite, 'engine': f'maplibre-gl@{version}',
        'date': time.strftime('%Y-%m-%d'),
    }}
    (OUT / 'style.json').write_text(json.dumps(style, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    size = sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())
    print(f'wrote src/map/: {len(cover)} tiles, {size / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
