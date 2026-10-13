"""WTC legend: subject abbreviations with full names and per-subject teachers.

Abbr detection: a non-bold word with x0 in [745, 764), len >= 2, a single
alnum token with a letter, not a date DD / roman numeral / degree word.
Entry assembly: rows attach to the nearest abbr below (within 15 pt: the
entry starts there); teacher-led (degree-first) rows attach upward; single
capitalized words attach upward only as wrapped firstnames; otherwise upward.
`legend_subs` spills a teacher chunk's tail into the next entry when it matches
that entry's name start (shared baselines).

Recovered from the one-off WTC import; vs the recovered script the pymupdf
import is lazy and the legend takes `base_year` (the recovered script
hardcoded the 2026/2027 academic year). Degrees and ranks are stripped from
teacher chunks (they never reach the calendar); the resolved (surname,
firstname) pairs are used only to tell rooms from teachers while parsing
cells.
"""
import re

from . import ir as IR


ROMAN = {'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII'}

DEG = {'dr', 'hab', 'inż', 'inz', 'mgr', 'prof', 'lic', 'med',
       'gen', 'bryg', 'ppłk', 'płk', 'mjr', 'por', 'ppor', 'kpr',
       'chor', 'mł', 'ml', 'rez', 'sierż', 'sierz', 'plut', 'st',
       'lek', 'kpt', 'mat', 'bosm', 'ogn', 'sekc', 'chorąży'}


def _pymupdf():
    import pymupdf
    return pymupdf


def deg_strip(words):
    """Strip leading degree/rank tokens; return (surname_parts, firstname)."""
    i = 0
    while i < len(words):
        w = words[i]
        if '(' in w or ')' in w:
            i += 1
            continue
        parts = [p for p in w.split('.') if p]
        if parts and all(p.lower() in DEG for p in parts):
            i += 1
        else:
            break
    rest = words[i:]
    if not rest:
        return None
    return rest


def entry_bounds(page):
    """Unique y of horizontal lines spanning the legend name column."""
    ys = set()
    for dr in page.get_drawings():
        r = dr['rect']
        if r.height < 1.5 and r.width > 20 and r.x0 > 755 and r.x1 > 800:
            ys.add(round(r.y0, 1))
    return sorted(ys)


def abbr_boxes(page, x_min):
    """Filled abbr-box rects right of the grid (rowspan height)."""
    boxes = []
    for dr in page.get_drawings():
        r = dr['rect']
        f = dr.get('fill')
        if f is None:
            continue
        if max(f) < 0.25:
            continue  # black border segments
        if r.x0 < x_min or r.width < 8 or r.width > 32:
            continue
        if r.height < 8 or r.height > 95:
            continue
        boxes.append(r)
    return boxes


def word_fonts(page):
    """Map word index -> bold flag using dict spans."""
    spans = []
    for b in page.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            for s in l['spans']:
                spans.append(s)
    out = []
    for w in page.get_text('words'):
        cx, cy = (w[0] + w[2]) / 2, (w[1] + w[3]) / 2
        best, best_key = False, None
        for s in spans:
            x0, y0, x1, y1 = s['bbox']
            if x0 <= cx <= x1 and y0 <= cy <= y1 and w[4] in s['text']:
                key = abs((x0 + x1) / 2 - cx)
                if best_key is None or key < best_key:
                    best, best_key = bool(s['flags'] & 16), key
        out.append(best)
    return out


def _is_abbr_word(text):
    t = text.strip()
    if len(t) < 2:
        return False
    if re.fullmatch(r'\d{2}', t) or t in ROMAN:
        return False
    parts = [p for p in t.split('.') if p]
    if parts and all(p.lower() in DEG for p in parts):
        return False
    return True


def is_deg_start(word):
    parts = [p for p in word.split('.') if p]
    return bool(parts) and all(p.lower() in DEG for p in parts)


def frag_line(toks):
    """Truncated-fragment line (page-break debris): only tiny tokens."""
    return len(toks) >= 3 and all(len(t) <= 3 for t in toks)


def split_name_teachers(lines):
    """Subject name lines; degree-led chunks = teachers; rest after = notes."""
    name = []
    teachers = []
    notes = []
    dropped = []
    cur = None
    for ln in lines:
        toks = ln.split()
        if not toks:
            continue
        if is_deg_start(toks[0]):
            if cur:
                teachers.append(cur)
            cur = toks
        elif (cur is not None and len(toks) <= 2
                and all(re.match(r'^[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż-]+$', t)
                        for t in toks)):
            cur = cur + toks  # teacher firstname on next line
        else:
            if cur:
                teachers.append(cur)
                cur = None
            if teachers:
                notes.append(ln)
            elif toks[0] == '.' or re.fullmatch(r'\d+', toks[0]):
                notes.append(ln)  # range note like '. 1 STRZEL.', not a name
            elif frag_line(toks):
                dropped.append(ln)
            else:
                name.append(ln)
    if cur:
        teachers.append(cur)
    clean = []
    for t in teachers:
        s = deg_strip(t)
        if s:
            clean.append(s)
    return ' '.join(name), clean, notes, dropped


