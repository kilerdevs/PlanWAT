"""WTC (wtc.wat.edu.pl/Plany): index.xml lists one Plansoft PDF per group.

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
