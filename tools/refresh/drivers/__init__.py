"""Faculty drivers. A driver turns one faculty's website into calendars.

To add a faculty, write `drivers/<name>.py` with a `Driver` class and point a `sources.json` entry at it
(`"driver": "<name>"`). The orchestrator (refresh.py) does everything else: pacing, block handling, validation,
change detection and state. A driver must provide:

    Driver(name, cfg, today)            cfg is the faculty's sources.json entry
    .discover(session) -> [Item]        the groups to refresh (session is a curl_cffi session)
    .page_ok(text) -> bool              True for a real timetable page (not an error or interstitial)
    .convert(item, raw: bytes) -> str   the calendar text for one fetched page (UTF-8, any line endings)
"""
import importlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Item:
    code: str   # the site's group code, also the .ics file name
    url: str    # the page to fetch
    page: str   # the page's own id (file stem on the faculty site), handed to the converter


def load(name, faculty, cfg, today):
    return importlib.import_module(f'drivers.{name}').Driver(faculty, cfg, today)
