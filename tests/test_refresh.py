"""Offline tests of the timetable refresh (tools/refresh): no network, fixtures are real crawled pages."""
import datetime as dt
import importlib.util
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
        self.assertNotIn('Ptaszek', ics)
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


if __name__ == '__main__':
    unittest.main()
