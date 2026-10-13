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
        items, seen = [], set()
        for href in re.findall(r'<gro href="([^"]+)"', text):
            stem = href[:-4] if href.lower().endswith('.htm') else href
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
