"""WTC Plansoft grid cells: candidate words inside a band's column range, each
assigned to the nearest block row, grouped by column, then lines by y.

Recovered from the one-off WTC import; vs the recovered script the pymupdf
import is lazy, `extract_cells` takes `base_year`, and the unused raw-legend
debug helper is gone. A typical cell (top to bottom): subject abbrev (1-2
lines), type letter, room (1+ lines, may wrap), teacher abbrev, subgroup lines
(the converter drops those).
"""
from . import ir as IR


def _pymupdf():
    import pymupdf
    return pymupdf


def extract_cells(path, base_year):
    doc = _pymupdf().open(path)
    bands, blocks = IR.extract(path, base_year)
    cells = []   # {date, day, block, lines:[[words...]], xc}
    for b in bands:
        ds = b['dates']
        xs = [d['x'] for d in ds]
        bounds = []
        for i in range(len(xs)):
            left = xs[i] - (xs[i] - xs[i-1]) / 2 if i > 0 else xs[i] - (xs[1] - xs[0]) / 2
            right = xs[i] + (xs[i+1] - xs[i]) / 2 if i < len(xs) - 1 else xs[i] + (xs[i] - xs[i-1]) / 2
            bounds.append((left, right))
        # block rows of this band+page
        bblocks = [bl for bl in blocks if bl['page'] == b['page'] and bl['day'] == b['day']]
        # band y-range: from band y to next band y on same page (or page bottom)
        samepage = sorted([x['y'] for x in bands if x['page'] == b['page']])
        i = samepage.index(b['y'])
        y_top = b['y']
        y_bot = samepage[i+1] if i + 1 < len(samepage) else 1200.0
        page = doc[b['page']]
        words = page.get_text('words')
        for bl in bblocks:
            # words inside this band's column range; each word goes to
            # the nearest block row (labels fall outside the range)
            x_left, x_right = bounds[0][0], bounds[-1][1]
            cand = [w for w in words
                    if y_top < w[1] < y_bot
                    and x_left - 2 <= (w[0] + w[2]) / 2 <= x_right + 2
                    and w[4] not in IR.DAYS
                    and not IR.BLOCK_RE.match(w[4])]
            mine = [w for w in cand
                    if min(bblocks, key=lambda b2: abs(b2['y'] - w[1])) is bl
                    and abs(bl['y'] - w[1]) < 20]
            # group by column
            bycol = {}
            for w in mine:
                xc = (w[0] + w[2]) / 2
                for ci, (lo, hi) in enumerate(bounds):
                    if lo <= xc < hi:
                        bycol.setdefault(ci, []).append(w)
                        break
            for ci, ws in sorted(bycol.items()):
                # lines by y
                lines = []
                for w in sorted(ws, key=lambda w: w[1]):
                    if lines and abs(w[1] - lines[-1][0][1]) < 2.5:
                        lines[-1].append(w)
                    else:
                        lines.append([w])
                text_lines = [' '.join(w[4] for w in sorted(ln, key=lambda w: w[0]))
                              for ln in lines]
                cells.append({'date': ds[ci]['date'], 'day': b['day'],
                              'block': bl['block'], 'page': b['page'],
                              'lines': text_lines})
    return bands, blocks, cells
