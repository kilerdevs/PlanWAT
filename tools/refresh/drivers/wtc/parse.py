"""WTC legend + cells -> event parts: subject/type/room/teachers/markers.

Cell shape (top to bottom): subject abbrev (1-2 lines), type letter, room
(1+ lines, may wrap), teacher abbrev (1-2 lines or `;`-joined), subgroup
lines (dropped). Teacher matching is scoped to the cell's subject teacher
list and needs a unique hit; the resolved names are parse intermediates
only — the emitter never writes them (no CONTACT line, no instructor line).

Recovered from the one-off WTC import; vs the recovered script the
/tmp/opencode audit runner (`__main__`) is gone and `parse_legend_full`
takes `base_year`.
"""
import os
import re

from . import cells as C
from . import legend2 as L2
from . import match as M

TYPEMAP = {'w': 'Wykład', 'ć': 'Ćwiczenia', 'L': 'Laboratorium',
           'S': 'Seminarium', 's': 'Seminarium', 'i': 'Zajęcia informacyjne',
           'E': 'Egzamin', 'e': 'Egzamin', 'Ep': 'Egzamin poprawkowy'}
BLOCKS = {'1-2': ('0800', '0935'), '3-4': ('0950', '1125'),
          '5-6': ('1140', '1315'), '7-8': ('1330', '1505'),
          '9-10': ('1600', '1735'), '11-12': ('1750', '1925'),
          '13-14': ('1940', '2115')}
DROP_RE = re.compile(r'^(Podgrupa.*|[AB]\s*-.*|-\s*.*|50%|\d{1,2})$')
ROMANS = {'I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII'}
RAW_ABBR_RE = re.compile(r'^[A-ZĄĆĘŁŃÓŚŹŻ][A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9_/-]{2,}$')
ROOMWORDS = {'budynek', 'bud', 'sala', 'aula', 'strzelnica', 'hala',
             'magazyn', 'schron', 'warsztat', 'poligon'}


def droppable(ln):
    s = ln.strip()
    return bool(DROP_RE.match(ln)) or ('cw.' in ln) or ('ćw.' in ln) \
        or ('podgrupa' in ln.lower()) or s.rstrip(';,') in ('A', 'B', 'C')


def _is_debris(ln):
    return droppable(ln) or ln.strip() in ROMANS


def parse_legend_full(path, base_year):
    subs, carried = L2.legend_subs(path, base_year)
    if carried:
        print('CARRY %s: %s' % (os.path.basename(path), carried))
    return subs


def _l0_teacher_frag(l0, subs):
    """First ;-part of L0 matches a teacher anywhere in this PDF's legend."""
    first = re.split(r'[;,]', l0)[0].strip().rstrip('.,;')
    if not first:
        return False
    return _matches_any_teacher(first, subs)


def _matches_any_teacher(tok, subs):
    for _a, v in subs.items():
        hs = M.single_match(tok, v['teachers'])
        if hs:
            return True
    return False


def _split_line_abbr(L, abbrs):
    """A line gluing room frag + subject ('55 DGB'): split it.

    Returns (subj, rest_lines, room_prefix) or None."""
    two = [a for a in abbrs if ' ' in a]
    for i, ln in enumerate(L):
        ws = ln.split()
        if len(ws) < 2:
            continue
        cands = []
        for a in two:
            aw = a.split()
            for j in range(len(ws) - len(aw) + 1):
                if ws[j:j + len(aw)] == aw:
                    cands.append((a, ws[:j], ws[j + len(aw):]))
        for j, w in enumerate(ws):
            if w in abbrs:
                cands.append((w, ws[:j], ws[j + 1:]))
        for a, before, after in cands:
            if before and all(re.fullmatch(r'[0-9KkSs\d\s/;.,() -]+', b) for b in before):
                return a, after + L[i + 1:], ' '.join(before)
    return None


