"""WTC (wtc.wat.edu.pl/Plany): index.xml lists one Plansoft PDF per group.

The index is flat (`/Plany/index.xml`) and names the semester it lists
(`<period name="WTC zima 2026/2027">`); the PDF links are relative to the same
directory. The crawler files those PDFs only when the index names the term being
refreshed, so an index from another semester never lands in the wrong folder.

The site sits behind Incapsula: the refresh session's cookie jar and browser
fingerprint do the work (plain throwaway requests loop without cookies), and
the PDFs are fetched with the index page as Referer, one at a time, on the
same polite pacing as every other faculty. Each PDF is converted with the
vendored Plansoft-grid pipeline (parse the day x block grid + legend with
pymupdf, needs `pip install pymupdf` on the crawl machine).

The calendar carries no personal data of staff: teacher names from the
legend are parse intermediates only (they steer the room/teacher split) and
never reach the output — no CONTACT line, no instructor line.
"""
import re
import tempfile
from pathlib import Path

import core
from drivers import Item, plansoft

from . import emit

PERIOD_TAG_RE = re.compile(r'<period\b[^>]*\bname\s*=\s*"([^"]*)"'
                           r'|<period\b[^>]*>([^<]*)</period>', re.I)
PERIOD_TERM_RE = re.compile(r'\b(zima|lato)\b[\s-]*(\d{2,4})', re.I)


def index_period(text):
    """The semester label the index carries: from the <period> attribute, else its element text."""
    m = PERIOD_TAG_RE.search(text)
    if not m:
        return ''
    return (m.group(1) or m.group(2) or '').strip()


def period_term(label):
    """'WTC zima 2026/2027' -> '2026-27-zima'; None when the label names no semester."""
    m = PERIOD_TERM_RE.search(label or '')
    if not m:
        return None
    year = int(m.group(2))
    if year < 100:
        year += 2000
    return f'{year}-{(year + 1) % 100:02d}-{m.group(1).lower()}'


class Driver:
    def __init__(self, faculty, cfg, today):
        self.faculty, self.cfg, self.today = faculty, cfg, today
        self.base = cfg['base'].format(season=core.season_of(today)[0])
        self.prefix = cfg.get('prefix', '')

    def discover(self, session):
        url = self.base + 'index.xml'
        r = session.get(url, timeout=30)
        text = plansoft.decode(r.content)
        if core.is_blocked(r.status_code, text):
            raise core.Blocked(f'index.xml: HTTP {r.status_code}')
        want = core.term_id(self.today)
        label = index_period(text)
        listed = period_term(label)
        if listed is not None and listed != want:
            # The faculty keeps the same index up until the coming semester's plans are ready;
            # those PDFs belong to another term and must not be filed under this one.
            print(f'[{self.faculty}] index lists {label!r}; nothing for {want} yet', flush=True)
            return []
        headers = getattr(session, 'headers', None)
        if headers is not None:
            # The PDFs are fetched with the index page as Referer, like a
            # visitor clicking through from the plan list.
            headers['Referer'] = url
        items, seen = [], set()
        for href in re.findall(r'<gro href="([^"]+)"', text):
            if not href.lower().endswith('.pdf'):
                continue
            stem = href[:-4]
            code = core.group_code(stem, self.prefix, self.cfg.get('keep_prefixes', ()))
            if code and code not in seen:
                seen.add(code)
                items.append(Item(code, self.base + href, stem))
        return items

    def page_ok(self, text):
        return text.lstrip('\ufeff').startswith('%PDF')

    def convert(self, item, raw):
        if not raw.startswith(b'%PDF'):
            raise ValueError(f'{item.code}: not a PDF (an error page?)')
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / f'{item.page}.pdf'
            src.write_bytes(raw)
            return emit.convert_pdf(item.code, str(src), self.today,
                                    core.period_label(self.cfg.get('label', 'WTC'), self.today))
