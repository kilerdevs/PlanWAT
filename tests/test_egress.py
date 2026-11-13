"""Offline tests for the egress rotator (tools/egress) and refresh retry/report logic."""
import os
import sys
import tempfile
import threading
import time
import unittest
import unittest.mock
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'egress'))
sys.path.insert(0, str(ROOT / 'tools' / 'refresh'))

import pool  # noqa: E402
import core  # noqa: E402
import refresh  # noqa: E402
import relay  # noqa: E402
import server  # noqa: E402


class ProxyUrl(unittest.TestCase):
    def test_bare_ip_port_becomes_http(self):
        self.assertEqual(pool.parse_proxy_url(' 1.2.3.4:8080 '), 'http://1.2.3.4:8080')

    def test_private_and_loopback_never_chain(self):
        for raw in ('10.0.0.5:3128', '192.168.1.7:8080', '127.0.0.1:8888', 'localhost:8080'):
            self.assertIsNone(pool.parse_proxy_url(raw), raw)

    def test_garbage_and_bad_ports_rejected(self):
        for raw in ('', 'nonsense', '1.2.3.4', '1.2.3.4:99999', 'http://1.2.3.4', 'gopher://8.8.8.8:70'):
            self.assertIsNone(pool.parse_proxy_url(raw), raw)

    def test_schemes_kept(self):
        self.assertEqual(pool.parse_proxy_url('socks5://8.8.8.8:1080'), 'socks5://8.8.8.8:1080')
        self.assertEqual(pool.parse_proxy_url('socks4://8.8.8.8:1080'), 'socks4://8.8.8.8:1080')
        # https upstreams can never chain (no TLS-wrap): rejected
        self.assertIsNone(pool.parse_proxy_url('https://9.9.9.9:443'))
        self.assertIsNone(pool.parse_proxy_url('https://9.9.9.9:8443'))

    def test_socks_aliases_normalize(self):
        self.assertEqual(pool.parse_proxy_url('socks5h://8.8.8.8:1080'), 'socks5://8.8.8.8:1080')
        self.assertEqual(pool.parse_proxy_url('socks4a://8.8.8.8:1080'), 'socks4://8.8.8.8:1080')
        self.assertEqual(pool.parse_proxy_url('socks4h://8.8.8.8:1080'), 'socks4://8.8.8.8:1080')

    def test_ipv6_keeps_its_brackets(self):
        self.assertEqual(pool.parse_proxy_url('[2001:4860:4860::8888]:8080'),
                         'http://[2001:4860:4860::8888]:8080')
        # loopback/unspecified v6 stays out of the pool
        self.assertIsNone(pool.parse_proxy_url('[::1]:8080'))
        self.assertIsNone(pool.parse_proxy_url('[::]:8080'))

    def test_strict_ip_filter(self):
        # multicast (not covered by is_private) must be rejected
        self.assertIsNone(pool.parse_proxy_url('224.0.0.1:8080'))
        self.assertIsNone(pool.parse_proxy_url('http://224.0.0.1:8080'))
        # reserved / link-local / unspecified also rejected
        for raw in ('http://255.255.255.255:8080', 'http://169.254.10.20:8080',
                    'http://0.0.0.0:8080', 'http://240.0.0.1:8080'):
            self.assertIsNone(pool.parse_proxy_url(raw), raw)
        # public still passes
        self.assertEqual(pool.parse_proxy_url('8.8.8.8:8080'), 'http://8.8.8.8:8080')
        self.assertEqual(pool.parse_proxy_url('9.9.9.9:1080'), 'http://9.9.9.9:1080')


class Normalize(unittest.TestCase):
    def test_plain_text(self):
        urls = pool.normalize_list('8.8.8.8:8080\n10.0.0.1:3128\njunk\n', 'plain')
        self.assertEqual(urls, ['http://8.8.8.8:8080'])

    def test_plain_text_takes_the_list_protocol(self):
        urls = pool.normalize_list('8.8.8.8:1080\n', 'plain', 'socks5')
        self.assertEqual(urls, ['socks5://8.8.8.8:1080'])

    def test_proxifly_json_buckets(self):
        text = '{"http": ["8.8.8.8:8080"], "socks5": [{"proxy": "9.9.9.9:1080"}], "socks4": []}'
        self.assertEqual(sorted(pool.normalize_list(text, 'proxifly')),
                         ['http://8.8.8.8:8080', 'socks5://9.9.9.9:1080'])

    def test_proxifly_https_bucket_dropped(self):
        text = '{"https": ["8.8.8.8:443"], "http": ["9.9.9.9:8080"]}'
        urls = pool.normalize_list(text, 'proxifly')
        self.assertEqual(urls, ['http://9.9.9.9:8080'])

    def test_broken_json_gives_nothing(self):
        self.assertEqual(pool.normalize_list('{nope', 'proxifly'), [])


R2 = {'example.test': ('https://example.test/index.xml', None)}
# The pool keeps per-host verdicts only for the faculty hosts it knows, so tests that drive a real
# faculty name through the proxy hand the pool that host too.
R2_WLO = dict(R2, **{'wlo.wat.edu.pl': ('https://wlo.wat.edu.pl/planyzajec/zima/index.xml', None)})


class PoolPick(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / 'pool.json'
        self.pool = pool.ProxyPool(self.tmp, R2)

    def test_verified_for_host_wins_sorted_by_latency(self):
        self.pool.entries = {
            'http://a:1': {'status': 'ok', 'latency_ms': 50, 'hosts': {'example.test': {'ok': True, 'ms': 900}}},
            'http://b:2': {'status': 'ok', 'latency_ms': 10, 'hosts': {}},
            'http://c:3': {'status': 'ok', 'latency_ms': 10,
                           'hosts': {'example.test': {'ok': True, 'ms': 100}}},
        }
        self.assertEqual(self.pool.pick('example.test'), 'http://c:3')

    def test_globally_alive_but_host_untried_is_offered_optimistically(self):
        self.pool.entries = {'http://b:2': {'status': 'ok', 'latency_ms': 10, 'hosts': {}}}
        self.assertEqual(self.pool.pick('example.test'), 'http://b:2')

    def test_host_failed_sits_out_until_cooldown(self):
        import time
        self.pool.entries = {'http://a:1': {'status': 'ok', 'hosts': {
            'example.test': {'ok': False, 'checked': time.time()}}}}
        self.assertIsNone(self.pool.pick('example.test'))

    def test_host_failed_mono_cooldown(self):
        import time
        mono = time.monotonic()
        self.pool.entries = {'http://a:1': {'status': 'ok', 'fails': 0, 'hosts': {
            'example.test': {'ok': False, 'checked': 0, 'checked_mono': mono}}}}
        self.assertIsNone(self.pool.pick('example.test'))

    def test_mark_verifies_and_persists(self):
        self.pool.mark('http://a:1', 'example.test', True, 42)
        self.assertEqual([p['url'] for p in self.pool.verified('example.test')], ['http://a:1'])
        self.assertEqual(self.pool.pick('example.test'), 'http://a:1')
        again = pool.ProxyPool(self.tmp, R2)
        self.assertTrue(again.entries['http://a:1']['hosts']['example.test']['ok'])

    def test_mark_fail_is_host_scoped(self):
        self.pool.entries = {'http://a:1': {'status': 'ok', 'hosts': {}}}
        self.pool.mark('http://a:1', 'example.test', False)
        self.assertIsNone(self.pool.pick('example.test'))
        self.assertEqual(self.pool.entries['http://a:1']['status'], 'ok')  # still alive globally

    def test_ewma_latency(self):
        # a faculty's verdict keeps its own latency; the entry's is Round 1's
        self.pool.mark('http://a:1', 'example.test', True, 100)
        self.assertEqual(self.pool.entries['http://a:1']['hosts']['example.test']['ms'], 100)
        self.pool.mark('http://a:1', 'example.test', True, 200)
        self.assertEqual(self.pool.entries['http://a:1']['hosts']['example.test']['ms'], int(0.7 * 100 + 0.3 * 200))
        self.assertNotIn('latency_ms', self.pool.entries['http://a:1'])
        self.pool.mark_alive('http://b:2', True, 100)
        self.pool.mark_alive('http://b:2', True, 200)
        self.assertEqual(self.pool.entries['http://b:2']['latency_ms'], int(0.7 * 100 + 0.3 * 200))

    def test_fails_penalize_ordering(self):
        self.pool.entries = {
            'http://a:1': {'status': 'ok', 'latency_ms': 10, 'fails': 10, 'hosts': {}},
            'http://b:2': {'status': 'ok', 'latency_ms': 500, 'fails': 0, 'hosts': {}},
        }
        self.assertEqual(self.pool.pick('example.test'), 'http://b:2')

    def test_misses_at_another_host_never_sink_a_verified_exit(self):
        two = dict(R2, **{'other.test': ('https://other.test/index.xml', None)})
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', two)
        p.entries = {
            'http://a:1': {'status': 'ok', 'latency_ms': 10, 'fails': 0,
                           'hosts': {'example.test': {'ok': True, 'ms': 10}}},
            'http://b:2': {'status': 'ok', 'latency_ms': 500, 'fails': 0,
                           'hosts': {'example.test': {'ok': True, 'ms': 500}}},
        }
        for _ in range(5):
            p.mark('http://a:1', 'other.test', False)
        self.assertEqual(p.entries['http://a:1']['fails'], 0)  # a probe's miss is that host's verdict only
        self.assertEqual(p.entries['http://a:1']['hosts']['other.test']['n_fail'], 5)
        self.assertEqual(p.pick('example.test'), 'http://a:1')  # its own verdict ranks it
        self.assertEqual(p.pick('other.test'), 'http://b:2')  # ...while the host it missed rests it

    def test_stale_aliveness_sinks_below_fresh(self):
        import time
        now = time.time()
        self.pool.entries = {
            'http://old:1': {'status': 'ok', 'latency_ms': 50, 'fails': 0,
                             'last_checked': now - 3 * 3600, 'hosts': {}},
            'http://new:2': {'status': 'ok', 'latency_ms': 2000, 'fails': 0,
                             'last_checked': now, 'hosts': {}},
        }
        self.assertEqual(self.pool.pick('example.test'), 'http://new:2')

    def test_failed_reprobe_revokes_aliveness(self):
        self.pool.entries = {'http://a:1': {'status': 'ok', 'latency_ms': 50, 'hosts': {}}}
        self.pool.mark_alive('http://a:1', False)
        self.assertEqual(self.pool.entries['http://a:1']['status'], 'fail')
        self.assertIsNone(self.pool.pick('example.test'))

    def test_pick_many(self):
        self.pool.entries = {
            f'http://n{i}:1': {'status': 'ok', 'latency_ms': 10 * i, 'fails': 0,
                               'hosts': {'example.test': {'ok': True, 'ms': 10 * i}}}
            for i in range(4)
        }
        got = self.pool.pick_many('example.test', 2)
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0], 'http://n0:1')
        self.assertEqual(len(self.pool.pick_many('example.test', 10)), 4)

    def test_pick_many_rotates_across_the_verified_tier(self):
        self.pool.entries = {
            f'http://n{i}:1': {'status': 'ok', 'latency_ms': 10 * i, 'fails': 0,
                               'hosts': {'example.test': {'ok': True, 'ms': 10 * i}}}
            for i in range(3)
        }
        # Consecutive picks start on consecutive exits: no single proxy absorbs the crawl.
        firsts = [self.pool.pick_many('example.test', 1)[0] for _ in range(4)]
        self.assertEqual(firsts, ['http://n0:1', 'http://n1:1', 'http://n2:1', 'http://n0:1'])
        self.assertEqual(self.pool.pick_many('example.test', 3),
                         ['http://n1:1', 'http://n2:1', 'http://n0:1'])

    def test_pick_many_keeps_the_optimistic_tail_behind_the_verified_tier(self):
        self.pool.entries = {
            'http://v:1': {'status': 'ok', 'latency_ms': 500, 'fails': 0,
                           'hosts': {'example.test': {'ok': True, 'ms': 500}}},
            'http://u:1': {'status': 'ok', 'latency_ms': 1, 'fails': 0, 'hosts': {}},
        }
        self.assertEqual(self.pool.pick_many('example.test', 2),
                         ['http://v:1', 'http://u:1'])

    def test_breaker_trips_and_clears(self):
        self.pool.mark('http://good:1', 'example.test', True, 50, live=True)
        self.assertEqual(self.pool.pick('example.test'), 'http://good:1')
        for i in range(10):
            self.pool.mark(f'http://f{i}:1', 'example.test', False, live=True)
        self.assertTrue(self.pool.stats()['tripped'])
        self.assertIsNone(self.pool.pick('example.test'))
        self.assertEqual(self.pool.pick_many('example.test'), [])
        self.pool.mark('http://good:1', 'example.test', True, 50, live=True)
        self.assertFalse(self.pool.stats()['tripped'])
        self.assertEqual(self.pool.pick('example.test'), 'http://good:1')

    def test_background_probes_never_trip_or_clear_the_breaker(self):
        for i in range(30):
            self.pool.mark(f'http://f{i}:1', 'example.test', False)  # probe marks: live=False
        self.assertFalse(self.pool.stats()['tripped'])
        self.pool.mark_alive('http://p:1', True, 50)
        self.assertFalse(self.pool.stats()['tripped'])
        # ...but a tripped breaker survives passing probes and needs live success to clear.
        for i in range(10):
            self.pool.mark(f'http://g{i}:1', 'example.test', False, live=True)
        self.assertTrue(self.pool.stats()['tripped'])
        self.pool.mark_alive('http://p:1', True, 50)
        self.assertTrue(self.pool.stats()['tripped'])
        self.pool.mark('http://good:1', 'example.test', True, 50, live=True)
        self.assertFalse(self.pool.stats()['tripped'])

    def test_stats_p50_p95(self):
        for i, ms in enumerate([10, 20, 30, 40]):
            self.pool.entries[f'http://p{i}:1'] = {'status': 'ok', 'latency_ms': ms,
                                                  'fails': 0, 'hosts': {}}
        st = self.pool.stats()
        self.assertIn('p50_ok_ms', st)
        self.assertIn('p95_ok_ms', st)
        self.assertIsNotNone(st['p50_ok_ms'])
        self.assertIsNotNone(st['p95_ok_ms'])
        self.assertIn('tripped', st)

    def test_probe_alive_latency_cutoff(self):
        from types import SimpleNamespace
        self.pool.fetch_via = lambda url, target, timeout: (
            SimpleNamespace(status_code=200, content=b'x' * 2000), 7000)
        self.assertIsNone(self.pool.probe_alive('http://8.8.8.8:8080'))

    def test_fetch_via_rewrites_to_remote_dns(self):
        import sys as _sys
        import types as _types
        captured = {}

        class _FakeResp:
            status_code = 200
            content = b'x' * 2000
            text = 'ok'

        def _fake_get(target, timeout=None, proxies=None, headers=None):
            captured['proxies'] = dict(proxies or {})
            return _FakeResp()

        fake_requests = _types.SimpleNamespace(get=_fake_get)
        fake_mod = _types.ModuleType('curl_cffi')
        fake_mod.requests = fake_requests
        prev = _sys.modules.get('curl_cffi')
        _sys.modules['curl_cffi'] = fake_mod
        try:
            self.pool.fetch_via('socks5://8.8.8.8:1080', 'https://example.test/', 5)
            self.assertEqual(captured['proxies']['http'], 'socks5h://8.8.8.8:1080')
            self.pool.fetch_via('socks4://8.8.8.8:1080', 'https://example.test/', 5)
            self.assertEqual(captured['proxies']['http'], 'socks4a://8.8.8.8:1080')
            self.pool.fetch_via('http://8.8.8.8:8080', 'https://example.test/', 5)
            self.assertEqual(captured['proxies']['http'], 'http://8.8.8.8:8080')
        finally:
            if prev is None:
                _sys.modules.pop('curl_cffi', None)
            else:
                _sys.modules['curl_cffi'] = prev

    def test_refresh_merges_probe_results_offline(self):
        def fetcher(url):
            if 'monosans' not in url or 'http.txt' not in url:
                raise OSError('list unreachable')
            return '8.8.8.8:8080\n9.9.9.9:1080\n'
        self.pool.probe_alive = lambda url: 50 if url == 'http://8.8.8.8:8080' else None
        self.pool.probe_host = lambda url, host: 60 if url == 'http://8.8.8.8:8080' else None
        self.pool._tcp_screen = lambda urls, **k: {u: 5 for u in urls}  # no sockets offline
        alive, tried, verified = self.pool.refresh(fetcher=fetcher, workers=2)
        self.assertEqual((alive, tried), (1, 2))
        self.assertEqual(verified, 1)
        self.assertTrue(self.pool.entries['http://8.8.8.8:8080']['hosts']['example.test']['ok'])

    def test_entry_cap_drops_oldest_fails(self):
        import time as _t
        self.assertEqual(pool.MAX_ENTRIES, 2000)
        now = _t.time()
        # 2005 recent fails with staggered last_checked
        for i in range(2005):
            self.pool.entries[f'http://old{i}:1'] = {'status': 'fail', 'fails': 1,
                                                    'last_checked': now - (2005 - i),
                                                    'hosts': {}}
        self.pool.probe_alive = lambda url: None
        self.pool.probe_host = lambda url, host: None
        self.pool.refresh(fetcher=lambda url: '', workers=2)
        self.assertLessEqual(len(self.pool.entries), pool.MAX_ENTRIES)

    def test_heal_kick_sets_event_on_thin_coverage(self):
        self.pool.heal_event.clear()
        # min_verified default 5, coverage 0 -> mark fail should set event
        self.pool.mark('http://thin:1', 'example.test', False)
        self.assertTrue(self.pool.heal_event.is_set())

    def test_corrupt_pool_file_never_crashes_pick(self):
        import json
        path = Path(tempfile.mkdtemp()) / 'pool.json'
        path.write_text(json.dumps({'version': pool.POOL_VERSION, 'entries': {
            'http://a:1': {'status': 'ok', 'latency_ms': 10, 'hosts': {}},
            'http://bad:2': 'nonsense',
            'http://badhosts:3': {'status': 'ok', 'hosts': ['not', 'a', 'dict']},
            'http://badnum:4': {'status': 'ok', 'latency_ms': 'slow', 'last_checked': 'yesterday',
                               'hosts': {}},
        }}), encoding='utf-8')
        p = pool.ProxyPool(path, R2)
        self.assertIn('http://a:1', p.entries)
        self.assertNotIn('http://bad:2', p.entries)
        self.assertEqual(p.entries['http://badhosts:3']['hosts'], {})
        self.assertNotIn('latency_ms', p.entries['http://badnum:4'])
        self.assertEqual(p.pick('example.test'), 'http://a:1')
        self.assertIsNotNone(p.stats()['p50_ok_ms'])  # sorting/median never sees a string

    def test_host_breaker_only_closes_the_failing_host(self):
        self.pool.entries = {
            'http://a:1': {'status': 'ok', 'latency_ms': 10, 'fails': 0,
                           'hosts': {'example.test': {'ok': True, 'ms': 10}}},
            'http://b:2': {'status': 'ok', 'latency_ms': 20, 'fails': 0,
                           'hosts': {'other.test': {'ok': True, 'ms': 20}}},
        }
        for _ in range(pool.HOST_BREAKER_N):
            self.pool.mark('http://a:1', 'example.test', False, live=True)
        self.assertIsNone(self.pool.pick('example.test'))
        self.assertEqual(self.pool.pick_many('example.test'), [])
        self.assertEqual(self.pool.pick('other.test'), 'http://b:2')
        self.assertEqual(self.pool.stats()['hosts_tripped'], 1)
        # A real success clears that host's breaker at once.
        self.pool.mark('http://a:1', 'example.test', True, 10, live=True)
        self.assertEqual(self.pool.pick('example.test'), 'http://a:1')
        self.assertEqual(self.pool.stats()['hosts_tripped'], 0)

    def test_total_list_failure_retries_soon_instead_of_freezing(self):
        import time as _t

        def boom(url):
            raise OSError('list unreachable')

        self.assertEqual(self.pool.refresh(fetcher=boom, workers=2), (0, 0, 0))
        self.assertIsNone(self.pool.last_refresh)  # not stamped: the pool is not "fresh"
        self.assertGreater(self.pool.retry_after, _t.time() + pool.RETRY_AFTER_S - 30)
        self.assertFalse(self.pool.needs_refresh())  # wait out the short retry window...
        self.pool.retry_after = 0
        self.assertTrue(self.pool.needs_refresh())   # ...then try again, not in max_age hours

    def test_probe_alive_requires_an_empty_204(self):
        from types import SimpleNamespace
        targets = []
        for code, body, expected in (
            (204, b'', 50),
            (200, b'', None),                       # not the endpoint's answer
            (200, b'<html>' + b'x' * 2000, None),   # a captive or error page
            (204, b'<html>' + b'x' * 2000, None),   # a 204 with a page in it is not the real one either
        ):
            self.pool.fetch_via = (lambda url, target, timeout, code=code, body=body:
                                   (targets.append(target), (SimpleNamespace(status_code=code, content=body), 50))[1])
            self.assertEqual(self.pool.probe_alive('http://8.8.8.8:8080'), expected, (code, body[:20]))
        self.assertEqual(set(targets), {pool.ROUND1_URL})

    def test_probe_host_rejects_a_block_page_even_with_a_200(self):
        from types import SimpleNamespace
        marker = b'<?xml'
        self.pool.round2['example.test'] = ('https://example.test/index.xml', marker)
        for body, expected in (
            (marker + b'<plan/>' * 200, 40),
            (b'<html>' + b'x' * 800 + b'Access Denied', None),
            (b'<html>' + b'x' * 800, None),  # 200, no marker: not the real index
            (marker + b'<plan/>', None),     # too small to be an index
        ):
            self.pool.fetch_via = (
                lambda url, target, timeout, body=body: (SimpleNamespace(status_code=200, content=body), 40))
            self.assertEqual(self.pool.probe_host('http://8.8.8.8:8080', 'example.test'), expected, body[:20])


