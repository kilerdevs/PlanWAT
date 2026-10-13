"""WTC Plansoft PDF grid geometry: day bands (date columns) and block rows.

Recovered from the one-off WTC import (see the WTC pendrive copy, planwat-wtc/);
the only changes vs the recovered script are a lazy pymupdf import (drivers must
import with stdlib only: the CI build job has no dependencies) and a `base_year`
parameter instead of the hardcoded 2026/2027 academic year.
"""
import datetime as D
import re

ROMAN = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7,
         'VIII': 8, 'IX': 9, 'X': 10, 'XI': 11, 'XII': 12}
DAYS = {'pon.': 0, 'wt.': 1, 'sr.': 2, 'czw.': 3, 'pt.': 4, 'sob.': 5, 'niedz.': 6}
DAYS['śr.'] = 2
ROMAN_RE = re.compile(r'^(I|II|III|IV|V|VI|VII|VIII|IX|X|XI|XII)$')
DD_RE = re.compile(r'^(\d{2})$')
BLOCK_RE = re.compile(r'^(\d+)-(\d+)$')


def _pymupdf():
    import pymupdf
    return pymupdf


def rows_of(words, tol=2.5):
    rows = []
    for w in sorted(words, key=lambda w: w[1]):
        if rows and abs(w[1] - rows[-1][0][1]) < tol:
            rows[-1].append(w)
        else:
            rows.append([w])
    for r in rows:
        r.sort(key=lambda w: w[0])
    return rows


def extract(path, base_year):
    """(bands, blocks) of one Plansoft PDF. Months IX-XII fall in `base_year`,
    I-II in the next one; a band is kept only when its dates step by 7 days
    and the first one matches the band's weekday."""
    doc = _pymupdf().open(path)
    bands = []
    blocks = []
    for pi, page in enumerate(doc):
        words = page.get_text('words')
        rows = rows_of(words)
        for ri, r in enumerate(rows):
            daytoks = [w for w in r if w[4] in DAYS and w[0] < 200]
            if not daytoks:
                continue
            blk = [w for w in r if BLOCK_RE.match(w[4]) and w[0] < 550]
            if blk:
                blocks.append({'page': pi, 'day': daytoks[0][4],
                               'block': blk[0][4], 'y': blk[0][1]})
                continue
            # header zone: this row plus rows within +-5pt (wrapped DD/roman)
            y0 = r[0][1]
            zone = [w for rr in rows for w in rr if abs(rr[0][1] - y0) <= 5.0]
            zone_by_x = sorted(zone, key=lambda w: w[0])
            dates = []
            used_romans = set()
            for w in zone_by_x:
                m = DD_RE.match(w[4])
                if not m or w[0] > 748:
                    continue
                rom = None
                # same-row nearest word to the right
                nxt = None
                for w2 in zone:
                    if abs(w2[1] - w[1]) < 2.5 and w2[0] > w[2]:
                        if nxt is None or w2[0] < nxt[0]:
                            nxt = w2
                if nxt is not None and nxt[0] - w[2] < 14:
                    if ROMAN_RE.match(nxt[4]):
                        rom = (nxt[4], id(nxt))
                if rom is None:
                    # same-x roman in another zone row (closest x wins)
                    best = None
                    best_key = None
                    for w2 in zone:
                        if (ROMAN_RE.match(w2[4]) and abs(w2[0] - w[0]) < 8
                                and abs(w2[1] - w[1]) > 2.5):
                            key = (abs(w2[0] - w[0]), abs(w2[1] - w[1]))
                            if best is None or key < best_key:
                                best, best_key = w2, key
                    if best is not None:
                        rom = (best[4], id(best))
                if rom and rom[1] not in used_romans:
                    used_romans.add(rom[1])
                    dd = int(m.group(1))
                    mo = ROMAN[rom[0]]
                    yr = base_year if mo >= 9 else base_year + 1
                    try:
                        dt = D.date(yr, mo, dd)
                        dates.append({'date': dt.isoformat(),
                                      'x': (w[0] + w[2]) / 2})
                    except ValueError:
                        pass
            dates.sort(key=lambda d: d['x'])
            if len(dates) >= 8:
                ok = all((D.date.fromisoformat(b['date'])
                          - D.date.fromisoformat(a['date'])).days == 7
                         for a, b in zip(dates, dates[1:]))
                wd = D.date.fromisoformat(dates[0]['date']).weekday()
                if wd != DAYS[daytoks[0][4]]:
                    ok = False
                if ok:
                    bands.append({'page': pi, 'day': daytoks[0][4],
                                  'y': r[0][1], 'dates': dates})
    return bands, blocks
