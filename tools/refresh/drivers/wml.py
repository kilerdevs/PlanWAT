"""WML (wml.wat.edu.pl/rozklady-zajec): a WordPress page embedding the current Plansoft index.xml.

The faculty republishes under revisioned directories (2025_sem_zima, 2026_sem_zima_2, ...),
so the driver resolves the live index through the landing page's <iframe> instead of a fixed
base, then crawls it like any other Plansoft faculty: WMT-coded group grids converted with
wlo2ics (lecturer aliases resolve data-driven; no staff names are emitted).
"""
import re
from urllib.parse import urljoin

import core
from drivers import plansoft


class Driver(plansoft.Driver):
    def __init__(self, faculty, cfg, today):
        self.faculty, self.cfg, self.today = faculty, cfg, today
        self.prefix = cfg.get('prefix', '')
        self.base = ''  # resolved from the landing page on discover

    def discover(self, session):
        landing = self.cfg.get('landing', 'https://wml.wat.edu.pl/rozklady-zajec/')
        r = session.get(landing, timeout=30)
        text = plansoft.decode(r.content)
        if core.is_blocked(r.status_code, text):
            raise core.Blocked(f'landing page: HTTP {r.status_code}')
        found = [src for src in re.findall(r'<iframe[^>]+src="([^"]+)"', text) if 'index.xml' in src]
        if not found:
            return []  # the faculty took the embed down: nothing to crawl, not a block
        index = urljoin(landing, found[0])
        r = session.get(index, timeout=30)
        text = plansoft.decode(r.content)
        if core.is_blocked(r.status_code, text):
            raise core.Blocked(f'index.xml: HTTP {r.status_code}')
        self.base = index.rsplit('/', 1)[0] + '/'
        return self.items(text)