class PoolActiveHosts(unittest.TestCase):
    def test_no_active_host_means_no_pool_work_at_all(self):
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2, active_hosts=[])
        self.assertFalse(p.enabled)
        self.assertEqual(p.coverage(), ({}, 0))
        self.assertFalse(p.needs_refresh())
        fetched = []
        self.assertEqual(p.refresh(fetcher=lambda url: fetched.append(url) or ''), (0, 0, 0))
        self.assertEqual(fetched, [])

    def test_coverage_only_counts_hosts_that_ride_the_pool(self):
        two = {'example.test': ('https://example.test/index.xml', None),
               'other.test': ('https://other.test/index.xml', None)}
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', two,
                           active_hosts=['example.test'])
        p.entries = {'http://a:1': {'status': 'ok', 'hosts': {
            'example.test': {'ok': True}, 'other.test': {'ok': True}}}}
        self.assertEqual(p.coverage(), ({'example.test': 1}, 1))
        self.assertTrue(p.enabled)


class MaintainOnceTest(unittest.TestCase):
    def test_unpacks_three_values(self):
        class Stub:
            force_refresh = False
            entries = {}

            def __init__(self):
                self._refresh_lock = threading.Lock()

            def needs_refresh(self):
                return True

            def refresh(self):
                return (7, 9, 3)
        msg = server.maintain_once(Stub())
        self.assertIn('7/9', msg)

    def test_fresh_when_no_refresh_needed(self):
        class Stub:
            force_refresh = False
            entries = {}

            def __init__(self):
                self._refresh_lock = threading.Lock()

            def needs_refresh(self):
                return False

            def refresh(self):
                raise AssertionError('should not refresh')
        self.assertEqual(server.maintain_once(Stub()), 'fresh')

    def test_list_failure_shortens_the_maintenance_sleep(self):
        import time as _t
        class Stub:
            retry_after = 0.0

        now = 1000.0
        stub = Stub()
        self.assertEqual(server.maintain_wait(stub, 600, now=now), 600)
        stub.retry_after = now + 120
        self.assertEqual(server.maintain_wait(stub, 600, now=now), 120)
        stub.retry_after = now - 30  # already elapsed: normal cadence
        self.assertEqual(server.maintain_wait(stub, 600, now=now), 600)
        stub.retry_after = now + 1  # never busy-loop on a sub-5 s retry
        self.assertEqual(server.maintain_wait(stub, 600, now=now), 5.0)


class FakeSocket:
    def __init__(self, recv_bytes):
        self._buf = bytes(recv_bytes)
        self.sent = b''
        self.timeout = None
        self.closed = False

    def settimeout(self, t):
        self.timeout = t

    def sendall(self, data):
        self.sent += bytes(data)

    def recv(self, n):
        if not self._buf:
            return b''
        chunk, self._buf = self._buf[:n], self._buf[n:]
        return chunk

    def close(self):
        self.closed = True

    def shutdown(self, *a):
        pass


class ChainTest(unittest.TestCase):
    def _patch_create(self, fake):
        import socket as _sock
        orig = _sock.create_connection
        _sock.create_connection = lambda *a, **k: fake
        return orig

    def test_socks4a_ignores_bind_address(self):
        import socket as _sock
        fake = FakeSocket(b'\x00\x5a\x01\x02\x03\x04\x05\x06')
        orig = self._patch_create(fake)
        try:
            sock = server.chain_connect('socks4://8.8.8.8:1080', 'example.test', 443)
            self.assertIs(sock, fake)
        finally:
            _sock.create_connection = orig

    def test_socks4a_refused(self):
        import socket as _sock
        fake = FakeSocket(b'\x00\x5b\x00\x00\x00\x00\x00\x00')
        orig = self._patch_create(fake)
        try:
            with self.assertRaises(OSError):
                server.chain_connect('socks4://8.8.8.8:1080', 'example.test', 443)
        finally:
            _sock.create_connection = orig

    def _socks5(self, reply_tail):
        """Drive one SOCKS5 handshake; returns (socket, sent bytes)."""
        import socket as _sock
        fake = FakeSocket(b'\x05\x00' + reply_tail)
        orig = self._patch_create(fake)
        try:
            sock = server.chain_connect('socks5://8.8.8.8:1080', 'example.test', 443)
        finally:
            _sock.create_connection = orig
        self.assertIs(sock, fake)
        self.assertIn(b'\x05\x01\x00\x03\x0cexample.test\x01\xbb', fake.sent)
        return fake

    def test_socks5_consumes_an_ipv4_reply_exactly(self):
        fake = self._socks5(b'\x05\x00\x00\x01\x08\x08\x08\x08\x01\xbb')
        self.assertEqual(fake._buf, b'')  # no double read, no leftover

    def test_socks5_consumes_a_domain_reply_exactly(self):
        # ATYP=3: the length byte precedes the name. Reading it twice used to eat the
        # first name byte and then block until the handshake timed out.
        fake = self._socks5(b'\x05\x00\x00\x03\x05proxy\x01\xbb')
        self.assertEqual(fake._buf, b'')

    def test_socks5_consumes_an_ipv6_reply_exactly(self):
        addr = bytes(range(16))
        fake = self._socks5(b'\x05\x00\x00\x04' + addr + b'\x01\xbb')
        self.assertEqual(fake._buf, b'')

    def test_socks5_unknown_address_type_is_refused(self):
        import socket as _sock
        fake = FakeSocket(b'\x05\x00\x05\x00\x00\x09')
        orig = self._patch_create(fake)
        try:
            with self.assertRaises(OSError):
                server.chain_connect('socks5://8.8.8.8:1080', 'example.test', 443)
            self.assertTrue(fake.closed)
        finally:
            _sock.create_connection = orig

    def test_http_connect_refusal_and_header_cap(self):
        import socket as _sock
        for reply in (b'HTTP/1.1 403 Forbidden\r\n\r\n',
                      b'X' * (server.CONNECT_HEAD_CAP + 1)):
            fake = FakeSocket(reply)
            orig = self._patch_create(fake)
            try:
                with self.assertRaises(OSError):
                    server.chain_connect('http://8.8.8.8:8080', 'example.test', 443)
            finally:
                _sock.create_connection = orig

    def test_hostname_too_long_rejected_upfront(self):
        with self.assertRaises(OSError):
            server.chain_connect('http://8.8.8.8:8080', 'a' * 300 + '.test', 443)

    def test_chain_connect_has_timeout_param(self):
        import inspect
        sig = inspect.signature(server.chain_connect)
        self.assertIn('timeout', sig.parameters)


class WalkTest(unittest.TestCase):
    HOST = 'wlo.wat.edu.pl'

    def test_open_walks_up_to_three(self):
        tmp = Path(tempfile.mkdtemp()) / 'pool.json'
        p = pool.ProxyPool(tmp, R2_WLO)
        p.entries = {
            'http://a:1': {'status': 'ok', 'latency_ms': 10, 'fails': 0,
                           'hosts': {self.HOST: {'ok': True, 'ms': 10}}},
            'http://b:2': {'status': 'ok', 'latency_ms': 20, 'fails': 0,
                           'hosts': {self.HOST: {'ok': True, 'ms': 20}}},
            'http://c:3': {'status': 'ok', 'latency_ms': 30, 'fails': 0,
                           'hosts': {self.HOST: {'ok': True, 'ms': 30}}},
        }
        calls = []
        orig = server.chain_connect

        def fake(proxy, host, port, timeout=6):
            calls.append((proxy, timeout))
            if proxy != 'http://c:3':
                raise OSError('refused')
            return object()
        server.chain_connect = fake
        try:
            handler = server.ProxyHandler.__new__(server.ProxyHandler)
            from types import SimpleNamespace
            handler.server = SimpleNamespace(pool=p, fallbacks={},
                                             fallbacks_lock=threading.Lock(), blocks=0,
                                             remember_tunnel=lambda h, v: None)
            sock, via, ms = handler._open(self.HOST, 443)
            self.assertEqual(via, 'http://c:3')
            self.assertIsInstance(ms, int)
            self.assertEqual([c[0] for c in calls],
                             ['http://a:1', 'http://b:2', 'http://c:3'])
            self.assertEqual(calls[0][1], 6)
            self.assertFalse(p.entries['http://a:1']['hosts'][self.HOST]['ok'])
            self.assertFalse(p.entries['http://b:2']['hosts'][self.HOST]['ok'])
        finally:
            server.chain_connect = orig

    def test_open_remembers_the_exit_for_block_reports(self):
        tmp = Path(tempfile.mkdtemp()) / 'pool.json'
        p = pool.ProxyPool(tmp, R2_WLO)
        p.entries = {
            'http://a:1': {'status': 'ok', 'latency_ms': 10, 'fails': 0,
                           'hosts': {self.HOST: {'ok': True, 'ms': 10}}},
        }
        orig = server.chain_connect
        server.chain_connect = lambda *a, **k: object()
        try:
            handler = server.ProxyHandler.__new__(server.ProxyHandler)
            from types import SimpleNamespace
            recent = []
            handler.server = SimpleNamespace(pool=p, fallbacks={},
                                             fallbacks_lock=threading.Lock(), blocks=0,
                                             remember_tunnel=lambda h, v: recent.append((h, v)))
            handler._open(self.HOST, 443)
            self.assertEqual(recent, [(self.HOST, 'http://a:1')])
        finally:
            server.chain_connect = orig

    def test_open_falls_back_after_all_fail(self):
        import socket as _sock
        tmp = Path(tempfile.mkdtemp()) / 'pool.json'
        p = pool.ProxyPool(tmp, R2_WLO)
        p.entries = {
            'http://a:1': {'status': 'ok', 'latency_ms': 10, 'fails': 0,
                           'hosts': {self.HOST: {'ok': True, 'ms': 10}}},
        }
        orig_chain = server.chain_connect
        orig_create = _sock.create_connection
        server.chain_connect = lambda *a, **k: (_ for _ in ()).throw(OSError('down'))
        _sock.create_connection = lambda *a, **k: object()
        try:
            handler = server.ProxyHandler.__new__(server.ProxyHandler)
            from types import SimpleNamespace
            handler.server = SimpleNamespace(pool=p, fallbacks={},
                                             fallbacks_lock=threading.Lock(), blocks=0,
                                             remember_tunnel=lambda h, v: None)
            sock, via, ms = handler._open(self.HOST, 443)
            self.assertEqual(via, 'direct-fallback')
            self.assertIsInstance(ms, int)
        finally:
            server.chain_connect = orig_chain
            _sock.create_connection = orig_create

    def test_connect_only_marks_success_once_bytes_flow(self):
        tmp = Path(tempfile.mkdtemp()) / 'pool.json'
        p = pool.ProxyPool(tmp, R2_WLO)
        p.entries = {
            'http://a:1': {'status': 'ok', 'latency_ms': 10, 'fails': 0, 'hosts': {}},
        }
        orig = server.chain_connect
        server.chain_connect = lambda *a, **k: object()
        try:
            handler = server.ProxyHandler.__new__(server.ProxyHandler)
            from types import SimpleNamespace
            handler.server = SimpleNamespace(pool=p, fallbacks={},
                                             fallbacks_lock=threading.Lock(), blocks=0,
                                             remember_tunnel=lambda h, v: None)
            _, via, ms = handler._open(self.HOST, 443)
            self.assertEqual(via, 'http://a:1')
            # CONNECT accepted, but no byte has flowed yet: the exit is not "verified".
            self.assertFalse(p.entries['http://a:1']['hosts'].get(self.HOST, {}).get('ok', False))
            handler._record_use(self.HOST, via, ms, True)
            self.assertTrue(p.entries['http://a:1']['hosts'][self.HOST]['ok'])
        finally:
            server.chain_connect = orig

    def test_a_blackholed_exit_is_failed_after_the_tunnel(self):
        tmp = Path(tempfile.mkdtemp()) / 'pool.json'
        p = pool.ProxyPool(tmp, R2_WLO)
        p.entries = {
            'http://a:1': {'status': 'ok', 'latency_ms': 10, 'fails': 0,
                           'hosts': {self.HOST: {'ok': True, 'ms': 10}}},
        }
        handler = server.ProxyHandler.__new__(server.ProxyHandler)
        handler.server = type('S', (), {'pool': p})()
        handler._record_use(self.HOST, 'http://a:1', 10, False)
        self.assertFalse(p.entries['http://a:1']['hosts'][self.HOST]['ok'])
        self.assertIsNone(p.pick(self.HOST))
        # direct exits are never fed back into the pool
        handler._record_use(self.HOST, 'direct', 10, False)
        handler._record_use(self.HOST, 'direct-fallback', 10, True)
        self.assertFalse(p.entries['http://a:1']['hosts'][self.HOST]['ok'])

    def test_fail_closed_host_never_falls_back_to_the_local_line(self):
        import socket as _sock
        orig_closed = server.fail_closed
        orig_create = _sock.create_connection
        server.fail_closed = lambda host: True
        _sock.create_connection = lambda *a, **k: self.fail('must not dial the local line')
        try:
            handler = server.ProxyHandler.__new__(server.ProxyHandler)
            from types import SimpleNamespace
            handler.server = SimpleNamespace(pool=None, fallbacks={},
                                             fallbacks_lock=threading.Lock())
            with self.assertRaises(OSError) as ctx:
                handler._fallback(self.HOST, 443)
            self.assertEqual(str(ctx.exception), 'proxy_empty')
        finally:
            server.fail_closed = orig_closed
            _sock.create_connection = orig_create

    def test_direct_fallback_still_works_for_other_hosts(self):
        import socket as _sock
        tmp = Path(tempfile.mkdtemp()) / 'pool.json'
        p = pool.ProxyPool(tmp, R2_WLO)
        orig_create = _sock.create_connection
        sentinel = object()
        _sock.create_connection = lambda *a, **k: sentinel
        try:
            handler = server.ProxyHandler.__new__(server.ProxyHandler)
            from types import SimpleNamespace
            handler.server = SimpleNamespace(pool=p, fallbacks={},
                                             fallbacks_lock=threading.Lock())
            self.assertEqual(handler._fallback(self.HOST, 443)[:2], (sentinel, 'direct-fallback'))
            self.assertEqual(handler.server.fallbacks[self.HOST], 1)
        finally:
            _sock.create_connection = orig_create


class RelayTest(unittest.TestCase):
    def test_relay_returns_counts(self):
        import socket as _sock
        a1, a2 = _sock.socketpair()
        b1, b2 = _sock.socketpair()
        result = []

        def run():
            result.append(server.relay(a1, b1, cap=5))
        t = threading.Thread(target=run, daemon=True)
        t.start()
        a2.sendall(b'hello')
        b2.sendall(b'world!')
        import time as _t
        _t.sleep(0.3)
        a2.close()
        b2.close()
        t.join(timeout=6)
        self.assertEqual(len(result), 1)
        up, down, secs = result[0]
        self.assertEqual(up, 5)
        self.assertEqual(down, 6)
        self.assertGreaterEqual(secs, 0)

    def test_relay_keeps_the_other_direction_alive_after_half_close(self):
        import socket as _sock
        client, proxy_side = _sock.socketpair()
        upstream, remote = _sock.socketpair()
        result = []
        t = threading.Thread(target=lambda: result.append(server.relay(proxy_side, upstream, cap=5)),
                             daemon=True)
        t.start()
        try:
            client.sendall(b'GET / HTTP/1.1\r\n\r\n')
            client.shutdown(_sock.SHUT_WR)  # the client has said everything it will say
            request = b''
            while True:
                chunk = remote.recv(4096)
                if not chunk:
                    break
                request += chunk
            self.assertEqual(request, b'GET / HTTP/1.1\r\n\r\n')
            response = b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhello'
            remote.sendall(response)
            remote.shutdown(_sock.SHUT_WR)
            got = b''
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                got += chunk
            self.assertEqual(got, response)
            t.join(timeout=5)
            self.assertFalse(t.is_alive())
            up, down, _secs = result[0]
            self.assertEqual((up, down), (len(request), len(response)))
        finally:
            client.close()
            remote.close()
            if t.is_alive():
                t.join(timeout=2)

    def test_idle_tunnel_is_dropped_before_the_hard_cap(self):
        import socket as _sock
        import time as _t
        a1, a2 = _sock.socketpair()
        b1, b2 = _sock.socketpair()
        try:
            start = _t.monotonic()
            server.relay(a2, b1, cap=30, idle=0.5)
            self.assertLess(_t.monotonic() - start, 5)
        finally:
            a1.close()
            b2.close()


