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

    def _term_start(self):
        """The first day of the term being refreshed, as YYYYMMDD."""
        season, year = core.season_of(self.today)
        return f'{year}0901' if season == 'zima' else f'{year + 1}0201'

    def _checked_plan(self, text):
        """(looks like a plan page, newest lesson date or '' on the page)."""
        if 'rozklad_container' not in text or 'lessons hidden' not in text:
            return False, ''
        dates = [x['date'].replace('_', '') for x in rozklad2ics.parse_hidden_lessons(text) if x['date']]
        return True, (max(dates) if dates else '')

    def page_ok(self, text):
        plan, latest = self._checked_plan(text)
        return plan and bool(latest) and latest >= self._term_start()

    def not_ready(self, text):
        """A healthy plan page without lessons of the term being refreshed yet.

        The faculty keeps the previous semester's grid (sometimes an empty one) up until the
        new plan is published. That is expected, not a failure: the old calendar stays and the
        page does not count towards the run's skip ratio (see refresh_faculty).
        """
        plan, latest = self._checked_plan(text)
        return plan and (not latest or latest < self._term_start())

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
        # only this term's lessons date it: the page may still list one of the last semester (a March class under a
        # winter plan), which would otherwise move the whole semester, and the site's week grid, back by months
        dates = [x['date'].replace('_', '') for x in rozklad2ics.parse_hidden_lessons(page) if x['date']]
        dates = [d for d in dates if d >= self._term_start() and core.term_season_of_ymd(d) == season]
        if dates:
            first = datetime.strptime(min(dates), '%Y%m%d').date()
            args += ['--term-start', (first - timedelta(days=first.weekday())).strftime('%Y%m%d')]
        return args
