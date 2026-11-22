import contextlib
import datetime as dt
import io
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools' / 'refresh'))

import ticker  # noqa: E402

UTC = dt.timezone.utc


def at(text):
    return dt.datetime.fromisoformat(text).replace(tzinfo=UTC)


class FakeGitHub:
    def __init__(self, runs=(), dispatch=204):
        self.runs, self.dispatch, self.calls = list(runs), dispatch, []

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == 'GET':
            return 200, {'workflow_runs': self.runs}
        return self.dispatch, None


class Slots(unittest.TestCase):
    def test_next_slot_follows_each_cron(self):
        self.assertEqual(ticker.next_slot(at('2026-11-22T20:00'), 120, 23), at('2026-11-22T20:23'))
        self.assertEqual(ticker.next_slot(at('2026-11-22T20:23'), 120, 23), at('2026-11-22T22:23'))
        self.assertEqual(ticker.next_slot(at('2026-11-22T23:59'), 120, 23), at('2026-11-23T00:23'))
        self.assertEqual(ticker.next_slot(at('2026-11-22T00:00'), 30, 7), at('2026-11-22T00:07'))
        self.assertEqual(ticker.next_slot(at('2026-11-22T00:07:01'), 30, 7), at('2026-11-22T00:37'))
        self.assertEqual(ticker.next_slot(at('2026-11-22T04:00'), 1440, 197), at('2026-11-23T03:17'))

    def test_the_table_matches_the_workflows_cron(self):
        for workflow, period, offset in ticker.JOBS:
            text = (ROOT / '.github' / 'workflows' / workflow).read_text(encoding='utf-8')
            crons = re.findall(r"cron:\s*'([^']+)'", text)
            self.assertEqual(crons, [ticker.cron_of(period, offset)], workflow)


class Tick(unittest.TestCase):
    slot = at('2026-11-22T20:23')

    def test_a_free_slot_starts_the_pass_with_its_tick(self):
        api = FakeGitHub()
        self.assertEqual(ticker.tick(api, 'refresh.yml', self.slot), 'started')
        method, path, body = api.calls[-1]
        self.assertEqual((method, path), ('POST', '/actions/workflows/refresh.yml/dispatches'))
        self.assertEqual(body, {'ref': 'master', 'inputs': {'tick': '2026-11-22T20:23:00Z'}})
        self.assertIn('created=%3E%3D2026-11-22T20:23:00Z', api.calls[0][1])

    def test_a_slot_another_server_took_is_left_alone(self):
        api = FakeGitHub([{'display_title': 'Refresh timetables', 'run_number': 190}])
        self.assertEqual(ticker.tick(api, 'refresh.yml', self.slot), 'slot taken by #190')
        self.assertEqual([c[0] for c in api.calls], ['GET'])

    def test_a_catch_up_does_not_take_the_slot(self):
        api = FakeGitHub([{'display_title': 'Refresh catch-up (plebania)', 'run_number': 191}])
        self.assertEqual(ticker.tick(api, 'refresh.yml', self.slot), 'started')

    def test_other_workflows_take_no_inputs_and_any_run_takes_their_slot(self):
        api = FakeGitHub()
        ticker.tick(api, 'collect.yml', self.slot)
        self.assertEqual(api.calls[-1][2], {'ref': 'master'})
        self.assertIn('slot taken', ticker.tick(FakeGitHub([{'display_title': 'x', 'run_number': 5}]),
                                                'collect.yml', self.slot))

    def test_a_refused_dispatch_is_an_error(self):
        with self.assertRaises(RuntimeError):
            ticker.tick(FakeGitHub(dispatch=403), 'refresh.yml', self.slot)

    def test_run_waits_its_delay_and_survives_errors(self):
        clock = [at('2026-11-22T20:20')]
        slept = []

        def sleep(seconds):
            slept.append(seconds)
            clock[0] += dt.timedelta(seconds=seconds)

        def broken(*_):
            raise OSError('network down')
        with contextlib.redirect_stdout(io.StringIO()) as out:
            ticker.run(broken, 4, now=lambda: clock[0], sleep=sleep, rounds=2)
        # From 20:20: refresh.yml's 20:23 slot fires at 20:27, then collect.yml's 20:37 one at 20:41.
        self.assertEqual(slept, [7 * 60, 14 * 60])
        self.assertIn('refresh.yml 20:23: network down', out.getvalue())
        self.assertIn('collect.yml 20:37: network down', out.getvalue())


if __name__ == '__main__':
    unittest.main()
