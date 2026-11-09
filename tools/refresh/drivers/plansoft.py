"""Plansoft faculty sites (WLO, WEL, WIM): the index lists one group page per group, each a static semester grid.

WLO and WEL publish the list as index.xml (`<gro href=...>`). WIM replaced that export with index.html in November
2026: the same Plansoft page, but the groups sit in the first `contentsColumn` while the other columns list lecturers
and rooms. Both exports yield the same group items, and a faculty that switches formats stays found.
"""
import re
import tempfile
from pathlib import Path

import core
import wlo2ics
from drivers import Item

ENCODINGS = ('utf-8', 'windows-1250')
GRO_LINK_RE = re.compile(r'<gro\b[^>]*\bhref\s*=\s*"([^"]+)"', re.I)
# Plansoft's HTML index: <td class="contentsColumn">groups</td><td ...>lecturers</td><td ...>rooms</td>.
GROUPS_COLUMN_RE = re.compile(r'<td\b[^>]*\bclass="[^"]*\bcontentsColumn\b[^"]*"[^>]*>(.*?)</td>', re.I | re.S)
ANCHOR_RE = re.compile(r'<a\b[^>]*\bhref\s*=\s*"([^"]+)"', re.I)


def decode(raw):
    for enc in ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


def listing_candidates(url):
    """A Plansoft index URL and its sibling export (index.xml <-> index.html), likely first."""
    m = re.search(r'/(index\.(?:xml|html?))$', url, re.I)
    if not m:
        return [url]
    other = 'index.html' if m.group(1).lower() == 'index.xml' else 'index.xml'
    return [url, url[:m.start(1)] + other]


def fetch_listing(session, url, what='index'):
    """(text, url) of a Plansoft group listing, trying the other export format when the first one is gone.

    A 404/410 on index.xml is not a wall: WIM moved its winter plans to index.html (November 2026). A block on the
    first candidate is a verdict and propagates instead of probing another URL. Gone when both exports are gone.
    """
    gone = []
    for candidate in listing_candidates(url):
        r = session.get(candidate, timeout=30)
        text = decode(r.content)
        if r.status_code in (404, 410):
            gone.append(f'{candidate.rsplit("/", 1)[-1]}: HTTP {r.status_code}')
            continue
        core.check_listing(r.status_code, text, what)
        return text, candidate
    raise core.Gone(f'{what}: {", ".join(gone) or "no listing"}, the page is gone')


def xml_hrefs(text):
    """The <gro href> list through a real XML parse, for indexes the regex cannot read."""
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(text.encode('utf-8', errors='replace'))
    except Exception:
        return []
    return [href for el in root.iter()
            if isinstance(el.tag, str) and el.tag.rsplit('}', 1)[-1].lower() == 'gro'
            for href in [el.get('href')] if href]


def html_hrefs(text):
    """The group page links of a Plansoft HTML index: the first 'Grupy' column only.

    The other columns list lecturers and rooms; their page stems (e.g. `mgr_inz_Cota_Ryszard` or `108_54`) would
    pass the group-code shape and be crawled as groups, so the column matters.
    """
    column = GROUPS_COLUMN_RE.search(text)
    return ANCHOR_RE.findall(column.group(1)) if column else []


def group_hrefs(text):
    """Group page hrefs named by a Plansoft listing, in either export format."""
    hrefs = GRO_LINK_RE.findall(text)
    if not hrefs:
        hrefs = xml_hrefs(text)
    if not hrefs:
        hrefs = html_hrefs(text)
    return hrefs


class Driver:
    def __init__(self, faculty, cfg, today):
        self.faculty, self.cfg, self.today = faculty, cfg, today
        self.base = cfg['base'].format(season=core.season_of(today)[0])
        self.prefix = cfg.get('prefix', '')

    def discover(self, session):
        text, _ = fetch_listing(session, self.base + 'index.xml', 'index.xml')
        return self.items(text)

    def items(self, text):
        """Group pages listed by a Plansoft index.xml or index.html: (code, url, page-id) items.

        `groups_re` (a config regex) keeps only matching page stems: WML's
        index also lists room/consultation pages the site is not built from.
        """
        groups_re = self.cfg.get('groups_re')
        rx = re.compile(groups_re, re.IGNORECASE) if groups_re else None
        items, seen = [], set()
        for href in group_hrefs(text):
            stem = href[:-4] if href.lower().endswith('.htm') else href
            if rx is not None and not rx.search(stem):
                continue
            code = core.group_code(stem, self.prefix, self.cfg.get('keep_prefixes', ()))
            if code and code not in seen:
                seen.add(code)
                items.append(Item(code, self.base + href, stem))
        return items

    def page_ok(self, text):
        return 'mergeWith' in text and 'Plansoft' in text

    def convert(self, item, raw):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / f'{item.page}.htm', Path(tmp) / 'out.ics'
            src.write_bytes(raw)
            wlo2ics.main([str(src), '-o', str(out), '--grupa', item.page, '--code', item.code,
                          '--faculty', self.faculty, '--period', core.period_label(self.cfg['label'], self.today)])
            return out.read_text(encoding='utf-8')
