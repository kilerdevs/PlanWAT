"""Offline tests of the timetable refresh (tools/refresh): no network, fixtures are real crawled pages."""
import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures' / 'refresh'
sys.path.insert(0, str(ROOT / 'tools' / 'refresh'))

import core  # noqa: E402
import fleet  # noqa: E402
import refresh  # noqa: E402
import runs  # noqa: E402
import wlo2ics  # noqa: E402
from drivers import Item  # noqa: E402
from drivers import plansoft  # noqa: E402
from drivers import wcy  # noqa: E402
from drivers import wml  # noqa: E402
from drivers import wtc  # noqa: E402 (stdlib-only import; pymupdf stays lazy)

TODAY = dt.date(2026, 10, 15)
INDEX = ('<?xml version="1.0"?><index><period name="zima"/>'
         '<gro href="WLO26AX1S1.htm"/><gro href="Kurs_-_Cos_10.26.htm"/></index>')
WLO_CFG = {'driver': 'plansoft', 'label': 'WLO', 'prefix': 'WLO', 'base': 'https://example.test/plan/{season}/'}
WTC_CFG = {'driver': 'wtc', 'label': 'WTC', 'prefix': 'WTC', 'base': 'https://example.test/plany/'}
WTC_INDEX = ('<?xml version="1.0"?><index><period>WTC zima 2026/2027</period>'
             '<gro href="WTC26M1.pdf"/><gro href="WTC26M2.pdf"/><gro href="Kurs_-_Cos.pdf"/></index>')
WML_CFG = {'driver': 'wml', 'label': 'WML', 'prefix': 'WML', 'keep_prefixes': ['WMT'],
           'groups_re': '^WMT', 'landing': 'https://example.test/plany/'}
WML_LANDING = ('<html><body>'
               '<iframe src="https://www.youtube.com/embed/abc"></iframe>'
               '<iframe src="https://example.test/plany/2026_sem_zima_2/index.xml"></iframe>'
               '</body></html>')
WML_INDEX = ('<?xml version="1.0"?><xml><data>'
             '<gro href="WMT26AX1S1.htm"/><gro href="K1103168.htm"/>'
             '<gro href="P1.htm"/><gro href="Studia_indywidualne.htm"/>'
             '</data></xml>')
HAS_PYMUPDF = importlib.util.find_spec('pymupdf') is not None


class Resp:
    def __init__(self, status=200, content=b'', headers=None):
        self.status_code, self.content = status, content
        self.headers = headers or {}

    @property
    def text(self):
        return self.content.decode('utf-8', errors='replace')


class FakeSession:
    """Serves canned responses by URL; anything else is a 404."""

    def __init__(self, routes):
        self.routes, self.seen = routes, []
        self.sent_headers = {}

    def get(self, url, timeout=0, headers=None):
        self.seen.append(url)
        self.sent_headers[url] = headers or {}
        return self.routes.get(url, Resp(404))


class SequenceSession(FakeSession):
    """Like FakeSession, but a URL mapped to a list serves it item by item (the last repeating).

    That models a page whose next fetch answers differently — e.g. a block page, then the real
    one through another exit of a rotating egress.
    """

    def __init__(self, routes):
        super().__init__({})
        self.queues = {url: (list(value) if isinstance(value, list) else [value])
                       for url, value in routes.items()}

    def get(self, url, timeout=0, headers=None):
        self.seen.append(url)
        self.sent_headers[url] = headers or {}
        queue = self.queues.get(url)
        if not queue:
            return Resp(404)
        return queue.pop(0) if len(queue) > 1 else queue[0]


def page(name):
    return (FIXTURES / name).read_bytes()


def wcy_page(dates):
    """A minimal WCY plan page: the hidden lesson island with `dates` (YYYY_MM_DD) + container."""
    lessons = ''.join(
        f'<div class="lesson"><span class="name">Matematyka (MAT)<br>W1</span>'
        f'<span class="date">{d}</span><span class="block_id">block1</span>'
        f'<span class="info">wykład;;s. 101</span></div>' for d in dates)
    return (f'<html><body><div class="lessons hidden">{lessons}</div>'
            f'<div class="rozklad_container"></div></body></html>')


class Detection(unittest.TestCase):
    def test_blocks(self):
        self.assertTrue(core.is_blocked(403, ''))
        self.assertTrue(core.is_blocked(200, '<iframe id="main-iframe" src="/_Incapsula_Resource?incident_id=1-2">'))
        self.assertTrue(core.is_blocked(200, 'Request unsuccessful. Incapsula incident ID: 1'))

    def test_not_modified_is_not_a_block(self):
        self.assertFalse(core.is_blocked(304, ''))

    def test_the_sensor_script_alone_is_not_a_block(self):
        self.assertFalse(core.is_blocked(200, '<script src="/_Incapsula_Resource?SWJIYLWA=1&ns=2"></script>Plansoft'))

    def test_term_and_codes(self):
        self.assertEqual(core.term_id(dt.date(2026, 10, 15)), '2026-27-zima')
        self.assertEqual(core.term_id(dt.date(2027, 1, 20)), '2026-27-zima')
        self.assertEqual(core.term_id(dt.date(2027, 4, 1)), '2026-27-lato')
        self.assertEqual(core.group_code('1PL26KP', 'WEL'), 'WEL1PL26KP')
        self.assertEqual(core.group_code('WEL23EA1S0', 'WEL'), 'WEL23EA1S0')
        self.assertEqual(core.group_code('WIG26BW1S0', 'WEL'), 'WIG26BW1S0')
        self.assertEqual(core.group_code('WME23BE1S1', 'WEL', ['WME']), 'WME23BE1S1')
        self.assertEqual(core.group_code('WMT26AX1S1', 'WML', ['WMT']), 'WMT26AX1S1')
        self.assertIsNone(core.group_code('Kurs_-_Cos_10.26', 'WLO'))

    def test_volatile_header_lines_do_not_count_as_a_change(self):
        a = 'BEGIN:VCALENDAR\r\nX-PLAN-GENERATED:20261001\r\nX\r\nEND:VCALENDAR\r\n'
        b = a.replace('20261001', '20261015')
        self.assertTrue(core.same_plan(a, b))
        self.assertFalse(core.same_plan(a, b.replace('\r\nX\r\n', '\r\nY\r\n')))
        self.assertFalse(core.same_plan(None, a))


class Conversion(unittest.TestCase):
    def convert(self, stem, code, prefix, label):
        cfg = dict(WLO_CFG, prefix=prefix, label=label)
        driver = plansoft.Driver(label.lower(), cfg, TODAY)
        return driver, driver.convert(Item(code, 'https://example.test/' + stem, stem), page(stem + '.htm'))

    def test_wlo_page_becomes_a_valid_calendar_with_its_own_code(self):
        driver, ics = self.convert('WLO26AX1S1', 'WLO26AX1S1', 'WLO', 'WLO')
        self.assertTrue(driver.page_ok(page('WLO26AX1S1.htm').decode('utf-8')))
        self.assertIn('X-PLAN-GROUP:WLO26AX1S1', ics)
        ok, why = core.validate(core.to_crlf(ics), 'WLO26AX1S1', '2026-27-zima')
        self.assertTrue(ok, why)

    def test_a_page_without_the_faculty_prefix_gets_one_consistently(self):
        _, ics = self.convert('1PL26KP', 'WEL1PL26KP', 'WEL', 'WEL')
        self.assertIn('X-PLAN-GROUP:WEL1PL26KP', ics)
        self.assertNotIn('X-PLAN-GROUP:1PL26KP', ics)
        ok, why = core.validate(core.to_crlf(ics), 'WEL1PL26KP', '2026-27-zima')
        self.assertTrue(ok, why)

    def test_validation_rejects_a_mislabelled_or_shrunken_calendar(self):
        _, ics = self.convert('1PL26KP', 'WEL1PL26KP', 'WEL', 'WEL')
        ics = core.to_crlf(ics)
        ok, why = core.validate(ics, 'WEL9PL26KP', '2026-27-zima')
        self.assertFalse(ok)
        events = ics.split('BEGIN:VEVENT')
        shrunk = 'BEGIN:VEVENT'.join(events[:2]) + 'END:VCALENDAR\r\n'
        self.assertFalse(core.validate(shrunk, 'WEL1PL26KP', '2026-27-zima', previous=ics)[0])


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        base = 'https://example.test/plan/zima/'
        self.routes = {
            base + 'index.xml': Resp(200, INDEX.encode()),
            base + 'WLO26AX1S1.htm': Resp(200, page('WLO26AX1S1.htm')),
        }

    def run_once(self, routes=None, extra=()):
        args = refresh.parse(['--out', str(self.tmp), '--force', *extra])
        state = core.State(self.tmp / core.STATE_FILE)
        session = SequenceSession(routes or self.routes)
        result = refresh.refresh_faculty('wlo', WLO_CFG, args, state, TODAY, session, sleep=lambda s: None)
        state.save()
        return result, session

    def ics(self):
        return self.tmp / 'timetables' / '2026-27-zima' / 'WLO26AX1S1.ics'

    def test_publishes_new_groups_and_skips_pages_that_are_not_group_codes(self):
        (changed, blocked, complete), session = self.run_once()
        self.assertEqual((changed, blocked, complete), (['WLO26AX1S1'], False, True))
        self.assertTrue(self.ics().is_file())
        self.assertFalse(any('Kurs' in u for u in session.seen))
        self.assertIn(b'\r\n', self.ics().read_bytes())

    def test_an_unchanged_page_changes_nothing(self):
        self.run_once()
        first = self.ics().read_bytes()
        (changed, blocked, complete), _ = self.run_once()
        self.assertEqual((changed, blocked, complete), ([], False, True))
        self.assertEqual(self.ics().read_bytes(), first)

    def touch_the_page(self):
        """The same page with one cosmetic change: a fresh digest, an identical conversion."""
        routes = dict(self.routes)
        routes['https://example.test/plan/zima/WLO26AX1S1.htm'] = Resp(
            200, page('WLO26AX1S1.htm').replace(b'<HTML>', b'<HTML data-x="1">'))
        return routes

    def test_a_filed_calendar_still_holding_last_semester_is_cleaned_not_read_as_shrunken(self):
        # What WCY's seeded files hold: last summer's lessons still filed under this term, so the
        # converted page drops far fewer events than the file holds. The file gets clipped before
        # the comparison, so publishing its cleaned-up version is not read as a huge loss.
        self.run_once()
        old = self.ics().read_text(encoding='utf-8')
        extras = ''.join(
            f'BEGIN:VEVENT\r\nUID:lato{m}-{d}@t\r\n'
            f'DTSTART;TZID=Europe/Warsaw:2026{m:02d}{d:02d}T080000\r\nSUMMARY:Fizyka\r\nEND:VEVENT\r\n'
            for m in range(1, 9) for d in range(1, 26))  # 200 lessons of the term before this one
        self.ics().write_text(old.replace('END:VCALENDAR', extras + 'END:VCALENDAR'), encoding='utf-8')
        (changed, blocked, complete), _ = self.run_once(self.touch_the_page())
        self.assertEqual((changed, blocked, complete), (['WLO26AX1S1'], False, True))
        cleaned = self.ics().read_text(encoding='utf-8')
        self.assertNotIn('lato1-1@t', cleaned)
        self.assertNotIn('20260101', cleaned)

    def test_a_filed_calendar_whose_plan_really_shrank_is_still_rejected(self):
        # The same machinery, with the extra lessons inside the term: the page dropping them is
        # real shrinkage (a half-broken page), so the guard holds and the old calendar stays.
        self.run_once()
        old = self.ics().read_text(encoding='utf-8')
        extras = ''.join(
            f'BEGIN:VEVENT\r\nUID:gora{m}-{d}-{n}@t\r\n'
            f'DTSTART;TZID=Europe/Warsaw:2026{m:02d}{d:02d}T08{n}0000\r\nSUMMARY:Fizyka\r\nEND:VEVENT\r\n'
            for m in (10, 11, 12) for d in range(1, 31) for n in range(3))
        self.ics().write_text(old.replace('END:VCALENDAR', extras + 'END:VCALENDAR'), encoding='utf-8')
        filed = self.ics().read_bytes()
        (changed, blocked, complete), _ = self.run_once(self.touch_the_page())
        self.assertEqual((changed, blocked, complete), ([], False, True))
        self.assertEqual(self.ics().read_bytes(), filed)
        state = core.State(self.tmp / core.STATE_FILE)
        self.assertEqual(state.faculties['wlo']['run']['skipped'], 1)

    def test_the_coming_semester_is_refreshed_into_its_own_term_with_its_own_state(self):
        args = refresh.parse(['--out', str(self.tmp), '--force'])
        state = core.State(self.tmp / core.STATE_FILE)
        coming = core.upcoming_reference(dt.date(2026, 8, 20))
        self.assertEqual(coming, dt.date(2026, 9, 1))
        result = refresh.refresh_faculty('wlo', WLO_CFG, args, state, coming, FakeSession(self.routes),
                                         sleep=lambda s: None, ahead=True)
        self.assertEqual(result, (['WLO26AX1S1'], False, True))
        self.assertTrue(self.ics().is_file())
        self.assertEqual(list(state.groups), ['WLO26AX1S1@2026-27-zima'])  # the running semester's entry is untouched
        self.assertNotIn('last_ok', state.faculties['wlo'])

    def test_lessons_of_another_semester_are_not_filed_under_the_term(self):
        self.run_once()
        ics = self.ics().read_text(encoding='utf-8')
        self.assertTrue(core.validate(ics, 'WLO26AX1S1', '2026-27-zima')[0])
        ok, why = core.validate(ics, 'WLO26AX1S1', '2026-27-lato')
        self.assertFalse(ok)
        self.assertIn('outside the term', why)

    def test_the_coming_semester_is_only_looked_for_before_it_starts(self):
        self.assertEqual(core.upcoming_reference(dt.date(2027, 1, 5)), dt.date(2027, 3, 1))
        for month in (3, 4, 5, 6, 7, 9, 10, 11, 12):
            self.assertIsNone(core.upcoming_reference(dt.date(2026, month, 15)))

    def test_a_block_stops_the_run_and_keeps_the_last_good_calendar(self):
        self.run_once()
        first = self.ics().read_bytes()
        blocked_page = b'<iframe id="main-iframe" src="/x?incident_id=7-8"></iframe>'
        routes = dict(self.routes)
        routes['https://example.test/plan/zima/WLO26AX1S1.htm'] = Resp(200, blocked_page)
        (changed, blocked, complete), _ = self.run_once(routes)
        self.assertEqual((changed, blocked, complete), ([], True, False))
        self.assertEqual(self.ics().read_bytes(), first)
        state = core.State(self.tmp / core.STATE_FILE)
        self.assertTrue(state.faculties['wlo']['blocked_at'])

    def test_a_forbidden_index_counts_as_blocked(self):
        routes = {'https://example.test/plan/zima/index.xml': Resp(403, b'Incapsula incident ID')}
        (changed, blocked, complete), _ = self.run_once(routes)
        self.assertEqual((changed, blocked, complete), ([], True, False))

    def test_a_flaky_index_is_retried_but_a_wall_is_not(self):
        session = FakeSession(self.routes)
        calls = []

        def get(url, timeout=0, headers=None):
            calls.append(url)
            if url.endswith('index.xml') and len([u for u in calls if u.endswith('index.xml')]) == 1:
                raise ConnectionError('reset by peer')
            return FakeSession.get(session, url, timeout=timeout, headers=headers)

        session.get = get
        args = refresh.parse(['--out', str(self.tmp), '--force'])
        state = core.State(self.tmp / core.STATE_FILE)
        changed, blocked, complete = refresh.refresh_faculty(
            'wlo', WLO_CFG, args, state, TODAY, session, sleep=lambda s: None)
        self.assertEqual((changed, blocked, complete), (['WLO26AX1S1'], False, True))
        self.assertEqual(len([u for u in calls if u.endswith('index.xml')]), 2)

    def test_robots_txt_that_disallows_the_pages_skips_the_faculty(self):
        routes = dict(self.routes)
        routes['https://example.test/robots.txt'] = Resp(200, b'User-agent: *\nDisallow: /plan/\n')
        (changed, blocked, complete), session = self.run_once(routes)
        self.assertEqual((changed, blocked, complete), ([], False, False))
        self.assertFalse(any(u.endswith('WLO26AX1S1.htm') for u in session.seen))

    def test_dry_run_writes_nothing(self):
        (changed, _, _), _ = self.run_once(extra=['--dry-run'])
        self.assertEqual(changed, ['WLO26AX1S1'])
        self.assertFalse(self.ics().exists())

    def test_a_cut_short_run_checks_the_stalest_groups_first(self):
        base = 'https://example.test/plan/zima/'
        index = ('<?xml version="1.0"?><index><period name="zima"/>'
                 '<gro href="WLO99ZZ9S9.htm"/><gro href="WLO26AX1S1.htm"/></index>')
        routes = {base + 'index.xml': Resp(200, index.encode()),
                  base + 'WLO26AX1S1.htm': Resp(200, page('WLO26AX1S1.htm'))}
        args = refresh.parse(['--out', str(self.tmp), '--force', '--limit', '1'])
        state = core.State(self.tmp / core.STATE_FILE)
        state.groups['WLO99ZZ9S9'] = {'checked': core.now_utc().isoformat()}  # seen just now
        session = FakeSession(routes)
        changed, blocked, complete = refresh.refresh_faculty(
            'wlo', WLO_CFG, args, state, TODAY, session, sleep=lambda s: None)
        self.assertEqual((changed, blocked, complete), (['WLO26AX1S1'], False, True))
        self.assertIn(base + 'WLO26AX1S1.htm', session.seen)
        self.assertNotIn(base + 'WLO99ZZ9S9.htm', session.seen)

    def test_a_resumed_run_skips_what_it_already_checked_since_the_cut(self):
        page_url = 'https://example.test/plan/zima/WLO26AX1S1.htm'
        self.run_once()  # checked just now, then cut off
        before = (core.now_utc() - dt.timedelta(hours=1)).isoformat()
        _, session = self.run_once(extra=['--resume-since', before])
        self.assertNotIn(page_url, session.seen)
        later = (core.now_utc() + dt.timedelta(hours=1)).isoformat()
        _, session = self.run_once(extra=['--resume-since', later])
        self.assertIn(page_url, session.seen)

    def test_a_resumed_run_still_reports_what_it_checked_before_the_cut(self):
        outcomes = self.tmp / 'outcomes.json'
        outcomes.with_name('outcomes.json.partial').write_text(json.dumps({
            'WLO26AX1S1@2026-27-zima': {'status': 'unchanged', 'at': '2026-10-24T14:10:00'},
            'WLO26AX2S1@2026-27-zima': {'status': 'changed', 'at': '2026-10-24T11:50:00'}}), encoding='utf-8')
        args = refresh.parse(['--out', str(self.tmp), '--outcomes', str(outcomes),
                              '--resume-since', '2026-10-24T14:00:00'])
        self.assertEqual(list(args.outcomes_log), ['WLO26AX1S1@2026-27-zima'])  # an older window's is dropped
        fresh = refresh.parse(['--out', str(self.tmp), '--outcomes', str(outcomes)])
        self.assertEqual(fresh.outcomes_log, {})

    def test_not_modified_revalidates_without_rewriting(self):
        self.run_once()
        first = self.ics().read_bytes()
        routes = dict(self.routes)
        routes['https://example.test/plan/zima/WLO26AX1S1.htm'] = Resp(304, b'')
        (changed, blocked, complete), session = self.run_once(routes)
        self.assertEqual((changed, blocked, complete), ([], False, True))
        self.assertEqual(self.ics().read_bytes(), first)

    def test_remembered_validators_are_sent_back(self):
        routes = dict(self.routes)
        routes['https://example.test/plan/zima/WLO26AX1S1.htm'] = Resp(
            200, page('WLO26AX1S1.htm'), {'Last-Modified': 'Tue, 13 Oct 2026 13:11:56 GMT'})
        _, session = self.run_once(routes)
        state = core.State(self.tmp / core.STATE_FILE)
        self.assertEqual(state.groups['WLO26AX1S1'].get('modified'), 'Tue, 13 Oct 2026 13:11:56 GMT')
        routes['https://example.test/plan/zima/WLO26AX1S1.htm'] = Resp(304, b'')
        _, session = self.run_once(routes)
        # The last fetch of the page carried the remembered validator.
        self.assertEqual(
            session.sent_headers['https://example.test/plan/zima/WLO26AX1S1.htm'],
            {'If-Modified-Since': 'Tue, 13 Oct 2026 13:11:56 GMT'})

    BLOCK_PAGE = b'<iframe id="main-iframe" src="/x?incident_id=1-2"></iframe>'

    def block_routes(self):
        routes = dict(self.routes)
        routes['https://example.test/plan/zima/WLO26AX1S1.htm'] = [
            Resp(200, self.BLOCK_PAGE), Resp(200, page('WLO26AX1S1.htm'))]
        return routes

    def test_a_block_page_is_retried_on_a_fresh_connection(self):
        # One flagged exit in the rotating pool must not read as a wall: the retry (a fresh
        # connection, hence another exit) gets the real page and the run finishes clean.
        (changed, blocked, complete), session = self.run_once(self.block_routes())
        self.assertEqual((changed, blocked, complete), (['WLO26AX1S1'], False, True))
        page_url = 'https://example.test/plan/zima/WLO26AX1S1.htm'
        self.assertEqual(len([u for u in session.seen if u == page_url]), 2)

    def test_a_block_that_survives_every_retry_is_still_a_wall(self):
        routes = dict(self.routes)
        routes['https://example.test/plan/zima/WLO26AX1S1.htm'] = Resp(200, self.BLOCK_PAGE)
        (changed, blocked, complete), session = self.run_once(routes)
        self.assertEqual((changed, blocked, complete), ([], True, False))
        page_url = 'https://example.test/plan/zima/WLO26AX1S1.htm'
        self.assertEqual(len([u for u in session.seen if u == page_url]), 3)  # 1 + 2 retries
        state = core.State(self.tmp / core.STATE_FILE)
        self.assertEqual(state.faculties['wlo']['run']['cause'], 'wall')

    def test_block_retries_can_be_switched_off(self):
        routes = dict(self.routes)
        routes['https://example.test/plan/zima/WLO26AX1S1.htm'] = Resp(200, self.BLOCK_PAGE)
        (_, blocked, _), session = self.run_once(routes, extra=['--block-retries', '0'])
        self.assertTrue(blocked)
        page_url = 'https://example.test/plan/zima/WLO26AX1S1.htm'
        self.assertEqual(len([u for u in session.seen if u == page_url]), 1)

    def test_a_blocked_index_is_retried_on_a_fresh_connection(self):
        routes = dict(self.routes)
        routes['https://example.test/plan/zima/index.xml'] = [
            Resp(403, b'Incapsula incident ID'), Resp(200, INDEX.encode())]
        (changed, blocked, complete), session = self.run_once(routes)
        self.assertEqual((changed, blocked, complete), (['WLO26AX1S1'], False, True))
        self.assertEqual(len([u for u in session.seen if u.endswith('index.xml')]), 2)

    def test_exhausted_transients_are_reported_and_retried_on_a_fresh_connection(self):
        # A 429/5xx wall that outlasts --retries is a block response like any other: the exit
        # that carried it is reported and the page rides a fresh connection (--block-retries).
        reported = []
        orig = refresh.post_block_report
        refresh.post_block_report = lambda host, url=None, timeout=5: reported.append(host)
        self.addCleanup(setattr, refresh, 'post_block_report', orig)
        page_url = 'https://example.test/plan/zima/WLO26AX1S1.htm'
        routes = dict(self.routes)
        routes[page_url] = [Resp(429, b'')] * 4 + [Resp(200, page('WLO26AX1S1.htm'))]
        (changed, blocked, complete), session = self.run_once(routes)
        self.assertEqual((changed, blocked, complete), (['WLO26AX1S1'], False, True))
        self.assertEqual(reported, ['example.test'])
        routes[page_url] = Resp(429, b'')
        reported.clear()
        (changed, blocked, complete), session = self.run_once(routes, extra=['--retries', '0'])
        self.assertEqual((changed, blocked, complete), ([], True, False))
        self.assertEqual(len([u for u in session.seen if u == page_url]), 3)  # 1 + 2 retries
        self.assertEqual(reported, ['example.test'] * 3)

    def test_a_block_response_is_reported_so_the_egress_demotes_the_exit(self):
        reported = []
        orig = refresh.post_block_report
        refresh.post_block_report = lambda host, url=None, timeout=5: reported.append(host)
        self.addCleanup(setattr, refresh, 'post_block_report', orig)
        self.run_once(self.block_routes())
        self.assertEqual(reported, ['example.test'])


