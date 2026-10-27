"""WIG (www.wig.wat.edu.pl/cpp): Plansoft PDFs, one per group, in a Phoca Download file tree.

The faculty's page `rozklady-zajec` (Joomla) links each group's PDF from a programme -> year category, but
the files themselves sit in plain directories (`/cpp/phocadownloadpap/<programme>/<mode>/WIG26AX1S0.pdf`,
mode `stacjonarne`, `niestacjonarne` or `drugistopien`) whose Apache listings are open. Discovery reads those
listings, not Joomla: Incapsula answers the Joomla pages with a challenge from datacenter addresses (the oracle
runner, checked 2026-10-26) while it serves the listings and PDFs to both runners, and two levels of small
listings cost less than sixty category pages. The listing above the programmes is hidden, so `dirs` in
sources.json names the programme directories; their subdirectories are found by the walk. The PDFs are
static files with `Last-Modified`, so the refresh's conditional fetch answers 304 for an unchanged plan.

What the configured directories miss (a new programme) the census finds: `census()` walks the Joomla tree
itself, every year category of `landing`, and names the directories of all the PDFs it links. It runs where
Joomla answers (refresh.py --census, the plebania runner via fleet.json, at most once a week, after its crawl and at
its pace); its result is
kept in refresh-state.json under `found` and handed back to `discover` as `cfg['found']` on any runner.

Each PDF is a wkhtmltopdf print of a Plansoft group page: a day x slot x week grid with a legend in its last
two columns, drawn with black ruling lines, cells reading SUBJ(type) / room / lecturer alias like WIM's.
Full-time plans repeat the day in every row (the IOE-style transposed grid); part-time plans span one day
cell over the weekday's rows. The converter rebuilds the table from the ruling lines and the words inside
them, writes it out as the Plansoft HTML `wlo2ics` already reads, and lets `wlo2ics` do the rest, so WIG
calendars follow the same rules as every Plansoft faculty. The header names the group and the semester: a
PDF of another group fails, and one of another semester is not ready yet (core.NotReady).

The calendar carries no personal data of staff: legend names and cell aliases are parse intermediates
only, dropped by `wlo2ics` before anything is written (no CONTACT line, no instructor line).
"""
import html
import random
import re
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin

import core
import wlo2ics
from drivers import Item, plansoft

HREF_RE = re.compile(r'<a href="([^"?/][^"]*)"', re.I)  # an Apache listing's entries (not its sort links or parent)
PDF_RE = re.compile(r'href="([^"]*/phocadownloadpap/[^"]+\.pdf)"', re.I)  # a Joomla category page's direct links
DIR_RE = re.compile(r'^(?!\.)[\w.-]+(?:/(?!\.)[\w.-]+)*$', re.A)  # a directory under `base`: never '..' or absolute
# full-time prints: 'SEMESTR - WIG ZIMA 2026-2027-CYW' / 'GRUPA - WIG26AX1S0';
# part-time prints: 'niestacjonarne Zima 2026_2027' / 'Nazwa Grupy: WIG26BX1N1'
GROUP_RE = re.compile(r'(?:GRUPA\s*-|Nazwa Grupy:)\s*([A-Z0-9_]+)')
TERM_RE = re.compile(r'\b(ZIMA|LATO)\s+(\d{4})\s*[-_]\s*\d{4}', re.I)
DIGIT_RE = re.compile(r'\d')
SHARE_RE = re.compile(r'^\d+\s*%$')  # '50%': a class for part of the group
SETTLEMENT_RE = re.compile(r'^\S+\s+\d+$')  # 'w 14', 'ć 30': a lecturer's hours, under the alias line
LINE = 1.5      # a ruling line is thinner than this (pt)
SNAP = 1.5      # line positions this close are one line (header rows draw their own, slightly offset)


def leaf_categories(text, landing):
    """The year categories `landing` links (`.../rozklady-zajec/<id>-.../<id>-...`), in page order."""
    path = re.escape(landing.split('://', 1)[-1].split('/', 1)[-1].rstrip('/'))
    found = re.findall(rf'href="(/{path}/\d+-[^"/?#]+/\d+-[^"/?#]+)"', text)
    return list(dict.fromkeys(urljoin(landing, href) for href in found))


