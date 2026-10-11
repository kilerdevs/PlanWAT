"""Tests for build.py (the static site generator).

Run: python3 -m unittest discover -s tests -v
"""
import base64
import datetime as dt
import hashlib
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import build  # noqa: E402

D = dt.date


def sha(text):
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode('utf-8')).digest()).decode() + "'"


def calendar(group, start, end, first_event, extra=''):
    """A minimal valid calendar for one group and term."""
    ymd = first_event.replace('-', '')
    lines = [
        'BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//test//test//PL',
        f'X-PLAN-GROUP:{group}', 'X-PLAN-FACULTY:Cybernetyki', f'X-PLAN-TERM:term {start}',
        f'X-PLAN-SEMESTER-START:{start.replace("-", "")}', f'X-PLAN-SEMESTER-END:{end.replace("-", "")}',
        'BEGIN:VEVENT', f'UID:{ymd}@test', f'DTSTART:{ymd}T080000', f'DTEND:{ymd}T093500',
        'SUMMARY:Matematyka', 'END:VEVENT',
    ]
    if extra:
        lines.insert(-2, extra)
    return '\r\n'.join(lines + ['END:VCALENDAR']) + '\r\n'


class FacultyTest(unittest.TestCase):
    def test_known_prefixes_map_to_their_faculty(self):
        self.assertEqual(build.faculty_of('WCY26KY3S1'), 'WCY')
        self.assertEqual(build.faculty_of('WEL24AB1S1'), 'WEL')
        self.assertEqual(build.faculty_of('WIG24AB1S1'), 'WIG')
        self.assertEqual(build.faculty_of('WML24AB1S1'), 'WML')
        self.assertEqual(build.faculty_of('WTC24AB1S1'), 'WTC')
        self.assertEqual(build.faculty_of('WCY26_Fiz1a'), 'WCY')

    def test_unknown_prefixes_fall_back_to_other(self):
        self.assertEqual(build.faculty_of('WME26BX1S1'), 'OTHER')
        self.assertEqual(build.faculty_of('ABC123'), 'OTHER')

    def test_plural_grup(self):
        self.assertEqual(build.plural_grup(1), '1 grupa')
        self.assertEqual(build.plural_grup(2), '2 grupy')
        self.assertEqual(build.plural_grup(5), '5 grup')
        self.assertEqual(build.plural_grup(186), '186 grup')


class PickTermTest(unittest.TestCase):
    TERMS = [
        build.Term('2026-27-zima', None, D(2026, 9, 28), D(2027, 2, 28)),
        build.Term('2026-27-lato', None, D(2027, 3, 1), D(2027, 6, 30)),
    ]

    def test_picks_the_term_that_contains_today(self):
        self.assertEqual(build.pick_term(self.TERMS, D(2027, 4, 10)).term_id, '2026-27-lato')

    def test_between_terms_picks_the_upcoming_one(self):
        terms = [build.Term('a', None, D(2026, 9, 28), D(2027, 1, 31)),
                 build.Term('b', None, D(2027, 3, 1), D(2027, 6, 30))]
        self.assertEqual(build.pick_term(terms, D(2027, 2, 15)).term_id, 'b')

    def test_after_the_last_term_keeps_the_latest(self):
        self.assertEqual(build.pick_term(self.TERMS, D(2027, 9, 1)).term_id, '2026-27-lato')

    def test_before_the_first_term_picks_the_first(self):
        self.assertEqual(build.pick_term(self.TERMS, D(2026, 8, 1)).term_id, '2026-27-zima')


