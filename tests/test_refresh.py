"""Offline tests of the timetable refresh (tools/refresh): no network, fixtures are real crawled pages."""
import datetime as dt
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures' / 'refresh'
sys.path.insert(0, str(ROOT / 'tools' / 'refresh'))

import core  # noqa: E402
import refresh  # noqa: E402
import wlo2ics  # noqa: E402
from drivers import Item  # noqa: E402
from drivers import plansoft  # noqa: E402
from drivers import wml  # noqa: E402
from drivers import wtc  # noqa: E402 (stdlib-only import; pymupdf stays lazy)

TODAY = dt.date(2026, 10, 15)
INDEX = ('<?xml version="1.0"?><index><period name="zima"/>'
         '<gro href="WLO26AX1S1.htm"/><gro href="Kurs_-_Cos_10.26.htm"/></index>')
WLO_CFG = {'driver': 'plansoft', 'label': 'WLO', 'prefix': 'WLO', 'base': 'https://example.test/plan/{season}/'}
WTC_CFG = {'driver': 'wtc', 'label': 'WTC', 'prefix': 'WTC', 'base': 'https://example.test/plany/{season}/'}
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


def page(name):
    return (FIXTURES / name).read_bytes()


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
        session = FakeSession(routes or self.routes)
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


class WtcDiscovery(unittest.TestCase):
    def discover(self, body, headers=None):
        driver = wtc.Driver('wtc', WTC_CFG, TODAY)
        session = FakeSession({'https://example.test/plany/zima/index.xml': Resp(200, body)})
        if headers is not None:
            session.headers = headers
        return driver, session, driver.discover(session)

    def test_lists_the_pdf_groups(self):
        _, _, items = self.discover(WTC_INDEX.encode())
        self.assertEqual([i.code for i in items], ['WTC26M1', 'WTC26M2'])
        self.assertEqual(items[0].url, 'https://example.test/plany/zima/WTC26M1.pdf')
        self.assertEqual(items[0].page, 'WTC26M1')

    def test_a_blocked_index_raises(self):
        driver = wtc.Driver('wtc', WTC_CFG, TODAY)
        session = FakeSession({'https://example.test/plany/zima/index.xml': Resp(403, b'')})
        with self.assertRaises(core.Blocked):
            driver.discover(session)

    def test_pdfs_are_fetched_with_the_index_as_referer(self):
        headers = {}
        _, _, _ = self.discover(WTC_INDEX.encode(), headers)
        self.assertEqual(headers.get('Referer'), 'https://example.test/plany/zima/index.xml')

    def test_page_ok_accepts_only_pdfs(self):
        driver = wtc.Driver('wtc', WTC_CFG, TODAY)
        self.assertTrue(driver.page_ok('%PDF-1.7\n%\xe2\xe3\xcf\xd3\n'))
        self.assertFalse(driver.page_ok('<html><body>Request unsuccessful. Incapsula</body></html>'))

    def test_non_pdf_bytes_are_rejected_before_conversion(self):
        driver = wtc.Driver('wtc', WTC_CFG, TODAY)
        with self.assertRaises(ValueError):
            driver.convert(Item('WTC26M1', 'https://example.test/WTC26M1.pdf', 'WTC26M1'), b'<html></html>')


@unittest.skipUnless(HAS_PYMUPDF, 'pymupdf not installed')
class WtcConversion(unittest.TestCase):
    def test_a_crawled_pdf_becomes_a_valid_calendar_without_staff_names(self):
        driver = wtc.Driver('wtc', WTC_CFG, TODAY)
        ics = driver.convert(Item('WTC26M1', 'https://example.test/plany/zima/WTC26M1.pdf', 'WTC26M1'),
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
        base = 'https://example.test/plany/zima/'
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
        session = ScriptedSession([Resp(200, INDEX.encode())] + [Resp(503, b'x')] * 10)
        (changed, blocked, complete), state = self.faculty(session)
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
        StubDriver.fails = {'wlo': {'main': 1}, 'wel': {'main': 1}}
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
        StubDriver.fails = {'wlo': {'ahead': 1}}
        session = FakeSession({})
        session.headers = {}
        today, coming = dt.date(2026, 8, 20), dt.date(2026, 9, 1)
        code = self.main(['--out', str(self.tmp), '--force', '--faculty', 'wlo'],
                         session, today)
        self.assertEqual(code, 0)  # the main pass was clean; only the ahead pass needed a resume
        dates = [day for fac, day, _ in StubDriver.calls if fac == 'wlo']
        self.assertEqual(dates.count(today), 2)  # the clean main pass + the group probe
        self.assertEqual(dates.count(coming), 2)  # the blocked ahead pass + its resume only
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
        self.assertEqual([budget for _, budget in self.wait_calls], [1800.0, 1800.0, 1800.0])

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
            i = 0
            while not stop.is_set():
                state.groups[f'G{i}'] = {'checked': 'x'}
                i += 1
        t = threading.Thread(target=churn)
        t.start()
        try:
            for _ in range(20):
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


if __name__ == '__main__':
    unittest.main()
