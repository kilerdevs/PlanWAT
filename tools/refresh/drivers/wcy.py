"""WCY (planzajec.wcy.wat.edu.pl): one page per group, rendered with its lessons embedded in the HTML.

Plain HTTP works (checked 2026-10-14 from the crawling machine; the old crawler drove a browser).
"""
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote, unquote

import core
import rozklad2ics
from drivers import Item


class Driver:
    def __init__(self, faculty, cfg, today):
        self.faculty, self.cfg, self.today = faculty, cfg, today

    def discover(self, session):
        r = session.get(self.cfg['index'], timeout=30)
        text = r.content.decode('utf-8', errors='replace')
        core.check_listing(r.status_code, text, 'group list')
        items, seen, foreign = [], set(), []
        # The group list is a Drupal jump menu: <option value="...rozklad?grupa_id=WCY21IT1S0">. The shared lecture and
        # exercise streams are named with a star (grupa_id=WCY26%2AFiz1a for "WCY26*Fiz1a"): the site files them as
        # WCY26_Fiz1a, a code a file and a URL can carry, and the page is asked for under the faculty's own name.
        other = self.cfg.get('foreign') or {}
        for value in re.findall(r'<option[^>]*value="[^"]*grupa_id=([^"&]+)', text):
            raw = value.strip()
            code = unquote(raw).replace('*', '_')
            if code in seen or core.group_code(code, '') != code:
                continue
            seen.add(code)
            item = Item(code, self.cfg['page'].format(group=quote(unquote(raw), safe='')), code)
            if code.upper().startswith('WCY'):
                items.append(item)
            elif other.get('prefix') and code.upper().startswith(other['prefix']):
                foreign.append(item)
        return items + self._unowned(session, foreign)

    def _unowned(self, session, foreign):
        """Another faculty's groups this menu lists (WIM's WME..B.. groups) that their own faculty does not: only this
        site has their plan. One the owner lists is the owner's, so no group gets two calendars; when the owner's
        index cannot be read, none is taken."""
        other = self.cfg.get('foreign') or {}
        if not foreign or not other.get('owner_index'):
            return []
        try:
            r = session.get(other['owner_index'].format(season=core.season_of(self.today)[0]), timeout=30)
            text = r.content.decode('cp1250', errors='replace')
            core.check_listing(r.status_code, text, 'owner index')
        except Exception:  # noqa: BLE001 (a wall, a moved page, a dead line: take none rather than guess)
            return []
        owned = {stem.upper() for stem in re.findall(r'href="([^"/]+)\.htm"', text)}
        if not owned:
            return []
        return [i for i in foreign if i.code.upper() not in owned]

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
        first, last = core.term_window(core.term_id(self.today))  # the build's own idea of "inside the term"
        dates = [d for d in dates if first <= d <= last]
        if dates:
            first = datetime.strptime(min(dates), '%Y%m%d').date()
            args += ['--term-start', (first - timedelta(days=first.weekday())).strftime('%Y%m%d')]
        return args