class BuildRealSiteTest(unittest.TestCase):
    """Build the repository's own timetables."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.nginx = cls.tmp / 'nginx.conf'
        shutil.copy(ROOT / 'deploy' / 'nginx.conf', cls.nginx)
        cls.out = cls.tmp / 'site'
        build.build(ROOT / 'timetables', cls.out, today=D(2026, 10, 15), base_path='/PlanWAT', nginx_conf=cls.nginx)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp)

    def pages(self):
        return sorted(self.out.rglob('*.html'))

    def test_writes_group_page_calendar_index_and_404(self):
        for rel in ('index.html', '404.html', 'WCY26KY3S1/index.html', 'WCY26KY3S1/plan.ics'):
            self.assertTrue((self.out / rel).is_file(), rel)

    def test_group_calendar_is_a_byte_copy_of_the_current_term(self):
        self.assertEqual((self.out / 'WCY26KY3S1' / 'plan.ics').read_bytes(),
                         (ROOT / 'timetables' / '2026-27-zima' / 'WCY26KY3S1.ics').read_bytes())

    def groups(self):
        return sorted({p.stem for p in (ROOT / 'timetables').glob('*/*.ics')})

    def test_every_group_in_the_repository_gets_a_page_and_its_calendar(self):
        for group in self.groups():
            self.assertTrue((self.out / group / 'index.html').is_file(), group)
            calendar = (self.out / group / 'plan.ics').read_bytes()
            self.assertIn(calendar, [p.read_bytes() for p in (ROOT / 'timetables').glob(f'*/{group}.ics')], group)

    def test_root_links_every_group_and_redirects_only_when_there_is_one(self):
        html = (self.out / 'index.html').read_text(encoding='utf-8')
        groups = self.groups()
        for group in groups:
            self.assertIn(f'href="{group}/"', html)
        if len(groups) == 1:
            self.assertIn(f'<meta http-equiv="refresh" content="0; url={groups[0]}/">', html)
        else:
            self.assertNotIn('http-equiv="refresh"', html)

    def test_root_offers_the_faculties_first_and_a_group_search(self):
        html = (self.out / 'index.html').read_text(encoding='utf-8')
        for code in ('WCY', 'WEL', 'WIG', 'WML', 'WTC'):
            self.assertIn(f'data-facbtn="{code}"', html)
        self.assertIn('Wydział Cybernetyki', html)
        self.assertNotIn('Faculty of', html)
        self.assertIn('id="groupSearch"', html)
        self.assertIn('id="noResults"', html)
        for group in self.groups():
            self.assertIn(f'data-group="{group}"', html)

    def test_every_page_pins_its_inline_code_in_a_meta_csp(self):
        for page in self.pages():
            html = page.read_text(encoding='utf-8')
            m = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">', html)
            self.assertIsNotNone(m, page)
            csp = m.group(1)
            for block in re.findall(r'<script>(.*?)</script>', html, re.S):
                self.assertIn(sha(block), csp, f'{page}: script hash missing')
            for block in re.findall(r'<style>(.*?)</style>', html, re.S):
                self.assertIn(sha(block), csp, f'{page}: style hash missing')
            self.assertNotIn('frame-ancestors', csp, 'ignored in a meta CSP')
            # Redundant here (every source is https or 'self'), and WebKit applies it to http://127.0.0.1,
            # which breaks local previews and the browser tests. The header CSP keeps it.
            self.assertNotIn('upgrade-insecure-requests', csp)
            self.assertIn("default-src 'none'", csp)

    def test_pages_have_no_inline_style_attributes_or_leftover_placeholders(self):
        for page in self.pages():
            html = page.read_text(encoding='utf-8')
            self.assertNotIn('style="', html, page)
            self.assertNotIn('@@', html, page)

    def test_group_page_uses_relative_urls_for_its_calendar(self):
        html = (self.out / 'WCY26KY3S1' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('href="plan.ics"', html)
        self.assertIn("fetch('plan.ics'", html)
        self.assertNotIn('/plan.ics', html)

    def test_group_page_first_paint_shows_the_calendar_metadata(self):
        html = (self.out / 'WCY26KY3S1' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<title>Plan zajęć WCY26KY3S1</title>', html)
        self.assertIn('>WCY26KY3S1</h1>', html)
        self.assertIn('Plan zajęć &middot; semestr zimowy 2026/27', html)
        self.assertIn('<dd>28.09.2026 &ndash; 22.02.2027</dd>', html)
        self.assertIn('download="plan-WCY26KY3S1.ics"', html)

    def test_404_links_home_through_the_base_path(self):
        self.assertIn('href="/PlanWAT/"', (self.out / '404.html').read_text(encoding='utf-8'))

    def test_nginx_header_csp_covers_every_page_and_forbids_framing(self):
        conf = self.nginx.read_text()
        header = re.search(r'add_header Content-Security-Policy "([^"]+)"', conf).group(1)
        self.assertIn("frame-ancestors 'none'", header)
        self.assertIn('upgrade-insecure-requests', header)
        for page in self.pages():
            html = page.read_text(encoding='utf-8')
            for block in re.findall(r'<(?:script|style)>(.*?)</(?:script|style)>', html, re.S):
                self.assertIn(sha(block), header, page)


class BuildManyGroupsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.tt = self.tmp / 'timetables'

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def add(self, term, group, text):
        (self.tt / term).mkdir(parents=True, exist_ok=True)
        (self.tt / term / f'{group}.ics').write_text(text, encoding='utf-8', newline='')

    def test_each_group_gets_its_current_term_and_the_root_lists_all_groups(self):
        self.add('2026-27-zima', 'WCY26KY3S1', calendar('WCY26KY3S1', '2026-09-28', '2027-02-22', '2026-10-05'))
        self.add('2026-27-lato', 'WCY26KY3S1', calendar('WCY26KY3S1', '2027-03-01', '2027-06-21', '2027-03-02'))
        self.add('2026-27-zima', 'WCY25IY1S1', calendar('WCY25IY1S1', '2026-09-28', '2027-02-22', '2026-10-06'))
        out = self.tmp / 'site'
        build.build(self.tt, out, today=D(2027, 3, 10), nginx_conf=None)
        self.assertIn('X-PLAN-SEMESTER-START:20270301', (out / 'WCY26KY3S1' / 'plan.ics').read_text(encoding='utf-8'))
        self.assertIn('X-PLAN-SEMESTER-START:20260928', (out / 'WCY25IY1S1' / 'plan.ics').read_text(encoding='utf-8'))
        root = (out / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('http-equiv="refresh"', root)
        self.assertIn('href="WCY25IY1S1/"', root)
        self.assertIn('href="WCY26KY3S1/"', root)

    def test_a_single_group_root_redirects_straight_to_it(self):
        self.add('2026-27-zima', 'WCY26KY3S1', calendar('WCY26KY3S1', '2026-09-28', '2027-02-22', '2026-10-05'))
        out = self.tmp / 'site'
        build.build(self.tt, out, today=D(2026, 10, 15), nginx_conf=None)
        root = (out / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<meta http-equiv="refresh" content="0; url=WCY26KY3S1/">', root)
        self.assertIn('href="WCY26KY3S1/"', root)

    def test_rejects_a_file_whose_name_disagrees_with_its_group(self):
        self.add('2026-27-zima', 'WCY26KY3S1', calendar('WCY26KY3S2', '2026-09-28', '2027-02-22', '2026-10-05'))
        with self.assertRaisesRegex(build.BuildError, 'WCY26KY3S2'):
            build.build(self.tt, self.tmp / 'site', today=D(2026, 10, 15), nginx_conf=None)

    def test_rejects_group_codes_that_are_not_plain_letters_and_digits(self):
        self.add('2026-27-zima', 'wcy-26', calendar('wcy-26', '2026-09-28', '2027-02-22', '2026-10-05'))
        with self.assertRaisesRegex(build.BuildError, 'wcy-26'):
            build.build(self.tt, self.tmp / 'site', today=D(2026, 10, 15), nginx_conf=None)

    def test_rejects_a_malformed_calendar(self):
        self.add('2026-27-zima', 'WCY26KY3S1', 'BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:x\r\nEND:VCALENDAR\r\n')
        with self.assertRaises(build.BuildError):
            build.build(self.tt, self.tmp / 'site', today=D(2026, 10, 15), nginx_conf=None)

    def test_escapes_metadata_in_html(self):
        self.add('2026-27-zima', 'WCY26KY3S1',
                 calendar('WCY26KY3S1', '2026-09-28', '2027-02-22', '2026-10-05').replace(
                     'X-PLAN-FACULTY:Cybernetyki', 'X-PLAN-FACULTY:<script>alert(1)</script>'))
        out = self.tmp / 'site'
        build.build(self.tt, out, today=D(2026, 10, 15), nginx_conf=None)
        html = (out / 'WCY26KY3S1' / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', html)


if __name__ == '__main__':
    unittest.main()