def parse_cell(lines, subs):
    """-> dict(event parts) or {'skip': reason}."""
    L = [ln for ln in lines if not droppable(ln)]
    if not L:
        return {'skip': 'fragment'}
    if L == ['I']:
        return {'skip': 'I-cell'}
    if L == ['B']:
        return {'skip': 'B-frag'}
    lead_stripped = 0
    while len(L) > 1 and _is_debris(L[0]):
        L = L[1:]
        lead_stripped += 1
    abbrs = set(subs)
    subj, raw_subj, rest, room_prefix = None, False, None, None
    if len(L) >= 2 and (L[0] + ' ' + L[1]).strip() in abbrs:
        subj, rest = (L[0] + ' ' + L[1]).strip(), L[2:]
    elif len(L) >= 2 and L[0] not in abbrs and L[1] in abbrs:
        L = L[1:]  # leading debris ahead of the real subject (narrow cols)
        lead_stripped += 1
        subj, rest = L[0], L[1:]
    elif L[0] in abbrs:
        subj, rest = L[0], L[1:]
    elif len(L) == 1 and L[0] in ROMANS:
        return {'skip': 'roman-debris'}
    elif len(L) == 1 and re.fullmatch(r'[0-9KkSs\d\s/;.,() -]+', L[0]):
        return {'skip': 'room-frag'}
    elif re.match(r'^(w|ć|L|S|s|i|E|e|Ep|P|B|r|Rep|lab|ć/wyj|lab/wyj)\b[\s.]', L[0]) and L[0] not in abbrs:
        return {'skip': 'type-frag'}
    elif M.is_marker(L[0].strip().rstrip('.,;')) or M.GR_FULL_RE.match(L[0].strip()):
        return {'skip': 'marker-frag'}
    elif _l0_teacher_frag(L[0], subs):
        return {'skip': 'teacher-frag'}
    elif len(L) == 1 and RAW_ABBR_RE.match(L[0]) and L[0] not in ROMANS:
        t0 = L[0].strip().rstrip('.,;')
        if M.is_marker(t0) or M.GR_FULL_RE.match(t0):
            return {'skip': 'marker-frag'}
        if _matches_any_teacher(L[0], subs):
            return {'skip': 'teacher-frag'}
        subj, raw_subj, rest = L[0], True, []
    else:
        # within-line abbr: '55 DGB' -> room frag + subject
        split = _split_line_abbr(L, abbrs)
        if split is not None:
            subj, rest, room_prefix = split
        else:
            return {'skip': 'unknown-subject', 'L0': L[0], 'lines': L}
    if not rest:
        typ, rest, room_lines_pre = None, [], []
    else:
        typ, rest = rest[0], rest[1:]
        if typ and len(typ.split()) > 1:
            hits = [w for w in typ.split() if w in TYPEMAP]
            if len(hits) == 1:
                room_lines_pre = [w for w in typ.split() if w != hits[0]]
                typ = hits[0]
            else:
                room_lines_pre = []
        else:
            room_lines_pre = []
    room_lines, teach_lines, markers, dropped = [], [], [], []
    if room_prefix:
        room_lines.append(room_prefix)
    room_lines.extend(room_lines_pre)
    in_teach = False
    for ln in rest:
        s = ln.strip()
        if not s:
            continue
        if s == 'B':
            continue  # subgroup-B marker, drop
        cand = [t for t in subs[subj]['teachers']] if not raw_subj else []
        matched, failed, nskip = [], None, 0
        parts = [p.strip().rstrip(';,') for p in re.split(r'[;,]', ln)
                 if p.strip().rstrip(';,')]
        for part in parts:
            if in_teach and teach_lines and _is_firstname_of(part, teach_lines[-1]):
                nskip += 1
                continue  # wrapped firstname, already recorded
            m = M.group_match(part, cand)
            if m is None:
                hs = M.single_match(part, cand)
                if len(hs) == 1:
                    m = cand[hs[0]]
            if m is None:
                failed = part
                break
            matched.append(' '.join(m).strip())
        if failed is None:
            if matched:
                in_teach = True
                teach_lines.extend(matched)
            elif nskip == len(parts):
                pass  # only wrapped-firstname continuations: ignore
            elif not in_teach:
                room_lines.append(ln)
            else:
                dropped.append(ln)
            continue
        if M.is_marker(failed) or M.GR_FULL_RE.match(failed.strip()):
            markers.append(failed)  # T-codes, Grupa markers -> DESCRIPTION
            continue
        if not in_teach:
            room_lines.append(ln)
        elif re.search(r'\d', failed) or failed.strip().rstrip('.').lower() in ROOMWORDS:
            room_lines.append(ln)  # room wrapped below its teacher
        else:
            dropped.append(failed)
    return {'subj': subj, 'raw_subj': raw_subj, 'type': typ,
            'room': ' '.join(room_lines),
            'teachers': list(dict.fromkeys(teach_lines)),
            'markers': markers, 'dropped': dropped,
            'lead_stripped': lead_stripped}


def _is_firstname_of(part, recorded):
    import unicodedata as _u

    def _n(x):
        x = x.lower().replace('.', '')
        return ''.join(c for c in _u.normalize('NFD', x) if _u.category(c) != 'Mn')
    p = _n(part)
    rec = _n(recorded).split()
    if not rec or not p:
        return False
    return p == rec[-1] or (len(p) == 1 and p == rec[-1][:1])
