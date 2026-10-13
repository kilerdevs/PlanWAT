"""WCY (planzajec.wcy.wat.edu.pl): one page per group, rendered with its lessons embedded in the HTML.

UNVERIFIED over plain HTTP: the old crawler drove a headed browser. Enable the faculty in sources.json only after
`python tools/refresh/refresh.py --faculty wcy --limit 2 --dry-run` succeeds from the machine that will run it.
"""
import re
import tempfile
from pathlib import Path

import core
import rozklad2ics
from drivers import Item


class Driver:
    def __init__(self, faculty, cfg, today):
        self.faculty, self.cfg, self.today = faculty, cfg, today

    def discover(self, session):
        r = session.get(self.cfg['index'], timeout=30)
        text = r.content.decode('utf-8', errors='replace')
        if core.is_blocked(r.status_code, text):
            raise core.Blocked(f'group list: HTTP {r.status_code}')
        items, seen = [], set()
        for value in re.findall(r'<option[^>]*value="([^"]+)"', text):
            code = value.strip()
            if code not in seen and core.group_code(code, '') == code and code.upper().startswith('WCY'):
                seen.add(code)
                items.append(Item(code, self.cfg['page'].format(group=code), code))
        return items

    def page_ok(self, text):
        return 'rozklad_container' in text and 'lessons hidden' in text

    def convert(self, item, raw):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / f'{item.code}.html', Path(tmp) / 'out.ics'
            src.write_bytes(raw)
            rozklad2ics.main([str(src), '-o', str(out), '--group', item.code])
            return out.read_text(encoding='utf-8')
