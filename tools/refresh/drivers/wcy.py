"""WCY (planzajec.wcy.wat.edu.pl): one page per group, rendered with its lessons embedded in the HTML.

Plain HTTP works (checked 2026-10-14 from the crawling machine; the old crawler drove a browser).
"""
import re
import tempfile
from datetime import datetime, timedelta
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
        # The group list is a Drupal jump menu: <option value="...rozklad?grupa_id=WCY21IT1S0">.
        for value in re.findall(r'<option[^>]*value="[^"]*grupa_id=([^"&]+)', text):
            code = value.strip()
            if code not in seen and core.group_code(code, '') == code and code.upper().startswith('WCY'):
                seen.add(code)
                items.append(Item(code, self.cfg['page'].format(group=code), code))
        return items

    def page_ok(self, text):
        # The faculty keeps showing the previous semester's lessons until the new plan is published; such a page
        # must not be filed under the current term, so it counts as "not ready" and the old calendar stays.
        if 'rozklad_container' not in text or 'lessons hidden' not in text:
            return False
        season, year = core.season_of(self.today)
        begins = f'{year}0901' if season == 'zima' else f'{year + 1}0201'
        dates = [x['date'].replace('_', '') for x in rozklad2ics.parse_hidden_lessons(text) if x['date']]
        return bool(dates) and max(dates) >= begins

    def convert(self, item, raw):
        with tempfile.TemporaryDirectory() as tmp:
            src, out = Path(tmp) / f'{item.code}.html', Path(tmp) / 'out.ics'
            src.write_bytes(raw)
            args = [str(src), '-o', str(out), '--group', item.code]
            args += self._term_args(raw.decode('utf-8', errors='replace'))
            rozklad2ics.main(args)
            return out.read_text(encoding='utf-8')

    def _term_args(self, page):
        """Term label and dates from the calendar, not from the page: its navigation links point at whichever
        semester the faculty shows next, which is not the one the lessons belong to."""
        season, year = core.season_of(self.today)
        label = f"semestr {'zimowy' if season == 'zima' else 'letni'} {year}/{(year + 1) % 100:02d}"
        args = ['--term', label]
        dates = [x['date'].replace('_', '') for x in rozklad2ics.parse_hidden_lessons(page) if x['date']]
        if dates:
            first = datetime.strptime(min(dates), '%Y%m%d').date()
            args += ['--term-start', (first - timedelta(days=first.weekday())).strftime('%Y%m%d')]
        return args