def legend_subs(path, base_year):
    """Full legend: abbr -> {name, teachers[(surname, first)], notes, ...}.

    Teacher chunks with 3+ tokens spill their tail into the next entry
    when the tail matches that entry's name start (shared baselines).
    Returns (subs, carried_log).
    """
    doc = _pymupdf().open(path)
    bands, _ = IR.extract(path, base_year)
    lastx = {}
    for b in bands:
        lastx[b['page']] = max(lastx.get(b['page'], 0), b['dates'][-1]['x'])
    entries = []
    for pi, page in enumerate(doc):
        words = page.get_text('words')
        fonts = word_fonts(page)
        fmap = {id(w): b for w, b in zip(words, fonts)}
        xmin = lastx.get(pi, lastx.get(pi - 1, 745.0)) + 3.0
        cands = []
        for w, bold in zip(words, fonts):
            if bold:
                continue
            # abbr column: right of grid Feb dates (<745), left of
            # names/teachers (>=764); DD/roman/degree guards in helper
            if 745 <= w[0] < 764 and _is_abbr_word(w[4]):
                cands.append(w)
        cands.sort(key=lambda w: w[1])
        groups, cur = [], []
        for w in cands:
            if cur and w[1] - cur[-1][1] > 12:
                groups.append(cur)
                cur = []
            cur.append(w)
        if cur:
            groups.append(cur)
        abbrs = []
        for g in groups:
            g = sorted(g, key=lambda w: w[0])
            txt = ' '.join(w[4] for w in g)
            cy = sum((w[1] + w[3]) / 2 for w in g) / len(g)
            abbrs.append((txt, cy, g[0]))
        # one entry per abbr; content rows attach below
        for ai, (txt, cy, w0) in enumerate(abbrs):
            entries.append({'abbr': txt, 'rows': [], 'page': pi, 'ay': cy, 'aw': [w0]})
        # attach content rows: each legend row goes to the entry whose
        # abbr is nearest below it (entry starts), except teacher-led rows
        # (degree-first) which belong upward, and rows already holding abbr
        rows = {}
        for w in words:
            if w[0] < 764 or w[0] > 900:
                continue
            rows.setdefault(round(w[1]), []).append(w)
        # previous content row per y (for firstname-continuation test)
        prev_y, prev_teacher = None, False
        for y in sorted(rows):
            ws = sorted(rows[y], key=lambda w: w[0])
            own = [e for e in entries
                   if e['page'] == pi and abs(e['ay'] - y) <= 3]
            if own:
                # abbr's own row: normal words stay, bold x<764 words
                # belong to the previous entry (merged baselines)
                for w in ws:
                    if w in [a for e in entries for a in e['aw']]:
                        continue
                    bi = fmap.get(id(w), False)
                    if bi and w[0] < 764:
                        above = [(y - e['ay'], e) for e in entries
                                 if e['page'] == pi and e['ay'] < y - 2]
                        if above:
                            above.sort()
                            above[0][1]['rows'].append([w])
                    else:
                        own[0]['rows'].append([w])
                continue
            # find nearest abbr strictly below (entry start) and above
            below = [(e['ay'] - y, e) for e in entries
                     if e['page'] == pi and e['ay'] >= y - 2]
            above = [(y - e['ay'], e) for e in entries
                     if e['page'] == pi and e['ay'] < y - 2]
            toks = ' '.join(w[4] for w in ws).split()
            teach = toks and is_deg_start(toks[0])
            single_cap = (len(toks) <= 2 and toks and all(
                re.match(r'^[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż-]+$', t)
                for t in toks))
            if teach and above:
                above.sort()
                above[0][1]['rows'].append(ws)
            elif single_cap and above and prev_teacher \
                    and prev_y is not None and y - prev_y < 12:
                # teacher firstname wrapped to next line: continuation
                above.sort()
                above[0][1]['rows'].append(ws)
            elif below and min(d for d, _e in below) < 15:
                # entry-start name line just above its abbr
                below.sort()
                below[0][1]['rows'].append(ws)
            elif above:
                above.sort()
                above[0][1]['rows'].append(ws)
            prev_y, prev_teacher = y, bool(teach)
        # flatten rows -> lines (current page's entries only)
        for e in entries:
            if e['page'] != pi:
                continue
            for a in e['aw']:
                for r in e['rows']:
                    if a in r:
                        r.remove(a)
            e['rows'] = [r for r in e['rows'] if r]
            lines = []
            rs = {}
            for r in e['rows']:
                for w in r:
                    rs.setdefault(round(w[1]), []).append(w)
            for k in sorted(rs):
                lines.append(' '.join(w[4] for w in sorted(rs[k], key=lambda w: w[0])))
            e['lines'] = lines
            w0 = e['aw'][0]
            e['apos'] = (pi, (w0[0] + w0[2]) / 2, (w0[1] + w0[3]) / 2)
    raw = [e['lines'] for e in entries]
    subs = {}
    carried_log = []
    carry = []
    for idx, e in enumerate(entries):
        if not e['abbr']:
            continue
        lines = carry + e['lines']
        carry = []
        name, teach, notes, dropped = split_name_teachers(lines)
        fixed = []
        for t in teach:
            if len(t) > 2 and idx + 1 < len(entries):
                nxt = ' '.join(raw[idx + 1][:2])
                tail = ' '.join(t[2:])
                if nxt.startswith(tail) and tail:
                    fixed.append(t[:2])
                    carry = [' '.join(t[2:])]
                    carried_log.append((e['abbr'], tail))
                    continue
            fixed.append(t)
        ts = []
        for t in fixed:
            if len(t) >= 2:
                ts.append((' '.join(t[:-1]), t[-1]))
            elif t:
                ts.append((t[0], ''))
        subs[e['abbr']] = {'name': name, 'teachers': ts,
                           'notes': notes, 'dropped': dropped,
                           'apos': e.get('apos')}
    return subs, carried_log