class TitlesTest(unittest.TestCase):
    def test_title_words_cover_academic_and_military_ranks(self):
        # Regression guard: a staff-name scrub once emptied this set, which
        # silently broke person detection. The calendar never emits names,
        # but the parser needs the titles to tell staff from subjects.
        for title in ('dr', 'hab', 'prof', 'mgr', 'inż', 'gen', 'mjr',
                      'por', 'kpt', 'ppłk', 'płk', 'mł'):
            self.assertIn(title, wlo2ics.TITLE_WORDS)

    def test_person_detection_ignores_brackets_and_dots(self):
        self.assertTrue(wlo2ics.looks_like_person('dr hab. inż. Kowalski Jan'))
        self.assertTrue(wlo2ics.looks_like_person('mł. Kowalski Jan'))
        self.assertFalse(wlo2ics.looks_like_person('Język obcy (II) międzywydziałowy'))
        self.assertFalse(wlo2ics.looks_like_person('Etyka zawodowa'))


class ClipTest(unittest.TestCase):
    def cal(self, *days):
        events = []
        for day in days:
            events += ['BEGIN:VEVENT', f'UID:{day}@t', f'DTSTART;TZID=Europe/Warsaw:{day}T080000', 'SUMMARY:Fizyka', 'END:VEVENT']
        return '\r\n'.join(['BEGIN:VCALENDAR', 'VERSION:2.0'] + events + ['END:VCALENDAR', ''])

    def test_a_page_with_two_semesters_keeps_only_the_one_being_filed(self):
        ics = self.cal('20260410', '20260622', '20260921', '20261005')
        out = core.clip_to_term(ics, '2026-27-zima')
        self.assertEqual(out.count('BEGIN:VEVENT'), 2)
        self.assertNotIn('20260410', out)
        self.assertIn('20260921', out)
        self.assertEqual(core.clip_to_term(self.cal('20260921'), '2026-27-zima'), self.cal('20260921'))
        # the summer term takes the spring lessons, and drops the autumn ones
        self.assertEqual(core.clip_to_term(self.cal('20270310', '20261005'), '2026-27-lato').count('BEGIN:VEVENT'), 1)


class PublicRoomTest(unittest.TestCase):
    def test_a_person_in_the_room_text_is_dropped_and_the_room_kept(self):
        self.assertEqual(wlo2ics.public_room('dr inż. Kowalski Jan, 255 S'), '255 S')
        self.assertEqual(wlo2ics.public_room('dr inż. Kowalski Jan, dr inż. Nowak Adam, 1.17/16'), '1.17/16')
        self.assertEqual(wlo2ics.public_room('mgr inż. Kowalski Jan;mgr inż. Nowak Adam, 3/ 23A;5/ 23A'), '3/ 23A;5/ 23A')
        self.assertEqual(wlo2ics.public_room('dr hab. inż.(prof. ucz.) Kowalski Jan, aula/135'), 'aula/135')

    def test_a_lecturer_alias_left_in_the_room_is_dropped(self):
        self.assertEqual(wlo2ics.public_room('ANazwisko'), '')
        self.assertEqual(wlo2ics.public_room('ANazwisko;314 S'), '314 S')
        self.assertEqual(wlo2ics.public_room('�Nazwisko'), '')
        self.assertEqual(wlo2ics.public_room('ANazwisko-Drugie'), '')

    def test_words_and_codes_that_are_not_aliases_stay(self):
        for room in ('Teams', 'Wyjazd', 'WAT', 'AWF', 'ST.nr 1(PWC2)', 'Bibl.'):
            self.assertEqual(wlo2ics.public_room(room), room)

    def test_a_person_alone_leaves_no_location(self):
        self.assertEqual(wlo2ics.public_room('dr hab. Kowalski Jan'), '')

    def test_ordinary_rooms_are_untouched(self):
        for room in ('314 S', '1.9/ 16;1.10/ 16', 'aula/ 135', '7a-b Bibl.', '', None):
            self.assertEqual(wlo2ics.public_room(room), room)


class WtcLegend(unittest.TestCase):
    def test_a_teacher_on_the_subjects_own_line_is_not_part_of_its_name(self):
        from drivers.wtc import legend2
        self.assertEqual(legend2.split_name_teachers(['Podstawy toksykologii plk dr Wachna Piotr'])[:2],
                         ('Podstawy toksykologii', [['Wachna', 'Piotr']]))
        self.assertEqual(legend2.split_name_teachers(['Inżynieria chemiczna', 'dr inż. Nowak Jan'])[:2],
                         ('Inżynieria chemiczna', [['Nowak', 'Jan']]))
        self.assertEqual(legend2.split_name_teachers(['Matematyka st. 2 Analiza'])[0], 'Matematyka st. 2 Analiza')


class WtcDiscovery(unittest.TestCase):
    def discover(self, body, headers=None):
        driver = wtc.Driver('wtc', WTC_CFG, TODAY)
        session = FakeSession({'https://example.test/plany/index.xml': Resp(200, body)})
        if headers is not None:
            session.headers = headers
        return driver, session, driver.discover(session)

    def test_lists_the_pdf_groups(self):
        _, _, items = self.discover(WTC_INDEX.encode())
        self.assertEqual([i.code for i in items], ['WTC26M1', 'WTC26M2'])
        self.assertEqual(items[0].url, 'https://example.test/plany/WTC26M1.pdf')
        self.assertEqual(items[0].page, 'WTC26M1')

    def test_the_period_attribute_form_is_read_too(self):
        index = ('<xml><period name="WTC zima 2026/2027"></period>'
                 '<gro href="WTC26M1.pdf"/></xml>')
        _, _, items = self.discover(index.encode())
        self.assertEqual([i.code for i in items], ['WTC26M1'])

    def test_an_index_of_another_term_lists_nothing(self):
        # The faculty keeps the same index up until the coming semester is ready; its PDFs
        # belong to the running one and must not be filed under the coming term.
        index = ('<xml><period name="WTC lato 2026/2027"></period>'
                 '<gro href="WTC26M1.pdf"/></xml>')
        _, session, items = self.discover(index.encode())
        self.assertEqual(items, [])
        self.assertEqual(session.seen, ['https://example.test/plany/index.xml'])

    def test_an_index_without_a_readable_period_still_lists(self):
        index = '<xml><period name=""></period><gro href="WTC26M1.pdf"/></xml>'
        _, _, items = self.discover(index.encode())
        self.assertEqual([i.code for i in items], ['WTC26M1'])

    def test_a_blocked_index_raises(self):
        driver = wtc.Driver('wtc', WTC_CFG, TODAY)
        session = FakeSession({'https://example.test/plany/index.xml': Resp(403, b'')})
        with self.assertRaises(core.Blocked):
            driver.discover(session)

    def test_pdfs_are_fetched_with_the_index_as_referer(self):
        headers = {}
        _, _, _ = self.discover(WTC_INDEX.encode(), headers)
        self.assertEqual(headers.get('Referer'), 'https://example.test/plany/index.xml')

    def test_page_ok_accepts_only_pdfs(self):
        driver = wtc.Driver('wtc', WTC_CFG, TODAY)
        self.assertTrue(driver.page_ok('%PDF-1.7\n%\xe2\xe3\xcf\xd3\n'))
        self.assertFalse(driver.page_ok('<html><body>Request unsuccessful. Incapsula</body></html>'))

    def test_non_pdf_bytes_are_rejected_before_conversion(self):
        driver = wtc.Driver('wtc', WTC_CFG, TODAY)
        with self.assertRaises(ValueError):
            driver.convert(Item('WTC26M1', 'https://example.test/WTC26M1.pdf', 'WTC26M1'), b'<html></html>')


class WtcPeriod(unittest.TestCase):
    def test_period_labels_are_read_from_both_xml_shapes(self):
        self.assertEqual(wtc.index_period('<period name="WTC zima 2026/2027"></period>'),
                         'WTC zima 2026/2027')
        self.assertEqual(wtc.index_period('<period>WTC lato 2026/2027</period>'), 'WTC lato 2026/2027')
        self.assertEqual(wtc.index_period('<xml></xml>'), '')

    def test_period_labels_name_their_term(self):
        self.assertEqual(wtc.period_term('WTC zima 2026/2027'), '2026-27-zima')
        self.assertEqual(wtc.period_term('WTC lato 2027/2028'), '2027-28-lato')
        self.assertEqual(wtc.period_term('WTC zima 26/27'), '2026-27-zima')
        self.assertEqual(wtc.period_term('WTC zima 26-27'), '2026-27-zima')
        self.assertIsNone(wtc.period_term('WTC semestr zimowy'))
        self.assertIsNone(wtc.period_term(''))