class Routing(unittest.TestCase):
    def test_infra_goes_direct(self):
        for host in ('github.com', 'api.github.com', 'x.actions.githubusercontent.com',
                     'pypi.org', 'files.pythonhosted.org', 'codeload.github.com',
                     'x.blob.core.windows.net',
                     'raw.githubusercontent.com'.replace('raw.', '')):
            self.assertEqual(server.route(host), 'direct', host)

    def test_proxy_lists_go_direct(self):
        self.assertEqual(server.route('raw.githubusercontent.com'), 'direct')

    def test_faculties_chain(self):
        for host in ('wlo.wat.edu.pl', 'wel.wat.edu.pl', 'www.wim.wat.edu.pl',
                      'planzajec.wcy.wat.edu.pl', 'wml.wat.edu.pl', 'wtc.wat.edu.pl', 'ioe.wat.edu.pl',
                      'www.wig.wat.edu.pl'):
            self.assertEqual(server.route(host), 'chain', host)

    def test_direct_faculty_list_overrides_the_pool(self):
        orig = server.DIRECT_FACULTY
        server.DIRECT_FACULTY = ('wtc.wat.edu.pl',)
        try:
            self.assertEqual(server.route('wtc.wat.edu.pl'), 'direct')
            self.assertEqual(server.route('sub.wtc.wat.edu.pl'), 'direct')
            self.assertEqual(server.route('wlo.wat.edu.pl'), 'chain')  # not listed: still pooled
            self.assertEqual(server.route('wtc.wat.edu.pl.evil.test'), 'deny')
        finally:
            server.DIRECT_FACULTY = orig

    def test_everything_else_denied(self):
        for host in ('evil.example', 'wat.edu.pl.evil.example', '', 'localhost', '127.0.0.1'):
            self.assertEqual(server.route(host), 'deny', host)

    def test_connect_targets(self):
        self.assertEqual(server.split_target('wlo.wat.edu.pl:443'), ('wlo.wat.edu.pl', 443))
        for bad in ('wlo.wat.edu.pl:22', 'no-port', 'a@b:443', 'h/443', 'h:abc'):
            self.assertIsNone(server.split_target(bad), bad)

    def test_backpressure_and_queue(self):
        import threading as _th
        self.assertEqual(server.ProxyServer.request_queue_size, 32)
        self.assertEqual(server.GuiServer.request_queue_size, 32)
        self.assertIsInstance(server.TUNNEL_SLOTS, type(_th.BoundedSemaphore(1)))

    def test_plain_forward_rejects_a_bad_port_without_crashing(self):
        from types import SimpleNamespace
        handler = server.ProxyHandler.__new__(server.ProxyHandler)
        handler.path = 'http://example.test:99999/'
        handler.headers = {}
        denied = []
        handler._deny = lambda code=403: denied.append(code)
        handler.server = SimpleNamespace(requests=0, active=0)
        handler._forward_plain()
        self.assertEqual(denied, [400])
        self.assertEqual((handler.server.requests, handler.server.active), (1, 0))

    def test_fail_closed_list_matches_only_that_host_and_children(self):
        saved = (server.FAIL_CLOSED_ALL, server.FAIL_CLOSED)
        server.FAIL_CLOSED_ALL = False
        server.FAIL_CLOSED = frozenset({'planzajec.wcy.wat.edu.pl'})
        try:
            self.assertTrue(server.fail_closed('planzajec.wcy.wat.edu.pl'))
            self.assertTrue(server.fail_closed('PLANZAJEC.WCY.WAT.EDU.PL.'))
            self.assertTrue(server.fail_closed('sub.planzajec.wcy.wat.edu.pl'))
            self.assertFalse(server.fail_closed('wlo.wat.edu.pl'))
            self.assertFalse(server.fail_closed('planzajec.wcy.wat.edu.pl.evil.test'))
        finally:
            server.FAIL_CLOSED_ALL, server.FAIL_CLOSED = saved

    def test_fail_closed_all_covers_faculty_but_not_outsiders(self):
        saved = (server.FAIL_CLOSED_ALL, server.FAIL_CLOSED)
        server.FAIL_CLOSED_ALL = True
        try:
            self.assertTrue(server.fail_closed('wlo.wat.edu.pl'))
            self.assertTrue(server.fail_closed('deep.sub.wat.edu.pl'))
            self.assertFalse(server.fail_closed('evil.example'))
            self.assertFalse(server.fail_closed('wat.edu.pl.evil.example'))
        finally:
            server.FAIL_CLOSED_ALL, server.FAIL_CLOSED = saved

    def test_faculty_targets_carry_a_positive_marker(self):
        targets = server.faculty_targets('zima')
        for host, (url, marker) in targets.items():
            self.assertTrue(url.startswith('https://'), host)
            self.assertTrue(marker, host)  # every host rejects a marker-less block page


class _RelayResponse:
    def __init__(self, url='https://relay.test/'):
        self.status_code = 200
        self.content = b'<html>ok</html>'
        self.text = self.content.decode('utf-8')
        self.headers = {'ETag': '"v1"', 'Content-Type': 'text/html; charset=utf-8'}
        self.url = url


class _RecordingSession:
    def __init__(self):
        self.calls = []
        self.headers = {'User-Agent': 'runner-ua', 'Accept-Language': 'pl-PL'}

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _RelayResponse(url)


class RelayClient(unittest.TestCase):
    """The refresh-side relay: opt-in, exact-host, safe headers, original URL preserved."""

    KEYS = ('PLANWAT_RELAY_URL', 'PLANWAT_RELAY_TOKEN', 'PLANWAT_RELAY_HOSTS')

    def setUp(self):
        self.saved = {key: os.environ.pop(key, None) for key in self.KEYS}
        self.addCleanup(self.restore)

    def restore(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_no_url_is_a_no_op(self):
        session = _RecordingSession()
        self.assertIs(relay.wrap(session), session)
        self.assertFalse(relay.host_relayed('wlo.wat.edu.pl'))

    def test_only_an_https_root_without_credentials_or_a_fragment_is_accepted(self):
        for raw in ('http://relay.test', 'https://', 'https://user:pass@relay.test',
                    'https://relay.test/#fragment', 'https://relay.test:8443',
                    'https://relay.test:abc', 'https://relay.test:99999',
                    'not a url'):
            os.environ['PLANWAT_RELAY_URL'] = raw
            self.assertEqual(relay.relay_url(), '', raw)
            self.assertFalse(relay.host_relayed('wlo.wat.edu.pl'), raw)
        os.environ['PLANWAT_RELAY_URL'] = 'https://relay.test/'
        self.assertEqual(relay.relay_url(), 'https://relay.test/')

    def test_default_hosts_override_and_off_switch(self):
        os.environ['PLANWAT_RELAY_URL'] = 'https://relay.test'
        for host in relay.DEFAULT_HOSTS:
            self.assertTrue(relay.host_relayed(host.upper() + '.'), host)
        self.assertFalse(relay.host_relayed('planzajec.wcy.wat.edu.pl'))
        self.assertFalse(relay.host_relayed('www.wim.wat.edu.pl'))

        os.environ['PLANWAT_RELAY_HOSTS'] = 'WTC.WAT.EDU.PL., wml.wat.edu.pl.'
        self.assertTrue(relay.host_relayed('wtc.wat.edu.pl'))
        self.assertTrue(relay.host_relayed('wml.wat.edu.pl'))
        self.assertFalse(relay.host_relayed('wlo.wat.edu.pl'))

        os.environ['PLANWAT_RELAY_HOSTS'] = 'off'
        self.assertFalse(relay.host_relayed('wtc.wat.edu.pl'))

    def test_a_listed_https_get_is_rewritten_to_the_worker(self):
        os.environ['PLANWAT_RELAY_URL'] = 'https://relay.test'
        os.environ['PLANWAT_RELAY_TOKEN'] = 's3cret'
        target = 'https://wlo.wat.edu.pl/plany/2026_sem_zima/index.xml?x=1&y=2'
        session = _RecordingSession()
        response = relay.wrap(session).get(target, timeout=30, headers={'Accept': 'text/html'})
        worker_url, kwargs = session.calls[0]
        self.assertEqual(worker_url.split('?', 1)[0], 'https://relay.test')
        from urllib.parse import parse_qs, urlsplit
        self.assertEqual(parse_qs(urlsplit(worker_url).query)['url'], [target])
        self.assertEqual(kwargs['timeout'], 30)
        self.assertEqual(kwargs['headers'],
                         {'Accept': 'text/html', 'Authorization': 'Bearer s3cret'})
        self.assertEqual(response.url, target)  # the caller keeps the faculty URL
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.text, '<html>ok</html>')

    def test_unlisted_hosts_and_plain_http_stay_on_the_original_session(self):
        os.environ['PLANWAT_RELAY_URL'] = 'https://relay.test'
        session = _RecordingSession()
        wrapped = relay.wrap(session)
        wcy = 'https://planzajec.wcy.wat.edu.pl/pl/rozklad'
        plain = 'http://wlo.wat.edu.pl/plany/index.xml'
        wrapped.get(wcy, timeout=5)
        wrapped.get(plain, timeout=5)
        self.assertEqual([url for url, _ in session.calls], [wcy, plain])

    def test_only_safe_headers_are_forwarded_and_the_relay_token_replaces_auth(self):
        os.environ['PLANWAT_RELAY_URL'] = 'https://relay.test'
        os.environ['PLANWAT_RELAY_TOKEN'] = 'relay-secret'
        session = _RecordingSession()
        relay.wrap(session).get(
            'https://wtc.wat.edu.pl/Plany/index.xml', timeout=5,
            headers={'Accept': 'text/html', 'Cookie': 'incap=1',
                     'Authorization': 'Bearer egress-token', 'X-Token': 'egress-token',
                     'If-None-Match': '"abc"', 'User-Agent': 'runner-ua',
                     'Referer': 'https://wtc.wat.edu.pl/Plany/'})
        sent = session.calls[0][1]['headers']
        self.assertNotIn('Cookie', sent)
        self.assertNotIn('X-Token', sent)
        self.assertEqual(sent['Authorization'], 'Bearer relay-secret')
        self.assertEqual(sent['If-None-Match'], '"abc"')
        self.assertEqual(sent['User-Agent'], 'runner-ua')
        self.assertEqual(sent['Referer'], 'https://wtc.wat.edu.pl/Plany/')

    def test_no_token_means_no_authorization_header(self):
        os.environ['PLANWAT_RELAY_URL'] = 'https://relay.test'
        session = _RecordingSession()
        relay.wrap(session).get('https://wtc.wat.edu.pl/Plany/index.xml', timeout=5)
        self.assertNotIn('Authorization', session.calls[0][1]['headers'])

    def test_a_worker_url_with_a_query_keeps_it_and_a_trailing_slash_is_trimmed(self):
        for root, prefix in (('https://relay.test/gateway?version=1',
                              'https://relay.test/gateway?version=1&url='),
                             ('https://relay.test/', 'https://relay.test?url=')):
            os.environ['PLANWAT_RELAY_URL'] = root
            session = _RecordingSession()
            relay.wrap(session).get('https://wtc.wat.edu.pl/Plany/index.xml', timeout=5)
            self.assertTrue(session.calls[0][0].startswith(prefix), root)

    def test_session_attributes_are_delegated(self):
        os.environ['PLANWAT_RELAY_URL'] = 'https://relay.test'
        session = _RecordingSession()
        self.assertIs(relay.wrap(session).headers, session.headers)

    def test_a_block_report_for_a_relayed_host_is_not_sent(self):
        os.environ['PLANWAT_RELAY_URL'] = 'https://relay.test'
        opened = []

        class Opener:
            def open(self, *args, **kwargs):
                opened.append((args, kwargs))
                raise OSError('offline')

        with unittest.mock.patch('urllib.request.build_opener', return_value=Opener()):
            refresh.post_block_report('wtc.wat.edu.pl', url='http://egress.test/api/block')
            self.assertEqual(opened, [])  # relayed: no pool exit to blame
            refresh.post_block_report('example.test', url='http://egress.test/api/block')
            self.assertEqual(len(opened), 1)  # everything else still reports


class RelayRouting(unittest.TestCase):
    def test_the_worker_host_is_direct_without_opening_all_workers_dev(self):
        orig = server.DIRECT_SUFFIXES
        server.DIRECT_SUFFIXES = orig + ('planwat-egress.example.workers.dev',)
        try:
            self.assertEqual(server.route('planwat-egress.example.workers.dev'), 'direct')
            self.assertEqual(server.route('PLANWAT-EGRESS.EXAMPLE.WORKERS.DEV.'), 'direct')
            self.assertEqual(server.route('someone-else.workers.dev'), 'deny')
            self.assertEqual(server.route('planwat-egress.example.workers.dev.evil.test'), 'deny')
        finally:
            server.DIRECT_SUFFIXES = orig

    def test_fail_closed_wins_over_the_direct_host_list(self):
        saved = (server.DIRECT_SUFFIXES, server.DIRECT_FACULTY, server.POOL_OFF,
                 server.FAIL_CLOSED_ALL, server.FAIL_CLOSED)
        server.DIRECT_SUFFIXES = saved[0] + ('wat.edu.pl',)
        server.DIRECT_FACULTY, server.POOL_OFF = (), False
        server.FAIL_CLOSED_ALL = False
        server.FAIL_CLOSED = frozenset({'planzajec.wcy.wat.edu.pl'})
        try:
            self.assertEqual(server.route('wlo.wat.edu.pl'), 'direct')
            self.assertEqual(server.route('planzajec.wcy.wat.edu.pl'), 'chain')
        finally:
            (server.DIRECT_SUFFIXES, server.DIRECT_FACULTY, server.POOL_OFF,
             server.FAIL_CLOSED_ALL, server.FAIL_CLOSED) = saved

    def test_host_lists_are_normalized(self):
        self.assertEqual(server.split_hosts(' WLO.WAT.EDU.PL., wtc.wat.edu.pl. '),
                         ('wlo.wat.edu.pl', 'wtc.wat.edu.pl'))
        self.assertEqual(server.split_hosts(''), ())


class RelayWiring(unittest.TestCase):
    def test_runner_and_egress_configs_carry_the_relay_settings(self):
        runner = (ROOT / 'deploy' / 'runner' / 'compose.yml').read_text(encoding='utf-8')
        for key in ('PLANWAT_RELAY_URL', 'PLANWAT_RELAY_TOKEN', 'PLANWAT_RELAY_HOSTS',
                    'EGRESS_DIRECT_HOSTS'):
            self.assertIn(key, runner)
        fragment = (ROOT / 'tools' / 'egress' / 'compose.fragment.yml').read_text(encoding='utf-8')
        self.assertIn('EGRESS_DIRECT_HOSTS', fragment)
        env = (ROOT / 'deploy' / 'runner' / '.env.example').read_text(encoding='utf-8')
        for key in ('PLANWAT_RELAY_URL', 'PLANWAT_RELAY_TOKEN', 'PLANWAT_RELAY_HOSTS',
                    'EGRESS_DIRECT_HOSTS'):
            self.assertIn(key, env)

    def test_the_worker_token_is_a_secret_not_a_wrangler_var(self):
        text = (ROOT / 'tools' / 'egress' / 'cloudflare' / 'wrangler.toml').read_text(encoding='utf-8')
        self.assertNotRegex(text, r'(?m)^\s*PLANWAT_RELAY_TOKEN\s*=')
        self.assertIn('secret put PLANWAT_RELAY_TOKEN', text)


class PlainHeaders(unittest.TestCase):
    class Headers(dict):
        def __init__(self, items, connection_values=()):
            super().__init__(items)
            self._connection = list(connection_values)

        def get_all(self, name):
            return self._connection if name.lower() == 'connection' else None

    def test_hop_by_hop_host_and_length_are_dropped(self):
        h = self.Headers([
            ('Host', 'evil.example'),
            ('Content-Length', '999'),
            ('Proxy-Connection', 'close'),
            ('Connection', 'x-secret'),
            ('Keep-Alive', 'timeout=5'),
            ('X-Secret', 'leak'),
            ('X-Keep', 'yes'),
            ('Cookie', 'a=b'),
            ('Transfer-Encoding', 'chunked'),
        ], connection_values=['X-Secret'])
        out = server.plain_forward_headers(h)
        self.assertIn('X-Keep: yes\r\n', out)
        self.assertIn('Cookie: a=b\r\n', out)
        for gone in ('Host:', 'Content-Length:', 'Proxy-Connection:', 'Connection:',
                     'Keep-Alive:', 'X-Secret:', 'Transfer-Encoding:'):
            self.assertNotIn(gone, out)

    def test_header_injection_is_dropped(self):
        h = self.Headers([('X-Ok', 'v\r\nInjected: yes'), ('X-Bad\r\nInj', 'v')])
        out = server.plain_forward_headers(h)
        self.assertEqual(out, '')


class Resp:
    def __init__(self, status, content=b''):
        self.status_code, self.content = status, content


class Flaky:
    def __init__(self, script):
        self.script, self.calls = script, []

    def get(self, url, timeout=0, headers=None):
        self.calls.append(url)
        step = self.script[min(len(self.calls) - 1, len(self.script) - 1)]
        if isinstance(step, Exception):
            raise step
        return step


class Retry(unittest.TestCase):
    def test_flaky_then_healthy_returns(self):
        session = Flaky([TimeoutError('t'), Resp(200, b'ok')])
        slept = []
        r = refresh.get_with_retry(session, 'https://example.test/', 5, {}, sleep=slept.append)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(session.calls), 2)
        self.assertEqual(len(slept), 1)

    def test_404_and_verdicts_are_not_retried(self):
        session = Flaky([Resp(404), Resp(200)])
        slept = []
        r = refresh.get_with_retry(session, 'https://example.test/', 5, {}, sleep=slept.append)
        self.assertEqual(r.status_code, 404)
        self.assertEqual((len(session.calls), slept), (1, []))

    def test_503_retries_then_raises_for_the_caller_to_stop_on(self):
        session = Flaky([Resp(503), Resp(503), Resp(200)])
        with self.assertRaises(core.Blocked):
            refresh.get_with_retry(session, 'https://example.test/', 5, {}, retries=1,
                                   sleep=lambda s: None)
        self.assertEqual(len(session.calls), 2)

    def test_persistent_failure_raises_last_error(self):
        session = Flaky([ConnectionError('down')])
        with self.assertRaises(ConnectionError):
            refresh.get_with_retry(session, 'https://example.test/', 5, {}, retries=2, sleep=lambda s: None)
        self.assertEqual(len(session.calls), 3)


