"""Tests for build.py (the static site generator).

Run: python3 -m unittest discover -s tests -v
"""
import base64
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools'))
import build  # noqa: E402
import scrub_staff  # noqa: E402

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
        self.assertEqual(build.faculty_of('WLO26AX1S1'), 'WLO')
        self.assertEqual(build.faculty_of('WCY26_Fiz1a'), 'WCY')
        self.assertEqual(build.faculty_of('WMT26AX1S0'), 'WML')
        self.assertEqual(build.faculty_of('WME26MX1S1'), 'WIM')
        self.assertEqual(build.faculty_of('IOE26HX1S0'), 'IOE')

    def test_unknown_prefixes_fall_back_to_other(self):
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

    def page_code(self, rel):
        """The page plus everything it loads from assets/: the parts that used to sit inline in every page."""
        text = (self.out / rel).read_text(encoding='utf-8')
        for url in re.findall(r'(?:\bsrc|href)="((?:\.\./)?assets/[^"]+)"', text):
            text += (self.out / url.replace('../', '', 1)).read_text(encoding='utf-8')
        return text

    def test_writes_group_page_calendar_index_and_404(self):
        for rel in ('index.html', '404.html', 'mapa/index.html', 'WCY26KY3S1/index.html', 'WCY26KY3S1/plan.ics'):
            self.assertTrue((self.out / rel).is_file(), rel)

    def test_group_calendar_is_a_byte_copy_of_the_current_term(self):
        self.assertEqual((self.out / 'WCY26KY3S1' / 'plan.ics').read_bytes(),
                         (ROOT / 'timetables' / '2026-27-zima' / 'WCY26KY3S1.ics').read_bytes())

    def test_offline_worker_manifests_and_icons(self):
        sw = (self.out / 'sw.js').read_text(encoding='utf-8')
        self.assertRegex(sw, r"var VERSION = '[0-9a-f]{16}';")
        self.assertNotIn('@@', sw)
        for name in ('icon.svg', 'icon-192.png', 'icon-512.png', 'maskable-512.png', 'apple-touch-icon.png'):
            self.assertTrue((self.out / 'icons' / name).is_file(), name)
        root = json.loads((self.out / 'manifest.webmanifest').read_text(encoding='utf-8'))
        self.assertEqual((root['start_url'], root['scope']), ('./', './'))
        group = json.loads((self.out / 'WCY26KY3S1' / 'manifest.webmanifest').read_text(encoding='utf-8'))
        self.assertEqual((group['start_url'], group['scope'], group['short_name']), ('./', '../', 'WCY26KY3S1'))
        for icon in group['icons']:
            self.assertTrue(icon['src'].startswith('../icons/'), icon)
            self.assertTrue((self.out / 'WCY26KY3S1' / icon['src']).resolve().is_file(), icon)
        self.assertIn({'maskable'}, [{i['purpose']} for i in group['icons']])
        page = self.page_code('WCY26KY3S1/index.html')
        self.assertIn('<link rel="manifest" href="manifest.webmanifest">', page)
        self.assertIn("navigator.serviceWorker.register('../sw.js', { scope: '../' })", page)
        index = self.page_code('index.html')
        self.assertIn("navigator.serviceWorker.register('sw.js', { scope: './' })", index)

    def test_manifests_offer_shortcuts_to_the_plans_and_the_map(self):
        root_dir = self.out
        root = json.loads((root_dir / 'manifest.webmanifest').read_text(encoding='utf-8'))
        self.assertEqual([s['name'] for s in root['shortcuts']], ['Wszystkie plany', 'Mapa kampusu'])
        self.assertEqual([s['url'] for s in root['shortcuts']], ['./', 'mapa/'])
        for shortcut in root['shortcuts']:
            self.assertTrue((root_dir / shortcut['url']).resolve().is_dir(), shortcut['url'])
            for icon in shortcut['icons']:
                self.assertTrue(icon['src'].startswith('icons/'), icon['src'])
                self.assertTrue((root_dir / icon['src']).resolve().is_file(), icon['src'])

        group_dir = root_dir / 'WCY26KY3S1'
        group = json.loads((group_dir / 'manifest.webmanifest').read_text(encoding='utf-8'))
        self.assertEqual([s['name'] for s in group['shortcuts']], ['Mój plan', 'Mapa kampusu'])
        self.assertEqual([s['url'] for s in group['shortcuts']], ['./', '../mapa/'])
        for shortcut in group['shortcuts']:
            self.assertTrue((group_dir / shortcut['url']).resolve().is_dir(), shortcut['url'])
            for icon in shortcut['icons']:
                self.assertTrue(icon['src'].startswith('../icons/'), icon['src'])
                self.assertTrue((group_dir / icon['src']).resolve().is_file(), icon['src'])

    def test_root_offers_a_faculty_year_group_finder(self):
        html = (self.out / 'index.html').read_text(encoding='utf-8')
        for marker in ('id="findGroup"', 'aria-controls="groupFinder"', 'id="groupFinder"',
                       'aria-labelledby="finderTitle"', 'aria-describedby="finderLead"',
                       'id="finderStep"', 'id="finderBack"', 'id="finderBody"'):
            self.assertIn(marker, html)
        self.assertIn('Nie znasz kodu grupy?', html)
        self.assertIn('Znajdź ją po wydziale i roku naboru', html)
        self.assertIn('Krok 1 z 3', html)
        for group in self.groups():
            row = re.search(r'<li class="row" data-group="' + re.escape(group) +
                            r'" data-fac="([A-Z]+)" data-year="(\d{4}|)">', html)
            self.assertIsNotNone(row, group)
            prefix = build.year_of(group)
            expected = str(2000 + int(prefix[3:5])) if prefix else ''
            self.assertEqual(row.group(2), expected, group)
            self.assertIn(f'<a class="group" href="{group}/">', html)

    def test_public_site_files(self):
        robots = (self.out / 'robots.txt').read_text(encoding='utf-8')
        self.assertIn('User-agent: *', robots)
        self.assertIn('Disallow: /PlanWAT/data/', robots)
        self.assertIn('Disallow: /PlanWAT/dev/', robots)
        self.assertNotIn('Disallow: /\n', robots)
        sec = (self.out / '.well-known' / 'security.txt').read_text(encoding='utf-8')
        self.assertIn('Contact: https://github.com/kilerdevs/PlanWAT/security/advisories/new', sec)
        expires = dt.datetime.strptime(re.search(r'^Expires: (\S+)$', sec, re.M).group(1), '%Y-%m-%dT%H:%M:%SZ')
        self.assertTrue(dt.datetime(2026, 10, 15) < expires < dt.datetime(2027, 10, 15))
        privacy = (self.out / 'prywatnosc' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('nigdy nie poprosi Cię o adres e-mail', privacy)
        self.assertIn("script-src 'none'", self.meta_csp('prywatnosc/index.html'))
        for rel in ('index.html', 'WCY26KY3S1/index.html'):
            html = (self.out / rel).read_text(encoding='utf-8')
            self.assertIn('nigdy nie poprosi Cię o adres e-mail', html, rel)
            self.assertRegex(html, r'href="(\.\./)?prywatnosc/"', rel)
        self.assertNotIn('nofollow', privacy)  # only the dev preview asks not to be indexed

    def test_reminder_calendar_has_one_alarm_per_class_and_valid_lines(self):
        raw = (self.out / 'WCY26KY3S1' / build.REMINDER_FILE).read_bytes()
        text = raw.decode('utf-8')
        self.assertEqual(text.count('BEGIN:VALARM'), text.count('BEGIN:VEVENT'))
        self.assertGreater(text.count('BEGIN:VALARM'), 0)
        self.assertEqual(text.count('TRIGGER:-PT15M'), text.count('BEGIN:VEVENT'))
        self.assertIn('X-WR-CALNAME:Plan zajęć WCY26KY3S1 (przypomnienia)', text)
        lines = raw.split(b'\r\n')
        self.assertEqual(lines[-1], b'')
        self.assertNotIn(b'\n', b''.join(lines))  # CRLF only
        self.assertTrue(all(len(l) <= 75 for l in lines), 'a line longer than 75 octets')
        self.assertIn('BEGIN:VALARM\r\nACTION:DISPLAY\r\nDESCRIPTION:Matematyka I\r\nTRIGGER:-PT15M\r\nEND:VALARM\r\nEND:VEVENT', text)
        # the same events, and every group gets one
        plain = (self.out / 'WCY26KY3S1' / 'plan.ics').read_text(encoding='utf-8')
        self.assertEqual(re.findall(r'^UID:[^\r\n]*', text, re.M), re.findall(r'^UID:[^\r\n]*', plain, re.M))
        for group in self.groups():
            self.assertTrue((self.out / group / build.REMINDER_FILE).is_file(), group)

    def groups(self):
        return sorted({p.stem for p in (ROOT / 'timetables').glob('*/*.ics')})

    def test_every_group_in_the_repository_gets_a_page_and_its_calendar(self):
        for group in self.groups():
            self.assertTrue((self.out / group / 'index.html').is_file(), group)
            calendar = (self.out / group / 'plan.ics').read_bytes()
            self.assertIn(calendar, [build.clip_to_term(p.read_bytes(), p.parent.name) for p in (ROOT / 'timetables').glob(f'*/{group}.ics')], group)

    def test_root_links_every_group_and_redirects_only_when_there_is_one(self):
        html = (self.out / 'index.html').read_text(encoding='utf-8')
        groups = self.groups()
        for group in groups:
            self.assertIn(f'href="{group}/"', html)
        if len(groups) == 1:
            self.assertIn(f'<meta http-equiv="refresh" content="0; url={groups[0]}/">', html)
        else:
            self.assertNotIn('http-equiv="refresh"', html)

    def test_root_has_faculty_filters_stars_and_live_cards_support(self):
        html = self.page_code('index.html')
        self.assertIn('data-fac="WCY"', html)
        self.assertIn('data-star="WCY26KY3S1"', html)
        self.assertIn('id="liveCards"', html)
        self.assertIn('window.PlanICS', html)
        self.assertIn("connect-src 'self'", html)

    def test_root_lists_collapsed_faculty_sections_and_a_group_search(self):
        html = (self.out / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('data-facbtn', html)
        self.assertNotIn('@@', html)
        self.assertIn('id="groupSearch"', html)
        self.assertIn('id="noResults"', html)
        self.assertIn('data-fac-section="WCY"', html)
        self.assertIn('data-fac-section="WLO"', html)
        self.assertIn('WLO &middot; Wydział Bezpieczeństwa, Logistyki i Zarządzania', html)
        self.assertIn('<details class="fac-sec"', html)
        self.assertNotIn('<details class="fac-sec" open', html)
        self.assertNotIn('<details open', html)
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
        html = self.page_code('WCY26KY3S1/index.html')
        self.assertIn('href="plan.ics"', html)
        self.assertIn("fetch(planFile", html)
        self.assertNotIn('/plan.ics', html)

    def test_shared_assets_are_content_addressed_sri_pinned_and_allowed_by_origin(self):
        for rel in ('index.html', 'WCY26KY3S1/index.html', 'mapa/index.html'):
            html = (self.out / rel).read_text(encoding='utf-8')
            tags = re.findall(r'<(?:link|script)\b[^>]*\b(?:href|src)="([^"]*assets/[^"]+)"[^>]*\bintegrity="sha256-([A-Za-z0-9+/=]+)"', html)
            self.assertEqual(len(tags), 3, rel)  # the stylesheet and the two scripts, nothing else
            csp = self.meta_csp(rel)
            self.assertRegex(csp, r"script-src 'self' ")
            self.assertRegex(csp, r"style-src 'self' ")
            for url, digest in tags:
                self.assertTrue(url.startswith(('assets/', '../assets/')), url)  # relative: any base path works
                body = (self.out / url.replace('../', '', 1)).read_bytes()
                self.assertEqual(base64.b64encode(hashlib.sha256(body).digest()).decode(), digest, url)
                name_hash = re.search(r'-([0-9a-f]{8})\.(?:js|css)$', url).group(1)
                self.assertTrue(hashlib.sha256(body).hexdigest().startswith(name_hash), url)

    def test_group_pages_share_one_copy_of_the_style_and_scripts(self):
        reference = None
        for group in self.groups():
            html = (self.out / group / 'index.html').read_text(encoding='utf-8')
            urls = set(re.findall(r'(?:\bhref|\bsrc)="((?:\.\./)?assets/[^"]+)"', html))
            if reference is None:
                reference = urls
            self.assertEqual(reference, urls, group)  # every group page loads the same three files
        self.assertEqual(len(reference), 3, reference)
        on_disk = {f'assets/{p.name}' for p in (self.out / 'assets').iterdir()}
        referenced = {url.replace('../', '', 1) for url in reference}
        for page in self.pages():
            referenced |= set(re.findall(r'"((?:\.\./)?assets/[^"]+)"', page.read_text(encoding='utf-8')))
            referenced = {url.replace('../', '', 1) for url in referenced}
        self.assertEqual(on_disk, referenced)  # nothing is written that no page loads, and nothing is missing
        sw = (self.out / 'sw.js').read_text(encoding='utf-8')
        for name in on_disk:
            self.assertIn(f"'{name}'", sw)  # the worker precaches them for offline
        for page in ('prywatnosc/index.html', '404.html'):
            self.assertNotIn('assets/', (self.out / page).read_text(encoding='utf-8'), page)

    def test_coverage_chart_counts_exactly_the_groups_the_build_publishes(self):
        published = [p.parent.name for p in self.out.glob('*/index.html')
                     if p.parent.name not in (build.MAP_DIR, build.PRIVACY_DIR)]
        counts = {}
        for group in published:
            counts[build.faculty_of(group)] = counts.get(build.faculty_of(group), 0) + 1
        svg = (self.out / 'pokrycie-wydzialow.svg').read_text(encoding='utf-8')
        self.assertIn(build.plural_grup(sum(counts.values())), svg)
        for code, n in counts.items():
            self.assertIn(f'>{code if code != "OTHER" else "Pozostałe"}<', svg)
            self.assertRegex(svg, rf'{code} {n}\b')
        self.assertNotIn('@@', svg)
        readme = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('https://kilerdevs.github.io/PlanWAT/pokrycie-wydzialow.svg', readme)
        self.assertNotIn('docs/diagrams/pokrycie-wydzialow.svg', readme)
        self.assertFalse((ROOT / 'docs' / 'diagrams' / 'pokrycie-wydzialow.svg').exists())  # never a stale copy again

    def test_group_page_first_paint_shows_the_calendar_metadata(self):
        html = (self.out / 'WCY26KY3S1' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<title>Plan zajęć WCY26KY3S1 – Wydział Cybernetyki, WAT | PlanWAT</title>', html)
        self.assertIn('>WCY26KY3S1</h1>', html)
        self.assertIn('Plan zajęć &middot; semestr zimowy 2026/27', html)
        self.assertIn('<dd>28.09.2026 &ndash; 22.02.2027</dd>', html)
        self.assertIn('download="plan-WCY26KY3S1.ics"', html)

    def meta_csp(self, rel):
        html = (self.out / rel).read_text(encoding='utf-8')
        return re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">', html).group(1)

    def test_only_the_map_page_may_load_the_map_engine_and_tiles(self):
        csp = self.meta_csp('mapa/index.html')
        self.assertRegex(csp, r"script-src [^;]*https://unpkg\.com")
        self.assertRegex(csp, r"connect-src 'self' https://tiles\.openfreemap\.org")
        self.assertRegex(csp, r"img-src data: blob: https://tiles\.openfreemap\.org")
        self.assertIn('worker-src blob:', csp)
        for rel in ('index.html', '404.html', 'prywatnosc/index.html', 'WCY26KY3S1/index.html'):
            csp = self.meta_csp(rel)
            for source in ('unpkg.com', 'openfreemap', 'blob:'):
                self.assertNotIn(source, csp, rel)

    def test_only_the_front_and_group_pages_may_register_the_worker_and_manifest(self):
        for rel in ('index.html', 'WCY26KY3S1/index.html'):
            csp = self.meta_csp(rel)
            self.assertIn("worker-src 'self';", csp, rel)
            self.assertIn("manifest-src 'self';", csp, rel)
            self.assertIn("img-src data: 'self';", csp, rel)
        for rel in ('404.html', 'prywatnosc/index.html'):
            self.assertNotIn('manifest-src', self.meta_csp(rel), rel)
        self.assertIn("manifest-src 'self';", self.meta_csp('mapa/index.html'))
        self.assertNotIn("'self'", self.meta_csp('mapa/index.html').split('worker-src')[1].split(';')[0])

    def test_map_engine_is_pinned_by_subresource_integrity(self):
        html = (self.out / 'mapa' / 'index.html').read_text(encoding='utf-8')
        tags = re.findall(r'<(?:script|link)[^>]+unpkg\.com[^>]*>', html)
        self.assertEqual(len(tags), 2)
        for tag in tags:
            self.assertRegex(tag, r'integrity="sha384-[A-Za-z0-9+/=]{64}"')
            self.assertIn('crossorigin="anonymous"', tag)
            self.assertIn('@4.7.1/', tag)

    def test_map_links_use_relative_urls(self):
        html = self.page_code('mapa/index.html')
        self.assertIn('href="../"', html)
        self.assertIn("'../' + encodeURIComponent(group) + '/plan.ics'", html)
        self.assertIn('href="mapa/"', (self.out / 'index.html').read_text(encoding='utf-8'))
        group = self.page_code('WCY26KY3S1/index.html')
        self.assertIn("'../mapa/?b='", group)
        self.assertIn("'../mapa/?g='", group)

    def test_404_links_home_through_the_base_path(self):
        self.assertIn('href="/PlanWAT/"', (self.out / '404.html').read_text(encoding='utf-8'))

    def test_404_may_look_up_the_group_list_to_fix_a_mistyped_link(self):
        html = (self.out / '404.html').read_text(encoding='utf-8')
        self.assertIn('data-base="/PlanWAT"', html)
        self.assertIn("root + '/data/groups.json'", html)
        csp = self.meta_csp('404.html')
        self.assertIn("connect-src 'self';", csp)
        script = re.search(r'<script>(.*?)</script>', html, re.S).group(1)
        self.assertIn(sha(script), csp)
        self.assertNotIn('innerHTML', script)  # the typed address only ever reaches the page as text

    def test_nginx_header_csp_covers_every_page_and_forbids_framing(self):
        conf = self.nginx.read_text()
        header = re.search(r'add_header Content-Security-Policy "([^"]+)"', conf).group(1)
        self.assertIn("frame-ancestors 'none'", header)
        self.assertIn('upgrade-insecure-requests', header)
        # pages that share their styles and scripts load them by origin (a meta hash cannot cover a file),
        # so the header of the self-hosted deployment has to allow the same
        self.assertIn("script-src 'self'", header)
        self.assertIn("style-src 'self'", header)
        for page in self.pages():
            html = page.read_text(encoding='utf-8')
            for block in re.findall(r'<(?:script|style)>(.*?)</(?:script|style)>', html, re.S | re.I):
                self.assertIn(sha(block), header, page)
        self.assertIn('https://unpkg.com', header)
        self.assertIn("worker-src 'self' blob:", header)
        self.assertIn("manifest-src 'self'", header)
        self.assertIn("connect-src 'self' https://tiles.openfreemap.org", header)


    def test_indexable_pages_have_their_own_title_description_and_social_card(self):
        pages = [self.out / 'index.html', self.out / build.MAP_DIR / 'index.html', self.out / build.PRIVACY_DIR / 'index.html']
        pages += sorted(self.out.glob('*/plan.ics'))
        titles, descriptions = set(), set()
        for page in pages:
            html = (page.parent / 'index.html' if page.name == 'plan.ics' else page).read_text(encoding='utf-8')
            title = re.search(r'<title>([^<]+)</title>', html).group(1)
            description = re.search(r'<meta name="description" content="([^"]+)">', html).group(1)
            self.assertIn('PlanWAT', title, page)
            self.assertGreater(len(description), 60, page)
            self.assertIn(f'<meta property="og:title" content="{title}">', html, page)
            self.assertIn('<meta property="og:locale" content="pl_PL">', html, page)
            titles.add(title)
            descriptions.add(description)
        self.assertEqual(len(titles), len(pages), 'every indexable page has its own title')
        self.assertEqual(len(descriptions), len(pages), 'and its own description')

    def test_front_page_names_the_site_and_the_university(self):
        html = (self.out / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<title>Plan zajęć WAT', html)
        self.assertIn('Wojskowej Akademii Technicznej', html)
        ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual((ld['@type'], ld['name']), ('WebSite', 'PlanWAT'))
        self.assertIn('Plan zajęć WAT', ld['alternateName'])
        self.assertNotIn('url', ld)  # no --site-url: nothing absolute is guessed
        self.assertNotIn('rel="canonical"', html)
        self.assertFalse((self.out / 'sitemap.xml').exists())
        # a real favicon file (search engines do not take a data: URL) that the page's CSP allows
        self.assertIn('<link rel="icon" href="icons/icon.svg" type="image/svg+xml">', html)
        self.assertTrue((self.out / 'icons' / 'icon.svg').is_file())
        self.assertIn("img-src data: 'self'", self.meta_csp('index.html'))

    def test_the_group_page_script_keeps_the_built_title(self):
        # search engines index the title after scripts run: the page must not shorten it again
        self.assertNotIn('document.title =', (self.out / 'WCY26KY3S1' / 'index.html').read_text(encoding='utf-8'))


class SearchEngineTest(unittest.TestCase):
    """--site-url: canonical URLs, absolute social cards, structured data and the sitemap."""
    SITE = 'https://kilerdevs.github.io/PlanWAT'

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.tt = self.tmp / 'timetables'
        for group, faculty in (('WCY26KY3S1', 'Cybernetyki'), ('ABC26X1', 'Chemii')):
            (self.tt / '2026-27-zima').mkdir(parents=True, exist_ok=True)
            text = calendar(group, '2026-09-28', '2027-02-22', '2026-10-05').replace(
                'X-PLAN-FACULTY:Cybernetyki', f'X-PLAN-GENERATED:20261011\r\nX-PLAN-FACULTY:{faculty}')
            (self.tt / '2026-27-zima' / f'{group}.ics').write_text(text, encoding='utf-8', newline='')

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def make(self, **kw):
        out = self.tmp / 'site'
        build.build(self.tt, out, today=D(2026, 10, 15), base_path='/PlanWAT', nginx_conf=None,
                    state_path=self.tmp / 'no-state.json', **kw)
        return out

    def test_pages_carry_canonical_urls_absolute_cards_and_breadcrumbs(self):
        out = self.make(site_url=self.SITE + '/')  # a trailing slash is tolerated
        html = (out / 'WCY26KY3S1' / 'index.html').read_text(encoding='utf-8')
        self.assertIn(f'<link rel="canonical" href="{self.SITE}/WCY26KY3S1/">', html)
        self.assertIn(f'<meta property="og:url" content="{self.SITE}/WCY26KY3S1/">', html)
        self.assertIn(f'<meta property="og:image" content="{self.SITE}/icons/icon-512.png">', html)
        ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(ld['@type'], 'BreadcrumbList')
        self.assertEqual([i['item'] for i in ld['itemListElement']], [f'{self.SITE}/', f'{self.SITE}/WCY26KY3S1/'])
        for rel, url in (('index.html', ''), (f'{build.MAP_DIR}/index.html', f'{build.MAP_DIR}/'),
                         (f'{build.PRIVACY_DIR}/index.html', f'{build.PRIVACY_DIR}/')):
            self.assertIn(f'<link rel="canonical" href="{self.SITE}/{url}">', (out / rel).read_text(encoding='utf-8'))
        # the structured data and social cards add no executable inline code: every page keeps its pinned CSP
        for page in out.rglob('index.html'):
            text = page.read_text(encoding='utf-8')
            csp = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">', text).group(1)
            for block in re.findall(r'<script>(.*?)</script>', text, re.S | re.I):
                self.assertIn(sha(block), csp, page)

    def test_a_group_of_an_unlisted_faculty_is_named_from_its_calendar(self):
        out = self.make(site_url=self.SITE)
        html = (out / 'ABC26X1' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<title>Plan zajęć ABC26X1 – Wydział Chemii, WAT | PlanWAT</title>', html)
        self.assertIn('(Wydział Chemii WAT), term 2026-09-28: zajęcia na dziś', html)

    def test_the_sitemap_lists_every_page_and_robots_points_at_it(self):
        out = self.make(site_url=self.SITE)
        sitemap = (out / 'sitemap.xml').read_text(encoding='utf-8')
        locs = re.findall(r'<loc>([^<]+)</loc>', sitemap)
        self.assertEqual(locs, [f'{self.SITE}/', f'{self.SITE}/{build.MAP_DIR}/', f'{self.SITE}/{build.PRIVACY_DIR}/',
                                f'{self.SITE}/ABC26X1/', f'{self.SITE}/WCY26KY3S1/'])
        self.assertIn(f'<loc>{self.SITE}/WCY26KY3S1/</loc><lastmod>2026-10-11</lastmod>', sitemap)
        self.assertIn(f'<loc>{self.SITE}/</loc><lastmod>2026-10-11</lastmod>', sitemap)
        self.assertTrue(sitemap.startswith('<?xml version="1.0" encoding="UTF-8"?>\n<urlset'))
        self.assertIn(f'Sitemap: {self.SITE}/sitemap.xml', (out / 'robots.txt').read_text(encoding='utf-8'))

    def test_the_dev_preview_gets_no_sitemap(self):
        out = self.make(site_url=self.SITE + '/dev', noindex=True)
        self.assertFalse((out / 'sitemap.xml').exists())
        self.assertEqual((out / 'robots.txt').read_text(encoding='utf-8'), 'User-agent: *\nDisallow: /\n')

    def test_rejects_a_site_url_that_is_not_absolute(self):
        with self.assertRaisesRegex(build.BuildError, 'site-url'):
            self.make(site_url='kilerdevs.github.io/PlanWAT')

    def test_structured_data_cannot_close_its_script_block(self):
        self.assertEqual(build._json_ld({'name': '</script><script>x'}), '{"name":"\\u003c/script>\\u003cscript>x"}')


class RemindersTest(unittest.TestCase):
    def test_folds_long_lines_on_character_boundaries_and_keeps_existing_alarms(self):
        long = 'Ż' * 60
        cal = ('BEGIN:VCALENDAR\nX-WR-CALNAME:X\nBEGIN:VEVENT\nSUMMARY:' + long + '\nEND:VEVENT\n'
               'BEGIN:VEVENT\nSUMMARY:B\nBEGIN:VALARM\nTRIGGER:-PT5M\nEND:VALARM\nEND:VEVENT\nEND:VCALENDAR\n')
        out = build.with_reminders(cal.encode('utf-8'))
        for line in out.split(b'\r\n'):
            self.assertLessEqual(len(line), 75)
            line.decode('utf-8')  # no character split across a fold
        text = out.decode('utf-8')
        self.assertEqual(text.count('BEGIN:VALARM'), 2)  # the second event keeps its own and gets no extra
        self.assertIn('DESCRIPTION:' + long, text.replace('\r\n ', ''))
        self.assertIn('X-WR-CALNAME:X (przypomnienia)', text)


class BuildManyGroupsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.tt = self.tmp / 'timetables'

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def add(self, term, group, text):
        (self.tt / term).mkdir(parents=True, exist_ok=True)
        (self.tt / term / f'{group}.ics').write_text(text, encoding='utf-8', newline='')

    def test_a_group_with_two_terms_gets_a_switcher_and_the_other_terms_calendar(self):
        self.add('2026-27-zima', 'WCY26KY3S1', calendar('WCY26KY3S1', '2026-09-28', '2027-02-22', '2026-10-05'))
        self.add('2026-27-lato', 'WCY26KY3S1', calendar('WCY26KY3S1', '2027-03-01', '2027-06-21', '2027-03-02'))
        self.add('2026-27-zima', 'WCY25IY1S1', calendar('WCY25IY1S1', '2026-09-28', '2027-02-22', '2026-10-06'))
        out = self.tmp / 'site'
        build.build(self.tt, out, today=D(2026, 10, 14), nginx_conf=None)
        page = (out / 'WCY26KY3S1' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('id="termSwitch"', page)
        self.assertIn('<a href="./" data-term="2026-27-zima" aria-current="true">Zima 2026/27</a>', page)
        self.assertIn('data-term="2026-27-lato">Lato 2026/27</a>', page)
        self.assertIn('X-PLAN-SEMESTER-START:20270301',
                      (out / 'WCY26KY3S1' / 'plan-2026-27-lato.ics').read_text(encoding='utf-8'))
        self.assertTrue((out / 'WCY26KY3S1' / 'plan-2026-27-lato-przypomnienia.ics').exists())
        self.assertNotIn('termSwitch', (out / 'WCY25IY1S1' / 'index.html').read_text(encoding='utf-8').split('<script>')[0])
        self.assertFalse((out / 'WCY25IY1S1' / 'plan-2026-27-lato.ics').exists())

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

    def test_group_page_shows_when_the_plan_was_updated_and_checked(self):
        self.add('2026-27-zima', 'WCY26KY3S1', calendar('WCY26KY3S1', '2026-09-28', '2027-02-22', '2026-10-05'))
        state = self.tmp / 'state.json'
        state.write_text('{"version":1,"groups":{"WCY26KY3S1":{"changed":"2026-10-13T17:35:00","checked":"2026-10-14T01:40:00"}}}')
        out = self.tmp / 'site'
        build.build(self.tt, out, today=D(2026, 10, 15), nginx_conf=None, state_path=state)
        html = (out / 'WCY26KY3S1' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<dt>Zaktualizowano</dt><dd>13.10.2026</dd>', html)
        self.assertIn('<dt>Sprawdzono</dt><dd>14.10.2026 03:40</dd>', html)
        self.assertIn('pozostanie darmowy', html)

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

    def test_calendars_that_name_staff_are_refused(self):
        for extra in ('CONTACT:Test Person', 'DESCRIPTION:Wykład\\nProwadzący: Test Person'):
            with self.subTest(extra=extra):
                self.add('2026-27-zima', 'WCY26KY3S1', calendar('WCY26KY3S1', '2026-09-28', '2027-02-22', '2026-10-05'))
                path = self.tt / '2026-27-zima' / 'WCY26KY3S1.ics'
                path.write_text(path.read_text(encoding='utf-8').replace('SUMMARY:Matematyka', 'SUMMARY:Matematyka\r\n' + extra),
                                encoding='utf-8', newline='')
                with self.assertRaisesRegex(build.BuildError, 'must not name staff'):
                    build.build(self.tt, self.tmp / 'site', today=D(2026, 10, 15), nginx_conf=None)

    def test_a_location_that_names_a_person_is_refused(self):
        for room in (r'dr inż. Nazwisko Imie\, 255 S', r'mgr inż. Nazwisko Imie\;mgr Inny Osoba\, 3/ 23A', 'prof. dr hab. Nazwisko Imie',
                     'ANazwisko', r'ANazwisko\;314 S', '�Nazwisko', 'ANazwisko-Drugie'):
            with self.subTest(room=room):
                self.add('2026-27-zima', 'WCY26KY3S1', calendar('WCY26KY3S1', '2026-09-28', '2027-02-22', '2026-10-05'))
                path = self.tt / '2026-27-zima' / 'WCY26KY3S1.ics'
                path.write_text(path.read_text(encoding='utf-8').replace('SUMMARY:Matematyka', 'SUMMARY:Matematyka\r\nLOCATION:' + room),
                                encoding='utf-8', newline='')
                with self.assertRaisesRegex(build.BuildError, 'LOCATION names a person'):
                    build.build(self.tt, self.tmp / 'site', today=D(2026, 10, 15), nginx_conf=None)

    def test_ordinary_rooms_are_not_mistaken_for_people(self):
        for room in ('314 S', r'1.9/ 16\;1.10/ 16', 'aula/ 135', '7a-b Bibl.', '1002 HILTON', 'Teams', 'Wyjazd', 'WAT', 'ST.nr 1(PWC2)'):
            self.assertFalse(build._names_person(room), room)

    def test_a_subject_that_merely_starts_with_prowadzenie_is_fine(self):
        self.add('2026-27-zima', 'WCY26KY3S1', calendar('WCY26KY3S1', '2026-09-28', '2027-02-22', '2026-10-05',
                                                          'DESCRIPTION:Wykład'))
        path = self.tt / '2026-27-zima' / 'WCY26KY3S1.ics'
        path.write_text(path.read_text(encoding='utf-8').replace('SUMMARY:Matematyka', 'SUMMARY:Prowadzenie negocjacji'),
                        encoding='utf-8', newline='')
        build.build(self.tt, self.tmp / 'site', today=D(2026, 10, 15), nginx_conf=None)

    def test_worker_version_follows_the_content_but_not_the_security_txt_date(self):
        self.add('2026-27-zima', 'WCY26KY3S1', calendar('WCY26KY3S1', '2026-09-28', '2027-02-22', '2026-10-05'))
        version = lambda out: re.search(r"VERSION = '(\w+)'", (out / 'sw.js').read_text(encoding='utf-8')).group(1)  # noqa: E731
        a, b, c = self.tmp / 'a', self.tmp / 'b', self.tmp / 'c'
        build.build(self.tt, a, today=D(2026, 10, 15), nginx_conf=None)
        build.build(self.tt, b, today=D(2026, 10, 16), nginx_conf=None)
        self.assertNotEqual((a / '.well-known' / 'security.txt').read_text(), (b / '.well-known' / 'security.txt').read_text())
        self.assertEqual(version(a), version(b))
        self.add('2026-27-zima', 'WCY26KY3S1', calendar('WCY26KY3S1', '2026-09-28', '2027-02-22', '2026-10-06'))
        build.build(self.tt, c, today=D(2026, 10, 15), nginx_conf=None)
        self.assertNotEqual(version(a), version(c))

    def test_noindex_marks_every_page_and_closes_robots_txt(self):
        self.add('2026-27-zima', 'WCY26KY3S1', calendar('WCY26KY3S1', '2026-09-28', '2027-02-22', '2026-10-05'))
        out = self.tmp / 'site'
        build.build(self.tt, out, today=D(2026, 10, 15), nginx_conf=None, noindex=True)
        self.assertEqual((out / 'robots.txt').read_text(), 'User-agent: *\nDisallow: /\n')
        for page in out.rglob('*.html'):
            html = page.read_text(encoding='utf-8')
            self.assertIn('<meta name="robots" content="noindex, nofollow">', html, page)
            csp = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">', html).group(1)
            for block in re.findall(r'<(?:script|style)>(.*?)</(?:script|style)>', html, re.S | re.I):
                self.assertIn(sha(block), csp, page)  # the extra meta tag leaves the hashes valid

    def test_rejects_groups_named_like_the_site_folders(self):
        for name in ('icons', 'prywatnosc', 'assets'):
            self.add('2026-27-zima', name, calendar(name, '2026-09-28', '2027-02-22', '2026-10-05'))
            with self.assertRaisesRegex(build.BuildError, 'reserved'):
                build.build(self.tt, self.tmp / 'site', today=D(2026, 10, 15), nginx_conf=None)
            (self.tt / '2026-27-zima' / f'{name}.ics').unlink()

    def test_rejects_a_group_named_like_the_data_folder(self):
        self.add('2026-27-zima', 'data', calendar('data', '2026-09-28', '2027-02-22', '2026-10-05'))
        with self.assertRaisesRegex(build.BuildError, 'reserved'):
            build.build(self.tt, self.tmp / 'site', today=D(2026, 10, 15), nginx_conf=None)

    def test_rejects_a_group_named_like_the_map_page(self):
        self.add('2026-27-zima', 'mapa', calendar('mapa', '2026-09-28', '2027-02-22', '2026-10-05'))
        with self.assertRaisesRegex(build.BuildError, 'reserved'):
            build.build(self.tt, self.tmp / 'site', today=D(2026, 10, 15), nginx_conf=None)

    def test_writes_the_group_list_and_year_files(self):
        one = 'LOCATION:1.16/ 16\\;1.17/16'
        self.add('2026-27-zima', 'WCY26KY3S1', calendar('WCY26KY3S1', '2026-09-28', '2027-02-22', '2026-10-05', one))
        self.add('2026-27-zima', 'WCY26KY1S1', calendar('WCY26KY1S1', '2026-09-28', '2027-02-22', '2026-10-05', 'LOCATION:1.16/16'))
        self.add('2026-27-zima', 'Inne', calendar('Inne', '2026-09-28', '2027-02-22', '2026-10-06', 'LOCATION:-'))
        out = self.tmp / 'site'
        build.build(self.tt, out, today=D(2026, 10, 15), nginx_conf=None)
        groups = json.loads((out / 'data' / 'groups.json').read_text(encoding='utf-8'))
        self.assertEqual(groups, [['Inne', 'term 2026-09-28', ''], ['WCY26KY1S1', 'term 2026-09-28', 'WCY26'],
                                  ['WCY26KY3S1', 'term 2026-09-28', 'WCY26']])
        year = json.loads((out / 'data' / 'year' / 'WCY26.json').read_text(encoding='utf-8'))
        self.assertEqual(year['groups'], ['WCY26KY1S1', 'WCY26KY3S1'])
        self.assertEqual(len(year['e']), 14)
        self.assertEqual(year['names'][year['e'][1]], 'Matematyka')
        self.assertFalse((out / 'data' / 'year' / '.json').exists())

    def test_reads_repeats_durations_utc_times_and_skips_cancelled_and_all_day_events(self):
        path = self.tmp / 'x.ics'
        path.write_text('\r\n'.join([
            'BEGIN:VCALENDAR',
            'BEGIN:VEVENT', 'UID:a', 'DTSTART;TZID=Europe/Warsaw:20261005T080000', 'DURATION:PT1H35M',
            'RRULE:FREQ=WEEKLY;BYDAY=MO,WE;UNTIL=20261014', 'EXDATE;TZID=Europe/Warsaw:20261007T080000',
            'SUMMARY:Fizyka', 'CATEGORIES:Wykład,Inne', 'LOCATION:100 S', 'END:VEVENT',
            'BEGIN:VEVENT', 'UID:b', 'DTSTART:20261006T060000Z', 'DTEND:20261006T073500Z', 'SUMMARY:UTC', 'END:VEVENT',
            'BEGIN:VEVENT', 'UID:c', 'DTSTART;VALUE=DATE:20261006', 'SUMMARY:Dzień', 'END:VEVENT',
            'BEGIN:VEVENT', 'UID:d', 'DTSTART:20261006T080000', 'DTEND:20261006T090000', 'STATUS:CANCELLED',
            'SUMMARY:Odwołane', 'END:VEVENT',
            'BEGIN:VEVENT', 'UID:e', 'DTSTART:20261008T080000', 'DTEND:20261008T090000', 'RRULE:FREQ=DAILY;COUNT=2',
            'SUMMARY:Codziennie', 'END:VEVENT',
            'BEGIN:VEVENT', 'UID:f', 'DTSTART:20261009T080000', 'DTEND:20261009T090000', 'RRULE:FREQ=MONTHLY',
            'SUMMARY:Miesięcznie', 'END:VEVENT',
            'END:VCALENDAR', '']), encoding='utf-8', newline='')
        got = build.calendar_lessons(path, build._tz(), D(2027, 2, 22))
        self.assertIn((D(2026, 10, 5), 480, 575, 'Fizyka', 'Wykład', '100 S'), got)
        self.assertIn((D(2026, 10, 12), 480, 575, 'Fizyka', 'Wykład', '100 S'), got)
        self.assertIn((D(2026, 10, 14), 480, 575, 'Fizyka', 'Wykład', '100 S'), got)
        self.assertNotIn(D(2026, 10, 7), [g[0] for g in got if g[3] == 'Fizyka'])
        self.assertEqual(len([g for g in got if g[3] == 'Fizyka']), 3)
        self.assertIn((D(2026, 10, 6), 480, 575, 'UTC', '', ''), got)
        self.assertEqual([g[0] for g in got if g[3] == 'Codziennie'], [D(2026, 10, 8), D(2026, 10, 9)])
        self.assertEqual(len([g for g in got if g[3] == 'Miesięcznie']), 1)
        self.assertNotIn('Dzień', [g[3] for g in got])
        self.assertNotIn('Odwołane', [g[3] for g in got])

    def test_year_prefixes(self):
        self.assertEqual(build.year_of('WCY26KY3S1'), 'WCY26')
        self.assertEqual(build.year_of('wlo22FO1S0'), 'WLO22')
        self.assertIsNone(build.year_of('WCY_M1'))


class ClipToTermTest(unittest.TestCase):
    def two_semesters(self, old='2026-04-10', new='2026-09-21', extra_new='2026-10-05'):
        text = calendar('WCY25KY1S1', '2026-09-28', '2027-02-22', new)
        events = []
        for day in (old, extra_new):
            ymd = day.replace('-', '')
            events += ['BEGIN:VEVENT', f'UID:{ymd}@test', f'DTSTART;TZID=Europe/Warsaw:{ymd}T100000',
                       f'DTEND;TZID=Europe/Warsaw:{ymd}T113500', 'SUMMARY:Fizyka z bardzo dlugim tytulem, ktory',
                       ' zostaje zlozony w drugiej linii', 'END:VEVENT']
        return text.replace('END:VCALENDAR', '\r\n'.join(events) + '\r\nEND:VCALENDAR').encode('utf-8')

    def test_lessons_of_last_semester_are_dropped_and_the_rest_stays_byte_for_byte(self):
        out = build.clip_to_term(self.two_semesters(), '2026-27-zima').decode('utf-8')
        self.assertNotIn('20260410', out)
        self.assertIn('20260921', out)
        self.assertIn('20261005', out)
        self.assertEqual(out.count('BEGIN:VEVENT'), 2)
        self.assertIn('Fizyka z bardzo dlugim tytulem, ktory\r\n zostaje zlozony w drugiej linii', out)
        self.assertNotIn('\n', out.replace('\r\n', ''))
        self.assertTrue(out.startswith('BEGIN:VCALENDAR\r\nVERSION:2.0\r\n') and out.endswith('END:VCALENDAR\r\n'))

    def test_a_clean_calendar_comes_back_unchanged(self):
        clean = calendar('WCY26KY3S1', '2026-09-28', '2027-02-22', '2026-10-05').encode('utf-8')
        self.assertIs(build.clip_to_term(clean, '2026-27-zima'), clean)

    def test_a_calendar_of_only_another_semester_goes_out_with_no_lessons(self):
        only_old = calendar('WCY26KY3S1', '2026-09-28', '2027-02-22', '2026-04-10').encode('utf-8')
        out = build.clip_to_term(only_old, '2026-27-zima').decode('utf-8')
        self.assertNotIn('BEGIN:VEVENT', out)
        self.assertIn('X-PLAN-GROUP:WCY26KY3S1', out)
        self.assertIn('X-PLAN-SEMESTER-START:20260928', out)
        self.assertTrue(out.startswith('BEGIN:VCALENDAR\r\n') and out.endswith('END:VCALENDAR\r\n'))

    def test_the_window_per_term(self):
        self.assertEqual(build.term_window('2026-27-zima'), ('20260901', '20270229'))
        self.assertEqual(build.term_window('2026-27-lato'), ('20270201', '20270930'))

    def test_the_site_publishes_the_clipped_plan_and_its_reminders(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        term = tmp / 'timetables' / '2026-27-zima'
        term.mkdir(parents=True)
        (term / 'WCY25KY1S1.ics').write_bytes(self.two_semesters())
        build.build(tmp / 'timetables', tmp / 'site', today=D(2026, 10, 15), nginx_conf=None)
        for name in ('plan.ics', 'plan-przypomnienia.ics'):
            published = (tmp / 'site' / 'WCY25KY1S1' / name).read_text(encoding='utf-8')
            self.assertNotIn('20260410', published, name)
            self.assertIn('20261005', published, name)


class RoomsDataTest(unittest.TestCase):
    def test_split_rooms_normalises_and_drops_what_is_not_a_room(self):
        self.assertEqual(build.split_rooms('1.16/ 16;1.17/16'), ['1.16/16', '1.17/16'])
        self.assertEqual(build.split_rooms('314 S'), ['314 S'])
        self.assertEqual(build.split_rooms('Teams'), [])
        self.assertEqual(build.split_rooms('-'), [])
        self.assertEqual(build.split_rooms('314 S;314 S'), ['314 S'])


class ScrubStaffTest(unittest.TestCase):
    def test_drops_contact_and_instructor_segments_but_keeps_the_rest(self):
        before = ('BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:a\r\nDTSTART:20261005T080000\r\n'
                  'SUMMARY:Matematyka\r\nCATEGORIES:Wykład\r\nCONTACT:Jan Kowalski\r\n'
                  'DESCRIPTION:Wykład\\nProwadzący: Jan Kowalski\\nGrupy: WLO1, WLO2\r\n'
                  'END:VEVENT\r\nEND:VCALENDAR\r\n')
        after, removed = scrub_staff.scrub_text(before)
        self.assertTrue(removed)
        self.assertNotIn('CONTACT', after)
        self.assertNotIn('owalski', after)
        self.assertIn('DESCRIPTION:Wykład\\nGrupy: WLO1, WLO2', after)
        self.assertTrue(after.endswith('\r\n') and '\n\n' not in after.replace('\r\n', '\n'))
        ok, why = scrub_staff.verify('probe', before, after)
        self.assertTrue(ok, why)

    def test_a_lecturer_alias_in_a_location_goes_but_the_real_room_stays(self):
        def cal(location):
            return '\r\n'.join(['BEGIN:VCALENDAR', 'BEGIN:VEVENT', 'UID:a', 'DTSTART:20261005T080000',
                                'SUMMARY:Matematyka', 'LOCATION:' + location, 'END:VEVENT', 'END:VCALENDAR', ''])
        after, _ = scrub_staff.scrub_text(cal('ANazwisko\\;314 S'))
        self.assertIn('LOCATION:314 S\r\n', after)
        self.assertNotIn('Nazwisko', after)
        after, _ = scrub_staff.scrub_text(cal('314 S\\, ANazwisko'))
        self.assertIn('LOCATION:314 S\r\n', after)
        after, _ = scrub_staff.scrub_text(cal('ANazwisko'))
        self.assertNotIn('LOCATION', after)
        self.assertIsNone(scrub_staff.scrub_text(cal('Teams')))

    def test_unfolds_before_scrubbing_so_folded_names_are_caught(self):
        before = ('BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:a\r\nDTSTART:20261005T080000\r\n'
                  'SUMMARY:Matematyka\r\nDESCRIPTION:Wykład\\nProwadzący: Aleksandra Dłu\r\n'
                  ' gosz imię\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n')
        after, removed = scrub_staff.scrub_text(before)
        self.assertTrue(removed)
        self.assertNotIn('ługosz', after)
        self.assertIn('DESCRIPTION:Wykład', after)

    def test_a_clean_crlf_calendar_is_byte_stable(self):
        before = ('BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:a\r\nDTSTART:20261005T080000\r\n'
                  'SUMMARY:Matematyka\r\nDESCRIPTION:Wykład\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n')
        self.assertIsNone(scrub_staff.scrub_text(before))

    def test_lf_endings_are_normalized_without_touching_content(self):
        before = ('BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:a\nDTSTART:20261005T080000\n'
                  'SUMMARY:Matematyka\nEND:VEVENT\nEND:VCALENDAR\n')
        after, removed = scrub_staff.scrub_text(before)
        self.assertFalse(removed)
        self.assertFalse([l for l in after.split('\n') if l and not l.endswith('\r')])
        self.assertIn('SUMMARY:Matematyka', after)


if __name__ == '__main__':
    unittest.main()