class WcyReadiness(unittest.TestCase):
    """The WCY driver tells 'healthy page, other semester' apart from 'something is wrong'."""

    def driver(self):
        cfg = {'driver': 'wcy', 'label': 'WCY',
               'index': 'https://example.test/pl/rozklad',
               'page': 'https://example.test/pl/rozklad?grupa_id={group}'}
        return wcy.Driver('wcy', cfg, TODAY)

    def test_a_page_of_this_semester_is_ok(self):
        d = self.driver()
        text = wcy_page(['2026_10_05'])
        self.assertTrue(d.page_ok(text))
        self.assertFalse(d.not_ready(text))

    def test_last_semesters_grid_is_not_ready_not_a_failure(self):
        d = self.driver()
        text = wcy_page(['2026_03_23'])
        self.assertFalse(d.page_ok(text))
        self.assertTrue(d.not_ready(text))

    def test_an_empty_plan_is_not_ready(self):
        d = self.driver()
        text = wcy_page([])
        self.assertFalse(d.page_ok(text))
        self.assertTrue(d.not_ready(text))

    def test_a_page_without_the_plan_structure_is_neither(self):
        d = self.driver()
        text = '<html><body>maintenance in progress</body></html>'
        self.assertFalse(d.page_ok(text))
        self.assertFalse(d.not_ready(text))

    def test_a_lesson_left_over_from_last_semester_does_not_date_this_one(self):
        # one March class under a winter plan used to start the semester on 2 March and end it in July
        d = self.driver()
        args = d._term_args(wcy_page(['2026_03_23', '2026_10_01', '2026_10_05']))
        self.assertEqual(args[args.index('--term-start') + 1], '20260928')  # Monday of the first winter class
        self.assertNotIn('--term-start', d._term_args(wcy_page(['2026_03_23'])))

    def test_a_summer_semester_starting_in_february_keeps_its_february_lessons(self):
        cfg = {'driver': 'wcy', 'label': 'WCY', 'index': 'https://example.test/pl/rozklad',
               'page': 'https://example.test/pl/rozklad?grupa_id={group}'}
        d = wcy.Driver("wcy", cfg, dt.date(2027, 3, 10))
        args = d._term_args(wcy_page(['2026_10_05', '2027_02_23', '2027_03_02']))
        self.assertEqual(args[args.index('--term-start') + 1], '20270222')