class Report(unittest.TestCase):
    def test_empty_url_is_silent(self):
        refresh.post_run_report({'exit': 0}, url='')

    def test_unreachable_gui_never_raises(self):
        refresh.post_run_report({'exit': 0}, url='http://127.0.0.1:1/api/run', timeout=1)

    def test_report_round_trips_through_the_gui(self):
        import json
        import threading
        import time
        import urllib.request
        from types import SimpleNamespace
        tmp = Path(tempfile.mkdtemp())
        test_pool = pool.ProxyPool(tmp / 'pool.json', R2)
        test_pool.entries = {'http://8.8.8.8:8080': {'status': 'ok', 'latency_ms': 120,
                                                     'fails': 0, 'source': 'test',
                                                     'last_checked': time.time(),
                                                     'hosts': {'example.test': {'ok': True,
                                                                                'ms': 120}}}}
        gui = server.GuiServer(('127.0.0.1', 0), server.GuiHandler)
        gui.pool, gui.runs, gui.proxy_port = test_pool, server.RunLog(tmp / 'runs.json'), 8888
        gui.proxy_server = SimpleNamespace(fallbacks={}, blocks=1,
                                           fallbacks_lock=threading.Lock())
        threading.Thread(target=gui.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{gui.server_address[1]}'
        refresh.post_run_report({'started': 's', 'ended': 'e', 'exit': 0,
                                 'faculties': {'wlo': {'checked': 5, 'changed': 1, 'blocked': False}}},
                                url=base + '/api/run', timeout=5)
        with urllib.request.urlopen(base + '/api/status', timeout=5) as r:
            st = json.loads(r.read().decode('utf-8'))
        # truthful per-host rollup: verified>0 => ROTATING
        self.assertEqual(st['mode'], 'ROTATING')
        self.assertEqual(st['fallbacks'], {})
        self.assertEqual(st['runs'][0]['faculties']['wlo']['changed'], 1)
        self.assertIn('p50_ok_ms', st['pool'])
        self.assertIn('p95_ok_ms', st['pool'])
        with urllib.request.urlopen(base + '/', timeout=5) as r:
            page = r.read().decode('utf-8')
        self.assertIn('ROTATING', page)
        self.assertIn('http://8.8.8.8:8080', page)
        self.assertIn('p50', page)
        self.assertIn('p95', page)
        gui.shutdown()

    def test_global_ok_without_verified_is_direct(self):
        import json
        import threading
        import time
        import urllib.request
        from types import SimpleNamespace
        tmp = Path(tempfile.mkdtemp())
        test_pool = pool.ProxyPool(tmp / 'pool.json', R2)
        test_pool.entries = {'http://8.8.8.8:8080': {'status': 'ok', 'latency_ms': 120,
                                                     'fails': 0, 'source': 'test',
                                                     'last_checked': time.time(), 'hosts': {}}}
        gui = server.GuiServer(('127.0.0.1', 0), server.GuiHandler)
        gui.pool, gui.runs, gui.proxy_port = test_pool, server.RunLog(tmp / 'runs.json'), 8888
        gui.proxy_server = SimpleNamespace(fallbacks={}, blocks=0,
                                           fallbacks_lock=threading.Lock())
        threading.Thread(target=gui.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{gui.server_address[1]}'
        try:
            with urllib.request.urlopen(base + '/api/status', timeout=5) as r:
                st = json.loads(r.read().decode('utf-8'))
            self.assertEqual(st['mode'], 'DIRECT (pula pusta)')
        finally:
            gui.shutdown()

    def test_open_runs_banner(self):
        tmp = Path(tempfile.mkdtemp())
        rl = server.RunLog(tmp / 'runs.json')
        rl.add({'phase': 'started', 'id': 1})
        self.assertEqual(len(rl.open_runs), 1)
        rl.add({'exit': 0, 'started': 's'})
        self.assertEqual(len(rl.open_runs), 0)
        self.assertEqual(len(rl.runs), 1)

    def test_open_runs_banner_in_dashboard(self):
        import threading
        import time
        import urllib.request
        from types import SimpleNamespace
        tmp = Path(tempfile.mkdtemp())
        test_pool = pool.ProxyPool(tmp / 'pool.json', R2)
        runs = server.RunLog(tmp / 'runs.json')
        runs.add({'phase': 'started', 'id': 7})
        gui = server.GuiServer(('127.0.0.1', 0), server.GuiHandler)
        gui.pool, gui.runs, gui.proxy_port = test_pool, runs, 8888
        gui.proxy_server = SimpleNamespace(fallbacks={}, blocks=0,
                                           fallbacks_lock=threading.Lock())
        threading.Thread(target=gui.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{gui.server_address[1]}'
        try:
            with urllib.request.urlopen(base + '/', timeout=5) as r:
                page = r.read().decode('utf-8')
            self.assertIn('przebieg w toku', page)
            self.assertIn('"id": 7', page)
        finally:
            gui.shutdown()

    def test_refresh_lock_202_then_409(self):
        import threading
        import urllib.request
        import urllib.error
        from types import SimpleNamespace
        tmp = Path(tempfile.mkdtemp())
        test_pool = pool.ProxyPool(tmp / 'pool.json', R2)
        gui = server.GuiServer(('127.0.0.1', 0), server.GuiHandler)
        gui.pool, gui.runs, gui.proxy_port = test_pool, server.RunLog(tmp / 'runs.json'), 8888
        gui.proxy_server = SimpleNamespace(fallbacks={}, blocks=0,
                                           fallbacks_lock=threading.Lock())
        threading.Thread(target=gui.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{gui.server_address[1]}'
        try:
            req = urllib.request.Request(base + '/api/refresh', data=b'', method='POST')
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(r.status, 202)
            req2 = urllib.request.Request(base + '/api/refresh', data=b'', method='POST')
            try:
                urllib.request.urlopen(req2, timeout=5)
                self.fail('expected 409')
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 409)
        finally:
            test_pool.force_refresh = False
            try:
                test_pool.heal_event.clear()
            except Exception:
                pass
            gui.shutdown()

    def test_token_auth(self):
        import os as _os
        import threading
        import urllib.request
        import urllib.error
        import json as _json
        from types import SimpleNamespace
        prev = _os.environ.get('EGRESS_API_TOKEN')
        _os.environ['EGRESS_API_TOKEN'] = 'secret123'
        tmp = Path(tempfile.mkdtemp())
        test_pool = pool.ProxyPool(tmp / 'pool.json', R2)
        gui = server.GuiServer(('127.0.0.1', 0), server.GuiHandler)
        gui.pool, gui.runs, gui.proxy_port = test_pool, server.RunLog(tmp / 'runs.json'), 8888
        gui.proxy_server = SimpleNamespace(fallbacks={}, blocks=0,
                                           fallbacks_lock=threading.Lock())
        threading.Thread(target=gui.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{gui.server_address[1]}'
        try:
            req = urllib.request.Request(base + '/api/run',
                                         data=_json.dumps({'exit': 0}).encode(),
                                         headers={'Content-Type': 'application/json'},
                                         method='POST')
            try:
                urllib.request.urlopen(req, timeout=5)
                self.fail('expected 401')
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 401)
            req2 = urllib.request.Request(base + '/api/run',
                                          data=_json.dumps({'exit': 0}).encode(),
                                          headers={'Content-Type': 'application/json',
                                                   'X-Token': 'secret123'},
                                          method='POST')
            with urllib.request.urlopen(req2, timeout=5) as r:
                self.assertEqual(r.status, 200)
            # Bearer is the documented form and must work too.
            req3 = urllib.request.Request(base + '/api/run',
                                          data=_json.dumps({'exit': 1}).encode(),
                                          headers={'Content-Type': 'application/json',
                                                   'Authorization': 'Bearer secret123'},
                                          method='POST')
            with urllib.request.urlopen(req3, timeout=5) as r:
                self.assertEqual(r.status, 200)
            req4 = urllib.request.Request(base + '/api/run',
                                          data=_json.dumps({'exit': 1}).encode(),
                                          headers={'Content-Type': 'application/json',
                                                   'Authorization': 'Bearer wrong'},
                                          method='POST')
            try:
                urllib.request.urlopen(req4, timeout=5)
                self.fail('expected 401')
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code, 401)
        finally:
            if prev is None:
                _os.environ.pop('EGRESS_API_TOKEN', None)
            else:
                _os.environ['EGRESS_API_TOKEN'] = prev
            gui.shutdown()

    def test_non_ascii_token_is_just_a_mismatch(self):
        import os as _os
        prev = _os.environ.get('EGRESS_API_TOKEN')
        _os.environ['EGRESS_API_TOKEN'] = 'sekret'
        try:
            h = server.GuiHandler.__new__(server.GuiHandler)
            h.headers = {'X-Token': 'sécret'}
            self.assertFalse(h._check_token())
            h.headers = {'Authorization': 'Bearer sécret'}
            self.assertFalse(h._check_token())
            h.headers = {'Authorization': 'Bearer sekret'}
            self.assertTrue(h._check_token())
        finally:
            if prev is None:
                _os.environ.pop('EGRESS_API_TOKEN', None)
            else:
                _os.environ['EGRESS_API_TOKEN'] = prev

    def test_gui_body_cap_and_bad_lengths(self):

        handler = server.GuiHandler.__new__(server.GuiHandler)
        for headers, expected in (
            ({'Content-Length': str(server.GUI_BODY_CAP + 1)}, OverflowError),
            ({'Content-Length': 'nope'}, None),
            ({'Content-Length': '-1'}, None),
        ):
            handler.headers = headers
            handler.rfile = type('R', (), {'read': lambda self, n: b''})()
            try:
                self.assertIs(handler._read_body(), expected)
            except OverflowError:
                self.assertIs(expected, OverflowError)

    def test_auth_is_checked_before_a_body_is_read(self):
        import os as _os
        import socket as _sock
        import threading
        from types import SimpleNamespace
        prev = _os.environ.get('EGRESS_API_TOKEN')
        _os.environ['EGRESS_API_TOKEN'] = 'sekret'
        tmp = Path(tempfile.mkdtemp())
        test_pool = pool.ProxyPool(tmp / 'pool.json', R2)
        gui = server.GuiServer(('127.0.0.1', 0), server.GuiHandler)
        gui.pool, gui.runs, gui.proxy_port = test_pool, server.RunLog(tmp / 'runs.json'), 8888
        gui.proxy_server = SimpleNamespace(fallbacks={}, blocks=0,
                                           fallbacks_lock=threading.Lock())
        threading.Thread(target=gui.serve_forever, daemon=True).start()
        try:
            with _sock.create_connection(gui.server_address, timeout=3) as s:
                # Announce a large body but never send it: only an auth check before the
                # read can answer promptly instead of blocking for the whole payload.
                s.sendall(b'POST /api/run HTTP/1.1\r\nHost: gui\r\n'
                          b'Content-Length: 500000\r\n\r\n')
                s.settimeout(3)
                line = s.recv(4096).split(b'\r\n', 1)[0]
            self.assertIn(b' 401 ', line)
        finally:
            if prev is None:
                _os.environ.pop('EGRESS_API_TOKEN', None)
            else:
                _os.environ['EGRESS_API_TOKEN'] = prev
            gui.shutdown()

    def test_stale_open_run_is_expired_and_persisted(self):
        tmp = Path(tempfile.mkdtemp()) / 'runs.json'
        runs = server.RunLog(tmp)
        runs.add({'phase': 'started', 'id': 1})
        old = time.time() - server.RunLog.STALE_OPEN_S - 60
        runs.open_runs[0]['received'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(old))
        self.assertEqual(runs.open_snapshot(), [])
        again = server.RunLog(tmp)
        self.assertEqual(again.open_runs, [])  # the expiry survived the rewrite
        runs.add({'phase': 'started', 'id': 2})
        self.assertEqual([r['id'] for r in server.RunLog(tmp).open_runs], [2])

    def test_dashboard_banner_does_not_rewrite_run_data(self):
        page = server.dashboard({'open_runs': [{'id': 1}], 'note': '%BANNER%',
                                 'nonce': '%NONCE%'})
        self.assertIn('przebieg w toku', page)
        self.assertIn('"note": "%BANNER%"', page)  # BOOT was inserted after the banner pass
        self.assertIn('"nonce": "%NONCE%"', page)  # ...and after the nonce pass

    def test_dashboard_has_a_nonce_and_security_headers(self):
        import re
        import threading
        import urllib.request
        from types import SimpleNamespace
        tmp = Path(tempfile.mkdtemp())
        test_pool = pool.ProxyPool(tmp / 'pool.json', R2)
        gui = server.GuiServer(('127.0.0.1', 0), server.GuiHandler)
        gui.pool, gui.runs, gui.proxy_port = test_pool, server.RunLog(tmp / 'runs.json'), 8888
        gui.proxy_server = SimpleNamespace(fallbacks={}, blocks=0,
                                           fallbacks_lock=threading.Lock())
        threading.Thread(target=gui.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{gui.server_address[1]}'
        try:
            with urllib.request.urlopen(base + '/', timeout=5) as r:
                page = r.read().decode('utf-8')
                csp = r.headers.get('Content-Security-Policy') or ''
                self.assertEqual(r.headers.get('X-Frame-Options'), 'DENY')
                self.assertEqual(r.headers.get('X-Content-Type-Options'), 'nosniff')
                self.assertEqual(r.headers.get('Referrer-Policy'), 'no-referrer')
            nonce = re.search(r"'nonce-([^']+)'", csp)
            self.assertIsNotNone(nonce, csp)
            self.assertIn(f'nonce="{nonce.group(1)}"', page)
            self.assertNotIn("<script>", page)
        finally:
            gui.shutdown()


class EgressHeaders(unittest.TestCase):
    def _set_token(self, value):
        import os
        prev = os.environ.get('EGRESS_API_TOKEN')
        if value is None:
            os.environ.pop('EGRESS_API_TOKEN', None)
        else:
            os.environ['EGRESS_API_TOKEN'] = value
        return prev

    def _restore(self, prev):
        import os
        if prev is None:
            os.environ.pop('EGRESS_API_TOKEN', None)
        else:
            os.environ['EGRESS_API_TOKEN'] = prev

    def test_bearer_and_x_token_are_both_sent(self):
        prev = self._set_token('sekret')
        try:
            headers = refresh.egress_headers()
            self.assertEqual(headers['Authorization'], 'Bearer sekret')
            self.assertEqual(headers['X-Token'], 'sekret')
            self.assertEqual(headers['Content-Type'], 'application/json')
        finally:
            self._restore(prev)

    def test_no_token_keeps_the_json_content_type(self):
        prev = self._set_token(None)
        try:
            self.assertEqual(refresh.egress_headers(),
                             {'Content-Type': 'application/json'})
        finally:
            self._restore(prev)

    def test_tick_forwards_slot_context_to_the_gui(self):
        sent = []
        now = [0.0]
        p = refresh.Progress(url='http://egress/api/progress', run='r1',
                             post=sent.append, clock=lambda: now[0])
        self.assertTrue(p.tick('wlo', 3, 10, faculty='wlo', lane='wlo', ahead=True, term='zima'))
        self.assertEqual(sent[0], {'event': 'tick', 'run': 'r1', 'slot': 'wlo', 'done': 3,
                                   'total': 10, 'faculty': 'wlo', 'lane': 'wlo', 'ahead': True,
                                   'term': 'zima'})
        now[0] = 1.0
        self.assertFalse(p.tick('wlo', 4, 10))  # throttled per slot


class BlockDispatch(unittest.TestCase):
    """The crawler reports block pages; the proxy demotes the exit that carried the tunnel."""

    HOST = 'wlo.wat.edu.pl'

    def pool_with_verified(self):
        tmp = Path(tempfile.mkdtemp()) / 'pool.json'
        p = pool.ProxyPool(tmp, R2_WLO)
        p.entries = {'http://a:1': {'status': 'ok', 'latency_ms': 10, 'fails': 0,
                                    'hosts': {self.HOST: {'ok': True, 'ms': 10}}}}
        return p

    def stub(self, p, recent):
        from types import SimpleNamespace
        return SimpleNamespace(pool=p, recent=deque(recent), recent_lock=threading.Lock())

    def test_demote_recent_marks_the_exit_that_carried_the_last_tunnel(self):
        p = self.pool_with_verified()
        stub = self.stub(p, [(self.HOST, 'http://a:1', time.monotonic())])
        via = server.ProxyServer.demote_recent(stub, self.HOST)
        self.assertEqual(via, 'http://a:1')
        self.assertFalse(p.entries['http://a:1']['hosts'][self.HOST]['ok'])

    def test_demote_recent_ignores_direct_old_and_other_host_tunnels(self):
        p = self.pool_with_verified()
        now = time.monotonic()
        stub = self.stub(p, [('other.test', 'http://a:1', now), (self.HOST, 'direct', now)])
        self.assertIsNone(server.ProxyServer.demote_recent(stub, self.HOST))
        stub = self.stub(p, [(self.HOST, 'http://a:1', now - 9999)])
        self.assertIsNone(server.ProxyServer.demote_recent(stub, self.HOST))
        self.assertTrue(p.entries['http://a:1']['hosts'][self.HOST]['ok'])

    def test_the_block_endpoint_demotes_through_the_gui(self):
        import json
        import urllib.request
        from types import SimpleNamespace
        tmp = Path(tempfile.mkdtemp())
        test_pool = pool.ProxyPool(tmp / 'pool.json', R2)
        gui = server.GuiServer(('127.0.0.1', 0), server.GuiHandler)
        calls = []
        gui.pool, gui.runs, gui.proxy_port = test_pool, server.RunLog(tmp / 'runs.json'), 8888
        gui.proxy_server = SimpleNamespace(demote_recent=lambda h: calls.append(h) or 'http://a:1',
                                           fallbacks={}, blocks=0,
                                           fallbacks_lock=threading.Lock())
        threading.Thread(target=gui.serve_forever, daemon=True).start()
        try:
            base = f'http://127.0.0.1:{gui.server_address[1]}'
            req = urllib.request.Request(base + '/api/block',
                                         data=json.dumps({'host': self.HOST}).encode('utf-8'),
                                         headers={'Content-Type': 'application/json'},
                                         method='POST')
            with urllib.request.urlopen(req, timeout=5) as r:
                body = json.loads(r.read().decode('utf-8'))
            self.assertEqual(body['demoted'], 'http://a:1')
            self.assertEqual(calls, [self.HOST])
        finally:
            gui.shutdown()


class FakeClock:
    """A hand-cranked clock for the egress' arrival-stamped progress state."""

    def __init__(self, now=1000.0):
        self.now = now

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class LiveRunTest(unittest.TestCase):
    """LiveRun: coarse crawler events in, a percent and an honest ETA out."""

    def start(self, clock, lanes=None, run='r1'):
        live = server.LiveRun(clock=clock)
        live.event({'event': 'run_start', 'run': run, 'profile': 'selfhosted',
                    'lanes': lanes or [{'lane': 'wat-edge', 'faculties': ['wlo', 'wel']},
                                       {'lane': 'wcy', 'faculties': ['wcy']}]})
        return live

    def test_snapshot_before_any_event_has_no_run(self):
        self.assertEqual(server.LiveRun(clock=FakeClock()).snapshot(),
                         {'active': False, 'run': None})

    def test_percent_and_eta_come_from_the_run_s_own_ticks(self):
        clock = FakeClock()
        live = self.start(clock, lanes=[{'lane': 'wlo', 'faculties': ['wlo']}])
        live.event({'event': 'faculty_start', 'run': 'r1', 'slot': 'wlo', 'faculty': 'wlo',
                    'lane': 'wlo', 'total': 100})
        for advance, done in ((60, 12), (60, 24)):
            clock.advance(advance)
            live.event({'event': 'tick', 'run': 'r1', 'slot': 'wlo', 'done': done, 'total': 100})
        snap = live.snapshot()
        self.assertTrue(snap['active'])
        self.assertEqual((snap['done'], snap['total'], snap['pct']), (24, 100, 24.0))
        slot = snap['lanes'][0]['slots'][0]
        self.assertEqual((slot['status'], slot['rate']), ('crawling', 0.2))
        self.assertEqual(slot['eta_s'], 380)  # 76 groups left at 0.2/s
        self.assertEqual(snap['eta_s'], 440)  # the lane's 380 plus the publish tail
        self.assertAlmostEqual(snap['eta_at'], clock.now + 440, places=3)

    def test_a_queued_faculty_is_estimated_from_its_siblings(self):
        clock = FakeClock()
        live = self.start(clock)
        live.event({'event': 'faculty_start', 'run': 'r1', 'slot': 'wlo', 'faculty': 'wlo',
                    'lane': 'wat-edge', 'total': 50})
        clock.advance(60)
        live.event({'event': 'tick', 'run': 'r1', 'slot': 'wlo', 'done': 30, 'total': 50})
        snap = live.snapshot()
        self.assertTrue(snap['estimated'])
        self.assertEqual(snap['pct'], 20.0)  # 30 of the three 50-group slots
        wat = [l for l in snap['lanes'] if l['lane'] == 'wat-edge'][0]
        wlo, wel = wat['slots']
        self.assertEqual(wlo['eta_s'], 40)
        self.assertTrue(wel['estimated'])
        self.assertEqual((wel['status'], wel['total'], wel['rate'], wel['eta_s']),
                         ('queued', 50, 0.5, 100))  # the sibling median, flagged
        self.assertEqual(wat['eta_s'], 140)
        self.assertEqual(snap['eta_s'], 200)  # the slower lane plus the publish tail

    def test_waiting_suspends_the_estimate_until_the_wall_topples(self):
        clock = FakeClock()
        live = self.start(clock, lanes=[{'lane': 'wlo', 'faculties': ['wlo']}])
        live.event({'event': 'faculty_start', 'run': 'r1', 'slot': 'wlo', 'faculty': 'wlo',
                    'lane': 'wlo', 'total': 40})
        clock.advance(30)
        live.event({'event': 'tick', 'run': 'r1', 'slot': 'wlo', 'done': 10, 'total': 40})
        clock.advance(10)
        live.event({'event': 'wait_start', 'run': 'r1', 'lane': 'wlo', 'faculties': ['wlo'],
                    'budget': 3600})
        snap = live.snapshot()
        self.assertTrue(snap['waiting'])
        self.assertEqual(snap['lanes'][0]['slots'][0]['status'], 'waiting')
        self.assertIsNone(snap['eta_s'])  # no number is better than a wrong one
        self.assertIsNone(snap['lanes'][0]['slots'][0]['eta_s'])
        clock.advance(3600)  # the budget runs out; the wall held
        live.event({'event': 'wait_end', 'run': 'r1', 'lane': 'wlo', 'faculties': ['wlo'],
                    'waited': 3600, 'probes': 5, 'recovered': False})
        snap = live.snapshot()
        self.assertFalse(snap['waiting'])
        self.assertEqual(snap['lanes'][0]['slots'][0]['status'], 'blocked')
        self.assertIsNone(snap['eta_s'])

    def test_each_lane_waits_on_its_own_wall(self):
        clock = FakeClock()
        live = self.start(clock, lanes=[{'lane': 'wlo', 'faculties': ['wlo']},
                                        {'lane': 'wel', 'faculties': ['wel']}])
        live.event({'event': 'faculty_start', 'run': 'r1', 'slot': 'wlo', 'faculty': 'wlo',
                    'lane': 'wlo', 'total': 20})
        live.event({'event': 'faculty_start', 'run': 'r1', 'slot': 'wel', 'faculty': 'wel',
                    'lane': 'wel', 'total': 20})
        live.event({'event': 'wait_start', 'run': 'r1', 'id': 'wlo', 'lane': 'wlo',
                    'faculties': ['wlo'], 'slots': ['wlo'], 'budget': 60})
        live.event({'event': 'wait_start', 'run': 'r1', 'id': 'wel', 'lane': 'wel',
                    'faculties': ['wel'], 'slots': ['wel'], 'budget': 120})
        snap = live.snapshot()
        self.assertTrue(snap['waiting'])
        self.assertEqual(sorted(snap['wait']['lanes']), ['wel', 'wlo'])
        self.assertEqual(sorted(snap['wait']['faculties']), ['wel', 'wlo'])
        self.assertEqual(snap['wait']['budget'], 120)
        self.assertEqual([l['slots'][0]['status'] for l in snap['lanes']], ['waiting', 'waiting'])
        # One wall topples: only that lane resumes; the other stays suspended.
        live.event({'event': 'wait_end', 'run': 'r1', 'id': 'wlo', 'lane': 'wlo',
                    'faculties': ['wlo'], 'slots': ['wlo'], 'recovered': True})
        snap = live.snapshot()
        self.assertEqual(snap['wait']['faculties'], ['wel'])
        self.assertEqual([l['slots'][0]['status'] for l in snap['lanes']], ['queued', 'waiting'])
        # The run ending clears every outstanding wait.
        live.event({'event': 'run_done', 'run': 'r1', 'exit': 0})
        snap = live.snapshot()
        self.assertIsNone(snap['wait'])
        self.assertFalse(snap['waiting'])
        self.assertEqual([l['slots'][0]['status'] for l in snap['lanes']], ['queued', 'stopped'])

    def test_a_late_ahead_slot_is_tracked_under_its_lane(self):
        clock = FakeClock()
        live = self.start(clock, lanes=[{'lane': 'wlo', 'faculties': ['wlo']}])
        live.event({'event': 'faculty_start', 'run': 'r1', 'slot': 'wlo~lato', 'faculty': 'wlo',
                    'lane': 'wlo', 'ahead': True, 'term': 'lato', 'total': 30})
        snap = live.snapshot()
        wlo = [l for l in snap['lanes'] if l['lane'] == 'wlo'][0]
        ahead = [s for s in wlo['slots'] if s['slot'] == 'wlo~lato'][0]
        self.assertTrue(ahead['ahead'])
        self.assertEqual(ahead['term'], 'lato')
        self.assertEqual(ahead['status'], 'crawling')

    def test_slot_lane_and_wait_caps_bound_the_page(self):
        live = server.LiveRun(clock=FakeClock())
        names = [f'f{i}' for i in range(server.LiveRun.MAX_SLOTS + 40)]
        lanes = [{'lane': 'flood', 'faculties': names}]
        lanes += [{'lane': f'l{i}', 'faculties': [f'x{i}']}
                  for i in range(server.LiveRun.MAX_LANES + 20)]
        live.event({'event': 'run_start', 'run': 'r1', 'lanes': lanes})
        with live.lock:
            self.assertEqual(len(live.state['slots']), server.LiveRun.MAX_SLOTS)
            self.assertLessEqual(len(live.state['lanes']), server.LiveRun.MAX_LANES)
        # A late event for an unknown slot cannot push the cap either.
        for i in range(server.LiveRun.MAX_SLOTS + 10):
            live.event({'event': 'tick', 'run': 'r1', 'slot': f'late{i}', 'done': 1, 'total': 2})
        with live.lock:
            self.assertEqual(len(live.state['slots']), server.LiveRun.MAX_SLOTS)
        # Waits are capped too (the oldest is evicted, never the list grown).
        for i in range(server.LiveRun.MAX_WAITS + 8):
            live.event({'event': 'wait_start', 'run': 'r1', 'id': f'w{i}',
                        'lane': f'w{i}', 'faculties': []})
        with live.lock:
            self.assertEqual(len(live.state['waits']), server.LiveRun.MAX_WAITS)

    def test_malformed_event_fields_are_ignored_not_fatal(self):
        clock = FakeClock()
        live = server.LiveRun(clock=clock)
        live.event({'event': 'run_start', 'run': 'r1',
                    'lanes': [{'lane': 'bad', 'faculties': 5},
                              {'lane': 'ok', 'faculties': ['wlo']}]})
        live.event({'event': 'wait_start', 'run': 'r1', 'id': 'x', 'lane': 'x',
                    'faculties': 5, 'slots': {'wlo': 1}, 'budget': 'soon'})
        live.event({'event': 'tick', 'run': 'r1', 'slot': ['wlo'], 'done': 'many',
                    'total': {}})
        snap = live.snapshot()
        self.assertEqual([s['slot'] for s in snap['lanes'][0]['slots']], ['wlo'])
        self.assertEqual(snap['wait']['budget'], 0)

    def test_completion_closes_the_lane_and_the_run(self):

        clock = FakeClock()
        live = self.start(clock, lanes=[{'lane': 'wlo', 'faculties': ['wlo']}])
        live.event({'event': 'faculty_start', 'run': 'r1', 'slot': 'wlo', 'faculty': 'wlo',
                    'lane': 'wlo', 'total': 40})
        clock.advance(60)
        live.event({'event': 'tick', 'run': 'r1', 'slot': 'wlo', 'done': 37, 'total': 40})
        clock.advance(20)
        live.event({'event': 'faculty_done', 'run': 'r1', 'slot': 'wlo', 'faculty': 'wlo',
                    'lane': 'wlo', 'changed': 3, 'blocked': False, 'complete': True})
        snap = live.snapshot()
        slot = snap['lanes'][0]['slots'][0]
        self.assertEqual((slot['status'], slot['done'], slot['total']), ('done', 40, 40))
        self.assertEqual(snap['pct'], 100.0)
        self.assertEqual(snap['eta_s'], 60)  # only the publish tail is left
        live.event({'event': 'run_done', 'run': 'r1', 'exit': 0, 'blocked': False,
                    'incomplete': False, 'degraded': False, 'changed': 3})
        snap = live.snapshot()
        self.assertFalse(snap['active'])
        self.assertEqual((snap['exit'], snap['changed']), (0, 3))
        self.assertEqual(snap['eta_s'], 0)

    def test_stalled_and_stale_are_honest_about_going_quiet(self):
        clock = FakeClock()
        live = self.start(clock, lanes=[{'lane': 'wlo', 'faculties': ['wlo']}])
        live.event({'event': 'faculty_start', 'run': 'r1', 'slot': 'wlo', 'faculty': 'wlo',
                    'lane': 'wlo', 'total': 40})
        clock.advance(30)
        live.event({'event': 'tick', 'run': 'r1', 'slot': 'wlo', 'done': 10, 'total': 40})
        clock.advance(server.LiveRun.STALL_S + 5)
        snap = live.snapshot()
        self.assertEqual(snap['lanes'][0]['slots'][0]['status'], 'stalled')
        self.assertIsNone(snap['eta_s'])
        self.assertTrue(snap['active'])
        self.assertFalse(snap['stale'])
        clock.advance(server.LiveRun.STALE_S)
        self.assertTrue(live.snapshot()['stale'])
        # the slot recovers the moment its next tick lands
        clock.advance(0)
        live.event({'event': 'tick', 'run': 'r1', 'slot': 'wlo', 'done': 20, 'total': 40})
        snap = live.snapshot()
        self.assertEqual(snap['lanes'][0]['slots'][0]['status'], 'crawling')
        self.assertFalse(snap['stale'])

    def test_a_new_run_replaces_a_finished_one_and_stragglers_are_ignored(self):
        clock = FakeClock()
        live = self.start(clock, lanes=[{'lane': 'wlo', 'faculties': ['wlo']}])
        live.event({'event': 'run_done', 'run': 'r1', 'exit': 0})
        ack = live.event({'event': 'tick', 'run': 'r2', 'slot': 'wlo', 'done': 1, 'total': 2})
        self.assertEqual(ack['run'], 'r2')
        self.assertEqual(live.snapshot()['done'], 1)
        # a straggler of the finished run never touches the live one
        self.assertIsNone(live.event({'event': 'tick', 'run': 'r1', 'slot': 'wlo',
                                      'done': 99, 'total': 2}))
        self.assertEqual(live.snapshot()['done'], 1)

    def test_dashboard_bakes_the_state_in_escaped(self):
        page = server.dashboard({'open_runs': [], 'evil': '</script><script>alert(1)</script>'})
        self.assertIn('\\u003c', page)
        self.assertNotIn('</script><script>', page)

    def test_progress_round_trips_through_the_gui(self):
        import urllib.request
        import json
        from types import SimpleNamespace
        tmp = Path(tempfile.mkdtemp())
        test_pool = pool.ProxyPool(tmp / 'pool.json', R2)
        live = server.LiveRun(clock=FakeClock())
        gui = server.GuiServer(('127.0.0.1', 0), server.GuiHandler)
        gui.pool, gui.runs, gui.proxy_port, gui.live = (test_pool, server.RunLog(tmp / 'runs.json'),
                                                        8888, live)
        gui.proxy_server = SimpleNamespace(fallbacks={}, blocks=0, fallbacks_lock=threading.Lock())
        threading.Thread(target=gui.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{gui.server_address[1]}'
        try:
            for event in ({'event': 'run_start', 'run': 'R',
                           'lanes': [{'lane': 'wcy', 'faculties': ['wcy']}]},
                          {'event': 'faculty_start', 'run': 'R', 'slot': 'wcy', 'faculty': 'wcy',
                           'lane': 'wcy', 'total': 8},
                          {'event': 'tick', 'run': 'R', 'slot': 'wcy', 'done': 2, 'total': 8}):
                req = urllib.request.Request(base + '/api/progress',
                                             data=json.dumps(event).encode('utf-8'),
                                             headers={'Content-Type': 'application/json'},
                                             method='POST')
                with urllib.request.urlopen(req, timeout=5) as r:
                    self.assertEqual(r.status, 200)
            with urllib.request.urlopen(base + '/api/progress', timeout=5) as r:
                snap = json.loads(r.read().decode('utf-8'))
            self.assertEqual((snap['run'], snap['done'], snap['total']), ('R', 2, 8))
            with urllib.request.urlopen(base + '/api/status', timeout=5) as r:
                st = json.loads(r.read().decode('utf-8'))
            self.assertEqual(st['progress']['run'], 'R')
            with urllib.request.urlopen(base + '/', timeout=5) as r:
                page = r.read().decode('utf-8')
            self.assertIn('crawl-bar', page)
            self.assertIn('"run": "R"', page)  # the first snapshot is baked in
        finally:
            gui.shutdown()


def start_gui(test_pool, proxy_server=None):
    """A live GUI on a free port for `test_pool`; returns (server, base URL). Caller shuts it down."""
    from types import SimpleNamespace
    gui = server.GuiServer(('127.0.0.1', 0), server.GuiHandler)
    gui.pool, gui.runs, gui.proxy_port = (test_pool, server.RunLog(Path(tempfile.mkdtemp()) / 'runs.json'),
                                          8888)
    gui.proxy_server = proxy_server or SimpleNamespace(fallbacks={}, blocks=0,
                                                       fallbacks_lock=threading.Lock())
    threading.Thread(target=gui.serve_forever, daemon=True).start()
    return gui, f'http://127.0.0.1:{gui.server_address[1]}'


class TokenEnv:
    """Context manager: EGRESS_API_TOKEN set to `value` (None = unset), restored afterwards."""

    def __init__(self, value):
        self.value = value

    def __enter__(self):
        import os
        self.prev = os.environ.get('EGRESS_API_TOKEN')
        if self.value is None:
            os.environ.pop('EGRESS_API_TOKEN', None)
        else:
            os.environ['EGRESS_API_TOKEN'] = self.value

    def __exit__(self, *exc):
        import os
        if self.prev is None:
            os.environ.pop('EGRESS_API_TOKEN', None)
        else:
            os.environ['EGRESS_API_TOKEN'] = self.prev


class VolunteerMode(unittest.TestCase):
    """EGRESS_POOL=off is a mode: every faculty host direct, the pool never used."""

    def setUp(self):
        saved = (server.POOL_OFF, server.DIRECT_FACULTY, server.FAIL_CLOSED_ALL, server.FAIL_CLOSED)
        self.addCleanup(self.restore, saved)

    @staticmethod
    def restore(saved):
        server.POOL_OFF, server.DIRECT_FACULTY, server.FAIL_CLOSED_ALL, server.FAIL_CLOSED = saved

    def test_pool_off_sends_every_faculty_host_direct_even_one_nobody_listed(self):
        server.POOL_OFF, server.DIRECT_FACULTY = True, ()
        for host in list(server.faculty_targets()) + ['nowy.wat.edu.pl']:
            self.assertEqual(server.route(host), 'direct', host)
        self.assertEqual(server.route('evil.example'), 'deny')

    def test_a_disabled_pool_never_hands_out_a_stale_exit(self):
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2, active_hosts=[])
        p.entries = {'http://a:1': {'status': 'ok', 'latency_ms': 10, 'fails': 0,
                                    'hosts': {'example.test': {'ok': True, 'ms': 10}}}}
        self.assertIsNone(p.pick('example.test'))
        self.assertEqual(p.pick_many('example.test'), [])

    def test_volunteer_compose_switches_the_pool_off_and_still_lists_every_host(self):
        import json
        import re
        text = (ROOT / 'tools' / 'volunteer' / 'compose.volunteer.yml').read_text(encoding='utf-8')
        self.assertRegex(text, r'(?m)^\s+EGRESS_POOL:\s*"off"\s*$')
        for key in ('PLANWAT_RELAY_URL', 'PLANWAT_RELAY_TOKEN', 'PLANWAT_RELAY_HOSTS',
                    'EGRESS_DIRECT_HOSTS'):
            self.assertIn(key, text)
        # The list is what egress images older than EGRESS_POOL read: it must stay complete.
        listed = re.search(r'(?m)^\s+EGRESS_DIRECT_FACULTY:\s*"([^"]*)"', text).group(1)
        listed = set(listed.replace(',', ' ').split())
        sources = json.loads((ROOT / 'tools' / 'refresh' / 'sources.json').read_text(encoding='utf-8'))
        source_hosts = set(re.findall(r'https?://([^/"]+)', json.dumps(sources)))
        self.assertLessEqual(set(server.faculty_targets()), listed)
        self.assertLessEqual(source_hosts, listed)

    def test_fail_closed_wins_over_the_direct_list(self):
        server.DIRECT_FACULTY = ('planzajec.wcy.wat.edu.pl', 'wat.edu.pl')
        server.FAIL_CLOSED_ALL, server.FAIL_CLOSED = False, frozenset({'planzajec.wcy.wat.edu.pl'})
        self.assertEqual(server.route('planzajec.wcy.wat.edu.pl'), 'chain')
        self.assertEqual(server.route('wlo.wat.edu.pl'), 'direct')  # listed, not pinned
        server.POOL_OFF = True
        self.assertEqual(server.route('planzajec.wcy.wat.edu.pl'), 'chain')  # refused, never direct

    def test_fail_closed_all_leaves_the_direct_list_alone(self):
        # `all` means every *chained* host; the operator's direct list still goes direct.
        server.DIRECT_FACULTY = ('wtc.wat.edu.pl',)
        server.FAIL_CLOSED_ALL, server.FAIL_CLOSED = True, frozenset()
        self.assertEqual(server.route('wtc.wat.edu.pl'), 'direct')
        self.assertEqual(server.route('wlo.wat.edu.pl'), 'chain')

    def test_refresh_is_refused_when_there_is_no_pool(self):
        import urllib.error
        import urllib.request
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2, active_hosts=[])
        gui, base = start_gui(p)
        try:
            req = urllib.request.Request(base + '/api/refresh', data=b'', method='POST')
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req, timeout=5)
            self.assertEqual(ctx.exception.code, 409)
            self.assertFalse(p.force_refresh)
        finally:
            gui.shutdown()


class HostHygiene(unittest.TestCase):
    """Untrusted job code picks the CONNECT target: one spelling, valid names, no blame on exits."""

    def test_canonical_host(self):
        self.assertEqual(server.canonical_host('FOO.WAT.EDU.PL.'), 'foo.wat.edu.pl')
        for bad in ('a' * 64 + '.wat.edu.pl', ('a' * 60 + '.') * 5 + 'wat.edu.pl', 'a..wat.edu.pl',
                    '-a.wat.edu.pl', 'a_b.wat.edu.pl', '[::1]', '::1', ''):
            self.assertEqual(server.canonical_host(bad), '', bad)

    def test_connect_targets_are_canonical_and_long_names_refused(self):
        self.assertEqual(server.split_target('WLO.WAT.EDU.PL.:443'), ('wlo.wat.edu.pl', 443))
        self.assertIsNone(server.split_target('x' * 300 + '.wat.edu.pl:443'))
        self.assertEqual(server.route('x' * 300 + '.wat.edu.pl'), 'deny')

    def test_invented_hosts_neither_trip_the_breaker_nor_grow_the_pool(self):
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2)
        p.entries = {'http://a:1': {'status': 'ok', 'latency_ms': 10, 'fails': 0,
                                    'hosts': {'example.test': {'ok': True, 'ms': 10}}}}
        p.heal_event.clear()
        for i in range(pool.BREAKER_N * 3):
            p.mark('http://a:1', f'nope{i}.wat.edu.pl', False, live=True)
        self.assertFalse(p.stats()['tripped'])
        self.assertEqual(list(p.entries['http://a:1']['hosts']), ['example.test'])
        self.assertEqual((p._host_fails, p._host_open), ({}, {}))
        self.assertFalse(p.heal_event.is_set())
        self.assertEqual(p.pick('example.test'), 'http://a:1')

    def test_a_name_that_fails_locally_is_not_blamed_on_the_exit(self):
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2_WLO)
        p.entries = {'http://a:1': {'status': 'ok', 'latency_ms': 10, 'fails': 0,
                                    'hosts': {'wlo.wat.edu.pl': {'ok': True, 'ms': 10}}}}
        orig = server.chain_connect
        server.chain_connect = lambda *a, **k: (_ for _ in ()).throw(server.BadTarget('bad hostname'))
        try:
            from types import SimpleNamespace
            handler = server.ProxyHandler.__new__(server.ProxyHandler)
            handler.server = SimpleNamespace(pool=p, fallbacks={}, fallbacks_lock=threading.Lock(),
                                             remember_tunnel=lambda h, v: None)
            with self.assertRaises(OSError) as ctx:
                handler._open('wlo.wat.edu.pl', 443)
            self.assertEqual(str(ctx.exception), 'deny')
            self.assertTrue(p.entries['http://a:1']['hosts']['wlo.wat.edu.pl']['ok'])
            self.assertEqual(p.entries['http://a:1']['fails'], 0)
        finally:
            server.chain_connect = orig

    def test_a_block_report_matches_the_tunnel_whatever_the_spelling(self):
        from types import SimpleNamespace
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2_WLO)
        p.entries = {'http://a:1': {'status': 'ok', 'latency_ms': 10, 'fails': 0,
                                    'hosts': {'wlo.wat.edu.pl': {'ok': True, 'ms': 10}}}}
        stub = SimpleNamespace(pool=p, recent_lock=threading.Lock(),
                               recent=deque([('wlo.wat.edu.pl', 'http://a:1', time.monotonic())]))
        self.assertEqual(server.ProxyServer.demote_recent(stub, 'WLO.wat.edu.pl.'), 'http://a:1')


