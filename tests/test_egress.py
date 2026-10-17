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
                                             fallbacks_lock=threading.Lock(), blocks=0)
            sock, via = handler._open(self.HOST, 443)
            self.assertEqual(via, 'http://c:3')
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
                                             fallbacks_lock=threading.Lock(), blocks=0)
            sock, via = handler._open(self.HOST, 443)
            self.assertEqual(via, 'direct-fallback')
        finally:
            server.chain_connect = orig_chain
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
            self.assertIn('run in progress', page)
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
        finally:
            if prev is None:
                _os.environ.pop('EGRESS_API_TOKEN', None)
            else:
                _os.environ['EGRESS_API_TOKEN'] = prev
            gui.shutdown()


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


if __name__ == '__main__':
    unittest.main()
