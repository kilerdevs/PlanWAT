"""WML (wml.wat.edu.pl): a WordPress site linking the Plansoft index.xml of each semester.

The faculty republishes under revisioned directories (2025_sem_zima, 2026_sem_zima_2, ...) and moves the page that
points at them (an <iframe> on /rozklady-zajec/ until October 2026, now the homepage menu's "Rozkłady zajęć" and its
archive links). So the driver reads every index.xml the landing page links or embeds and takes the one of the semester
it crawls, the newest revision of it, then crawls it like any other Plansoft faculty: WMT-coded group grids converted
with wlo2ics (lecturer aliases resolve data-driven; no staff names are emitted).
"""
import re
from urllib.parse import urljoin

import core
from drivers import plansoft


DIR_RE = re.compile(r'/(\d{4})_sem_(zima|lato)(?:_(\d+))?/index\.xml$', re.I)


class Driver(plansoft.Driver):
    def __init__(self, faculty, cfg, today):
        self.faculty, self.cfg, self.today = faculty, cfg, today
        self.prefix = cfg.get('prefix', '')
        self.base = ''  # resolved from the landing page on discover

    def discover(self, session):
        landing = self.cfg.get('landing', 'https://wml.wat.edu.pl/')
        r = session.get(landing, timeout=30)
        text = plansoft.decode(r.content)
        core.check_listing(r.status_code, text, 'landing page')
        links = list(dict.fromkeys(urljoin(landing, u) for u in
                                   re.findall(r'<(?:iframe|a)\b[^>]*?\b(?:src|href)="([^"]+/index\.xml)"', text)))
        index = self.pick(links)
        r = session.get(index, timeout=30)
        text = plansoft.decode(r.content)
        core.check_listing(r.status_code, text, 'index.xml')
        self.base = index.rsplit('/', 1)[0] + '/'
        return self.items(text)

    def pick(self, links):
        """The index.xml of the semester crawled (directory <year>_sem_<season>, the newest revision of it); the first
        linked when no directory names a semester. Gone when none is linked, or the semester has none yet."""
        if not links:
            raise core.Gone('the landing page links no index.xml (the timetable page moved?)')
        season, year = core.season_of(self.today)
        named, mine = False, []
        for pos, url in enumerate(links):
            m = DIR_RE.search(url)
            if not m:
                continue
            named = True
            if (int(m.group(1)), m.group(2).lower()) == (year, season):
                mine.append((int(m.group(3) or 1), -pos, url))
        if mine:
            return max(mine)[2]
        if named:
            raise core.Gone(f'no index.xml for {year}_sem_{season} linked yet')
        return links[0]