class PoolHealing(unittest.TestCase):
    def test_thin_coverage_does_not_chain_refreshes_back_to_back(self):
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2)
        p.entries = {f'http://n{i}:1': {'status': 'ok', 'hosts': {}} for i in range(40)}
        p.last_refresh = time.time() - 30
        self.assertFalse(p.needs_refresh())  # thin (0 verified), but refreshed seconds ago
        p.last_refresh = time.time() - pool.HEAL_MIN_GAP_S - 1
        self.assertTrue(p.needs_refresh())

    def test_heal_kick_only_for_hosts_the_pool_maintains(self):
        two = dict(R2, **{'other.test': ('https://other.test/index.xml', None)})
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', two, active_hosts=['example.test'])
        p.heal_event.clear()
        p.mark('http://a:1', 'other.test', False, live=True)
        self.assertFalse(p.heal_event.is_set())
        p.mark('http://a:1', 'example.test', False, live=True)
        self.assertTrue(p.heal_event.is_set())

    def test_a_cooldown_survives_a_reboot_on_the_wall_clock(self):
        import json
        path = Path(tempfile.mkdtemp()) / 'pool.json'
        ahead = time.monotonic() + 10 ** 6  # stamped by a previous boot with a longer uptime
        path.write_text(json.dumps({'version': pool.POOL_VERSION, 'entries': {
            'http://a:1': {'status': 'ok', 'latency_ms': 10, 'fails': 0, 'last_checked_mono': ahead,
                           'hosts': {'example.test': {'ok': False, 'checked': time.time() - 3600,
                                                      'checked_mono': ahead}}}}}), encoding='utf-8')
        p = pool.ProxyPool(path, R2)
        self.assertNotIn('checked_mono', p.entries['http://a:1']['hosts']['example.test'])
        self.assertEqual(p.pick('example.test'), 'http://a:1')  # the 10-minute cooldown is over


