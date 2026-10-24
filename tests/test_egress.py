"""Offline tests for the egress rotator (tools/egress) and refresh retry/report logic."""
import sys
import tempfile
import threading
import time
import unittest
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'egress'))
sys.path.insert(0, str(ROOT / 'tools' / 'refresh'))

import pool  # noqa: E402
import core  # noqa: E402
import refresh  # noqa: E402
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
        self.pool.mark('http://a:1', 'example.test', True, 100)
        self.assertEqual(self.pool.entries['http://a:1']['latency_ms'], 100)
        self.pool.mark('http://a:1', 'example.test', True, 200)
        self.assertEqual(self.pool.entries['http://a:1']['latency_ms'], int(0.7 * 100 + 0.3 * 200))
        self.pool.mark_alive('http://b:2', True, 100)
        self.pool.mark_alive('http://b:2', True, 200)
        self.assertEqual(self.pool.entries['http://b:2']['latency_ms'], int(0.7 * 100 + 0.3 * 200))

    def test_fails_penalize_ordering(self):
        self.pool.entries = {
            'http://a:1': {'status': 'ok', 'latency_ms': 10, 'fails': 10,
                           'hosts': {'example.test': {'ok': True, 'ms': 10}}},
            'http://b:2': {'status': 'ok', 'latency_ms': 500, 'fails': 0,
                           'hosts': {'example.test': {'ok': True, 'ms': 500}}},
        }
        self.assertEqual(self.pool.pick('example.test'), 'http://b:2')

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

    def test_probe_alive_requires_the_expected_image_and_no_block_page(self):
        from types import SimpleNamespace
        good = b'\x89PNG\r\n\x1a\n' + b'x' * 2000
        for body, expected in (
            (good, 50),
            (good + b'incapsula incident id', None),
            (b'<html>' + b'x' * 2000, None),  # 200 + big body, but not the OSM tile
        ):
            self.pool.fetch_via = (
                lambda url, target, timeout, body=body: (SimpleNamespace(status_code=200, content=body), 50))
            self.assertEqual(self.pool.probe_alive('http://8.8.8.8:8080'), expected, body[:20])

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
        p = pool.ProxyPool(tmp, R2)
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
        p = pool.ProxyPool(tmp, R2)
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
        p = pool.ProxyPool(tmp, R2)
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
        p = pool.ProxyPool(tmp, R2)
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
        p = pool.ProxyPool(tmp, R2)
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
        p = pool.ProxyPool(tmp, R2)
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
                      'planzajec.wcy.wat.edu.pl', 'wml.wat.edu.pl', 'wtc.wat.edu.pl', 'ioe.wat.edu.pl'):
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
        p = pool.ProxyPool(tmp, R2)
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


if __name__ == '__main__':
    unittest.main()