@unittest.skipUnless(HAS_PYMUPDF, 'pymupdf not installed')
class WtcConversion(unittest.TestCase):
    def test_a_crawled_pdf_becomes_a_valid_calendar_without_staff_names(self):
        driver = wtc.Driver('wtc', WTC_CFG, TODAY)
        ics = driver.convert(Item('WTC26M1', 'https://example.test/plany/WTC26M1.pdf', 'WTC26M1'),
                             page('WTC26M1.pdf'))
        self.assertIn('X-PLAN-GROUP:WTC26M1', ics)
        self.assertIn('X-PLAN-SOURCE:wtc-plansoft', ics)
        self.assertEqual(ics.count('BEGIN:VEVENT'), 34)
        self.assertNotIn('CONTACT', ics)
        self.assertNotIn('prowadz', ics.lower())
        ok, why = core.validate(core.to_crlf(ics), 'WTC26M1', '2026-27-zima')
        self.assertTrue(ok, why)

    def test_full_faculty_run_publishes_a_name_free_calendar(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        base = 'https://example.test/plany/'
        routes = {
            base + 'index.xml': Resp(200, WTC_INDEX.encode()),
            base + 'WTC26M1.pdf': Resp(200, page('WTC26M1.pdf')),
            base + 'WTC26M2.pdf': Resp(404, b'not yet'),
        }
        args = refresh.parse(['--out', str(tmp), '--force'])
        state = core.State(tmp / core.STATE_FILE)
        session = FakeSession(routes)
        changed, blocked, complete = refresh.refresh_faculty(
            'wtc', WTC_CFG, args, state, TODAY, session, sleep=lambda s: None)
        self.assertEqual((changed, blocked, complete), (['WTC26M1'], False, True))
        ics = tmp / 'timetables' / '2026-27-zima' / 'WTC26M1.ics'
        self.assertTrue(ics.is_file())
        raw = ics.read_bytes()
        self.assertIn(b'\r\n', raw)
        self.assertNotIn(b'CONTACT', raw)
        self.assertNotIn(b'Prowadz', raw)


class WmlDiscovery(unittest.TestCase):
    LANDING = 'https://example.test/plany/'
    INDEX = 'https://example.test/plany/2026_sem_zima_2/index.xml'

    def discover(self, landing_body, index_body=None):
        routes = {self.LANDING: Resp(200, landing_body)}
        if index_body is not None:
            routes[self.INDEX] = Resp(200, index_body)
        driver = wml.Driver('wml', WML_CFG, TODAY)
        return driver, driver.discover(FakeSession(routes))

    def test_lists_the_wmt_groups_through_the_landing_iframe(self):
        _, items = self.discover(WML_LANDING.encode(), WML_INDEX.encode())
        self.assertEqual([i.code for i in items], ['WMT26AX1S1'])
        self.assertEqual(items[0].url,
                         'https://example.test/plany/2026_sem_zima_2/WMT26AX1S1.htm')
        self.assertEqual(items[0].page, 'WMT26AX1S1')

    def test_a_page_without_the_embed_is_not_a_block(self):
        _, items = self.discover(b'<html><body>no timetables here</body></html>')
        self.assertEqual(items, [])

    def test_a_blocked_landing_page_raises(self):
        driver = wml.Driver('wml', WML_CFG, TODAY)
        session = FakeSession({self.LANDING: Resp(403, b'')})
        with self.assertRaises(core.Blocked):
            driver.discover(session)

    def test_a_blocked_index_raises(self):
        driver = wml.Driver('wml', WML_CFG, TODAY)
        session = FakeSession({self.LANDING: Resp(200, WML_LANDING.encode()),
                               self.INDEX: Resp(403, b'')})
        with self.assertRaises(core.Blocked):
            driver.discover(session)


class WmlConversion(unittest.TestCase):
    def convert(self):
        driver = wml.Driver('wml', WML_CFG, TODAY)
        return driver.convert(Item('WMT26AX1S1', 'https://example.test/WMT26AX1S1.htm', 'WMT26AX1S1'),
                              page('WMT26AX1S1.htm'))

    def test_a_crawled_page_becomes_a_valid_calendar_without_staff_names(self):
        ics = self.convert()
        self.assertIn('X-PLAN-GROUP:WMT26AX1S1', ics)
        self.assertIn('X-PLAN-SOURCE:wml-plansoft', ics)
        self.assertIn('SUMMARY:Matematyka 1', ics)
        self.assertEqual(ics.count('BEGIN:VEVENT'), 145)
        self.assertNotIn('CONTACT', ics)
        self.assertNotIn('prowadzący:', ics.lower())
        self.assertNotIn('Nazwisko', ics)
        ok, why = core.validate(core.to_crlf(ics), 'WMT26AX1S1', '2026-27-zima')
        self.assertTrue(ok, why)

    def test_full_faculty_run_publishes_a_name_free_calendar(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        base = 'https://example.test/plany/2026_sem_zima_2/'
        routes = {
            WML_CFG['landing']: Resp(200, WML_LANDING.encode()),
            base + 'index.xml': Resp(200, WML_INDEX.encode()),
            base + 'WMT26AX1S1.htm': Resp(200, page('WMT26AX1S1.htm')),
        }
        args = refresh.parse(['--out', str(tmp), '--force'])
        state = core.State(tmp / core.STATE_FILE)
        changed, blocked, complete = refresh.refresh_faculty(
            'wml', WML_CFG, args, state, TODAY, FakeSession(routes), sleep=lambda s: None)
        self.assertEqual((changed, blocked, complete), (['WMT26AX1S1'], False, True))
        raw = (tmp / 'timetables' / '2026-27-zima' / 'WMT26AX1S1.ics').read_bytes()
        self.assertIn(b'\r\n', raw)
        self.assertNotIn(b'CONTACT', raw)
        self.assertNotIn('prowadzący:'.encode(), raw.lower())

    def test_short_cells_keep_rooms_and_subjects(self):
        # WMT22AC1S0 mixes 4-seg [lecturer, room, SUBJECT, type] cells with
        # 3-seg [room-or-lecturer, SUBJECT, type] and 2-seg [SUBJECT, type].
        driver = wml.Driver('wml', WML_CFG, TODAY)
        ics = driver.convert(Item('WMT22AC1S0', 'https://example.test/WMT22AC1S0.htm', 'WMT22AC1S0'),
                             page('WMT22AC1S0.htm'))
        self.assertIn('X-PLAN-GROUP:WMT22AC1S0', ics)
        self.assertEqual(ics.count('BEGIN:VEVENT'), 103)
        self.assertIn('LOCATION:132 K', ics)
        self.assertIn('Szkolenie strzeleckie', ics)
        self.assertNotIn('CONTACT', ics)
        self.assertNotIn('prowadzący:', ics.lower())
        ok, why = core.validate(core.to_crlf(ics), 'WMT22AC1S0', '2026-27-zima')
        self.assertTrue(ok, why)


class PlansoftFiltering(unittest.TestCase):
    WEL_INDEX = ('<?xml version="1.0"?><xml><data>'
                 '<gro href="1PL26KP.htm"/><gro href="WEL26EX1S0.htm"/>'
                 '<gro href="IOE23HX1S0.htm"/><gro href="WME23BE1S1.htm"/>'
                 '<gro href="WIG26BW1S0.htm"/></data></xml>')

    def test_wel_keeps_its_own_groups_but_not_ioe_or_wme(self):
        # The IOE/WME pages listed by WEL belong to the IOE institute and
        # the WIM faculty: crawling them here would publish every such
        # group twice under two codes.
        cfg = dict(WLO_CFG, prefix='WEL', label='WEL', keep_prefixes=['WME'],
                   groups_re='^(?!IOE|WME)')
        items = plansoft.Driver('wel', cfg, TODAY).items(self.WEL_INDEX)
        self.assertEqual([i.code for i in items],
                         ['WEL1PL26KP', 'WEL26EX1S0', 'WIG26BW1S0'])

    def test_ioe_keeps_only_ioe_groups(self):
        cfg = dict(WLO_CFG, prefix='', label='IOE',
                   base='https://example.test/plany/lato/',
                   groups_re='^IOE')
        driver = plansoft.Driver('ioe', cfg, TODAY)
        self.assertEqual(driver.base, 'https://example.test/plany/lato/')
        items = driver.items(self.WEL_INDEX)
        self.assertEqual([i.code for i in items], ['IOE23HX1S0'])


class IoeConversion(unittest.TestCase):
    def convert(self):
        cfg = dict(WLO_CFG, prefix='', label='IOE',
                   base='https://example.test/plany/lato/',
                   groups_re='^IOE')
        driver = plansoft.Driver('ioe', cfg, TODAY)
        return driver.convert(Item('IOE26HX1S0', 'https://example.test/IOE26HX1S0.htm', 'IOE26HX1S0'),
                              page('IOE26HX1S0.htm'))

    def test_a_transposed_page_becomes_a_valid_calendar_without_staff_names(self):
        ics = self.convert()
        self.assertIn('X-PLAN-GROUP:IOE26HX1S0', ics)
        self.assertIn('X-PLAN-SOURCE:ioe-plansoft', ics)
        self.assertIn('PRODID:-//PlanWAT//IOE//PL', ics)
        self.assertEqual(ics.count('BEGIN:VEVENT'), 210)
        self.assertIn('SUMMARY:Matematyka 1', ics)
        self.assertIn('LOCATION:315a S', ics)
        self.assertNotIn('CONTACT', ics)
        self.assertNotIn('prowadzący:', ics.lower())
        self.assertNotIn('Pta.S', ics)
        self.assertNotIn('Bi.Ka', ics)
        ok, why = core.validate(core.to_crlf(ics), 'IOE26HX1S0', '2026-27-zima')
        self.assertTrue(ok, why)


class BlockModelTest(unittest.TestCase):
    def model(self):
        return core.BlockModel({})

    def seed(self, model, name, durations, causes=None):
        model.data[core.group_of(name)] = {
            'durations': [{'dur': d, 'cause': (causes[i] if causes else None),
                           'at_iso': '2026-10-14T12:00:00'} for i, d in enumerate(durations)],
            'blocked_at': None, 'cause': None}

    def test_no_history_means_the_default(self):
        self.assertEqual(self.model().estimate('wlo'), core.BLOCK_DEFAULT)

    def test_estimate_is_the_clamped_median(self):
        model = self.model()
        self.seed(model, 'wlo', [3600, 7200, 10800])
        self.assertEqual(model.estimate('wlo'), 7200)
        self.seed(model, 'wlo', [60])
        self.assertEqual(model.estimate('wlo'), core.BLOCK_MIN)
        self.seed(model, 'wlo', [100000])
        self.assertEqual(model.estimate('wlo'), core.BLOCK_MAX)

    def test_wall_durations_win_over_flaky_ones(self):
        model = self.model()
        self.seed(model, 'wlo', [300, 400, 20000], ['flaky', 'flaky', 'wall'])
        self.assertEqual(model.estimate('wlo'), 20000)  # the lone wall, not the flaky median
        self.seed(model, 'wlo', [300, 400], ['flaky', None])  # no walls: every episode counts
        self.assertEqual(model.estimate('wlo'), core.BLOCK_MIN)  # median 350, clamped

    def test_old_number_only_entries_still_count(self):
        model = self.model()
        model.data[core.group_of('wlo')] = {'durations': [3600, 7200, 10800], 'blocked_at': None}
        self.assertEqual(model.estimate('wlo'), 7200)

    def test_a_recovery_teaches_the_duration_with_its_cause(self):
        model = self.model()
        t0 = dt.datetime(2026, 10, 14, 12, 0, 0)
        model.note_blocked('wlo', cause='wall', at=t0)
        duration = model.note_recovered('wlo', t0 + dt.timedelta(hours=3))
        self.assertEqual(duration, 3 * 3600)
        self.assertEqual(model.estimate('wlo'), 3 * 3600)
        entry = model.data[core.group_of('wlo')]
        self.assertIsNone(entry['blocked_at'])
        self.assertEqual(entry['durations'], [{'dur': 3 * 3600, 'cause': 'wall',
                                               'at_iso': (t0 + dt.timedelta(hours=3)).isoformat()}])

    def test_recovery_without_a_block_teaches_nothing(self):
        model = self.model()
        self.assertIsNone(model.note_recovered('wlo'))
        self.assertEqual(model.estimate('wlo'), core.BLOCK_DEFAULT)

    def test_history_is_capped(self):
        model = self.model()
        t0 = dt.datetime(2026, 10, 14, 12, 0, 0)
        for i in range(core.BLOCK_KEEP + 3):
            model.note_blocked('wlo', at=t0)
            model.note_recovered('wlo', t0 + dt.timedelta(seconds=1000 + i))
        self.assertEqual(len(model.data[core.group_of('wlo')]['durations']), core.BLOCK_KEEP)

    def test_wlo_and_wel_share_one_policy_group(self):
        model = self.model()
        t0 = dt.datetime(2026, 10, 14, 12, 0, 0)
        model.note_blocked('wlo', cause='wall', at=t0)
        model.note_recovered('wlo', t0 + dt.timedelta(hours=3))
        self.assertEqual(model.estimate('wel'), 3 * 3600)  # learned through wlo
        self.assertEqual(list(model.data), ['wat-edge'])  # one entry, not one per faculty
        model.note_blocked('wim', cause='wall', at=t0)
        model.note_recovered('wim', t0 + dt.timedelta(hours=5))
        self.assertEqual(model.estimate('wim'), 5 * 3600)  # uninvolved faculties stay solo
        self.assertEqual(model.estimate('wlo'), 3 * 3600)


class FakeClock:
    def __init__(self):
        self.now, self.sleeps = 0.0, []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class WaitForRecovery(unittest.TestCase):
    def test_recovers_on_the_third_probe_with_quadratic_gaps(self):
        model = core.BlockModel({})
        answers = iter([False, False, True])
        clock = FakeClock()
        recovered, waited, probes = refresh.wait_for_recovery(
            'wlo', lambda: next(answers), model, budget=10 ** 6, max_probes=5,
            sleep=clock.sleep, clock=clock)
        self.assertTrue(recovered)
        self.assertEqual(probes, 3)
        # Default estimate 7200 s: probes land at 288, 1152, 2592.
        self.assertEqual(len(clock.sleeps), 3)
        for got, want in zip(clock.sleeps, (288.0, 864.0, 1440.0)):
            self.assertAlmostEqual(got, want)
        self.assertAlmostEqual(waited, 2592.0)
        # Never noted blocked: nothing learned (keyed by policy group).
        self.assertEqual(len(model.data[core.group_of('wlo')]['durations']), 0)

    def test_learns_the_duration_when_the_episode_was_recorded(self):
        model = core.BlockModel({})
        model.note_blocked('wlo', cause='wall', at=core.now_utc())
        clock = FakeClock()
        recovered, waited, probes = refresh.wait_for_recovery(
            'wlo', lambda: True, model, budget=10 ** 6, max_probes=5,
            sleep=clock.sleep, clock=clock)
        self.assertTrue(recovered)
        self.assertEqual(probes, 1)
        entry = model.data[core.group_of('wlo')]
        self.assertEqual(len(entry['durations']), 1)
        self.assertEqual(entry['durations'][0]['cause'], 'wall')

    def test_a_small_budget_spreads_every_probe_inside_it(self):
        model = core.BlockModel({})
        clock = FakeClock()
        recovered, waited, probes = refresh.wait_for_recovery(
            'wlo', lambda: False, model, budget=1000, max_probes=5,
            sleep=clock.sleep, clock=clock)
        self.assertFalse(recovered)
        self.assertLessEqual(waited, 1000)
        # Horizon min(7200, 1000) = 1000: probes land at 40, 160, 360, 640, 1000.
        self.assertEqual(probes, 5)
        for got, want in zip(clock.sleeps, (40.0, 120.0, 200.0, 280.0, 360.0)):
            self.assertAlmostEqual(got, want)
        self.assertAlmostEqual(waited, 1000.0)
        self.assertEqual(model.estimate('wlo'), core.BLOCK_DEFAULT)  # no recovery, nothing learned

    def test_a_small_estimate_is_the_horizon(self):
        model = core.BlockModel({})
        model.data[core.group_of('wlo')] = {
            'durations': [{'dur': 1200, 'cause': 'wall', 'at_iso': '2026-10-14T12:00:00'}],
            'blocked_at': None, 'cause': None}
        self.assertEqual(model.estimate('wlo'), 1200)
        clock = FakeClock()
        recovered, waited, probes = refresh.wait_for_recovery(
            'wlo', lambda: False, model, budget=10 ** 6, max_probes=5,
            sleep=clock.sleep, clock=clock)
        self.assertFalse(recovered)
        self.assertEqual(probes, 5)
        self.assertAlmostEqual(clock.sleeps[0], 48.0)  # 1200 * (1/5)^2
        self.assertAlmostEqual(waited, 1200.0)

    def test_zero_budget_probes_nothing(self):
        model = core.BlockModel({})
        clock = FakeClock()
        recovered, waited, probes = refresh.wait_for_recovery(
            'wlo', lambda: True, model, budget=0, max_probes=5,
            sleep=clock.sleep, clock=clock)
        self.assertEqual((recovered, waited, probes), (False, 0, 0))
        self.assertEqual(clock.sleeps, [])


class ScriptedSession(FakeSession):
    """Replays a script of responses/exceptions per fetch, then 404s."""

    def __init__(self, script):
        super().__init__({})
        self.script = list(script)

    def get(self, url, timeout=0, headers=None):
        self.seen.append(url)
        self.sent_headers[url] = headers or {}
        item = self.script.pop(0) if self.script else Resp(404)
        if isinstance(item, Exception):
            raise item
        return item


class RetryTaxonomy(unittest.TestCase):
    URL = 'https://example.test/plan/zima/WLO26AX1S1.htm'

    def get(self, script, retries=3):
        session, sleeps = ScriptedSession(script), []
        try:
            result = refresh.get_with_retry(session, self.URL, timeout=1, headers={},
                                            retries=retries, sleep=sleeps.append)
        except Exception as err:  # noqa: BLE001 (the taxonomy is the point)
            return err, session, sleeps
        return result, session, sleeps

    def test_transient_statuses_are_retried_then_raise_blocked(self):
        for status in (408, 425, 429, 500, 502, 503, 504):
            err, session, sleeps = self.get([Resp(status, b'x')] * 4)
            self.assertIsInstance(err, core.Blocked, status)
            self.assertEqual(len(session.seen), 4)
            self.assertEqual(len(sleeps), 3)

    def test_a_recovered_transient_returns_the_page(self):
        result, session, _ = self.get([Resp(503, b'x'), Resp(200, page('WLO26AX1S1.htm'))], retries=1)
        self.assertIsInstance(result, Resp)
        self.assertEqual(len(session.seen), 2)

    def test_an_empty_200_is_transient(self):
        result, session, _ = self.get([Resp(200, b''), Resp(200, b'page')], retries=1)
        self.assertEqual(result.content, b'page')
        self.assertEqual(len(session.seen), 2)

    def test_verdict_statuses_return_at_once(self):
        for status in (403, 404):
            result, session, sleeps = self.get([Resp(status, b'no')], retries=3)
            self.assertIsInstance(result, Resp)
            self.assertEqual(result.status_code, status)
            self.assertEqual(len(session.seen), 1)  # never retried
            self.assertEqual(sleeps, [])

    def test_a_block_page_returns_as_a_verdict(self):
        body = b'<iframe id="main-iframe" src="/_Incapsula_Resource?incident_id=1-2"></iframe>'
        result, session, sleeps = self.get([Resp(200, body)], retries=3)
        self.assertIsInstance(result, Resp)
        self.assertEqual(len(session.seen), 1)
        self.assertEqual(sleeps, [])

    def test_transport_flakiness_raises_the_transport_error(self):
        err, session, sleeps = self.get([TimeoutError('boom')] * 4)
        self.assertIsInstance(err, TimeoutError)
        self.assertNotIsInstance(err, core.Blocked)
        self.assertEqual(len(sleeps), 3)
        result, _, _ = self.get([TimeoutError('boom'), Resp(200, b'page')], retries=1)
        self.assertEqual(result.content, b'page')


class DiscoverRetry(unittest.TestCase):
    """discover_with_retry: transport flakiness first, then single flagged exits of the pool."""

    class Driver:
        def __init__(self, outcomes):
            self.outcomes, self.calls = list(outcomes), 0

        def discover(self, session):
            self.calls += 1
            out = self.outcomes.pop(0) if self.outcomes else []
            if isinstance(out, Exception):
                raise out
            return out

    def retry(self, driver, retries=0, block_retries=0, on_block=None):
        return refresh.discover_with_retry(driver, None, retries=retries, backoff=0.0,
                                           sleep=lambda s: None,
                                           block_retries=block_retries, on_block=on_block)

    def test_a_blocked_discover_is_retried_and_reports_the_flagged_exit(self):
        driver = DiscoverRetry.Driver([core.Blocked('403'), ['a']])
        reported = []
        items = self.retry(driver, block_retries=1, on_block=lambda: reported.append(1))
        self.assertEqual(items, ['a'])
        self.assertEqual((driver.calls, reported), (2, [1]))

    def test_a_sustained_block_raises_and_reports_each_flagged_exit(self):
        driver = DiscoverRetry.Driver([core.Blocked('403')] * 3)
        reported = []
        with self.assertRaises(core.Blocked):
            self.retry(driver, block_retries=2, on_block=lambda: reported.append(1))
        self.assertEqual((driver.calls, len(reported)), (3, 2))

    def test_without_block_retries_a_block_raises_at_once(self):
        driver = DiscoverRetry.Driver([core.Blocked('403')])
        with self.assertRaises(core.Blocked):
            self.retry(driver, retries=2)
        self.assertEqual(driver.calls, 1)

    def test_transport_flakiness_keeps_its_own_budget(self):
        driver = DiscoverRetry.Driver([TimeoutError('x'), ['a']])
        self.assertEqual(self.retry(driver, retries=1, block_retries=5), ['a'])
        self.assertEqual(driver.calls, 2)

    def test_a_transport_error_during_the_block_retries_is_raised(self):
        driver = DiscoverRetry.Driver([core.Blocked('403'), TimeoutError('boom')])
        with self.assertRaises(TimeoutError):
            self.retry(driver, block_retries=1)


class ExhaustionCause(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.base = 'https://example.test/plan/zima/'

    def faculty(self, session):
        args = refresh.parse(['--out', str(self.tmp), '--force'])
        state = core.State(self.tmp / core.STATE_FILE)
        result = refresh.refresh_faculty('wlo', WLO_CFG, args, state, TODAY, session,
                                         sleep=lambda s: None)
        return result, state

    def test_http_transients_exhaust_as_a_wall(self):
        # robots.txt, then 4 tries per attempt (--retries 3) on each of 1 + 2 fresh connections
        # (--block-retries 2).
        session = ScriptedSession([Resp(200, INDEX.encode())] + [Resp(503, b'x')] * 13)
        (changed, blocked, complete), state = self.faculty(session)
        self.assertEqual(session.script, [])
        self.assertEqual((changed, blocked, complete), ([], True, False))
        run = state.faculties['wlo']['run']
        self.assertEqual(run['cause'], 'wall')
        self.assertTrue(run['blocked'])

    def test_transport_flakiness_exhausts_as_flaky(self):
        class Flaky(FakeSession):
            def get(self, url, timeout=0, headers=None):
                self.seen.append(url)
                if url.endswith('.htm'):
                    raise TimeoutError('boom')
                return super().get(url, timeout=timeout, headers=headers)

        routes = {self.base + 'index.xml': Resp(200, INDEX.encode())}
        (changed, blocked, complete), state = self.faculty(Flaky(routes))
        self.assertEqual((changed, blocked, complete), ([], True, False))
        self.assertEqual(state.faculties['wlo']['run']['cause'], 'flaky')


class NotReadyTest(unittest.TestCase):
    """Pages of another semester are expected during publication season, not a failure."""

    class Driver:
        def __init__(self, faculty, cfg, today):
            self.faculty = faculty

        def discover(self, session):
            return [Item(f'WCY26A{i}1S1', f'https://example.test/wcy{i}.htm', f'WCY26A{i}1S1')
                    for i in range(6)]

        def page_ok(self, text):
            return text.startswith('ready')

        def not_ready(self, text):
            return text.startswith('old')

        def convert(self, item, raw):
            raise ValueError('never called')

    def test_not_ready_pages_count_as_such_and_do_not_degrade_the_run(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        routes = {f'https://example.test/wcy{i}.htm': Resp(200, b'old semester grid')
                  for i in range(6)}
        args = refresh.parse(['--out', str(tmp), '--force'])
        state = core.State(tmp / core.STATE_FILE)
        orig_load = refresh.drivers.load
        refresh.drivers.load = lambda name, faculty, cfg, today: NotReadyTest.Driver(faculty, cfg, today)
        self.addCleanup(setattr, refresh.drivers, 'load', orig_load)
        result = refresh.refresh_faculty('wcy', {'driver': 'stub', 'label': 'WCY'}, args, state,
                                         TODAY, FakeSession(routes), sleep=lambda s: None)
        self.assertEqual(result, ([], False, True))
        run = state.faculties['wcy']['run']
        self.assertEqual(run['not_ready'], 6)
        self.assertEqual(run['skipped'], 0)
        self.assertFalse(run['degraded'])


class BlockReports(unittest.TestCase):
    def test_faculty_host_reads_the_config_urls(self):
        self.assertEqual(refresh.faculty_host({'base': 'https://wlo.wat.edu.pl/planzajec/{season}/'}),
                         'wlo.wat.edu.pl')
        self.assertEqual(refresh.faculty_host(
            {'page': 'https://planzajec.wcy.wat.edu.pl/pl/rozklad?grupa_id={group}'}),
            'planzajec.wcy.wat.edu.pl')
        self.assertEqual(refresh.faculty_host({}), '')

    def test_a_block_report_without_a_sink_is_a_no_op(self):
        orig = os.environ.pop('PLANWAT_EGRESS_BLOCK', None)
        if orig is not None:
            self.addCleanup(os.environ.__setitem__, 'PLANWAT_EGRESS_BLOCK', orig)
        refresh.post_block_report('example.test')  # nothing configured: must not raise
        refresh.post_block_report('', url='http://127.0.0.1:9/block')  # nothing to report

    def test_a_block_report_to_a_dead_sink_is_swallowed(self):
        refresh.post_block_report('example.test', url='http://127.0.0.1:9/block', timeout=1)


class Defaults(unittest.TestCase):
    def test_the_crawl_is_aggressive_by_default(self):
        args = refresh.parse(['--out', '/tmp/nowhere'])
        self.assertEqual(args.fresh_hours, 1.0)
        self.assertEqual(args.lanes, 6)
        self.assertEqual(args.block_retries, 2)

    def test_the_selfhosted_profile_paces_without_going_slow(self):
        args = refresh.parse(['--out', '/tmp/nowhere', '--profile', 'selfhosted'])
        self.assertEqual(args.delay, (1.5, 4.0))


class FreshTest(unittest.TestCase):
    def test_recent_means_fresh(self):
        state = core.State('/nonexistent/refresh-state.json')
        state.groups['A'] = {'checked': core.now_utc().isoformat(), 'term': '2026-27-zima'}
        self.assertTrue(state.fresh('A', core.now_utc(), 20, '2026-27-zima'))

    def test_a_future_stamp_is_not_fresh(self):
        state = core.State('/nonexistent/refresh-state.json')
        state.groups['A'] = {'checked': (core.now_utc() + dt.timedelta(hours=1)).isoformat(),
                             'term': '2026-27-zima'}
        self.assertFalse(state.fresh('A', core.now_utc(), 20, '2026-27-zima'))

    def test_another_term_is_not_fresh(self):
        state = core.State('/nonexistent/refresh-state.json')
        state.groups['A'] = {'checked': core.now_utc().isoformat(), 'term': '2026-27-lato'}
        self.assertFalse(state.fresh('A', core.now_utc(), 20, '2026-27-zima'))

    def test_a_term_less_entry_rechecks_once(self):
        state = core.State('/nonexistent/refresh-state.json')
        state.groups['A'] = {'checked': core.now_utc().isoformat()}  # written before terms
        self.assertFalse(state.fresh('A', core.now_utc(), 20, '2026-27-zima'))
        self.assertTrue(state.fresh('A', core.now_utc(), 20))  # without a term, age still rules


class CadenceTest(unittest.TestCase):
    def test_publication_windows_refresh_twice_as_often(self):
        for month in (1, 2, 8):
            self.assertEqual(core.effective_fresh_hours(20, dt.date(2026, month, 15)), 10)
        for month in (3, 4, 5, 6, 7, 9, 10, 11, 12):
            self.assertEqual(core.effective_fresh_hours(20, dt.date(2026, month, 15)), 20)


class RobotsCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.base = 'https://example.test/plan/zima/'

    def test_a_cached_disallow_needs_no_network(self):
        args = refresh.parse(['--out', str(self.tmp), '--force'])
        state = core.State(self.tmp / core.STATE_FILE)
        state.data['robots'] = {'example.test': {
            'fetched_iso': core.now_utc().isoformat(),
            'text': 'User-agent: *\nDisallow: /plan/\n'}}
        session = FakeSession({self.base + 'index.xml': Resp(200, INDEX.encode())})
        result = refresh.refresh_faculty('wlo', WLO_CFG, args, state, TODAY, session,
                                         sleep=lambda s: None)
        self.assertEqual(result, ([], False, False))
        self.assertNotIn('https://example.test/robots.txt', session.seen)
        self.assertFalse(any(u.endswith('.htm') for u in session.seen))

    def test_a_fresh_fetch_is_stored(self):
        args = refresh.parse(['--out', str(self.tmp), '--force'])
        state = core.State(self.tmp / core.STATE_FILE)
        routes = {self.base + 'index.xml': Resp(200, INDEX.encode()),
                  self.base + 'WLO26AX1S1.htm': Resp(200, page('WLO26AX1S1.htm')),
                  'https://example.test/robots.txt': Resp(200, b'User-agent: *\nDisallow:\n')}
        result = refresh.refresh_faculty('wlo', WLO_CFG, args, state, TODAY, FakeSession(routes),
                                         sleep=lambda s: None)
        self.assertEqual(result[0], ['WLO26AX1S1'])
        self.assertIn('example.test', state.data['robots'])

    def test_a_stale_entry_refetches(self):
        args = refresh.parse(['--out', str(self.tmp), '--force'])
        state = core.State(self.tmp / core.STATE_FILE)
        state.data['robots'] = {'example.test': {
            'fetched_iso': (core.now_utc() - dt.timedelta(hours=25)).isoformat(),
            'text': 'User-agent: *\nDisallow: /plan/\n'}}
        routes = {self.base + 'index.xml': Resp(200, INDEX.encode()),
                  self.base + 'WLO26AX1S1.htm': Resp(200, page('WLO26AX1S1.htm')),
                  'https://example.test/robots.txt': Resp(200, b'User-agent: *\nDisallow:\n')}
        session = FakeSession(routes)
        result = refresh.refresh_faculty('wlo', WLO_CFG, args, state, TODAY, session,
                                         sleep=lambda s: None)
        self.assertEqual(result[0], ['WLO26AX1S1'])
        self.assertIn('https://example.test/robots.txt', session.seen)


class DegradedTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.base = 'https://example.test/plan/zima/'

    def faculty(self, routes, last_count=None):
        args = refresh.parse(['--out', str(self.tmp), '--force'])
        state = core.State(self.tmp / core.STATE_FILE)
        if last_count is not None:
            state.faculties['wlo'] = {'last_count': last_count}
        session = FakeSession(routes)
        result = refresh.refresh_faculty('wlo', WLO_CFG, args, state, TODAY, session,
                                         sleep=lambda s: None)
        return result, state

    def six_group_routes(self, page_body):
        index = ('<?xml version="1.0"?><index><period name="zima"/>'
                 + ''.join(f'<gro href="WLO26A{i}1S1.htm"/>' for i in range(6)) + '</index>')
        return {self.base + 'index.xml': Resp(200, index.encode()),
                **{self.base + f'WLO26A{i}1S1.htm': Resp(200, page_body) for i in range(6)}}

    def test_many_skips_flag_the_run_degraded(self):
        (changed, blocked, complete), state = self.faculty(
            self.six_group_routes(b'<html><body>not a timetable page</body></html>'))
        self.assertEqual((blocked, complete), (False, True))
        run = state.faculties['wlo']['run']
        self.assertTrue(run['degraded'])
        self.assertEqual(run['skipped'], 6)

    def test_a_few_skips_stay_clean(self):
        # Five groups simply not yet published (404: attempted but not skipped) and one
        # unreadable page: 1/6 skips is below the threshold.
        index = ('<?xml version="1.0"?><index><period name="zima"/>'
                 + ''.join(f'<gro href="WLO26A{i}1S1.htm"/>' for i in range(6)) + '</index>')
        routes = {self.base + 'index.xml': Resp(200, index.encode()),
                  self.base + 'WLO26A51S1.htm': Resp(200, b'<html><body>not a timetable page</body></html>')}
        (changed, blocked, complete), state = self.faculty(routes)
        self.assertEqual((blocked, complete), (False, True))
        run = state.faculties['wlo']['run']
        self.assertEqual((run['checked'], run['skipped']), (6, 1))
        self.assertFalse(run['degraded'])

    def test_a_shrunken_listing_flags_the_run_degraded(self):
        index = ('<?xml version="1.0"?><index><period name="zima"/>'
                 '<gro href="WLO26AX1S1.htm"/></index>')
        routes = {self.base + 'index.xml': Resp(200, index.encode()),
                  self.base + 'WLO26AX1S1.htm': Resp(200, page('WLO26AX1S1.htm'))}
        (changed, blocked, complete), state = self.faculty(routes, last_count=20)
        self.assertEqual((blocked, complete), (False, True))
        self.assertTrue(state.faculties['wlo']['run']['degraded'])
        self.assertEqual(state.faculties['wlo']['last_count'], 1)

    def test_a_listing_failure_is_reported_fresh(self):
        # A transient listing error (say, the egress proxy was restarting) must not resend the
        # previous run's stats and degraded flag as this run's verdict: the faculty gets its
        # own entry, with this run's timestamp and the cause named.
        def boom(*a, **k):
            raise ConnectionError('proxy CONNECT aborted')
        original = refresh.discover_with_retry
        refresh.discover_with_retry = boom
        self.addCleanup(setattr, refresh, 'discover_with_retry', original)
        (changed, blocked, complete), state = self.faculty({})
        self.assertEqual((changed, blocked, complete), ([], False, False))
        run = state.faculties['wlo']['run']
        self.assertEqual((run['cause'], run['blocked'], run['degraded']), ('listing', False, True))
        self.assertEqual((run['checked'], run['changed']), (0, 0))

    def test_a_stable_listing_stays_clean(self):
        index = ('<?xml version="1.0"?><index><period name="zima"/>'
                 '<gro href="WLO26AX1S1.htm"/></index>')
        routes = {self.base + 'index.xml': Resp(200, index.encode()),
                  self.base + 'WLO26AX1S1.htm': Resp(200, page('WLO26AX1S1.htm'))}
        (_, _, _), state = self.faculty(routes, last_count=2)
        self.assertFalse(state.faculties['wlo']['run']['degraded'])


class PacingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.base = 'https://example.test/plan/zima/'

    def faculty(self, routes, pacing=None):
        args = refresh.parse(['--out', str(self.tmp), '--force'])
        state = core.State(self.tmp / core.STATE_FILE)
        if pacing is not None:
            state.data['pacing'] = pacing
        session = FakeSession(routes)
        result = refresh.refresh_faculty('wlo', WLO_CFG, args, state, TODAY, session,
                                         sleep=lambda s: None)
        return result, state

    def test_a_block_raises_the_group_multiplier(self):
        routes = {self.base + 'index.xml': Resp(403, b'Incapsula incident ID')}
        (_, _, _), state = self.faculty(routes)
        self.assertEqual(state.data['pacing']['wat-edge'], 1.5)

    def test_a_clean_faculty_decays_the_multiplier(self):
        routes = {self.base + 'index.xml': Resp(200, INDEX.encode()),
                  self.base + 'WLO26AX1S1.htm': Resp(200, page('WLO26AX1S1.htm'))}
        (_, _, _), state = self.faculty(routes, pacing={'wat-edge': 2.0})
        self.assertAlmostEqual(state.data['pacing']['wat-edge'], 1.8)

    def test_a_clean_faculty_never_drops_below_one(self):
        routes = {self.base + 'index.xml': Resp(200, INDEX.encode()),
                  self.base + 'WLO26AX1S1.htm': Resp(200, page('WLO26AX1S1.htm'))}
        (_, _, _), state = self.faculty(routes)
        self.assertEqual(state.data['pacing']['wat-edge'], 1.0)

    def test_the_pause_scales_with_the_multiplier(self):
        index = ('<?xml version="1.0"?><index><period name="zima"/>'
                 '<gro href="WLO26AX1S1.htm"/><gro href="WLO26BX1S1.htm"/></index>')
        routes = {self.base + 'index.xml': Resp(200, index.encode()),
                  self.base + 'WLO26AX1S1.htm': Resp(200, page('WLO26AX1S1.htm')),
                  self.base + 'WLO26BX1S1.htm': Resp(404, b'gone')}
        args = refresh.parse(['--out', str(self.tmp), '--force'])
        state = core.State(self.tmp / core.STATE_FILE)
        state.data['pacing'] = {'wat-edge': 2.0}
        calls = []
        real_uniform = refresh.random.uniform
        refresh.random.uniform = lambda a, b: calls.append((a, b)) or real_uniform(a, b)
        try:
            refresh.refresh_faculty('wlo', WLO_CFG, args, state, TODAY, FakeSession(routes),
                                    sleep=lambda s: None)
        finally:
            refresh.random.uniform = real_uniform
        self.assertEqual(len(calls), 1)
        lo, hi = calls[0]
        self.assertEqual((lo, hi), (args.delay[0] * 2.0, args.delay[1] * 2.0))


class CorruptStateTest(unittest.TestCase):
    def test_a_corrupt_state_is_quarantined_and_starts_fresh(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        path = tmp / core.STATE_FILE
        path.write_text('{not json', encoding='utf-8')
        state = core.State(path)
        self.assertEqual(state.data, {'version': 1, 'groups': {}, 'faculties': {}})
        backups = list(tmp.glob(core.STATE_FILE + '.corrupt-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding='utf-8'), '{not json')

    def test_valid_json_of_the_wrong_shape_is_quarantined_too(self):
        for text in ('[]', 'null', '"state"', '1', '{"version": 1, "groups": []}',
                     '{"version": 1, "groups": {}, "faculties": null}'):
            with self.subTest(text=text):
                tmp = Path(tempfile.mkdtemp())
                self.addCleanup(shutil.rmtree, tmp)
                path = tmp / core.STATE_FILE
                path.write_text(text, encoding='utf-8')
                state = core.State(path)
                self.assertEqual(state.data, {'version': 1, 'groups': {}, 'faculties': {}})
                backups = list(tmp.glob(core.STATE_FILE + '.corrupt-*'))
                self.assertEqual([b.read_text(encoding='utf-8') for b in backups], [text])

    def test_a_good_state_without_faculties_still_loads(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        path = tmp / core.STATE_FILE
        path.write_text('{"version": 1, "groups": {"A": {"checked": "x"}}}', encoding='utf-8')
        state = core.State(path)
        self.assertEqual(state.groups, {'A': {'checked': 'x'}})
        self.assertEqual(state.faculties, {})
        self.assertEqual(list(tmp.glob(core.STATE_FILE + '.corrupt-*')), [])


class StubDriver:
    """Scripted stand-in for faculty drivers in main() tests: one group per faculty
    (or `counts[faculty]`), Blocked `fails[faculty]['main'|'ahead']` times first."""

    calls = []   # (faculty, date, session id) per discover
    fails = {}   # faculty -> {'main': n, 'ahead': n}
    dirty = set()  # faculties whose discover mutates session.headers, like WTC
    counts = {}  # faculty -> groups listed

    def __init__(self, faculty, cfg, today):
        self.faculty, self.today = faculty, today

    def discover(self, session):
        StubDriver.calls.append((self.faculty, self.today, id(session)))
        if isinstance(getattr(session, 'headers', None), dict) and self.faculty in StubDriver.dirty:
            session.headers['Referer'] = 'https://example.test/index.xml'
        kind = 'ahead' if (self.today.day == 1 and self.today.month in (3, 9)) else 'main'
        left = StubDriver.fails.get(self.faculty, {})
        if left.get(kind, 0) > 0:
            left[kind] -= 1
            raise core.Blocked(f'{self.faculty} {kind} wall')
        return [Item(f'{self.faculty.upper()}26A{i}1S1',
                     f'https://example.test/{self.faculty.upper()}26A{i}1S1.htm',
                     f'{self.faculty.upper()}26A{i}1S1')
                for i in range(StubDriver.counts.get(self.faculty, 1))]

    def page_ok(self, text):
        return True

    def convert(self, item, raw):
        raise ValueError('stub: nothing converts')


class MainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        StubDriver.calls, StubDriver.fails = [], {}
        StubDriver.dirty, StubDriver.counts = set(), {}
        orig_load = refresh.drivers.load
        refresh.drivers.load = lambda name, faculty, cfg, today: StubDriver(faculty, cfg, today)
        self.addCleanup(setattr, refresh.drivers, 'load', orig_load)
        self.sessions = []
        orig_new_session = refresh.new_session

        def fresh():
            session = FakeSession({})
            session.headers = {}
            self.sessions.append(session)
            return session

        refresh.new_session = fresh
        self.addCleanup(setattr, refresh, 'new_session', orig_new_session)
        self.orig_egress = os.environ.get('PLANWAT_EGRESS_STATUS')
        os.environ['PLANWAT_EGRESS_STATUS'] = ''  # the test has no egress box to report to
        self.addCleanup(self._restore_egress)
        orig_wait = refresh.wait_for_recovery
        self.wait_calls = []

        def counting(name, probe, model, budget, *rest):
            self.wait_calls.append((name, budget))
            return orig_wait(name, probe, model, budget, *rest)

        refresh.wait_for_recovery = counting
        self.addCleanup(setattr, refresh, 'wait_for_recovery', orig_wait)

    def _restore_egress(self):
        if self.orig_egress is None:
            os.environ.pop('PLANWAT_EGRESS_STATUS', None)
        else:
            os.environ['PLANWAT_EGRESS_STATUS'] = self.orig_egress

    def main(self, argv, session, today):
        clock = FakeClock()
        return refresh.main(argv, session=session, today=today, sleep=clock.sleep, clock=clock)

    def test_shared_policy_group_waits_once_then_resumes_both(self):
        # The wall must outlast the discover block-retries (--block-retries 2 -> 3 attempts):
        # a single Blocked verdict is retried on a fresh connection, not taken for a wall.
        StubDriver.fails = {'wlo': {'main': 3}, 'wel': {'main': 3}}
        StubDriver.dirty = {'wlo'}
        session = FakeSession({})
        session.headers = {}
        code = self.main(['--out', str(self.tmp), '--force', '--faculty', 'wlo,wel'],
                         session, dt.date(2026, 10, 15))
        # A clean resume clears the earlier incomplete marks: everything was covered
        # after the recovery, and nobody is left blocked.
        self.assertEqual(code, 0)
        self.assertEqual([name for name, _ in self.wait_calls], ['wat-edge'])
        state = core.State(self.tmp / core.STATE_FILE)
        for name in ('wlo', 'wel'):
            self.assertTrue(state.faculties[name]['wait']['recovered'])
            self.assertIsNone(state.faculties[name]['blocked_at'])
        self.assertEqual(session.headers, {})  # the Referer mutation did not leak
        wlo_sessions = {sid for fac, day, sid in StubDriver.calls if fac == 'wlo'}
        wel_sessions = {sid for fac, day, sid in StubDriver.calls if fac == 'wel'}
        # wlo: main pass, group probe, resume — each on its own session; wel: main pass, resume.
        self.assertEqual(len(wlo_sessions), 3)
        self.assertEqual(len(wel_sessions), 2)
        self.assertEqual(len(self.sessions), 3)  # probe + two fresh resume sessions

    def test_recovery_reruns_only_the_ahead_pass_when_main_finished(self):
        StubDriver.fails = {'wlo': {'ahead': 3}}  # outlast the discover block-retries (3 attempts)
        session = FakeSession({})
        session.headers = {}
        today, coming = dt.date(2026, 8, 20), dt.date(2026, 9, 1)
        code = self.main(['--out', str(self.tmp), '--force', '--faculty', 'wlo'],
                         session, today)
        self.assertEqual(code, 0)  # the main pass was clean; only the ahead pass needed a resume
        dates = [day for fac, day, _ in StubDriver.calls if fac == 'wlo']
        self.assertEqual(dates.count(today), 2)  # the clean main pass + the group probe
        self.assertEqual(dates.count(coming), 4)  # the blocked ahead pass (3 tries) + its resume only
        state = core.State(self.tmp / core.STATE_FILE)
        self.assertTrue(state.faculties['wlo']['wait']['recovered'])
        self.assertTrue(state.faculties['wlo']['run']['ahead'])

    def test_wait_budgets_split_the_remaining_run_budget(self):
        StubDriver.fails = {'wlo': {'main': 99}, 'wim': {'main': 99}, 'ioe': {'main': 99}}
        session = FakeSession({})
        session.headers = {}
        code = self.main(['--out', str(self.tmp), '--force', '--faculty', 'wlo,wim,ioe',
                          '--max-block-wait-minutes', '90'], session, dt.date(2026, 10, 15))
        self.assertEqual(code, 3)  # nothing recovered; still blocked
        self.assertEqual([name for name, _ in self.wait_calls], ['wat-edge', 'wim', 'ioe'])
        self.assertEqual([round(budget, 6) for _, budget in self.wait_calls], [1800.0, 1800.0, 1800.0])

    def test_the_faculties_left_blocked_are_exported_for_the_handoff(self):
        StubDriver.fails = {'wim': {'main': 99}}
        session = FakeSession({})
        session.headers = {}
        out = self.tmp / 'github-output'
        with unittest.mock.patch.dict(os.environ, {'GITHUB_OUTPUT': str(out)}):
            code = self.main(['--out', str(self.tmp), '--force', '--faculty', 'wim,ioe', '--max-block-wait-minutes', '5'],
                             session, dt.date(2026, 10, 15))
        self.assertEqual(code, 3)
        self.assertEqual([round(budget) for _, budget in self.wait_calls], [300])  # the short wait it was given
        exported = dict(line.split('=', 1) for line in out.read_text(encoding='utf-8').splitlines())
        self.assertEqual(exported['blocked_faculties'], 'wim')  # ioe went through: only wim is another runner's
        self.assertEqual(exported['incomplete_faculties'], 'wim')

    def test_policy_groups_become_lanes_in_the_order_asked(self):
        self.assertEqual(refresh.plan_lanes(['wim', 'wel', 'ioe', 'wlo', 'wml']),
                         [['wim'], ['wel', 'wlo'], ['ioe'], ['wml']])

    def test_independent_policy_groups_crawl_side_by_side_on_their_own_sessions(self):
        code = refresh.main(['--out', str(self.tmp), '--force', '--faculty', 'wlo,wel,wim,ioe',
                             '--lanes', '3'], today=dt.date(2026, 10, 15), sleep=lambda s: None)
        self.assertEqual(code, 0)
        # wat-edge (wlo+wel), wim and ioe: one session per lane, none shared across lanes
        self.assertEqual(len(self.sessions), 3)
        by_fac = {}
        for fac, day, sid in StubDriver.calls:
            by_fac.setdefault(fac, set()).add(sid)
        self.assertEqual(by_fac['wlo'], by_fac['wel'])  # the shared wall shares a session
        self.assertEqual(len({frozenset(v) for v in by_fac.values()}), 3)

    def test_a_state_save_survives_another_lane_mutating_it(self):
        state = core.State(self.tmp / core.STATE_FILE)
        import threading
        stop = threading.Event()

        def churn():
            # inserts and deletes keep the dict small but its size changing: what trips a concurrent dump
            i = 0
            while not stop.is_set():
                state.groups[f'G{i % 300}'] = {'checked': 'x'}
                state.groups.pop(f'G{(i + 150) % 300}', None)
                i += 1
        t = threading.Thread(target=churn)
        t.start()
        try:
            for _ in range(10):
                state.save()
        finally:
            stop.set()
            t.join()
        self.assertTrue(core.State(self.tmp / core.STATE_FILE).groups)

    def test_degraded_forces_incomplete_and_exports(self):
        StubDriver.counts = {'wlo': 6}
        pages = {f'https://example.test/WLO26A{i}1S1.htm': Resp(200, b'junk') for i in range(6)}
        session = FakeSession(pages)
        session.headers = {}
        out = self.tmp / 'github-output'
        orig = os.environ.get('GITHUB_OUTPUT')
        os.environ['GITHUB_OUTPUT'] = str(out)
        self.addCleanup(lambda: os.environ.pop('GITHUB_OUTPUT', None)
                        if orig is None else os.environ.__setitem__('GITHUB_OUTPUT', orig))
        code = self.main(['--out', str(self.tmp), '--force', '--faculty', 'wlo'],
                         session, dt.date(2026, 10, 15))
        self.assertEqual(code, 4)
        exported = out.read_text(encoding='utf-8')
        self.assertIn('degraded=true', exported)
        self.assertIn('incomplete=true', exported)


class PlansoftXmlFallbackTest(unittest.TestCase):
    def test_single_quoted_attrs_fall_back_to_xml(self):
        index = "<?xml version=\"1.0\"?><index><gro href='WLO26AX1S1.htm'/></index>"
        items = plansoft.Driver('wlo', WLO_CFG, TODAY).items(index)
        self.assertEqual([i.code for i in items], ['WLO26AX1S1'])
        self.assertEqual(items[0].url, WLO_CFG['base'].format(season='zima') + 'WLO26AX1S1.htm')

    def test_garbage_still_lists_nothing(self):
        self.assertEqual(plansoft.Driver('wlo', WLO_CFG, TODAY).items('not xml at all'), [])


class ReconcileBounds(unittest.TestCase):
    OLD = ('BEGIN:VCALENDAR\r\nX-PLAN-SEMESTER-START:20260928\r\n'
           'X-PLAN-SEMESTER-END:20270222\r\nEND:VCALENDAR\r\n')
    NEW_FLIPPED = ('BEGIN:VCALENDAR\r\nX-PLAN-SEMESTER-START:20260302\r\n'
                   'X-PLAN-SEMESTER-END:20260727\r\nEND:VCALENDAR\r\n')

    def test_flipped_label_restored_from_filed_term(self):
        ics, patched = core.reconcile_term_bounds(self.NEW_FLIPPED, self.OLD, '2026-27-zima')
        self.assertTrue(patched)
        self.assertIn('X-PLAN-SEMESTER-START:20260928', ics)
        self.assertIn('X-PLAN-SEMESTER-END:20270222', ics)

    def test_matching_label_untouched(self):
        ics, patched = core.reconcile_term_bounds(self.OLD, self.OLD, '2026-27-zima')
        self.assertEqual((ics, patched), (self.OLD, False))

    def test_no_old_file_keeps_new(self):
        ics, patched = core.reconcile_term_bounds(self.NEW_FLIPPED, None, '2026-27-zima')
        self.assertEqual((ics, patched), (self.NEW_FLIPPED, False))

    def test_old_flipped_too_keeps_new(self):
        ics, patched = core.reconcile_term_bounds(self.NEW_FLIPPED, self.NEW_FLIPPED, '2026-27-zima')
        self.assertEqual((ics, patched), (self.NEW_FLIPPED, False))


class ProgressTest(unittest.TestCase):
    """The crawler's live progress stream: opt-in, throttled per slot, never fatal."""

    def test_silent_without_a_url_keeps_tests_and_cli_runs_offline(self):
        p = refresh.Progress(url='', run='r1')
        calls = []
        p.post = calls.append
        self.assertFalse(p.send('run_start', lanes=[]))
        self.assertFalse(p.tick('wlo', 1, 10))
        self.assertEqual(calls, [])

    def test_events_carry_the_run_and_ticks_are_throttled_per_slot(self):
        now = [100.0]
        posts = []
        p = refresh.Progress(url='http://egress:8080/api/progress', run='r1',
                             post=posts.append, clock=lambda: now[0])
        self.assertTrue(p.send('run_start', lanes=[{'lane': 'wlo', 'faculties': ['wlo']}]))
        self.assertTrue(p.tick('wlo', 1, 10))
        self.assertFalse(p.tick('wlo', 2, 10))  # inside the window: dropped, not queued
        self.assertTrue(p.tick('wel', 1, 4))  # every slot keeps its own window
        now[0] += p.throttle
        self.assertTrue(p.tick('wlo', 3, 10))
        self.assertEqual([e['event'] for e in posts], ['run_start', 'tick', 'tick', 'tick'])
        self.assertEqual([e['run'] for e in posts], ['r1'] * 4)
        self.assertEqual(posts[1], {'event': 'tick', 'run': 'r1', 'slot': 'wlo', 'done': 1, 'total': 10})

    def test_a_failed_delivery_is_logged_once_and_never_raises(self):
        logs = []
        self.addCleanup(setattr, refresh, 'log', refresh.log)
        refresh.log = logs.append
        calls = [0]

        def post(_):
            calls[0] += 1
            if calls[0] != 3:
                raise OSError('egress down')

        p = refresh.Progress(url='http://egress:8080/api/progress', post=post)
        self.assertFalse(p.send('tick', slot='wlo', done=1))
        self.assertFalse(p.send('tick', slot='wlo', done=2))
        self.assertTrue(p.send('tick', slot='wlo', done=3))  # delivered: the next spell is loud again
        self.assertFalse(p.send('tick', slot='wlo', done=4))
        self.assertEqual(len(logs), 2)


class LiveProgressTest(unittest.TestCase):
    """run_lane/main wire the reporter into a whole run: start, ticks, walls, the end."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        StubDriver.calls, StubDriver.fails = [], {}
        StubDriver.dirty, StubDriver.counts = set(), {}
        orig_load = refresh.drivers.load
        refresh.drivers.load = lambda name, faculty, cfg, today: StubDriver(faculty, cfg, today)
        self.addCleanup(setattr, refresh.drivers, 'load', orig_load)
        orig_new_session = refresh.new_session
        refresh.new_session = lambda: self._session()
        self.addCleanup(setattr, refresh, 'new_session', orig_new_session)
        orig_status = os.environ.get('PLANWAT_EGRESS_STATUS')
        os.environ['PLANWAT_EGRESS_STATUS'] = ''
        self.addCleanup(self._restore, 'PLANWAT_EGRESS_STATUS', orig_status)

    def _session(self):
        session = FakeSession({})
        session.headers = {}
        return session

    def _restore(self, name, orig):
        if orig is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = orig

    def capture(self):
        """Route the run's events into a list instead of an egress box."""
        sent = []
        orig_deliver = refresh.Progress._deliver
        refresh.Progress._deliver = lambda self, payload: sent.append(payload)
        self.addCleanup(setattr, refresh.Progress, '_deliver', orig_deliver)
        orig = os.environ.get('PLANWAT_EGRESS_PROGRESS')
        os.environ['PLANWAT_EGRESS_PROGRESS'] = 'http://egress:8080/api/progress'
        self.addCleanup(self._restore, 'PLANWAT_EGRESS_PROGRESS', orig)
        return sent

    def main(self, argv, session, today):
        clock = FakeClock()
        return refresh.main(argv, session=session, today=today, sleep=clock.sleep, clock=clock)

    def test_streams_run_start_ticks_and_done(self):
        sent = self.capture()
        StubDriver.counts = {'wlo': 3}
        code = self.main(['--out', str(self.tmp), '--force', '--faculty', 'wlo'],
                         self._session(), dt.date(2026, 10, 15))
        self.assertEqual(code, 0)
        self.assertEqual(sent[0]['event'], 'run_start')
        self.assertEqual(sent[0]['lanes'], [{'lane': 'wat-edge', 'faculties': ['wlo']}])
        self.assertEqual(sent[-1]['event'], 'run_done')
        self.assertEqual(sent[-1]['exit'], 0)
        self.assertEqual({e['run'] for e in sent}, {sent[0]['run']})
        self.assertEqual([(e['slot'], e['lane'], e['total']) for e in sent
                          if e['event'] == 'faculty_start'], [('wlo', 'wat-edge', 3)])
        tick_events = [e for e in sent if e['event'] == 'tick']
        self.assertTrue(tick_events)
        # The throttle drops ticks that arrive inside its window, so the exact count depends on
        # pacing; the first and the last iteration always carry one (the first starts the window,
        # the last is preceded by a sleep at least as long as the profile's floor).
        self.assertEqual([(e['slot'], e['done'], e['total']) for e in tick_events[:1]], [('wlo', 0, 3)])
        self.assertEqual((tick_events[-1]['slot'], tick_events[-1]['done'], tick_events[-1]['total']),
                         ('wlo', 2, 3))
        self.assertEqual({(e['slot'], e['total']) for e in tick_events}, {('wlo', 3)})
        done = [e for e in sent if e['event'] == 'faculty_done']
        self.assertEqual(len(done), 1)
        self.assertEqual((done[0]['slot'], done[0]['blocked'], done[0]['complete']),
                         ('wlo', False, True))

    def test_reports_the_wall_and_the_recovery(self):
        sent = self.capture()
        StubDriver.fails = {'wlo': {'main': 3}, 'wel': {'main': 3}}
        StubDriver.dirty = {'wlo'}
        code = self.main(['--out', str(self.tmp), '--force', '--faculty', 'wlo,wel'],
                         self._session(), dt.date(2026, 10, 15))
        self.assertEqual(code, 0)
        blocked = [e for e in sent if e['event'] == 'faculty_done' and e['blocked']]
        self.assertEqual({e['slot'] for e in blocked}, {'wlo', 'wel'})
        wait = next(e for e in sent if e['event'] == 'wait_start')
        self.assertEqual(wait['lane'], 'wat-edge')
        self.assertEqual(sorted(wait['faculties']), ['wel', 'wlo'])
        end = next(e for e in sent if e['event'] == 'wait_end')
        self.assertTrue(end['recovered'])
        resumed = [e for e in sent if e['event'] == 'faculty_start']
        self.assertEqual([e['slot'] for e in resumed], ['wlo', 'wel'])
        self.assertEqual(sorted(e['slot'] for e in sent
                                if e['event'] == 'faculty_done' and not e['blocked']), ['wel', 'wlo'])

    def test_the_ahead_pass_gets_its_own_slot(self):
        sent = self.capture()
        StubDriver.counts = {'wlo': 2}
        today = dt.date(2026, 8, 20)
        coming = core.upcoming_reference(today)
        code = self.main(['--out', str(self.tmp), '--force', '--faculty', 'wlo'],
                         self._session(), today)
        self.assertEqual(code, 0)
        starts = [e for e in sent if e['event'] == 'faculty_start']
        self.assertEqual([e['slot'] for e in starts], ['wlo', f'wlo~{core.term_id(coming)}'])
        self.assertTrue(starts[1]['ahead'])
        ahead_done = [e for e in sent if e['event'] == 'faculty_done' and e.get('ahead')]
        self.assertEqual([e['slot'] for e in ahead_done], [f'wlo~{core.term_id(coming)}'])


class QuietStretch(unittest.TestCase):
    """Adaptive freshness: a group checked again and again unchanged waits longer the next
    time, a change puts it back onto the full cadence, and the off switch restores the old
    round-robin. A published plan resets the streak; a repeated 200 with the same digest
    raises it, like a 304."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    ROUTES = {
        'https://example.test/plan/zima/index.xml': Resp(200, INDEX.encode()),
        'https://example.test/plan/zima/WLO26AX1S1.htm': Resp(200, page('WLO26AX1S1.htm')),
    }

    def entry(self, streak, age_hours):
        return {'WLO26AX1S1': {'checked': (core.now_utc() - dt.timedelta(hours=age_hours)).isoformat(),
                               'hash': 'x', 'term': '2026-27-zima', 'streak': streak}}

    def run_faculty(self, groups, adaptive, routes=None):
        args = refresh.parse(['--out', str(self.tmp), '--adaptive-hours', str(adaptive)])
        state = core.State(self.tmp / core.STATE_FILE)
        state.data['groups'].update(groups)
        session = SequenceSession(dict(routes if routes is not None else self.ROUTES))
        result = refresh.refresh_faculty('wlo', WLO_CFG, args, state, TODAY, session, sleep=lambda s: None)
        state.save()
        return result, state, session

    def test_interval_doubles_per_quiet_check_and_caps_at_the_fence(self):
        self.assertEqual(core.quiet_interval({}, 1.0, 4.0), 1.0)  # untracked entry: first check's wisdom
        self.assertEqual(core.quiet_interval({'streak': 0}, 1.0, 4.0), 1.0)
        self.assertEqual(core.quiet_interval({'streak': 1}, 1.0, 4.0), 2.0)
        self.assertEqual(core.quiet_interval({'streak': 2}, 1.0, 4.0), 4.0)
        self.assertEqual(core.quiet_interval({'streak': 9}, 1.0, 4.0), 4.0)
        self.assertEqual(core.quiet_interval({'streak': 9}, 2.0, 0), 2.0)  # the off switch
        self.assertEqual(core.quiet_interval({'streak': 9}, 3.0, 2.0), 3.0)  # a low cap loses to the base
        self.assertEqual(core.quiet_interval('torn', 1.0, 4.0), 1.0)
        self.assertEqual(core.quiet_interval({'streak': 'x'}, 1.0, 4.0), 1.0)
        self.assertEqual(core.quiet_interval({'streak': -1}, 1.0, 4.0), 1.0)

    def test_a_group_inside_its_stretched_gap_is_not_fetched_at_all(self):
        # Two quiet checks sit behind this one (streak 2 = a 4 h gap); the last check is
        # 3 h old, so the faculty lists its groups but the group page stays untouched.
        (changed, blocked, complete), state, session = self.run_faculty(self.entry(2, age_hours=3.0), adaptive=4.0)
        self.assertEqual((changed, blocked, complete), ([], False, True))
        self.assertEqual([u for u in session.seen if 'WLO26AX1S1' in u], [])
        self.assertEqual(state.groups['WLO26AX1S1']['streak'], 2)

    def test_the_off_switch_rechecks_what_stretching_would_skip(self):
        # The same entry that stretching keeps out of the network (above), with the switch
        # off: the page is asked for, the plan repeats itself, and the quiet raise still
        # happens -- so switching adaptive freshness back on later finds this streak saved.
        first, _, _ = self.run_faculty(self.entry(0, age_hours=3.0), adaptive=0)
        self.assertEqual(first, (['WLO26AX1S1'], False, True))  # seeds the calendar
        entry = {'checked': (core.now_utc() - dt.timedelta(hours=3)).isoformat(),
                 'hash': self.digest(), 'term': '2026-27-zima', 'streak': 2}
        (changed, blocked, complete), state, session = self.run_faculty({'WLO26AX1S1': entry}, adaptive=0)
        self.assertEqual((changed, blocked, complete), ([], False, True))
        self.assertIn('https://example.test/plan/zima/WLO26AX1S1.htm', session.seen)
        self.assertEqual(state.groups['WLO26AX1S1']['streak'], 3)

    def digest(self):
        path = self.tmp / 'timetables' / '2026-27-zima' / 'WLO26AX1S1.ics'
        return core.sha256(path.read_bytes())

    def test_older_than_its_gap_the_group_is_back_to_work_and_a_new_plan_makes_it_hot(self):
        # Past the 4 h fence the group is fetched; nothing is filed yet, so the plan counts
        # as new: published, and the streak lands on 0 again.
        groups = self.entry(2, age_hours=5.0)
        groups['WLO26AX1S1'].pop('hash')
        self.tmp.mkdir(parents=True, exist_ok=True)
        (changed, blocked, complete), state, session = self.run_faculty(groups, adaptive=4.0)
        self.assertEqual((changed, blocked, complete), (['WLO26AX1S1'], False, True))
        self.assertEqual(state.groups['WLO26AX1S1']['streak'], 0)

    def test_a_changed_digest_with_the_same_plan_only_counts_as_quiet(self):
        # First pass: the group files its calendar and leaves hot (streak 0). Then the digest
        # is pointed at a page difference that is only a generated stamp: the hash no longer
        # short-circuits, the plans compare equal after all, so the check counts as quiet
        # and the doubled gap starts.
        first, state, _ = self.run_faculty(self.entry(0, age_hours=3.0), adaptive=0)
        self.assertEqual(first, (['WLO26AX1S1'], False, True))
        self.assertEqual(state.groups['WLO26AX1S1']['streak'], 0)
        state.groups['WLO26AX1S1']['hash'] = 'stale-from-the-previous-page'
        state.groups['WLO26AX1S1']['checked'] = (core.now_utc() - dt.timedelta(hours=3)).isoformat()
        state.save()
        second, state, session = self.run_faculty({}, adaptive=0)
        self.assertEqual(second, ([], False, True))
        self.assertEqual(state.groups['WLO26AX1S1']['streak'], 1)


class FleetPlan(unittest.TestCase):
    """tools/refresh/fleet.py plan: the faculties split over the runners GitHub sees online."""
    FLEET = [{'name': 'plebania', 'label': 'planwat-plebania', 'speed': 4.0, 'always_on': False, 'faculties': None},
             {'name': 'oracle', 'label': 'planwat-oracle', 'speed': 1.0, 'always_on': True, 'faculties': None}]
    WANTED = ['wlo', 'wel', 'wim', 'ioe', 'wcy', 'wml', 'wtc']
    STATE = {'faculties': {'wlo': {'last_count': 131}, 'wel': {'last_count': 158}, 'wim': {'last_count': 88},
                           'ioe': {'last_count': 15}, 'wcy': {'last_count': 155}, 'wml': {'last_count': 162},
                           'wtc': {'last_count': 23}},
             'pacing': {'wat-edge': 2.7, 'wcy': 3.0, 'wml': 3.0, 'wtc': 3.0}}

    def shares(self, online, runners=None):
        result = fleet.plan(runners or self.FLEET, self.WANTED, self.STATE, online)
        return {s['runner']: s['faculties'].split(',') for s in result['shards']}, result

    def test_both_online_the_fast_one_takes_the_most_and_both_finish_close(self):
        shares, result = self.shares({'planwat', 'planwat-plebania', 'planwat-oracle'})
        self.assertEqual(sorted(shares['plebania'] + shares['oracle']), sorted(self.WANTED))
        etas = {s['runner']: s['eta'] for s in result['shards']}
        costs = {s['runner']: s['cost'] for s in result['shards']}
        self.assertGreater(costs['plebania'], 3 * costs['oracle'])
        # No lane could move to the other runner and finish the pass sooner.
        self.assertLess(max(etas.values()), sum(costs.values()) / 4)

    def test_a_lane_never_splits(self):
        shares, _ = self.shares({'planwat-plebania', 'planwat-oracle'})
        holder = [r for r, fs in shares.items() if 'wlo' in fs]
        self.assertEqual(len(holder), 1)
        self.assertIn('wel', shares[holder[0]])

    def test_plebania_off_the_vps_takes_everything(self):
        shares, result = self.shares({'planwat', 'planwat-oracle'})
        self.assertEqual(shares, {'oracle': self.WANTED})
        self.assertEqual(result['down'], ['plebania'])

    def test_vps_down_plebania_takes_everything(self):
        shares, _ = self.shares({'planwat-plebania'})
        self.assertEqual(shares, {'plebania': self.WANTED})

    def test_nobody_online_plans_nothing_rather_than_queueing(self):
        shares, result = self.shares(set())
        self.assertEqual(shares, {})
        self.assertEqual(result['unassigned'], self.WANTED)

    def test_unknown_status_falls_back_to_the_always_on_runner(self):
        shares, result = self.shares(None)
        self.assertEqual(shares, {'oracle': self.WANTED})
        self.assertFalse(result['known'])

    def test_a_runner_limited_to_some_faculties_gets_only_those(self):
        limited = [dict(self.FLEET[0], faculties=['wim', 'ioe']), self.FLEET[1]]
        shares, _ = self.shares({'planwat-plebania', 'planwat-oracle'}, runners=limited)
        self.assertTrue(set(shares.get('plebania', [])) <= {'wim', 'ioe'})
        self.assertEqual(sorted(sum(shares.values(), [])), sorted(self.WANTED))
        alone = [dict(self.FLEET[0], faculties=['wim'])]
        shares, result = self.shares({'planwat-plebania'}, runners=alone)
        self.assertEqual(shares, {'plebania': ['wim']})
        self.assertIn('wcy', result['unassigned'])

    def test_a_share_keeps_the_order_asked(self):
        shares, _ = self.shares({'planwat-oracle'})
        self.assertEqual(shares['oracle'], self.WANTED)

    def test_online_labels_reads_githubs_runner_list(self):
        runners = [{'name': 'a', 'status': 'online', 'labels': ['planwat', 'planwat-oracle']},
                   {'name': 'b', 'status': 'offline', 'labels': ['planwat', 'planwat-plebania']}]
        self.assertEqual(fleet.online_labels(runners), {'planwat', 'planwat-oracle'})
        self.assertIsNone(fleet.online_labels(None))

    def test_cost_falls_back_for_an_unknown_faculty(self):
        self.assertEqual(fleet.faculty_cost({}, 'wim'), fleet.DEFAULT_SIZE)
        self.assertEqual(fleet.faculty_cost({'faculties': {'wcy': {'last_count': 10}}, 'pacing': {'wcy': 9}},
                                            'wcy'), 30)

    def test_the_shipped_fleet_is_valid(self):
        runners = fleet.load_fleet()
        self.assertEqual(sum(r['always_on'] for r in runners), 1)
        for bad in ({'runners': []}, {'runners': [{'name': 'Bad Name', 'label': 'x'}]},
                    {'runners': [{'name': 'a', 'label': 'x', 'speed': 0}]},
                    {'runners': [{'name': 'a', 'label': 'x'}, {'name': 'a', 'label': 'y'}]},
                    [], None, {'runners': None}, {'runners': ['oracle']}):
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'fleet.json'
                path.write_text(json.dumps(bad))
                with self.assertRaises(ValueError):
                    fleet.load_fleet(path)

    def test_cli_writes_the_matrix(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'state.json').write_text(json.dumps(self.STATE))
            (tmp / 'runners.json').write_text(json.dumps(
                [{'name': 'x', 'status': 'online', 'labels': ['planwat', 'planwat-oracle']}]))
            out = tmp / 'out'
            with unittest.mock.patch.dict(os.environ, {'GITHUB_OUTPUT': str(out), 'GITHUB_STEP_SUMMARY': ''}):
                code = fleet.main(['plan', '--state', str(tmp / 'state.json'), '--runners', str(tmp / 'runners.json'),
                                   '--faculty', 'wcy,wim'])
            self.assertEqual(code, 0)
            values = dict(line.split('=', 1) for line in out.read_text().splitlines())
            self.assertEqual(json.loads(values['matrix']),
                             [{'runner': 'oracle', 'label': 'planwat-oracle', 'faculties': 'wcy,wim', 'wave': 1,
                               'wait': fleet.BLOCK_WAIT}])  # nobody else up to take over: wait walls out
            self.assertEqual(values['shards'], '1')
            self.assertEqual(fleet.main(['plan', '--state', str(tmp / 'state.json'), '--faculty', 'nope']), 2)


class FleetMerge(unittest.TestCase):
    """tools/refresh/fleet.py merge: two runners push one branch without losing each other's state."""

    def test_disjoint_passes_both_survive(self):
        base = {'version': 1, 'groups': {'WCY1': {'checked': 'old'}, 'WIM1': {'checked': 'old'}},
                'faculties': {'wcy': {'last_count': 1}, 'wim': {'last_count': 2}},
                'pacing': {'wcy': 3.0, 'wim': 1.0}, 'blocks': {}, 'robots': {}}
        # The VPS crawled WIM and pushed first...
        theirs = json.loads(json.dumps(base))
        theirs['groups']['WIM1'] = {'checked': 'vps'}
        theirs['faculties']['wim'] = {'last_count': 3}
        theirs['robots']['www.wim.wat.edu.pl'] = {'at': 'vps'}
        # ...while plebania crawled WCY, starting from the same base. Its line state (from its own tool cache)
        # carries other numbers for WIM too: those are its line's, not this pass's.
        mine = json.loads(json.dumps(base))
        mine['groups']['WCY1'] = {'checked': 'plebania'}
        mine['groups']['WCY2'] = {'checked': 'plebania'}
        mine['faculties'] = {'wcy': {'last_count': 5}, 'wim': {'last_count': 99}}
        mine['pacing'] = {'wcy': 2.0, 'wim': 2.5}
        mine['blocks'] = {'wcy': {'durations': [60]}}
        out = fleet.merge_state(base, mine, theirs, ['wcy'])
        self.assertEqual(out['groups'], {'WCY1': {'checked': 'plebania'}, 'WCY2': {'checked': 'plebania'},
                                         'WIM1': {'checked': 'vps'}})
        self.assertEqual(out['faculties'], {'wcy': {'last_count': 5}, 'wim': {'last_count': 3}})
        self.assertEqual(out['pacing'], {'wcy': 2.0, 'wim': 1.0})
        self.assertEqual(out['blocks'], {'wcy': {'durations': [60]}})
        self.assertEqual(out['robots'], {'www.wim.wat.edu.pl': {'at': 'vps'}})

    def test_a_shared_policy_group_follows_its_faculty(self):
        mine = {'version': 1, 'groups': {}, 'faculties': {'wlo': {'x': 1}, 'wel': {'x': 2}},
                'pacing': {'wat-edge': 1.5}, 'blocks': {'wat-edge': {'durations': [1]}}}
        out = fleet.merge_state({}, mine, {'version': 1, 'groups': {}, 'faculties': {}}, ['wlo', 'wel'])
        self.assertEqual(out['pacing'], {'wat-edge': 1.5})
        self.assertEqual(out['blocks'], {'wat-edge': {'durations': [1]}})

    def test_nothing_on_the_branch_yet(self):
        mine = {'version': 1, 'groups': {'A': {'checked': 'x'}}, 'faculties': {'wim': {}}}
        out = fleet.merge_state({}, mine, {}, ['wim'])
        self.assertEqual(out['groups'], {'A': {'checked': 'x'}})
        self.assertEqual(out['version'], 1)

    def test_cli_merges_in_place_and_seed_copies_the_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'base.json').write_text(json.dumps({'version': 1, 'groups': {}, 'faculties': {}}))
            (tmp / 'mine.json').write_text(json.dumps({'version': 1, 'groups': {'WIM1': {'checked': 'a'}},
                                                       'faculties': {'wim': {'last_count': 1}}}))
            (tmp / 'into.json').write_text(json.dumps({'version': 1, 'groups': {'WCY1': {'checked': 'b'}},
                                                       'faculties': {}, 'pacing': {'wcy': 2.0}}))
            self.assertEqual(fleet.main(['merge', '--base', str(tmp / 'base.json'), '--mine', str(tmp / 'mine.json'),
                                         '--into', str(tmp / 'into.json'), '--faculty', 'wim']), 0)
            merged = core.State(tmp / 'into.json')
            self.assertEqual(set(merged.groups), {'WIM1', 'WCY1'})
            self.assertEqual(merged.data['pacing'], {'wcy': 2.0})
            self.assertEqual(fleet.main(['seed', '--state', str(tmp / 'into.json'), '--out',
                                         str(tmp / 'cache' / 'line.json')]), 0)
            line = json.loads((tmp / 'cache' / 'line.json').read_text())
            self.assertEqual(set(line), set(core.LINE_KEYS))
            self.assertEqual(line['pacing'], {'wcy': 2.0})


class FleetCombine(unittest.TestCase):
    """tools/refresh/fleet.py combine: one refresh-outcome.json for pages.yml out of every share's."""

    PLAN = [{'runner': 'plebania', 'faculties': 'wlo,wel,wcy', 'wave': 1}, {'runner': 'oracle', 'faculties': 'wim,wtc', 'wave': 1}]

    def shard(self, runner, wave=1, **kw):
        return {'runner': runner, 'wave': str(wave), 'skipped': 'false', 'pushed': 'false', 'changed': '0',
                'blocked': 'false', 'incomplete': 'false', 'degraded': 'false', 'failed': 'false',
                'blocked_faculties': '', 'incomplete_faculties': '', **kw}

    def test_any_push_rebuilds(self):
        out = fleet.combine(self.PLAN, [self.shard('plebania', pushed='true', changed='3'), self.shard('oracle', changed='1')], 0)
        self.assertEqual((out['pushed'], out['changed'], out['incomplete']), ('true', '4', 'false'))

    def test_all_quiet_skips_the_rebuild(self):
        out = fleet.combine(self.PLAN, [self.shard('plebania'), self.shard('oracle')], 0)
        self.assertEqual(out['pushed'], 'false')

    def test_a_missing_or_skipped_share_rebuilds_and_is_incomplete(self):
        for outcomes in ([self.shard('oracle')], [self.shard('oracle'), self.shard('plebania', skipped='true')]):
            out = fleet.combine(self.PLAN, outcomes, 0)
            self.assertEqual((out['pushed'], out['incomplete'], out['missing']), ('', 'true', ['plebania']))

    def test_one_blocked_share_blocks_the_pass(self):
        out = fleet.combine(self.PLAN, [self.shard('plebania'), self.shard('oracle', blocked='true', incomplete='true',
                                                                            blocked_faculties='wtc', incomplete_faculties='wtc')], 0)
        self.assertEqual((out['blocked'], out['incomplete'], out['blocked_faculties']), ('true', 'true', ['wtc']))

    def test_a_faculty_taken_over_cleanly_is_neither_blocked_nor_incomplete(self):
        took = [{'runner': 'plebania', 'faculties': 'wtc', 'wave': 2, 'from': 'wtc:oracle'}]
        blocked = self.shard('oracle', blocked='true', incomplete='true', blocked_faculties='wtc', incomplete_faculties='wtc')
        out = fleet.combine(self.PLAN + took, [self.shard('plebania'), blocked, self.shard('plebania', 2, pushed='true')], 0)
        self.assertEqual((out['blocked'], out['incomplete'], out['pushed']), ('false', 'false', 'true'))
        again = self.shard('plebania', 2, blocked='true', blocked_faculties='wtc', incomplete_faculties='wtc')
        out = fleet.combine(self.PLAN + took, [self.shard('plebania'), blocked, again], 0)
        self.assertEqual(out['blocked_faculties'], ['wtc'])  # blocked on both: still blocked

    def test_a_lost_share_taken_over_completes_the_pass_but_still_rebuilds(self):
        took = [{'runner': 'plebania', 'faculties': 'wim,wtc', 'wave': 2}]
        out = fleet.combine(self.PLAN + took, [self.shard('plebania'), self.shard('plebania', 2)], 0)
        self.assertEqual((out['incomplete'], out['pushed'], out['missing']), ('false', '', ['oracle']))

    def test_a_takeover_that_never_reported_leaves_the_pass_incomplete(self):
        took = [{'runner': 'plebania', 'faculties': 'wtc', 'wave': 2}]
        blocked = self.shard('oracle', blocked='true', blocked_faculties='wtc', incomplete_faculties='wtc')
        out = fleet.combine(self.PLAN + took, [self.shard('plebania'), blocked], 0)
        self.assertEqual((out['incomplete'], out['blocked']), ('true', 'false'))

    def test_an_older_report_without_faculty_lists_counts_as_its_flags(self):
        old = {'runner': 'oracle', 'pushed': 'true', 'changed': '0', 'blocked': 'true', 'incomplete': 'true'}
        out = fleet.combine(self.PLAN, [self.shard('plebania'), old], 0)
        self.assertEqual(sorted(out['blocked_faculties']), ['wim', 'wtc'])

    def test_a_pass_with_no_runner_is_incomplete(self):
        out = fleet.combine([], [], 0)
        self.assertEqual((out['pushed'], out['incomplete']), ('false', 'true'))

    def test_an_old_pass_leaves_the_issues_alone(self):
        self.assertFalse(fleet.combine(self.PLAN, [self.shard('oracle')], fleet.REPORT_HOURS + 1)['current'])

    def test_cli_writes_the_gate_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'shards').mkdir()
            (tmp / 'shards' / 'shard-1-oracle.json').write_text(json.dumps(self.shard('oracle', pushed='true')))
            out = tmp / 'gh'
            with unittest.mock.patch.dict(os.environ, {'GITHUB_OUTPUT': str(out), 'GITHUB_STEP_SUMMARY': ''}):
                fleet.main(['combine', '--matrix', '[{"runner": "oracle", "faculties": "wim"}]', '--handoff', '[]',
                            '--planned', str(int(dt.datetime.now(dt.timezone.utc).timestamp())),
                            '--dir', str(tmp / 'shards'), '--out', str(tmp / 'refresh-outcome.json')])
            self.assertEqual(json.loads((tmp / 'refresh-outcome.json').read_text()),
                             {'pushed': 'true', 'changed': '0', 'blocked': 'false'})
            self.assertIn('current=true', out.read_text())


class FleetHandoff(unittest.TestCase):
    """tools/refresh/fleet.py handoff: what one runner left blocked or unfinished goes to another one that is up."""

    FLEET = FleetPlan.FLEET
    BOTH = {'planwat', 'planwat-plebania', 'planwat-oracle'}
    PLAN = [{'runner': 'plebania', 'label': 'planwat-plebania', 'faculties': 'wlo,wel,wcy,wml', 'wave': 1},
            {'runner': 'oracle', 'label': 'planwat-oracle', 'faculties': 'wim,ioe,wtc', 'wave': 1}]

    def shard(self, runner, **kw):
        return FleetCombine.shard(self, runner, **kw)

    def takeover(self, outcomes, online=None, fleet_=None):
        result = fleet.handoff(fleet_ or self.FLEET, self.PLAN, outcomes, FleetPlan.STATE,
                               self.BOTH if online is None else online)
        return {s['runner']: (s['faculties'], s['from']) for s in result['shards']}, result

    def test_a_blocked_faculty_goes_to_the_other_runner(self):
        took, result = self.takeover([self.shard('plebania'),
                                      self.shard('oracle', blocked='true', blocked_faculties='wtc', incomplete_faculties='wtc')])
        self.assertEqual(took, {'plebania': ('wtc', 'wtc:oracle')})
        self.assertEqual(result['shards'][0]['wait'], fleet.BLOCK_WAIT)  # nobody after it: wait the wall out
        self.assertEqual(result['left'], {'wtc': {'runner': 'oracle', 'why': 'blocked'}})

    def test_a_lane_moves_whole_and_never_back_to_the_runner_that_left_it(self):
        took, _ = self.takeover([self.shard('plebania', blocked='true', blocked_faculties='wlo,wel',
                                            incomplete_faculties='wlo,wel'), self.shard('oracle')])
        self.assertEqual(took, {'oracle': ('wlo,wel', 'wlo:plebania,wel:plebania')})

    def test_nobody_else_online_leaves_it_for_the_next_pass(self):
        took, result = self.takeover([self.shard('plebania'), self.shard('oracle', blocked='true', blocked_faculties='wtc',
                                                                         incomplete_faculties='wtc')],
                                     online={'planwat', 'planwat-oracle'})
        self.assertEqual((took, result['unassigned']), ({}, ['wtc']))

    def test_unknown_runners_leave_it_to_an_always_on_one(self):
        took, _ = self.takeover([self.shard('plebania', blocked='true', blocked_faculties='wcy', incomplete_faculties='wcy'),
                                 self.shard('oracle')], online=set())
        self.assertEqual(took, {})  # nothing online at all
        result = fleet.handoff(self.FLEET, self.PLAN, [self.shard('plebania', blocked='true', blocked_faculties='wcy',
                                                                  incomplete_faculties='wcy'), self.shard('oracle')],
                               FleetPlan.STATE, None)
        self.assertEqual([(s['runner'], s['faculties']) for s in result['shards']], [('oracle', 'wcy')])

    def test_a_share_that_never_ran_is_taken_over_whole(self):
        for outcomes in ([self.shard('plebania')], [self.shard('plebania'), self.shard('oracle', skipped='true')],
                         [self.shard('plebania'), self.shard('oracle', failed='true', incomplete='true')]):
            took, _ = self.takeover(outcomes)
            self.assertEqual(took, {'plebania': ('wim,ioe,wtc', 'wim:oracle,ioe:oracle,wtc:oracle')}, outcomes)

    def test_an_unfinished_faculty_is_taken_over_too(self):
        took, result = self.takeover([self.shard('plebania'), self.shard('oracle', incomplete='true',
                                                                         incomplete_faculties='ioe')])
        self.assertEqual(took, {'plebania': ('ioe', 'ioe:oracle')})
        self.assertEqual(result['left']['ioe']['why'], 'unfinished')

    def test_a_clean_pass_hands_nothing_off(self):
        took, result = self.takeover([self.shard('plebania'), self.shard('oracle')])
        self.assertEqual((took, result['unassigned']), ({}, []))

    def test_an_allowlist_is_respected(self):
        only = [dict(self.FLEET[0], faculties=['wlo', 'wel', 'wcy', 'wml']), self.FLEET[1]]
        took, result = self.takeover([self.shard('plebania'), self.shard('oracle', blocked='true', blocked_faculties='wtc',
                                                                         incomplete_faculties='wtc')], fleet_=only)
        self.assertEqual((took, result['unassigned']), ({}, ['wtc']))

    def test_the_plan_waits_briefly_only_where_a_takeover_is_possible(self):
        both = fleet.plan(self.FLEET, FleetPlan.WANTED, FleetPlan.STATE, self.BOTH)
        self.assertEqual({s['wait'] for s in both['shards']}, {fleet.HANDOFF_WAIT})
        alone = fleet.plan(self.FLEET, FleetPlan.WANTED, FleetPlan.STATE, {'planwat', 'planwat-oracle'})
        self.assertEqual({s['wait'] for s in alone['shards']}, {fleet.BLOCK_WAIT})

    def test_cli_writes_the_takeover_matrix(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'shards').mkdir()
            (tmp / 'shards' / 'shard-1-plebania.json').write_text(json.dumps(self.shard('plebania')))
            (tmp / 'shards' / 'shard-1-oracle.json').write_text(json.dumps(
                self.shard('oracle', blocked='true', blocked_faculties='wtc', incomplete_faculties='wtc')))
            (tmp / 'runners.json').write_text(json.dumps(
                [{'name': 'a', 'status': 'online', 'labels': ['planwat', 'planwat-plebania']},
                 {'name': 'b', 'status': 'online', 'labels': ['planwat', 'planwat-oracle']}]))
            out = tmp / 'gh'
            with unittest.mock.patch.dict(os.environ, {'GITHUB_OUTPUT': str(out), 'GITHUB_STEP_SUMMARY': ''}):
                self.assertEqual(fleet.main(['handoff', '--matrix', json.dumps(self.PLAN), '--dir', str(tmp / 'shards'),
                                             '--state', str(tmp / 'none.json'), '--runners', str(tmp / 'runners.json')]), 0)
            values = dict(line.split('=', 1) for line in out.read_text().splitlines())
            self.assertEqual(json.loads(values['matrix']),
                             [{'runner': 'plebania', 'label': 'planwat-plebania', 'faculties': 'wtc', 'wave': 2,
                               'wait': fleet.BLOCK_WAIT, 'from': 'wtc:oracle'}])
            self.assertEqual(values['shards'], '1')


class RunHistory(unittest.TestCase):
    """tools/refresh/runs.py: the last passes on the data branch (refresh-runs.json, README.md)."""

    PLANNED = dt.datetime(2026, 10, 25, 12, 0, tzinfo=dt.timezone.utc)
    MATRIX = [{'runner': 'plebania', 'faculties': 'wcy,wel'}, {'runner': 'oracle', 'faculties': 'ioe'}]

    def shard(self, runner, minutes=30, **kw):
        start = self.PLANNED.timestamp() + 60
        return {'runner': runner, 'skipped': 'false', 'pushed': 'true', 'changed': '0', 'blocked': 'false',
                'incomplete': 'false', 'degraded': 'false', 'started': str(start), 'ended': str(start + minutes * 60),
                **kw}

    def state(self, at='2026-10-25T12:20:00'):
        run = lambda **kw: {'at': at, 'checked': 10, 'changed': 0, 'skipped': 0, 'not_ready': 0,  # noqa: E731
                            'blocked': False, 'degraded': False, 'cause': None, **kw}
        return {'version': 1, 'faculties': {
            'wcy': {'run': run(checked=100, changed=2, not_ready=38)},
            'wel': {'run': run(blocked=True, cause='wall', checked=0)},
            'ioe': {'run': run(at='2026-10-25T09:00:00')}}}

    def record(self, matrix=None, outcomes=None, plan_info=None, state=None, run_id=7, planned=None, handoff=()):
        return runs.build_run(run_id=run_id, number=512, attempt=1, event='schedule', url='https://x/7',
                              planned=planned or self.PLANNED, ended=self.PLANNED + dt.timedelta(minutes=41),
                              matrix=self.MATRIX if matrix is None else matrix,
                              outcomes=[self.shard('plebania', changed='2'), self.shard('oracle', 12)]
                              if outcomes is None else outcomes,
                              plan_info=plan_info or {'down': []}, state=self.state() if state is None else state,
                              handoff=handoff)

    def test_a_pass_names_each_server_its_faculties_and_its_time(self):
        run = self.record(plan_info={'down': ['spare']})
        self.assertEqual([(r['name'], r['faculties'], r['status'], r['minutes']) for r in run['runners']],
                         [('plebania', ['wcy', 'wel'], 'done', 30), ('oracle', ['ioe'], 'done', 12)])
        self.assertEqual(run['offline'], ['spare'])
        self.assertEqual((run['result'], run['changed'], run['planned'], run['ended']),
                         ('changed', 2, '2026-10-25T12:00:00', '2026-10-25T12:41:00'))

    def test_faculty_numbers_are_taken_only_from_this_pass(self):
        facs = {f['id']: f for f in self.record()['faculties']}
        self.assertEqual((facs['wcy']['checked'], facs['wcy']['changed'], facs['wcy']['not_ready']), (100, 2, 38))
        self.assertEqual((facs['wel']['blocked'], facs['wel']['cause'], facs['wel']['runner']), (True, 'wall', 'plebania'))
        self.assertFalse(facs['ioe']['fresh'])  # its run entry is from an earlier pass
        self.assertEqual(self.record()['checked'], 100)

    def test_results(self):
        result = lambda **kw: self.record(**kw)['result']  # noqa: E731
        self.assertEqual(result(outcomes=[self.shard('plebania'), self.shard('oracle')]), 'ok')
        self.assertEqual(result(outcomes=[self.shard('plebania', blocked='true', changed='3'), self.shard('oracle')]),
                         'blocked')
        self.assertEqual(result(outcomes=[self.shard('plebania')]), 'incomplete')  # oracle never reported
        self.assertEqual(result(outcomes=[self.shard('plebania', degraded='true'), self.shard('oracle')]), 'degraded')
        self.assertEqual(result(matrix=[], outcomes=[], plan_info={'down': ['plebania', 'oracle']}), 'idle')

    def test_a_takeover_is_recorded_with_whose_faculty_it_took(self):
        blocked = self.shard('oracle', 12, blocked='true', incomplete='true', blocked_faculties='ioe',
                             incomplete_faculties='ioe')
        took = dict(self.shard('plebania', 9, changed='1'), wave='2')
        state = self.state()
        state['faculties']['ioe']['run']['at'] = '2026-10-25T12:40:00'  # plebania's, after the takeover
        run = self.record(outcomes=[self.shard('plebania'), blocked, took], state=state,
                          handoff=[{'runner': 'plebania', 'faculties': 'ioe', 'from': 'ioe:oracle'}])
        self.assertEqual([(r['name'], r['wave'], r['status']) for r in run['runners']],
                         [('plebania', 1, 'done'), ('oracle', 1, 'blocked'), ('plebania', 2, 'done')])
        self.assertEqual(run['runners'][1]['blocked_on'], ['ioe'])
        self.assertEqual(run['runners'][2]['from'], {'ioe': 'oracle'})
        ioe = {f['id']: f for f in run['faculties']}['ioe']
        self.assertEqual((ioe['runner'], ioe['from']), ('plebania', {'runner': 'oracle', 'why': 'blocked'}))
        self.assertEqual(run['result'], 'changed')  # taken over cleanly: the pass is not blocked
        text = runs.markdown([run])
        self.assertIn('**plebania** (WCY, WEL, IOE (od oracle)) · **oracle** (IOE)', text)
        self.assertIn('| **oracle** | IOE | 0 | 12 min, zablokowany na IOE |', text)
        self.assertIn('| **plebania** (przejęcie) | IOE (od oracle) | 1 | 9 min |', text)
        self.assertIn('| IOE | plebania | 10 | 0 | przejęty po blokadzie na oracle |', text)
        stale = self.record(outcomes=[self.shard('plebania'), blocked],
                            handoff=[{'runner': 'plebania', 'faculties': 'ioe', 'from': 'ioe:oracle'}])
        self.assertIn('przejęty po blokadzie na oracle, brak danych z tego przebiegu', runs.markdown([stale]))
        self.assertEqual(stale['result'], 'incomplete')  # the takeover never reported

    def test_a_skipped_or_silent_server_says_so(self):
        run = self.record(outcomes=[self.shard('plebania', skipped='true')])
        self.assertEqual([r['status'] for r in run['runners']], ['skipped', 'missing'])
        self.assertIsNone(run['runners'][1]['minutes'])

    def test_history_keeps_the_newest_ten_and_a_rerun_replaces_its_first_attempt(self):
        history = []
        for i in range(12):
            history = runs.add_run(history, self.record(run_id=100 + i, planned=self.PLANNED + dt.timedelta(hours=2 * i)))
        self.assertEqual([r['id'] for r in history], list(range(111, 101, -1)))
        rerun = dict(history[3], attempt=2, result='ok')
        history = runs.add_run(history, rerun)
        self.assertEqual(len(history), 10)
        self.assertEqual(history[3]['attempt'], 2)

    def test_a_pass_is_new_for_the_site_when_its_result_or_servers_differ(self):
        def quiet(i, **kw):
            kw.setdefault('outcomes', [self.shard('plebania'), self.shard('oracle')])
            return self.record(run_id=100 + i, planned=self.PLANNED + dt.timedelta(hours=2 * i), **kw)

        first = quiet(0)
        self.assertTrue(runs.shows_new(runs.add_run([], first), first))  # nothing on record before it
        history = runs.add_run([], first)
        again = quiet(1)
        self.assertFalse(runs.shows_new(runs.add_run(history, again), again))
        blocked = quiet(1, outcomes=[self.shard('plebania', blocked='true'), self.shard('oracle')])
        self.assertTrue(runs.shows_new(runs.add_run(history, blocked), blocked))
        alone = quiet(1, matrix=[self.MATRIX[1]], outcomes=[self.shard('oracle')], plan_info={'down': ['plebania']})
        self.assertTrue(runs.shows_new(runs.add_run(history, alone), alone))  # plebania went off
        full = [quiet(i) for i in range(1, 11)]
        late = quiet(-5, outcomes=[self.shard('plebania', blocked='true'), self.shard('oracle')])
        history = runs.add_run(runs.add_run([], full[0]), late)
        for r in full[1:]:
            history = runs.add_run(history, r)
        self.assertFalse(runs.shows_new(history, late))  # fell off the history: nothing to show

    def test_markdown_shows_the_latest_pass_and_every_server(self):
        older = self.record(run_id=6, planned=self.PLANNED - dt.timedelta(hours=2), matrix=[self.MATRIX[1]],
                            outcomes=[self.shard('oracle')], plan_info={'down': ['plebania']})
        text = runs.markdown([self.record(), older], 'https://site/stan/', 'https://github.com/o/r')
        self.assertIn('> [!TIP]\n> **Ostatni przebieg: zmiany w 2 planach.** 25 paź 2026 · 13:00', text)
        self.assertIn('| 25 paź · 13:00 | Zmiany w 2 planach | **plebania** (WCY, WEL) · **oracle** (IOE) | 100 | 41 min |',
                      text)
        self.assertIn('| **oracle** (IOE) · ~~plebania~~ |', text)
        self.assertIn('| plebania | | | wyłączony |', text)
        self.assertIn('| WEL | plebania | 0 | 0 | blokada Incapsula |', text)
        self.assertIn('| IOE | oracle | – | – | brak danych z tego przebiegu |', text)
        self.assertIn('Ostatnie 2 przebiegi', text)
        self.assertIn('[https://site/stan/](https://site/stan/)', text)
        self.assertEqual(text.count('<details>'), text.count('</details>'))
        self.assertIn('Brak zapisanych przebiegów', runs.markdown([]))

    def test_a_blocked_pass_is_a_caution(self):
        text = runs.markdown([self.record(outcomes=[self.shard('plebania', blocked='true'), self.shard('oracle')])])
        self.assertEqual(text.split('\n')[2], '> [!CAUTION]')

    def test_cli_records_rewrites_the_readme_and_recovers_from_a_damaged_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / 'shards').mkdir()
            for o in (self.shard('plebania', changed='2'), self.shard('oracle')):
                (tmp / 'shards' / f"shard-{o['runner']}.json").write_text(json.dumps(o))
            (tmp / 'refresh-state.json').write_text(json.dumps(self.state()))
            (tmp / 'refresh-runs.json').write_text('[1, 2')  # damaged: start a new history
            args = ['record', '--matrix', json.dumps(self.MATRIX), '--plan', 'not json', '--planned',
                    str(int(self.PLANNED.timestamp())), '--dir', str(tmp / 'shards'),
                    '--state', str(tmp / 'refresh-state.json'), '--runs', str(tmp / 'refresh-runs.json'),
                    '--readme', str(tmp / 'README.md'), '--run-id', '7', '--run-number', '512', '--event', 'schedule',
                    '--url', 'https://x/7', '--repo-url', '']
            (tmp / 'refresh-outcome.json').write_text(json.dumps({'pushed': 'true', 'changed': '2', 'blocked': 'false'}))
            outcome = ['--outcome', str(tmp / 'refresh-outcome.json')]
            self.assertEqual(runs.main(args + outcome), 0)
            self.assertEqual(json.loads((tmp / 'refresh-outcome.json').read_text()),
                             {'pushed': 'true', 'changed': '2', 'blocked': 'false', 'history': 'new'})
            self.assertEqual(runs.main(args + ['--run-id', '8'] + outcome), 0)  # the next pass, ending the same way
            self.assertEqual(json.loads((tmp / 'refresh-outcome.json').read_text())['history'], 'same')
            saved = json.loads((tmp / 'refresh-runs.json').read_text())
            self.assertEqual([r['id'] for r in saved['runs']], [8, 7])
            self.assertEqual(saved['runs'][0]['offline'], [])
            readme = (tmp / 'README.md').read_text()
            self.assertTrue(readme.startswith('# Odświeżanie planów'))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                runs.main(['render', '--summary', '--runs', str(tmp / 'refresh-runs.json')])
            self.assertIn('\n### Odświeżanie planów', out.getvalue())
            self.assertIn('\n#### Szczegóły', out.getvalue())


if __name__ == '__main__':
    unittest.main()