class GuiAuth(unittest.TestCase):
    """With a token set, reads are behind it too; health probes keep a bare 200."""

    def test_padded_token_in_the_environment_still_matches_the_crawler(self):
        with TokenEnv('  sekret \n'):
            h = server.GuiHandler.__new__(server.GuiHandler)
            h.headers = refresh.egress_headers()
            self.assertTrue(h._check_token())

    def test_status_is_liveness_only_without_the_token(self):
        import json
        import urllib.error
        import urllib.request
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2)
        p.entries = {'http://8.8.8.8:8080': {'status': 'ok', 'hosts': {}}}
        with TokenEnv('sekret'):
            gui, base = start_gui(p)
            try:
                with urllib.request.urlopen(base + '/api/status', timeout=5) as r:
                    self.assertEqual(json.loads(r.read().decode('utf-8')),
                                     {'ok': True, 'auth': 'required'})
                with self.assertRaises(urllib.error.HTTPError) as ctx:
                    urllib.request.urlopen(base + '/api/progress', timeout=5)
                self.assertEqual(ctx.exception.code, 401)
                with urllib.request.urlopen(base + '/', timeout=5) as r:
                    page = r.read().decode('utf-8')
                self.assertIn('action="/login"', page)
                self.assertNotIn('8.8.8.8', page)
                req = urllib.request.Request(base + '/api/status', headers={'X-Token': 'sekret'})
                with urllib.request.urlopen(req, timeout=5) as r:
                    self.assertIn('pool', json.loads(r.read().decode('utf-8')))
            finally:
                gui.shutdown()

    def test_browser_login_sets_a_cookie_that_opens_reads_but_not_the_api(self):
        import http.client
        import json
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2)
        with TokenEnv('sekret'):
            gui, _ = start_gui(p)
            host, port = gui.server_address
            try:
                def call(method, path, body=None, headers=None):
                    conn = http.client.HTTPConnection(host, port, timeout=5)
                    conn.request(method, path, body=body, headers=headers or {})
                    resp = conn.getresponse()
                    data = resp.read()
                    conn.close()
                    return resp, data
                form = {'Content-Type': 'application/x-www-form-urlencoded'}
                resp, _ = call('POST', '/login', 'token=zle', form)
                self.assertEqual(resp.status, 401)
                resp, _ = call('POST', '/login', 'token=sekret', form)
                self.assertEqual((resp.status, resp.getheader('Location')), (303, '/'))
                cookie = resp.getheader('Set-Cookie')
                self.assertIn('HttpOnly', cookie)
                self.assertIn('SameSite=Strict', cookie)
                self.assertNotIn('sekret', cookie)  # derived, never the API secret itself
                jar = {'Cookie': cookie.split(';', 1)[0]}
                resp, data = call('GET', '/api/status', headers=jar)
                self.assertIn('pool', json.loads(data.decode('utf-8')))
                resp, data = call('GET', '/', headers=jar)
                self.assertIn(b'mode-pill', data)
                resp, _ = call('POST', '/api/run', '{"exit": 0}',
                               dict(jar, **{'Content-Type': 'application/json'}))
                self.assertEqual(resp.status, 401)  # the POST API takes the token, not a cookie
            finally:
                gui.shutdown()

    def test_no_token_keeps_the_lan_behaviour(self):
        import json
        import urllib.request
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2)
        with TokenEnv(None):
            gui, base = start_gui(p)
            try:
                with urllib.request.urlopen(base + '/api/status', timeout=5) as r:
                    self.assertIn('pool', json.loads(r.read().decode('utf-8')))
            finally:
                gui.shutdown()


class StatusHonesty(unittest.TestCase):
    """A fail-closed host with no exit is refused (403), so the GUI must not call it DIRECT."""

    def test_a_fail_closed_host_without_exits_reads_fail_closed(self):
        import json
        import urllib.request
        wcy = 'planzajec.wcy.wat.edu.pl'
        targets = {wcy: ('https://planzajec.wcy.wat.edu.pl/pl/rozklad', b'grupa_id=wcy'),
                   'wtc.wat.edu.pl': ('https://wtc.wat.edu.pl/Plany/index.xml', b'<?xml')}
        saved = (server.DIRECT_FACULTY, server.FAIL_CLOSED_ALL, server.FAIL_CLOSED)
        server.DIRECT_FACULTY = ('wtc.wat.edu.pl',)
        server.FAIL_CLOSED_ALL, server.FAIL_CLOSED = False, frozenset({wcy})
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', targets, active_hosts=[wcy])
        gui, base = start_gui(p)
        try:
            with TokenEnv(None), urllib.request.urlopen(base + '/api/status', timeout=5) as r:
                st = json.loads(r.read().decode('utf-8'))
            self.assertEqual(st['mode'], 'FAIL-CLOSED (pula pusta)')
            self.assertEqual(st['hosts'][wcy]['mode'], 'FAIL-CLOSED')
            self.assertEqual(st['hosts']['wtc.wat.edu.pl']['mode'], 'DIRECT (lista)')
        finally:
            gui.shutdown()
            server.DIRECT_FACULTY, server.FAIL_CLOSED_ALL, server.FAIL_CLOSED = saved


if __name__ == '__main__':
    unittest.main()


R2_HUNT = {'wml.wat.edu.pl': ('https://wml.wat.edu.pl/rozklady-zajec/', b'index.xml'),
           'wtc.wat.edu.pl': ('https://wtc.wat.edu.pl/Plany/index.xml', b'<?xml'),
           'wlo.wat.edu.pl': ('https://wlo.wat.edu.pl/planyzajec/zima/index.xml', b'<?xml')}


class PoolHunt(unittest.TestCase):
    """pool.hunt / adopt: exits for a faculty nobody's own line gets through (docs/EGRESS.md)."""

    def make(self, alive, works, hunt=True):
        """A pool of `alive` {url: latency}, where works(url, host) says who gets through."""
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2_HUNT, active_hosts=[], hunt=hunt)
        now = time.time()
        p.entries = {u: {'status': 'ok', 'latency_ms': ms, 'fails': 0, 'last_checked': now, 'hosts': {}}
                     for u, ms in alive.items()}
        self.probes = []
        lock = threading.Lock()

        def probe_host(url, host):
            with lock:
                self.probes.append((url, host))
            return 50 if works(url, host) else None
        p.probe_host = probe_host
        p._discover = lambda *a, **k: ('ok', [], [])  # no list fetching offline
        return p

    def alive(self, n, slow=()):
        return {f'http://8.8.{i}.1:8080': (9000 if i in slow else 100 + i) for i in range(n)}

    def test_every_candidate_with_a_sensible_ping_is_tried_until_one_gets_through(self):
        p = self.make(self.alive(50, slow={3}), lambda u, h: u == 'http://8.8.40.1:8080' and h == 'wml.wat.edu.pl')
        out = p.hunt(['wml.wat.edu.pl'], want=1, workers=1)
        self.assertEqual(out['wml.wat.edu.pl']['exits'], ['http://8.8.40.1:8080'])
        tried = [u for u, _ in self.probes]
        self.assertNotIn('http://8.8.3.1:8080', tried)  # 9 s ping: not sensible
        self.assertEqual(tried[:3], ['http://8.8.0.1:8080', 'http://8.8.1.1:8080', 'http://8.8.2.1:8080'])
        self.assertEqual(tried[-1], 'http://8.8.40.1:8080')  # stopped once it had what it wanted
        self.assertEqual(p.verified('wml.wat.edu.pl')[0]['url'], 'http://8.8.40.1:8080')
        self.assertEqual(p.pick_many('wml.wat.edu.pl', 3, verified_only=True), ['http://8.8.40.1:8080'])

    def test_a_proxy_that_passes_one_wall_is_tried_on_the_others(self):
        good = 'http://8.8.7.1:8080'
        p = self.make(self.alive(10), lambda u, h: u == good and h in ('wml.wat.edu.pl', 'wlo.wat.edu.pl'))
        out = p.hunt(['wml.wat.edu.pl', 'wtc.wat.edu.pl', 'wlo.wat.edu.pl'], want=1, workers=1)
        self.assertEqual({h: r['exits'] for h, r in out.items()},
                         {'wml.wat.edu.pl': [good], 'wtc.wat.edu.pl': [], 'wlo.wat.edu.pl': [good]})
        self.assertIn((good, 'wtc.wat.edu.pl'), self.probes)
        self.assertEqual(out['wtc.wat.edu.pl']['tried'], 10)  # every candidate, nothing found

    def test_budget_and_the_cache_spare_the_faculty(self):
        clock = FakeClock()
        p = self.make(self.alive(30), lambda u, h: False)

        def slow(url, host):
            clock.t += 20
            return None
        p.probe_host = slow
        out = p.hunt(['wtc.wat.edu.pl'], workers=1, budget_s=100, clock=clock)
        self.assertLessEqual(out['wtc.wat.edu.pl']['tried'], 6)
        # asked again within half an hour: nobody new is probed
        p.probe_host = lambda u, h: self.fail('probed again')
        again = p.hunt(['wtc.wat.edu.pl'], workers=1)
        self.assertEqual(again['wtc.wat.edu.pl']['verified'], 0)

    def test_a_fresh_pool_keeps_discovering_until_enough_fast_candidates(self):
        p = self.make({}, lambda u, h: False)
        calls = []

        def discover(fetcher, workers, start, cap=None):
            calls.append(cap)
            n = len(p.entries)
            for i in range(n, n + (20 if len(calls) < 3 else 0)):
                p.entries[f'http://8.8.{i}.2:8080'] = {'status': 'ok', 'latency_ms': 100, 'fails': 0,
                                                       'last_checked': time.time(), 'hosts': {}}
            return 'ok', [], []
        p._discover = discover
        out = p.hunt(['wtc.wat.edu.pl'], workers=2)
        self.assertEqual(calls, [pool.HUNT_PROBE, pool.HUNT_PROBE])  # 40 fast ones known: enough
        self.assertEqual(out['wtc.wat.edu.pl']['tried'], 40)
        p.hunts.clear()
        p.entries = {}
        calls.clear()
        p._discover = lambda *a, **k: (calls.append(1), ('ok', [], []))[1]
        p.hunt(['wtc.wat.edu.pl'])
        self.assertEqual(len(calls), 1)  # the lists had nobody new: no point asking again

    def test_an_exit_just_verified_is_handed_out_without_a_probe(self):
        p = self.make(self.alive(5), lambda u, h: False)
        p.mark('http://8.8.2.1:8080', 'wml.wat.edu.pl', True, 40)  # the scout's find, a minute ago
        self.probes.clear()
        out = p.hunt(['wml.wat.edu.pl'], want=1)
        self.assertEqual(self.probes, [])
        self.assertEqual(out['wml.wat.edu.pl']['exits'], ['http://8.8.2.1:8080'])

    def test_a_scouted_pool_that_every_wall_refused_still_discovers(self):
        p = self.make(self.alive(50), lambda u, h: False)
        for u in list(p.entries):
            p.mark(u, 'wtc.wat.edu.pl', False)  # the scout tried them all there a minute ago
        calls = []
        p._discover = lambda *a, **k: (calls.append(1), ('ok', [], []))[1]
        p.hunt(['wtc.wat.edu.pl'])
        self.assertEqual(len(calls), 1)  # 50 alive, none untried: look for new ones

    def test_known_exits_are_rechecked_first(self):
        p = self.make(self.alive(5), lambda u, h: u == 'http://8.8.2.1:8080')
        p.mark('http://8.8.2.1:8080', 'wml.wat.edu.pl', True, 40)
        p.entries['http://8.8.2.1:8080']['hosts']['wml.wat.edu.pl']['checked'] -= pool.HUNT_TRUST_S + 60
        self.probes.clear()
        out = p.hunt(['wml.wat.edu.pl'], want=1)
        self.assertEqual(self.probes, [('http://8.8.2.1:8080', 'wml.wat.edu.pl')])
        self.assertEqual(out['wml.wat.edu.pl']['exits'], ['http://8.8.2.1:8080'])

    def test_hunt_async_reports_running_then_done(self):
        p = self.make(self.alive(3), lambda u, h: True)
        gate = threading.Event()
        real = p.probe_host

        def held(url, host):
            gate.wait(5)
            return real(url, host)
        p.probe_host = held
        state = p.hunt_async(['wml.wat.edu.pl'], want=1, workers=1)
        self.assertEqual(state['wml.wat.edu.pl']['state'], 'running')
        gate.set()
        for _ in range(100):
            if p.hunt_status()['wml.wat.edu.pl']['state'] == 'done':
                break
            time.sleep(0.02)
        self.assertEqual(p.hunt_status()['wml.wat.edu.pl']['verified'], 1)

    def test_a_host_asked_for_during_a_hunt_waits_queued_then_runs(self):
        p = self.make(self.alive(3), lambda u, h: False)
        gate = threading.Event()
        real = p.probe_host
        p.probe_host = lambda u, h: (gate.wait(5), real(u, h))[1]
        p.hunt_async(['wtc.wat.edu.pl'], workers=1)
        self.assertEqual(p.hunt_async(['wml.wat.edu.pl'])['wml.wat.edu.pl']['state'], 'queued')
        gate.set()
        for _ in range(200):
            if p.hunt_status()['wml.wat.edu.pl']['state'] == 'done':
                break
            time.sleep(0.02)
        self.assertEqual({h: v['state'] for h, v in p.hunt_status().items()},
                         {'wtc.wat.edu.pl': 'done', 'wml.wat.edu.pl': 'done'})

    def test_adopt_checks_every_shared_exit_itself(self):
        p = self.make({}, lambda u, h: u == 'http://8.8.8.8:3128')
        got = p.adopt('wml.wat.edu.pl', ['8.8.8.8:3128', 'http://9.9.9.9:80', '127.0.0.1:80', 'junk', 42])
        self.assertEqual(got, ['http://8.8.8.8:3128'])
        self.assertEqual(sorted(u for u, _ in self.probes), ['http://8.8.8.8:3128', 'http://9.9.9.9:80'])
        self.assertEqual(p.adopt('example.org', ['8.8.8.8:3128']), [])
        self.assertEqual(p.pick_many('wml.wat.edu.pl', 3, verified_only=True), ['http://8.8.8.8:3128'])

    def test_verified_only_picks_need_the_hunt(self):
        p = self.make({'http://8.8.8.8:3128': 100}, lambda u, h: True, hunt=False)
        p.mark('http://8.8.8.8:3128', 'wml.wat.edu.pl', True, 40)
        self.assertEqual(p.pick_many('wml.wat.edu.pl', 3, verified_only=True), [])  # no pooled host, no hunt
        p.hunt_on = True
        self.assertEqual(p.pick_many('wml.wat.edu.pl', 3, verified_only=True), ['http://8.8.8.8:3128'])
        p.entries['http://9.9.9.9:80'] = {'status': 'ok', 'latency_ms': 10, 'fails': 0, 'hosts': {}}
        # merely alive is not offered on the hunt port
        self.assertEqual(p.pick_many('wml.wat.edu.pl', 3, verified_only=True), ['http://8.8.8.8:3128'])


