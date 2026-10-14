"""Plansoft faculty sites (WLO, WEL, WIM): index.xml lists the group pages, each page is one static semester grid."""
import re
import tempfile
from pathlib import Path

import core
import wlo2ics
from drivers import Item

ENCODINGS = ('utf-8', 'windows-1250')


def decode(raw):
    for enc in ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode('utf-8', errors='replace')


class Driver:
    def __init__(self, faculty, cfg, today):
        self.faculty, self.cfg, self.today = faculty, cfg, today
        self.base = cfg['base'].format(season=core.season_of(today)[0])
        self.prefix = cfg.get('prefix', '')

    def discover(self, session):
        r = session.get(self.base + 'index.xml', timeout=30)
        text = decode(r.content)
        if core.is_blocked(r.status_code, text):
            raise core.Blocked(f'index.xml: HTTP {r.status_code}')
        return self.items(text)

    def items(self, text):
        """Group pages listed by an index.xml: (code, url, page-id) items.

        `groups_re` (a config regex) keeps only matching page stems: WML's
        index also lists room/consultation pages the site is not built from.
        """
        groups_re = self.cfg.get('groups_re')
        rx = re.compile(groups_re, re.IGNORECASE) if groups_re else None
        hrefs = re.findall(r'<gro href="([^"]+)"', text)
        if not hrefs:
            hrefs = self._xml_hrefs(text)  # odd quoting or spacing defeated the regex
        items, seen = [], set()
        for href in hrefs:
            stem = href[:-4] if href.lower().endswith('.htm') else href
            if rx is not None and not rx.search(stem):
                continue
            code = core.group_code(stem, self.prefix, self.cfg.get('keep_prefixes', ()))
            if code and code not in seen:
                seen.add(code)
                items.append(Item(code, self.base + href, stem))
        return items

    @staticmethod
    def _xml_hrefs(text):
        """The same <gro href> list through a real XML parse, for indexes the regex cannot read."""
        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(text.encode('utf-8', errors='replace'))
        except Exception:
            return []
        return [href for el in root.iter()
                if isinstance(el.tag, str) and el.tag.rsplit('}', 1)[-1].lower() == 'gro'
                for href in [el.get('href')] if href]

    def page_ok(self, text):
        return 'mergeWith' in text and 'Plansoft' in text

    def convert(self, item, raw):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / f'{item.page}.htm', Path(tmp) / 'out.ics'
            src.write_bytes(raw)
            wlo2ics.main([str(src), '-o', str(out), '--grupa', item.page, '--code', item.code,
                          '--faculty', self.faculty, '--period', core.period_label(self.cfg['label'], self.today)])
            return out.read_text(encoding='utf-8')