def listing(text, url):
    """(subdirectories, PDFs) an Apache directory listing names, as absolute URLs."""
    hrefs = [urljoin(url, h) for h in HREF_RE.findall(text)]
    return [h for h in hrefs if h.endswith('/')], [h for h in hrefs if h.lower().endswith('.pdf')]


def _pymupdf():
    import pymupdf
    return pymupdf


def _snap(values, min_count):
    """Ruling-line positions: values within SNAP merged (first one kept), rare ones (header colspans) dropped."""
    out = []
    for v in sorted(values):
        if out and v - out[-1][0] <= SNAP:
            out[-1][1] += 1
        else:
            out.append([v, 1])
    return [v for v, n in out if n >= min_count]


def page_grid(page):
    """(columns, rows) boundaries of the page's table, from its black filled hairline rectangles."""
    xs, ys = [], []
    for d in page.get_drawings():
        fill = d.get('fill')
        if fill is None or sum(fill) > 0.05:
            continue
        r = d['rect']
        if r.width < LINE and r.height > 3:
            xs.append(r.x0)
        elif r.height < LINE and r.width > 3:
            ys.append(r.y0)
    # a column line runs through most rows; header colspans add a few short, offset segments
    cols = _snap(xs, max(2, len(set(round(y) for y in ys)) // 3))
    rows = _snap(ys, 1)
    return cols, rows


def _spans(page):
    """(word, x0, y0, x1, y1, spaced) of every word on the page, boxed round its own characters: one text
    run may cross cells ('Mat2(w) Mat2(w)') or start with padding spaces (a legend short), so runs are cut at
    whitespace and each piece lands in the cell it is printed in. `spaced` marks a word the run separated
    from the previous one by a space (in small print '111 58' sits closer than two separate runs)."""
    out = []
    for block in page.get_text('rawdict')['blocks']:
        for line in block.get('lines', []):
            for s in line['spans']:
                word, spaced = [], False
                for c in s['chars'] + [None]:
                    if c is not None and not c['c'].isspace():
                        word.append(c)
                        continue
                    if word:
                        out.append((''.join(w['c'] for w in word),
                                    min(w['bbox'][0] for w in word), min(w['bbox'][1] for w in word),
                                    max(w['bbox'][2] for w in word), max(w['bbox'][3] for w in word), spaced))
                        word = []
                    spaced = True
    return out


def _index(bounds, v):
    for i in range(len(bounds) - 1):
        if bounds[i] <= v < bounds[i + 1]:
            return i
    return None


def _visible(spans):
    """Spans minus those another span on the same line already covers: a row split by a page break prints
    the glyphs at the break on both pages ('Mat2(ć)' at the bottom of one, 'at(ć)' at the top of the next)."""
    keep = []
    for s in sorted(spans, key=lambda s: s[1] - s[3]):  # widest first
        mid = (s[2] + s[4]) / 2
        if not any(abs(mid - (k[2] + k[4]) / 2) < 2.0 and k[1] - 0.5 <= s[1] and s[3] <= k[3] + 0.5 for k in keep):
            keep.append(s)
    return keep


def _lines(spans):
    """A cell's words as text lines, top to bottom."""
    rows = []
    for s in sorted(_visible(spans), key=lambda s: ((s[2] + s[4]) / 2, s[1])):
        mid = (s[2] + s[4]) / 2
        if rows and abs(mid - rows[-1][0]) < 2.0:
            rows[-1][1].append(s)
        else:
            rows.append([mid, [s]])
    out = []
    for _, ss in rows:
        ss.sort(key=lambda s: s[1])
        text = ''
        for i, s in enumerate(ss):
            gap = s[1] - ss[i - 1][3] if i else 0
            text += (' ' if i and (s[5] or gap > 0.8) else '') + s[0]
        out.append(' '.join(text.split()))
    return out


def _page_rows(page):
    """[(top, bottom, {column: [spans]})] of the page's table, and its column count."""
    cols, ys = page_grid(page)
    if len(cols) < 6 or len(ys) < 2:
        return [], 0
    cells = {}
    for s in _spans(page):
        r = _index(ys, (s[2] + s[4]) / 2)
        c = _index(cols, (s[1] + s[3]) / 2)
        if r is not None and c is not None:
            cells.setdefault((r, c), []).append(s)
    return [(ys[r], ys[r + 1], {c: v for (rr, c), v in cells.items() if rr == r}) for r in range(len(ys) - 1)], \
        len(cols) - 1


def _same_row(last, first, step):
    """The row cut by a page break: wkhtmltopdf prints one long canvas, so its top on the next page sits one
    page step (the page less its two 10 mm margins) above where it started, and it keeps its height."""
    return (abs((last[0] - first[0]) - step) < 1.2
            and abs((last[1] - last[0]) - (first[1] - first[0])) < 0.8)


def read_tables(path):
    """Every table row of the PDF as a list of cells, each cell a list of text lines; plus the page text.

    Pages whose table has another column count than the first (an empty trailing page) are left out.
    """
    doc = _pymupdf().open(path)
    rows, text, width = [], [], None
    for page in doc:
        text.append(page.get_text())
        page_rows, n = _page_rows(page)
        if not page_rows or (width is not None and n != width):
            continue
        step = page.rect.height - 2 * 72 * 10 / 25.4
        if rows and width is not None and _same_row(rows[-1], page_rows[0], step):
            top, bottom, cells = page_rows.pop(0)
            prev = rows[-1][2]
            for c, spans in cells.items():
                prev.setdefault(c, []).extend((t, x0, y0 + step, x1, y1 + step, sp) for t, x0, y0, x1, y1, sp in spans)
        width = n
        rows.extend(page_rows)
    return [[_lines(cells.get(c, [])) for c in range(width)] for _, _, cells in rows], '\n'.join(text)


def is_lesson(lines):
    """A lesson cell opens (after any '50%' share line) with SUBJ(type)."""
    rest = [t for t in lines if not SHARE_RE.match(t)]
    return bool(rest) and '(' in rest[0]


def lesson_segments(lines, aliases):
    """A lesson cell's lines -> the Plansoft <font> segments wlo2ics reads as a WIM cell.

    The cell reads [share], SUBJ(type), room, alias. The subject line wraps mid-token in narrow columns
    ('PZiP(w' + ')'), so lines are glued while its bracket is open. The alias is the last line when the
    legend names it or it has no digit (rooms always carry one: 'A 59', '111 58', '06 58;17 58'); the lines
    between subject and alias are one wrapped room ('Tor.J;' / 'Siw.K' is one alias slot). The alias is
    dropped here: it would only steer lecturer names the calendar never carries, and an empty alias slot
    falls back to the legend's settlement.
    A share ('50%') goes last, where wlo2ics keeps a WIM cell's notes ('Uwaga: 50%').
    """
    lines = list(lines)
    shares = []
    while lines and SHARE_RE.match(lines[0]):
        shares.append(lines.pop(0))
    head = lines.pop(0)
    while lines and head.count('(') > head.count(')'):
        head += lines.pop(0)
    while lines and (lines[-1] in aliases or not DIGIT_RE.search(lines[-1])):
        lines.pop()
    parts = ' '.join(lines).split(';')
    if len(parts) > 1 and not re.search(r'[\s/]', parts[-1].strip()):
        parts.pop()  # a long room list cut off by the printed cell ('...;124 K;12'): the stub names no building
    room = ';'.join(parts)
    return [head, room, ''] + shares if shares else [head, room]


def legend_entry(short_lines, full_lines):
    """(short, full) of a legend row: a settlement cell keeps its hours line ('Pta.S' / 'w 14' -> 'w 14')."""
    short = list(short_lines)
    if len(short) > 1 and SETTLEMENT_RE.match(short[-1]):
        short = short[-1:]
    return ' '.join(short), ' '.join(full_lines)


def _font(text):
    return f'<font>{html.escape(text)}</font>'


def _text(cell):
    return ' '.join(cell)


def _slot(cell):
    return re.sub(r'-\s+', '-', _text(cell))  # '9-' / '10' wrapped in the narrow slot column


def plansoft_html(rows, footer):
    """The rebuilt table as the transposed Plansoft page wlo2ics reads (IOE shape): every lesson row
    [day, slot, spacer, week cells..., legend short, legend full], each weekday opening with its date strip.

    WIG prints two layouts of the same grid: full-time plans repeat the day in every row and keep an empty
    spacer column; part-time plans span one day cell over the weekday's rows. Column roles therefore come
    from the content (a day name, a slot, a date), and a weekday's rows run from one date strip to the next.
    """
    width = max((len(r) for r in rows), default=0)
    if width < 6:
        return '<html><body></body></html>'
    body = range(width - 2)  # the last two columns are the legend

    def column(rx, read=_text):
        return next((c for c in body for r in rows if rx.match(read(r[c]))), None)

    day_col, slot_col = column(wlo2ics.DAY_RE), column(wlo2ics.SLOT_RE, _slot)
    if day_col is None or slot_col is None:
        return '<html><body></body></html>'
    weeks = [c for c in body if c > slot_col and any(r[c] for r in rows)]  # the spacer is empty throughout
    strips = [i for i, r in enumerate(rows)
              if sum(bool(wlo2ics.DATE_RE.match(_text(r[c]))) for c in weeks) >= max(2, len(weeks) // 3)]
    day_of = {}
    for n, start in enumerate(strips):
        stop = strips[n + 1] if n + 1 < len(strips) else len(rows)
        day = next((_text(rows[i][day_col]) for i in range(start, stop)
                    if wlo2ics.DAY_RE.match(_text(rows[i][day_col]))), '')
        for i in range(start, stop):
            day_of[i] = day
    aliases = {r[-2][0] for r in rows if len(r[-2]) > 1 and SETTLEMENT_RE.match(r[-2][-1])}
    pad = max(0, 15 - len(weeks))  # wlo2ics reads a row as a grid row from 20 cells on
    out = ['<html><body><table>']
    for i, r in enumerate(rows):
        slot = _slot(r[slot_col])
        lesson = bool(wlo2ics.SLOT_RE.match(slot))
        # a row neither strip nor lesson (a month header, legend padding) carries only its legend
        day = day_of.get(i, '') if (i in strips or lesson) else ''
        tds = [f'<td>{html.escape(day)}</td>', f'<td>{html.escape(slot if lesson else "")}</td>', '<td></td>']
        for c in weeks:
            cell = r[c]
            if is_lesson(cell):
                tds.append('<td>' + ''.join(_font(x) for x in lesson_segments(cell, aliases)) + '</td>')
            else:
                tds.append(f'<td>{html.escape(_text(cell))}</td>')
        tds += ['<td></td>'] * pad
        short, full = legend_entry(r[-2], r[-1])
        if short:
            payload = html.escape(f'<P>{html.escape(full)}</P>', quote=True)
            tds.append(f'<td mergeWith="{payload}">{html.escape(short)}</td><td>{html.escape(full)}</td>')
        else:
            tds.append('<td></td><td></td>')
        out.append('<tr>' + ''.join(tds) + '</tr>')
    out.append('</table>')
    out.append(f'<p>{html.escape(footer)}</p></body></html>')
    return '\n'.join(out)


def pdf_term(text):
    """'SEMESTR - WIG ZIMA 2026-2027-CYW' -> '2026-27-zima'; None when the header names no semester."""
    m = TERM_RE.search(text)
    if not m:
        return None
    year = int(m.group(2))
    return f'{year}-{(year + 1) % 100:02d}-{m.group(1).lower()}'


class Driver:
    def __init__(self, faculty, cfg, today, sleep=time.sleep):
        self.faculty, self.cfg, self.today, self.sleep = faculty, cfg, today, sleep
        self.prefix = cfg.get('prefix', '')

    def _get(self, session, url, what):
        r = session.get(url, timeout=30)
        text = plansoft.decode(r.content)
        if r.status_code == 404:
            return ''  # a directory renamed or gone lists nothing (the run's listed-count canary notices)
        if core.is_blocked(r.status_code, text):
            raise core.Blocked(f'{what}: HTTP {r.status_code}')
        return text

    def discover(self, session):
        """Every group PDF under the programme directories: each listing, then the mode directories it names."""
        base = self.cfg['base']
        groups_re = self.cfg.get('groups_re')
        rx = re.compile(groups_re, re.I) if groups_re else None
        # programme directories descend one level (their modes); directories the census found are read as they are
        queue = [(urljoin(base, d.strip('/') + '/'), 0) for d in self.cfg.get('dirs', [])]
        queue += [(urljoin(base, d + '/'), 1) for d in self.cfg.get('found', {}).get('dirs', [])
                  if isinstance(d, str) and DIR_RE.match(d)]
        pdfs, n, seen_dirs = [], 0, set()
        while queue:
            url, depth = queue.pop(0)
            if url in seen_dirs:
                continue
            seen_dirs.add(url)
            if n:
                self.sleep(random.uniform(1.0, 2.0))
            n += 1
            subdirs, found = listing(self._get(session, url, 'file listing'), url)
            pdfs += found
            if depth < 1:
                queue += [(d, depth + 1) for d in subdirs if d.startswith(url)]
        items, seen = [], set()
        for pdf in pdfs:
            stem = pdf.rsplit('/', 1)[-1][:-4]
            if rx is not None and not rx.search(stem):
                continue
            code = core.group_code(stem, self.prefix, self.cfg.get('keep_prefixes', ()))
            if code and code not in seen:
                seen.add(code)
                items.append(Item(code, pdf, stem))
        return items

    def census(self, session, pause=(1.0, 2.0)):
        """{'dirs': [...], 'pdfs': n}: the directories (relative to `base`) of every PDF the Joomla year categories
        link, `pause` seconds apart (refresh.py passes the crawl's own pace). Raises core.Blocked where Incapsula
        challenges this address (datacenter lines)."""
        landing, base = self.cfg['landing'], self.cfg['base']
        text = self._get(session, landing, 'category list')
        pdfs = []
        for n, url in enumerate(leaf_categories(text, landing)):
            if n:
                self.sleep(random.uniform(*pause))
            pdfs += PDF_RE.findall(self._get(session, url, 'category page'))
        dirs = set()
        for pdf in dict.fromkeys(urljoin(landing, p) for p in pdfs):
            if pdf.startswith(base):
                rel = pdf[len(base):].rsplit('/', 1)[0]
                if '/' in pdf[len(base):] and DIR_RE.match(rel):
                    dirs.add(rel)
        return {'dirs': sorted(dirs), 'pdfs': len(set(pdfs))}

    def page_ok(self, text):
        return text.lstrip('\ufeff').startswith('%PDF')

    def convert(self, item, raw):
        if not raw.startswith(b'%PDF'):
            raise ValueError(f'{item.code}: not a PDF (an error page?)')
        with tempfile.TemporaryDirectory() as tmp:
            src, page, out = Path(tmp) / f'{item.page}.pdf', Path(tmp) / f'{item.page}.htm', Path(tmp) / 'out.ics'
            src.write_bytes(raw)
            rows, text = read_tables(str(src))
            m = GROUP_RE.search(text)
            if not m or m.group(1) != item.code:
                raise ValueError(f'{item.code}: the PDF is the plan of {m.group(1) if m else "no group"}')
            want, term = core.term_id(self.today), pdf_term(text)
            if term != want:
                raise core.NotReady(f'{item.code}: the PDF shows {term or "no semester"}, not {want}')
            # the header names the semester; the update footer alone would date a plan printed in August a year early
            footer = re.search(r'Data aktualizacji:[^\n]*', text)
            page.write_text(plansoft_html(rows, footer.group(0) if footer else ''), encoding='utf-8')
            wlo2ics.main([str(page), '-o', str(out), '--grupa', item.code, '--code', item.code,
                          '--faculty', self.faculty, '--year', term[:4],
                          '--period', core.period_label(self.cfg.get('label', 'WIG'), self.today)])
            return out.read_text(encoding='utf-8')