R2_ALL = dict(R2_HUNT, **{'ioe.wat.edu.pl': ('https://ioe.wat.edu.pl/plany/lato/index.xml', b'<?xml')})


class ProbeTargets(unittest.TestCase):
    """The egress probes the page the crawler lists: the walls cover the plan directories only (13.11.2026)."""

    def test_probe_targets_are_the_pages_the_crawler_lists(self):
        import datetime
        import json
        from drivers import plansoft, wml
        src = json.loads((ROOT / 'tools' / 'refresh' / 'sources.json').read_text(encoding='utf-8'))
        with unittest.mock.patch.dict(os.environ, {'EGRESS_SEASON': ''}):
            for day in (datetime.date(2026, 11, 13), datetime.date(2027, 1, 20), datetime.date(2027, 4, 1)):
                t = {h: url for h, (url, _) in server.faculty_targets(today=day).items()}
                season, year = core.season_of(day)
                for f, host in (('wlo', 'wlo.wat.edu.pl'), ('wel', 'wel.wat.edu.pl'), ('wtc', 'wtc.wat.edu.pl'),
                                ('ioe', 'ioe.wat.edu.pl')):
                    # either export the crawler reads (WLO's index.xml is gone, its index.html is the listing)
                    self.assertIn(t[host], plansoft.listing_candidates(src[f]['base'].format(season=season)
                                                                       + 'index.xml'), (day, f))
                self.assertEqual(t['planzajec.wcy.wat.edu.pl'], src['wcy']['index'])
                m = wml.DIR_RE.search(t['wml.wat.edu.pl'])
                self.assertEqual((int(m.group(1)), m.group(2)), (year, season), day)
                self.assertTrue(t['wml.wat.edu.pl'].startswith(src['wml']['landing']))

    def test_verdicts_on_a_page_no_longer_probed_are_dropped(self):
        import json
        path = Path(tempfile.mkdtemp()) / 'pool.json'
        old = {'wml.wat.edu.pl': ('https://wml.wat.edu.pl/rozklady-zajec/', b'index.xml'),
               'wtc.wat.edu.pl': ('https://wtc.wat.edu.pl/Plany/index.xml', b'<?xml')}
        p = pool.ProxyPool(path, old)
        p.mark('http://8.8.8.8:80', 'wml.wat.edu.pl', False)
        p.mark('http://8.8.8.8:80', 'wtc.wat.edu.pl', True, 50)
        p.save()
        new = dict(old, **{'wml.wat.edu.pl': ('https://wml.wat.edu.pl/wp-content/uploads/rozklady_zajec/'
                                              '2026_sem_zima/index.xml', b'<?xml')})
        again = pool.ProxyPool(path, new)
        self.assertEqual(set(again.entries['http://8.8.8.8:80']['hosts']), {'wtc.wat.edu.pl'})
        # a file from before the pages were recorded: the old WLO and WML pages were wrong, the rest stand
        legacy = json.loads(path.read_text(encoding='utf-8'))
        legacy.pop('targets')
        for h in ('wml.wat.edu.pl', 'wtc.wat.edu.pl'):
            legacy['entries']['http://8.8.8.8:80']['hosts'][h] = {'ok': False, 'checked': time.time()}
        path.write_text(json.dumps(legacy), encoding='utf-8')
        self.assertEqual(set(pool.ProxyPool(path, new).entries['http://8.8.8.8:80']['hosts']), {'wtc.wat.edu.pl'})
        again.mark('http://8.8.8.8:80', 'wml.wat.edu.pl', True, 50)
        moved = again.retarget(dict(new, **{'wml.wat.edu.pl': ('https://wml.wat.edu.pl/x/index.xml', b'<?xml')}))
        self.assertEqual(moved, {'wml.wat.edu.pl'})
        self.assertEqual(set(again.entries['http://8.8.8.8:80']['hosts']), {'wtc.wat.edu.pl'})


class PoolScout(unittest.TestCase):
    """The scout and the candidate pipeline (pool.scout_once, docs/EGRESS.md "Zwiad")."""

    def make(self, entries=None, works=lambda u, h: False, listed='', alive=lambda u: 100):
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2_ALL, active_hosts=[], hunt=True)
        p.host_gap = 0
        p.entries = entries or {}
        self.probes = []
        lock = threading.Lock()

        def probe_host(url, host):
            with lock:
                self.probes.append((url, host))
            return 50 if works(url, host) else None
        p.probe_host = probe_host
        p.probe_alive = alive
        p._tcp_screen = lambda urls, **k: {u: 5 for u in urls}
        self.fetcher = lambda url: listed if 'monosans' in url and 'http.txt' in url else ''
        return p

    @staticmethod
    def entry(ms, age=0, **hosts):
        return {'status': 'ok', 'latency_ms': ms, 'fails': 0, 'last_checked': time.time() - age,
                'hosts': {h.replace('_', '.') + '.wat.edu.pl': v for h, v in hosts.items()}}

    def test_tor_ports_are_pinned_in_the_pool(self):
        self.assertEqual(pool.parse_pinned('socks5h://tor:9050'), 'socks5://tor:9050')
        self.assertEqual(pool.parse_pinned(' socks5://127.0.0.1:9051 '), 'socks5://127.0.0.1:9051')
        for bad in ('tor:9050', 'socks4://tor:9050', 'socks5://u:p@tor:9050', 'socks5://tor', ''):
            self.assertIsNone(pool.parse_pinned(bad), bad)
        self.assertIsNone(pool.parse_proxy_url('socks5://tor:9050'))  # never from a list, nor shared by a runner
        tor = ['socks5://tor:9050', 'socks5://tor:9051']
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2_ALL, active_hosts=[], pinned=tor + ['junk'])
        self.assertEqual(p.pinned, tor)
        self.assertEqual({p.entries[u]['source'] for u in tor}, {'tor'})
        self.assertEqual({p.entries[u]['cc'] for u in tor}, {'PL'})
        p.host_gap = 0
        p.probe_alive = lambda u: None  # Tor still bootstrapping: Round 1 fails...
        p.probe_host = lambda u, h: None
        p._tcp_screen = lambda urls, **k: {}
        p.scout_once(fetcher=lambda url: '', batch=0)
        self.assertEqual(sorted(p.entries), tor)  # ...and they stay, not into the dead map
        self.assertEqual(p.dead, {})
        p.entries['http://8.8.8.8:80'] = {'status': 'fail', 'last_checked': 0, 'fails': 0, 'hosts': {}}
        with unittest.mock.patch.object(pool, 'MAX_ENTRIES', 1):
            p._make_room(0)
        self.assertEqual(sorted(p.entries), tor)  # evicted last of all
        p.save()
        again = pool.ProxyPool(p.path, R2_ALL, active_hosts=[], pinned=tor[:1])
        self.assertTrue(again.entries[tor[0]]['pinned'])
        self.assertNotIn('pinned', again.entries[tor[1]])  # not configured any more: an ordinary entry

    def test_tor_ports_are_rechecked_every_cycle_and_retried_on_a_faculty_soon(self):
        tor = 'socks5://tor:9050'
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2_ALL, active_hosts=[], pinned=[tor])
        p.host_gap = 0
        alive = []
        p.probe_alive = lambda u: alive.append(u) or 1500
        through = {'wml.wat.edu.pl'}
        probes = []
        p.probe_host = lambda u, h: probes.append(h) or (900 if h in through else None)
        p._tcp_screen = lambda urls, **k: {}
        p.scout_once(fetcher=lambda url: '', batch=0)
        self.assertEqual(alive, [tor])
        self.assertEqual(sorted(probes), sorted(R2_ALL))  # 1500 ms is fine for a Polish exit
        self.assertEqual([r['url'] for r in p.exits('wml.wat.edu.pl')], [tor])
        p.scout_once(fetcher=lambda url: '', batch=0)
        self.assertEqual(alive, [tor, tor])  # fresh, but re-checked anyway: it is cheap and its circuit changes
        probes.clear()
        for hv in p.entries[tor]['hosts'].values():
            hv['checked'] -= pool.VERIFY_TTL_S + 1
        through.add('wlo.wat.edu.pl')
        p.scout_once(fetcher=lambda url: '', batch=0)
        self.assertIn('wlo.wat.edu.pl', probes)  # a refusal rests VERIFY_TTL_S, not HOST_RETRY_S
        self.assertEqual([r['url'] for r in p.exits('wlo.wat.edu.pl')], [tor])

    def test_a_failed_faculty_probe_does_not_make_a_proxy_look_alive(self):
        p = self.make({'http://8.8.8.8:80': self.entry(100, age=5 * 3600)})
        before = p.entries['http://8.8.8.8:80']['last_checked']
        p.mark('http://8.8.8.8:80', 'wtc.wat.edu.pl', False)
        self.assertEqual(p.entries['http://8.8.8.8:80']['last_checked'], before)
        p.mark('http://8.8.8.8:80', 'wml.wat.edu.pl', True, 300)  # getting through proves it alive
        self.assertGreater(p.entries['http://8.8.8.8:80']['last_checked'], before)

    def test_a_full_pool_still_lets_newcomers_in_and_keeps_its_exits(self):
        with unittest.mock.patch.object(pool, 'MAX_ENTRIES', 4):
            p = self.make({'http://1.1.1.1:80': self.entry(100, wml={'ok': True, 'ms': 300}),
                           'http://1.1.1.2:80': self.entry(100, age=3 * 3600),  # stale verdict: goes first
                           'http://1.1.1.3:80': self.entry(2000),
                           'http://1.1.1.4:80': self.entry(50)},
                          listed='8.8.8.8:80\n9.9.9.9:80\n')
            got = p._discover(self.fetcher, 2, time.monotonic(), cap=10)
        self.assertEqual(sorted(got[2]), ['http://8.8.8.8:80', 'http://9.9.9.9:80'])
        self.assertEqual(sorted(p.entries), ['http://1.1.1.1:80', 'http://1.1.1.4:80',
                                             'http://8.8.8.8:80', 'http://9.9.9.9:80'])

    def test_candidates_come_from_the_whole_list_and_the_dead_wait(self):
        listed = '\n'.join(f'8.8.{i // 250}.{i % 250 + 1}:80' for i in range(500))
        p = self.make(listed=listed, alive=lambda u: None)
        p._discover(self.fetcher, 4, time.monotonic(), cap=500)
        self.assertEqual((len(p.entries), len(p.dead)), (0, 500))  # every one tried, none past the head cut
        self.assertEqual(p._unseen(p._lists(self.fetcher), 10), [])  # dead ones are not looked at again...
        p.dead = {u: t - pool.DEAD_RETRY_S - 1 for u, t in p.dead.items()}
        self.assertEqual(len(p._unseen(p._lists(self.fetcher), 10)), 10)  # ...until DEAD_RETRY_S has passed
        p.save_dead()
        self.assertEqual(len(pool.ProxyPool(p.path, R2_ALL).dead), 0)  # expired ones are not kept on disk

    def test_polish_candidates_come_first(self):
        import json
        doc = json.dumps([{'proxy': 'http://8.8.8.8:80', 'geolocation': {'country': 'DE'}},
                          {'proxy': 'socks5://9.9.9.9:1080', 'geolocation': {'country': 'pl'}}])
        meta = {}
        self.assertEqual(pool.normalize_list(doc, 'proxifly', '', meta),
                         ['http://8.8.8.8:80', 'socks5://9.9.9.9:1080'])
        self.assertEqual(meta, {'http://8.8.8.8:80': 'DE', 'socks5://9.9.9.9:1080': 'PL'})
        p = self.make()
        lists = {f'http://8.8.8.{i}:80': ('x', None, None) for i in range(1, 30)}
        lists['http://9.9.9.9:80'] = ('proxifly-pl', 'PL', None)
        lists['http://7.7.7.7:80'] = ('geonode-pl', 'PL', True)        # a Polish home line: first of all
        lists['http://6.6.6.6:80'] = ('proxyscrape', 'NL', True)       # a home line elsewhere: before the rest
        self.assertEqual(p._unseen(lists, 3), ['http://7.7.7.7:80', 'http://9.9.9.9:80', 'http://6.6.6.6:80'])

    def test_lists_that_yield_more_live_proxies_are_drawn_from_more(self):
        p = self.make()
        p.sources = {'good': [1000, 150], 'bad': [10000, 100]}  # 15% alive vs 1%
        lists = {f'http://8.8.{i // 250}.{i % 250 + 1}:80': ('good' if i < 500 else 'bad', None, None)
                 for i in range(5500)}
        picked = p._unseen(lists, 500)
        good = sum(1 for u in picked if lists[u][0] == 'good')
        self.assertGreater(good, 150)  # an even draw would give about 45
        p.save_dead()
        self.assertEqual(pool.ProxyPool(p.path, R2_ALL).sources, p.sources)

    def test_lists_that_say_where_a_proxy_lives(self):
        import json
        scrape = json.dumps({'proxies': [
            {'proxy': 'socks5://145.220.227.132:1080', 'ip_data': {'countryCode': 'NL', 'hosting': False}},
            {'proxy': 'http://51.38.129.42:3169', 'ip_data': {'countryCode': 'PL', 'hosting': True}},
            {'proxy': 'junk'}]})
        meta, res = {}, {}
        self.assertEqual(pool.normalize_list(scrape, 'proxyscrape', '', meta, res),
                         ['socks5://145.220.227.132:1080', 'http://51.38.129.42:3169'])
        self.assertEqual((meta, res), ({'socks5://145.220.227.132:1080': 'NL', 'http://51.38.129.42:3169': 'PL'},
                                       {'socks5://145.220.227.132:1080': True, 'http://51.38.129.42:3169': False}))
        geo = json.dumps({'data': [
            {'ip': '83.14.246.42', 'port': '1080', 'protocols': ['socks5'], 'country': 'PL',
             'isp': 'Orange Polska Spolka Akcyjna'},
            {'ip': '57.128.231.218', 'port': '1203', 'protocols': ['https', 'socks4'], 'country': 'PL', 'isp': 'OVH SAS'}]})
        meta, res = {}, {}
        self.assertEqual(pool.normalize_list(geo, 'geonode', '', meta, res),
                         ['socks5://83.14.246.42:1080', 'http://57.128.231.218:1203', 'socks4://57.128.231.218:1203'])
        self.assertEqual(res, {'socks5://83.14.246.42:1080': True, 'http://57.128.231.218:1203': False,
                               'socks4://57.128.231.218:1203': False})
        spys = 'Proxy list (#400)\nIP address:Port CountryCode-Anonymity\n\n185.32.4.210:8070 PL-N-S +\n1.0.0.1:x DE-H\n'
        meta = {}
        self.assertEqual(pool.normalize_list(spys, 'spys', 'http', meta), ['http://185.32.4.210:8070'])
        self.assertEqual(meta, {'http://185.32.4.210:8070': 'PL'})
        self.assertEqual([pool.priority(*a) for a in (('PL', True), ('PL', None), ('NL', True), ('NL', False))],
                         [0, 1, 2, 3])

    def test_a_home_line_may_be_slower_and_still_be_tried(self):
        p = self.make({'http://1.1.1.1:80': dict(self.entry(4000), res=True),
                       'http://1.1.1.2:80': self.entry(4000)})
        jobs, _ = p._faculty_jobs(['wtc.wat.edu.pl'], 12, pool.HUNT_MAX_MS, 10)
        self.assertEqual(jobs, [('http://1.1.1.1:80', 'wtc.wat.edu.pl')])

    def test_tcp_screen_keeps_only_ports_that_answer(self):
        import socket as _s
        srv = _s.socket()
        srv.bind(('127.0.0.1', 0))
        srv.listen(8)
        closed = _s.socket()
        closed.bind(('127.0.0.1', 0))
        dead_port = closed.getsockname()[1]
        closed.close()
        try:
            p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2_ALL)
            up = f'http://127.0.0.1:{srv.getsockname()[1]}'
            got = p._tcp_screen([up, f'http://127.0.0.1:{dead_port}'], timeout=2, concurrency=1)
            self.assertEqual(list(got), [up])
        finally:
            srv.close()

    def test_scout_tests_every_new_proxy_on_every_faculty(self):
        good = 'http://8.8.8.8:80'
        p = self.make(works=lambda u, h: u == good and h == 'wml.wat.edu.pl',
                      listed='8.8.8.8:80\n9.9.9.9:80\n', alive=lambda u: 100 if u == good else 5000)
        st = p.scout_once(fetcher=self.fetcher, tcp_workers=4, r1_workers=2)
        self.assertEqual(sorted(self.probes), sorted((good, h) for h in R2_ALL))  # 5 s ping: not tested
        self.assertEqual((st['alive_new'], st['tests'], st['passed']), (2, 4, 1))
        self.assertEqual([r['url'] for r in p.exits('wml.wat.edu.pl')], [good])
        self.assertEqual(st['exits']['wml.wat.edu.pl'], 1)
        # next cycle: a faculty that refused it is not asked again soon
        self.probes.clear()
        p.scout_once(fetcher=self.fetcher)
        self.assertEqual(self.probes, [])

    def test_a_faculty_with_enough_exits_only_tries_faster_proxies(self):
        ents = {f'http://1.1.1.{i}:80': self.entry(100 + i, ioe={'ok': True, 'ms': 300, 'checked': time.time()})
                for i in range(1, 4)}
        ents['http://8.8.8.8:80'] = self.entry(50)    # faster than the kept ones
        ents['http://9.9.9.9:80'] = self.entry(900)   # slower
        p = self.make(ents)
        jobs, _ = p._faculty_jobs(['ioe.wat.edu.pl'], 3, pool.HUNT_MAX_MS, 100)
        self.assertEqual(jobs, [('http://8.8.8.8:80', 'ioe.wat.edu.pl')])
        jobs, _ = p._faculty_jobs(['ioe.wat.edu.pl'], 12, pool.HUNT_MAX_MS, 100)  # short of keep: everyone
        self.assertEqual({u for u, _ in jobs}, {'http://8.8.8.8:80', 'http://9.9.9.9:80'})

    def test_an_exit_that_failed_once_is_tried_again_soon_a_stranger_is_not(self):
        then = time.time() - pool.VERIFY_TTL_S - 60
        p = self.make({'http://1.1.1.1:80': self.entry(100, wtc={'ok': False, 'n_ok': 7, 'n_fail': 1, 'checked': then}),
                       'http://1.1.1.2:80': self.entry(100, wtc={'ok': False, 'n_fail': 1, 'checked': then})})
        jobs, _ = p._faculty_jobs(['wtc.wat.edu.pl'], 12, pool.HUNT_MAX_MS, 10)
        self.assertEqual(jobs, [('http://1.1.1.1:80', 'wtc.wat.edu.pl')])  # free proxies flap: a good one comes back

    def test_aged_exits_are_reverified_and_dropped_when_they_fail(self):
        old = time.time() - pool.VERIFY_TTL_S - 60
        p = self.make({'http://1.1.1.1:80': self.entry(100, wtc={'ok': True, 'ms': 300, 'checked': old}),
                       'http://1.1.1.2:80': self.entry(100, wtc={'ok': True, 'ms': 200, 'checked': time.time()})},
                      works=lambda u, h: False)
        st = p.scout_once(fetcher=self.fetcher, hosts=['wtc.wat.edu.pl'])
        self.assertEqual((st['reverified'], st['kept']), (1, 0))
        self.assertEqual([r['url'] for r in p.exits('wtc.wat.edu.pl')], ['http://1.1.1.2:80'])

    def test_stale_alive_entries_are_rechecked_and_the_dead_leave(self):
        p = self.make({'http://1.1.1.1:80': self.entry(100, age=2 * 3600),
                       'http://1.1.1.2:80': self.entry(100, age=2 * 3600, wtc={'ok': True, 'ms': 1}),
                       'http://1.1.1.3:80': self.entry(100)}, alive=lambda u: None)
        self.assertEqual(p._recheck(10, 2), (2, 1))
        self.assertNotIn('http://1.1.1.1:80', p.entries)
        self.assertIn('http://1.1.1.1:80', p.dead)
        self.assertEqual(p.entries['http://1.1.1.2:80']['status'], 'fail')  # a faculty's exit: its own probe decides

    def test_faculty_probes_never_exceed_the_gate(self):
        p = self.make({f'http://1.1.1.{i}:80': self.entry(100) for i in range(1, 9)})
        p.faculty_probes = 2
        p._faculty_gate = threading.BoundedSemaphore(2)
        inside, peak, lock = [0], [0], threading.Lock()

        def slow(url, host):
            with lock:
                inside[0] += 1
                peak[0] = max(peak[0], inside[0])
            time.sleep(0.01)
            with lock:
                inside[0] -= 1
        p.probe_host = slow
        p._run_faculty([(u, h) for u in p.entries for h in R2_ALL], workers=8)
        self.assertEqual(peak[0], 2)

    def test_the_scout_steps_aside_while_a_hunt_runs(self):
        p = self.make({'http://1.1.1.1:80': self.entry(100)})
        p._hunting = 1
        t = threading.Thread(target=p._run_faculty, args=([('http://1.1.1.1:80', 'wtc.wat.edu.pl')], 1))
        t.start()
        time.sleep(0.3)
        self.assertEqual(self.probes, [])
        p._hunting = 0
        t.join(5)
        self.assertEqual(self.probes, [('http://1.1.1.1:80', 'wtc.wat.edu.pl')])

    def test_a_quiet_scout_sleeps_until_the_lists_may_change(self):
        p = self.make()
        p._lists_cache = (time.monotonic(), {'http://8.8.8.8:80': ('x', None, None)})
        p.scout = {'unseen': 0, 'tests_left': 0}
        self.assertEqual(p.scout_wait(60), pool.VERIFY_TTL_S / 2)
        p.scout = {'unseen': 5, 'tests_left': 0}
        self.assertEqual(p.scout_wait(60), 60)


