"""The runner's sealed telemetry for the operator's dashboard (tools/refresh/telemetry.py)."""
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'refresh'))

import stack  # noqa: E402
import telemetry  # noqa: E402

KEY = '11' * 32


class Sealing(unittest.TestCase):
    def test_only_the_key_opens_it(self):
        blob = telemetry.seal({'a': 1, 'events': ['x' * 500]}, KEY)
        self.assertNotIn('xxxx', blob)
        self.assertEqual(telemetry.unseal(blob, KEY), {'a': 1, 'events': ['x' * 500]})
        self.assertIsNone(telemetry.unseal(blob, '22' * 32))
        self.assertIsNone(telemetry.unseal(blob[:-4] + 'AAAA', KEY))

    def test_no_key_no_telemetry(self):
        self.assertIsNone(telemetry.seal({}, ''))
        self.assertIsNone(telemetry.seal({}, 'short'))
        with unittest.mock.patch.dict(os.environ, {'PLANWAT_DASH_KEY': ''}):
            self.assertIsNone(telemetry.sealed())

    def test_the_heartbeat_carries_it_only_with_the_key(self):
        runner = stack.Runner(None, stack.Me('oracle1', [], {}, [], [], {}, {}, {}, (), ()), None)
        with unittest.mock.patch.dict(os.environ, {'PLANWAT_DASH_KEY': ''}):
            self.assertNotIn('tel', runner._doc())
        with unittest.mock.patch.dict(os.environ, {'PLANWAT_DASH_KEY': KEY}):
            tel = telemetry.unseal(runner._doc()['tel'], KEY)
        self.assertEqual(tel['v'], telemetry.VERSION)


class Recording(unittest.TestCase):
    def test_lines_are_kept_with_their_kind_and_faculty_newest_last_bounded(self):
        t = telemetry.Telemetry(clock=lambda: 100.0)
        for i in range(telemetry.EVENTS + 5):
            t.event(f'[wlo] line {i}')
        t.event('egress: Tor up (pid 1, Polish exits, 4 circuits)')
        t.event('nothing special: here')
        ev = t.snapshot()['events']
        self.assertEqual(len(ev), telemetry.EVENTS)
        self.assertEqual((ev[-3]['fac'], ev[-2]['kind'], ev[-1]['kind']), ('wlo', 'egress', 'log'))
        self.assertGreater(ev[-1]['n'], ev[0]['n'])

    def test_requests_are_counted_per_host_and_route(self):
        t = telemetry.Telemetry()
        t.request('wlo.wat.edu.pl', 'pool', 200, 812.4, 5000)
        t.request('wlo.wat.edu.pl', 'pool', 304, 100, 0)
        t.request('wlo.wat.edu.pl', 'pool', 0, 60000, 0)
        t.request('wlo.wat.edu.pl', 'direct', 403, 50, 900)
        req = t.snapshot()['req']['wlo.wat.edu.pl']
        self.assertEqual({k: req['pool'][k] for k in ('n', 's2xx', 's304', 'err', 'ms', 'bytes')},
                         {'n': 3, 's2xx': 1, 's304': 1, 'err': 1, 'ms': 60912, 'bytes': 5000})
        self.assertEqual(req['direct']['other'], 1)

    def test_system_reads_proc_and_turns_samples_into_rates(self):
        proc = Path(tempfile.mkdtemp())
        (proc / 'self').mkdir()
        (proc / 'net').mkdir()
        (proc / 'loadavg').write_text('0.50 0.40 0.30 1/200 999\n')
        (proc / 'meminfo').write_text('MemTotal:  1024000 kB\nMemFree: 1000 kB\nMemAvailable:  512000 kB\n')
        (proc / 'self' / 'status').write_text('Name: python\nVmRSS:\t  204800 kB\n')
        net = 'h1\nh2\n    lo: 999 0 0 0 0 0 0 0 999 0\n  eth0: {rx} 0 0 0 0 0 0 0 {tx} 0\n'
        (proc / 'stat').write_text('cpu  100 0 100 800 0 0 0 0\n')
        (proc / 'net' / 'dev').write_text(net.format(rx=0, tx=0))
        now = [10.0]
        t = telemetry.Telemetry(clock=lambda: now[0], proc=proc)
        first = t.system()
        self.assertEqual((first['load'], first['mem_mb'], first['mem_free_mb'], first['rss_mb']),
                         ([0.5, 0.4, 0.3], 1000, 500, 200))
        self.assertNotIn('cpu', first)
        (proc / 'stat').write_text('cpu  150 0 150 900 0 0 0 0\n')  # 100 busy of 200 ticks
        (proc / 'net' / 'dev').write_text(net.format(rx=20480, tx=10240))
        now[0] = 20.0
        second = t.system()
        self.assertEqual((second['cpu'], second['rx_kbs'], second['tx_kbs']), (50.0, 2.0, 1.0))

    def test_a_machine_without_proc_still_reports(self):
        t = telemetry.Telemetry(proc=Path('/nonexistent'))
        self.assertEqual(t.system(), {})


if __name__ == '__main__':
    unittest.main()
