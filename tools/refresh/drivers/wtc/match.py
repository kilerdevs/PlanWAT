"""Teacher-abbrev matcher, scoped to one subject's teacher list.

Normalisation: lowercase, NFD strip, `rz` -> `z`. Rules (unique hit required):
surname prefix, 2-letter prefix, S+F / F+S initials, glued splits, capitals
initials, dotted parts, hyphen components, consonant subsequence anchored at
the first consonant. Also the T-code / Gr. group markers, which the converter
keeps as DESCRIPTION `Grupy:` lines.

Recovered from the one-off WTC import; the unused pixmap color sampler is
gone (the emitter samples legend colors itself), so this module is stdlib
only. Teacher names never leave this module except as parse intermediates:
the emitter drops them before writing the calendar.
"""
import re
import unicodedata


def norm(s):
    s = s.lower().replace('.', ' ').replace(';', ' ')
    s = ''.join(c for c in unicodedata.normalize('NFD', s)
                if unicodedata.category(c) != 'Mn')
    return s.replace('rz', 'z')


VOWELS = set('aeiouyąęó')


def consonants(s):
    return ''.join(c for c in norm(s) if c.isalpha() and c not in VOWELS)


def _subseq(t, s):
    i = 0
    for c in s:
        if i < len(t) and c == t[i]:
            i += 1
    return i == len(t) and len(t) > 0


MARKER_RE = re.compile(r'^T\d+(\.\d+)?[A-ZĄĆĘŁŃÓŚŹŻ]?\.?$')
GR_BARE_RE = re.compile(r'^Gr\.$')
GR_FULL_RE = re.compile(r'^Gr\.\s*\S+\.?$')


def is_marker(tok):
    t = tok.strip().rstrip('.')
    return bool(MARKER_RE.match(t)) or t in ('B',) or bool(GR_BARE_RE.match(tok.strip()))


def _parts(tok):
    return [p for p in re.split(r'[.\-\s]+', norm(tok)) if p]


def single_match(tok, teachers):
    """Match one teacher token against [(surname, firstname)]. Return idx list."""
    t = re.sub(r'\s+', '', norm(tok)).rstrip('-')
    if not t:
        return []
    hits = []
    for i, (S, F) in enumerate(teachers):
        s, f = norm(S), norm(F)
        if not s:
            continue
        ok = False
        if f and len(t) >= 3 and s.startswith(t):
            ok = True  # Kub->Kubica
        elif len(t) == 2 and s.startswith(t):
            ok = True  # Gr->Grabka (scoped-unique only, enforced by caller)
        elif f and len(t) == 2 and t[0] == s[0] and t[1] == f[0]:
            ok = True  # RJ
        elif len(t) == 2 and f and t[0] == f[0] and t[1] == s[0]:
            ok = True  # MW (firstname initial + surinitial)
        elif len(t) >= 3:
            cs = consonants(S)
            if cs and t[0] == cs[0] and _subseq(t, cs):
                ok = True  # Czw->Czerwiński (anchored subsequence)
            else:
                for k in range(1, len(t)):
                    a, b = t[:k], t[k:]
                    if not b:
                        continue
                    if s.startswith(a) and f.startswith(b):
                        ok = True  # MajN, SpA, MKOCZ, KlM, KEr
                        break
                    if f.startswith(a) and s.startswith(b):
                        ok = True  # IzWo, MtGr
                        break
        if not ok:
            caps = [c for c in tok if c.isupper()]
            if len(caps) == 2 and f and caps[0].lower() == f[0] and caps[1].lower() == s[0]:
                ok = True  # MtGr (capitals = first+sur initials)
        if not ok:
            ps = _parts(tok)
            if len(ps) >= 2 and s.startswith(ps[0]) and (not f or f.startswith(ps[-1])):
                ok = True  # Wo.J, Na.J., Osz-Now.
            elif '-' in S:
                sp = [p for p in re.split(r'[-\s]+', s) if p]
                if len(ps) >= 2 and len(ps) >= len(sp) and \
                        all(sp[j].startswith(ps[j]) for j in range(len(sp))):
                    ok = True
                elif len(ps) >= 2 and f and any(
                        sp[j].startswith(ps[0]) and f.startswith(ps[-1])
                        for j in range(len(sp))):
                    ok = True  # Now. A (later hyphen part + firstname)
                elif len(ps) == 1 and any(sxx.startswith(ps[0]) for sxx in sp):
                    ok = True  # Now. -> Nowińska part
        if ok:
            hits.append(i)
    return hits


def group_match(gtok, teachers):
    """Match a ';'-separated teacher group string. Returns (surname, first) or None."""
    toks = [t.strip() for t in gtok.split() if t.strip()]
    if not toks:
        return None
    # try whole glued
    glued = ''.join(toks)
    hits = single_match(glued, teachers)
    if len(hits) == 1:
        return teachers[hits[0]]
    # last token = firstname cand, rest = surname cand
    if len(toks) >= 2:
        first, sur = toks[-1], ''.join(toks[:-1])
        cands = []
        for i, (S, F) in enumerate(teachers):
            s, f = norm(S), norm(F)
            ss = norm(sur).replace(' ', '')
            ff = norm(first)
            if (s.startswith(ss) or ss.startswith(s)) and (f.startswith(ff) or ff == f[0]):
                cands.append(i)
        if len(cands) == 1:
            return teachers[cands[0]]
    return None


def is_gray_white(hexcolor, tol=20):
    r = int(hexcolor[1:3], 16)
    g = int(hexcolor[3:5], 16)
    b = int(hexcolor[5:7], 16)
    if r > 242 and g > 242 and b > 242:
        return True
    return max(r, g, b) - min(r, g, b) < tol