class HuntPort(unittest.TestCase):
    """server.py's hunt port: verified exits only, faculty HTTPS only, never direct."""

    def handler(self, p):
        from types import SimpleNamespace
        h = server.ProxyHandler.__new__(server.ProxyHandler)
        h.server = SimpleNamespace(pool=p, pool_only=True, remember_tunnel=lambda host, via: None)
        return h

    def test_routes_only_faculty_https_through_verified_exits(self):
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2_HUNT, active_hosts=[], hunt=True)
        h = self.handler(p)
        for host, port in (('github.com', 443), ('wml.wat.edu.pl', 80), ('localhost', 443)):
            with self.assertRaises(OSError):
                h._open(host, port)
        with self.assertRaisesRegex(OSError, 'proxy_empty'):
            h._open('wml.wat.edu.pl', 443)  # no exit: refused, never this box's own line
        p.mark('http://8.8.8.8:3128', 'wml.wat.edu.pl', True, 40)
        with unittest.mock.patch.object(server, 'chain_connect', lambda *a, **k: 'sock'):
            self.assertEqual(h._open('WML.wat.edu.pl.', 443)[:2], ('sock', 'http://8.8.8.8:3128'))

    def test_plain_http_is_refused(self):
        h = self.handler(None)
        sent = []
        h._deny = lambda code=403: sent.append(code)
        h._forward_plain()
        self.assertEqual(sent, [403])

    def test_hunt_api_needs_the_token_and_known_hosts(self):
        import json
        import urllib.error
        import urllib.request
        from types import SimpleNamespace
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2_HUNT, active_hosts=[], hunt=True)
        p.probe_host = lambda u, h: 30 if u == 'http://8.8.8.8:3128' else None
        p._discover = lambda *a, **k: ('ok', [], [])
        gui = server.GuiServer(('127.0.0.1', 0), server.GuiHandler)
        gui.pool, gui.runs, gui.proxy_port = p, server.RunLog(Path(tempfile.mkdtemp()) / 'runs.json'), 8888
        gui.proxy_server = SimpleNamespace(fallbacks={}, blocks=0, fallbacks_lock=threading.Lock(),
                                           demote_recent=lambda host: None)
        gui.hunt_server, gui.hunt_port = None, 8889
        threading.Thread(target=gui.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{gui.server_address[1]}'

        def call(path, body=None, token='sekret'):
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(base + path, data=data, method='POST' if data else 'GET',
                                         headers={'X-Token': token, 'Content-Type': 'application/json'})
            try:
                with urllib.request.urlopen(req, timeout=10) as r:
                    return r.status, json.loads(r.read())
            except urllib.error.HTTPError as err:
                return err.code, json.loads(err.read())
        try:
            with unittest.mock.patch.dict(os.environ, {'EGRESS_API_TOKEN': 'sekret'}):
                self.assertEqual(call('/api/hunt', {'hosts': ['wml.wat.edu.pl']}, token='nope')[0], 401)
                self.assertEqual(call('/api/hunt', {'hosts': ['example.org']})[0], 400)
                self.assertEqual(call('/api/exits', {'host': 'wml.wat.edu.pl', 'exits': 'x'})[0], 400)
                code, got = call('/api/exits', {'host': 'wml.wat.edu.pl', 'exits': ['8.8.8.8:3128', '9.9.9.9:80']})
                self.assertEqual((code, got['verified']), (200, ['http://8.8.8.8:3128']))
                code, got = call('/api/hunt', {'hosts': ['wtc.wat.edu.pl']})
                self.assertEqual((code, got['port']), (202, 8889))
                for _ in range(100):
                    code, got = call('/api/hunt')
                    if got['hosts'].get('wtc.wat.edu.pl', {}).get('state') == 'done':
                        break
                    time.sleep(0.02)
                self.assertEqual(got['hosts']['wtc.wat.edu.pl']['state'], 'done')
                with unittest.mock.patch.object(server, 'HUNT_ON', False):
                    self.assertEqual(call('/api/hunt', {'hosts': ['wtc.wat.edu.pl']})[0], 409)
                # the exits marked per faculty, and on the status the panel reads
                self.assertEqual(call('/api/exits?host=wml.wat.edu.pl', token='nope')[0], 401)
                self.assertEqual(call('/api/exits?host=example.org')[0], 400)
                code, got = call('/api/exits?host=wml.wat.edu.pl')
                self.assertEqual((code, [r['url'] for r in got['wml.wat.edu.pl']]), (200, ['http://8.8.8.8:3128']))
                code, got = call('/api/exits')
                self.assertEqual(set(got), set(R2_HUNT))
                code, st = call('/api/status')
                self.assertEqual(st['exits']['wml.wat.edu.pl'][0]['url'], 'http://8.8.8.8:3128')
                self.assertEqual(st['hosts']['wml.wat.edu.pl']['verified'], 1)
        finally:
            gui.shutdown()


class EgressClient(unittest.TestCase):
    """tools/refresh/egress.py: the crawler asks its egress to check shared exits, then to hunt."""

    def setUp(self):
        import egress as client
        self.client = client
        p = pool.ProxyPool(Path(tempfile.mkdtemp()) / 'pool.json', R2_HUNT, active_hosts=[], hunt=True)
        p.probe_host = lambda u, h: 30 if (u, h) in self.works else None
        p._discover = lambda *a, **k: ('ok', [], [])
        p.entries = {'http://8.8.4.4:3128': {'status': 'ok', 'latency_ms': 90, 'fails': 0,
                                             'last_checked': time.time(), 'hosts': {}}}
        self.works = set()
        from types import SimpleNamespace
        gui = server.GuiServer(('127.0.0.1', 0), server.GuiHandler)
        gui.pool, gui.runs, gui.proxy_port = p, server.RunLog(Path(tempfile.mkdtemp()) / 'runs.json'), 8888
        gui.proxy_server = SimpleNamespace(fallbacks={}, blocks=0, fallbacks_lock=threading.Lock(),
                                           demote_recent=lambda host: None)
        gui.hunt_server, gui.hunt_port = None, 8889
        threading.Thread(target=gui.serve_forever, daemon=True).start()
        self.addCleanup(gui.shutdown)
        self.api = f'http://127.0.0.1:{gui.server_address[1]}'
        env = unittest.mock.patch.dict(os.environ, {'EGRESS_API_TOKEN': 'sekret'})
        env.start()
        self.addCleanup(env.stop)

    def egress(self, token='sekret'):
        return self.client.Egress(self.api, 'http://127.0.0.1:8889', token, log=lambda m: None,
                                  sleep=lambda s: time.sleep(0.01))

    def test_shared_exits_first_then_a_hunt(self):
        self.works = {('http://8.8.8.8:3128', 'wml.wat.edu.pl'), ('http://8.8.4.4:3128', 'wtc.wat.edu.pl')}
        e = self.egress()
        self.assertEqual(e.hunt('wml.wat.edu.pl', ['8.8.8.8:3128']), ['http://8.8.8.8:3128'])
        self.assertEqual(e.hunt('wtc.wat.edu.pl', ['8.8.8.8:3128']), ['http://8.8.4.4:3128'])
        self.assertEqual(e.hunt('wlo.wat.edu.pl'), [])

    def test_an_egress_without_the_hunt_or_the_token_cannot_hunt(self):
        with self.assertRaises(self.client.Unavailable):
            self.egress(token='wrong').hunt('wml.wat.edu.pl')
        old = self.client.Egress('http://127.0.0.1:9', 'http://127.0.0.1:9', '', log=lambda m: None)
        self.assertFalse(old.available())

    def test_a_local_egress_starts_on_loopback_and_stops_with_the_crawl(self):
        local = self.client.LocalEgress(data=tempfile.mkdtemp(), log=lambda m: None, tor=False)
        try:
            self.assertTrue(local.available())
            self.assertTrue(local.proxy_url().startswith('http://127.0.0.1:'))
            code, got = local._call('/api/status')
            self.assertEqual(code, 200)
            self.assertIsNotNone(got.get('hunt_port'))
            # no regular pool work there: every faculty host is off the pool until a hunt asks for one
            self.assertTrue(all(v['mode'].startswith('DIRECT') for v in got['hosts'].values()))
        finally:
            local.close()
        self.assertIsNotNone(local.proc.poll())

    def test_a_runner_local_egress_scouts_between_crawls_and_steps_aside_for_them(self):
        import sys as _sys
        home = Path(tempfile.mkdtemp())
        seen = []

        def popen(cmd, **kw):
            seen.append(kw)
            return __import__('subprocess').Popen(cmd, **kw)

        def local():
            e = self.client.LocalEgress(log=lambda m: None, persistent=True, home=home, popen=popen,
                                        scout={'EGRESS_SCOUT': 'off'}, tor=False)
            e._venv = lambda: _sys.executable  # the test's python has what the egress needs
            return e

        crawl = local()
        self.addCleanup(crawl.stop)
        self.assertTrue(crawl.ensure())  # nothing running yet: nothing to stop
        crawl.close()  # the crawl ends: scouting starts, detached from the job
        daemon = crawl.pid
        self.assertTrue(self.client._pid_alive(daemon))
        self.assertEqual(seen[-1]['env']['RUNNER_TRACKING_ID'], '0')  # the runner's orphan cleanup leaves it
        self.assertTrue(seen[-1]['start_new_session'])
        self.assertEqual(seen[-1]['env']['EGRESS_DATA'], str(home))  # the data a crawl's hunt uses too
        self.assertEqual(oct((home / 'daemon.json').stat().st_mode & 0o777), '0o600')
        nxt = local()
        nxt.ensure()  # the next crawl: the daemon gives the memory back
        self.assertFalse(self.client._pid_alive(daemon))
        self.assertTrue(nxt.available())  # a hunt: a temporary egress on the same data
        self.assertEqual(seen[-1]['env']['EGRESS_DATA'], str(home))
        temp = nxt.proc
        nxt.close()
        self.assertIsNotNone(temp.poll())  # the temporary one went with the crawl...
        self.assertTrue(self.client._pid_alive(nxt.pid))  # ...and scouting resumed
        nxt.stop()
        self.assertFalse(self.client._pid_alive(nxt.pid))

    def test_start_updates_the_scout_only_when_its_code_changed_and_only_where_it_belongs(self):
        import json
        import sys as _sys
        home = Path(tempfile.mkdtemp())
        launched = []

        def local():
            e = self.client.LocalEgress(log=lambda m: None, persistent=True, home=home, scout={'EGRESS_SCOUT': 'off'},
                                        tor=False)
            e._venv = lambda: _sys.executable
            real = e._launch
            e._launch = lambda: (launched.append(1), real())[1]
            return e

        first = local()
        self.addCleanup(first.stop)
        self.assertTrue(first.resume())
        self.assertTrue(local().resume())  # running this code already: left alone
        self.assertEqual(len(launched), 1)
        with unittest.mock.patch.object(self.client, 'code_hash', lambda: 'newer'):
            self.assertTrue(local().resume())  # new code: restarted
        self.assertEqual(len(launched), 2)
        self.assertFalse(self.client._pid_alive(first.pid))
        fleet = home / 'fleet.json'
        fleet.write_text(json.dumps({'runners': [{'name': 'oracle', 'egress': 'remote'}]}))
        with unittest.mock.patch.object(self.client, 'LocalEgress', lambda **k: self.fail('started on oracle')):
            self.assertEqual(self.client.main(['start', '--runner', 'oracle', '--fleet', str(fleet)]), 0)

    def test_without_a_venv_there_is_no_scouting_but_hunts_still_work(self):
        from types import SimpleNamespace
        e = self.client.LocalEgress(log=lambda m: None, persistent=True, home=tempfile.mkdtemp(),
                                    run=lambda *a, **k: SimpleNamespace(returncode=1, stderr=b'no network'), tor=False)
        e.ensure()
        try:
            self.assertTrue(e.available())  # the temporary one, as before
        finally:
            e.close()
        self.assertIsNotNone(e.proc.poll())
        self.assertFalse((Path(e.home) / 'daemon.json').exists())  # no venv, no daemon

    # -- Tor beside a local egress (LocalTor)
    def fake_bundle(self, binary):
        """A tarball shaped like the expert bundle (plus a file that must not be unpacked), and its sha256."""
        import hashlib
        import io
        import tarfile
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w:gz') as tar:
            for name in self.client.TOR_FILES + ('tor/pluggable_transports/lyrebird',):
                data = binary if name == 'tor/tor' else b'x'
                info = tarfile.TarInfo(name)
                info.size, info.mode = len(data), 0o755
                tar.addfile(info, io.BytesIO(data))
        return buf.getvalue(), hashlib.sha256(buf.getvalue()).hexdigest()

    # stands in for tor: reads its torrc, says it bootstrapped in the log it names, and waits
    FAKE_TOR = (b'#!/bin/sh\nlog=$(sed -n "s/^Log notice file //p" "$2")\n'
                b'echo "[notice] Bootstrapped 100% (done): Done" > "$log"\n'
                b'trap "exit 0" TERM\nwhile :; do sleep 0.2; done\n')

    def tor(self, home, fetched):
        tgz, digest = self.fake_bundle(self.FAKE_TOR)

        def fetch(url, dest):
            fetched.append(url)
            Path(dest).write_bytes(tgz)
        patch = unittest.mock.patch.object(self.client, 'TOR_SHA256', digest)
        patch.start()
        self.addCleanup(patch.stop)
        return self.client.LocalTor(home, log=lambda m: None, sleep=lambda s: time.sleep(0.05), fetch=fetch)

    def test_tor_is_fetched_once_checked_and_started_with_polish_exits(self):
        home = Path(tempfile.mkdtemp()) / 'egress'
        fetched = []
        tor = self.tor(home, fetched)
        self.addCleanup(tor.stop)
        urls = tor.ensure()
        self.assertEqual(len(urls), self.client.TOR_PORTS)
        self.assertTrue(all(u.startswith('socks5://127.0.0.1:') for u in urls))
        rc = (home / 'torrc').read_text()
        self.assertIn('ExitNodes {pl}', rc)
        self.assertIn('StrictNodes 1', rc)
        self.assertIn(f"GeoIPFile {home.parent / ('tor-' + self.client.TOR_VERSION)}/data/geoip", rc)
        self.assertEqual(rc.count('SocksPort 127.0.0.1:'), self.client.TOR_PORTS)
        self.assertFalse((tor.bundle / 'tor' / 'pluggable_transports').exists())  # only what it needs
        pid = tor._read_state()['pid']
        self.assertEqual(tor.ensure(), urls)  # running: reused
        self.assertEqual(tor._read_state()['pid'], pid)
        tor.stop()
        self.assertFalse(self.client._pid_alive(pid, b'tor'))
        self.assertEqual(tor.ensure(), urls)  # again, on the same ports (the pool's pinned entries stay)
        self.assertEqual(len(fetched), 1)  # the bundle is kept

    def test_a_tor_bundle_that_does_not_match_its_hash_is_not_run(self):
        home = Path(tempfile.mkdtemp()) / 'egress'
        tor = self.tor(home, [])
        with unittest.mock.patch.object(self.client, 'TOR_SHA256', '0' * 64):
            self.assertEqual(tor.ensure(), [])
        self.assertFalse(tor.bundle.exists())

    def test_the_local_egress_pins_its_tor_ports(self):
        from types import SimpleNamespace
        urls = ['socks5://127.0.0.1:9050', 'socks5://127.0.0.1:9051']
        stopped = []
        fake = SimpleNamespace(ensure=lambda: urls, stop=lambda: stopped.append(1))
        e = self.client.LocalEgress(data=tempfile.mkdtemp(), log=lambda m: None, tor=fake)
        try:
            self.assertTrue(e.available())
            self.assertEqual(e._env()['EGRESS_TOR'], ','.join(urls))
            code, got = e._call('/api/status')
            self.assertEqual(code, 200)
            pinned = sorted(p['url'] for p in got['proxies'] if p['source'] == 'tor')
            self.assertEqual(pinned, urls)  # in its pool, waiting for their first Round 1
        finally:
            e.close()
        self.assertEqual(stopped, [1])  # a temporary egress takes its Tor with it

