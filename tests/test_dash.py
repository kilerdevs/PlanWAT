"""The operator's local fleet dashboard (tools/dash/dash.py): what it derives from the docs, and how it serves them."""
import http.client
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'refresh'))
sys.path.insert(0, str(ROOT / 'tools' / 'dash'))

import board  # noqa: E402
import dash  # noqa: E402
import telemetry  # noqa: E402

KEY = '33' * 32
P = 'refs/planwat/pass/1761000000-42/'


def slot(state='open', **kw):
    return {'slot': 'wlo', 'state': state, 'leader': 'northflank2', 'group': 'wat-edge', 'listed': 131, 'fresh': 0,
            'not_ready': 0, 'chunks': [], **kw}


WLO = slot(chunks=[{'id': 0, 'codes': ['a'] * 24, 'state': 'done', 'done_by': 'northflank2', 'changed': 2},
                   {'id': 1, 'codes': ['b'] * 83, 'state': 'free', 'by': None},
                   {'id': 2, 'codes': ['c'] * 24, 'state': 'held', 'by': 'northflank1'}],
           cant={'oracle1': {'cause': 'wall'}, 'oracle2': {'cause': 'wall'}},
           via={'northflank1': 'pool', 'northflank2': 'pool'}, via_tor=['northflank2'],
           hunting={'runner': 'oracle3'})


class Derive(unittest.TestCase):
    def test_a_slot_says_who_did_what_and_how_each_runner_gets_there(self):
        v = dash.slot_view('s/wlo', WLO)
        self.assertEqual((v['total'], v['done'], v['held'], v['changed']), (131, 24, 24, 2))
        self.assertEqual(v['by'], {'northflank2': 24})
        self.assertEqual(v['routes'], {'oracle1': 'wall', 'oracle2': 'wall', 'northflank1': 'pool',
                                       'northflank2': 'tor', 'oracle3': 'hunting'})
        self.assertEqual(dash.slot_name('s/wml@2027-28-zima'), 'wml~2027-28-zima')

    def test_a_runner_crawling_from_its_own_address_is_direct(self):
        d = slot(chunks=[{'codes': ['a'], 'state': 'held', 'by': 'oracle2'}], leader='oracle1')
        self.assertEqual(dash.routes_of(d), {'oracle1': 'direct', 'oracle2': 'direct'})

    def test_runner_status(self):
        lanes = {'wat-edge': {'slot': 'wlo', 'chunk': 3, 'tick': 4}}
        self.assertEqual(dash.runner_status({'lanes': lanes}, 10, False), 'crawling')
        self.assertEqual(dash.runner_status({'lanes': {'g': {'slot': 'wcy', 'chunk': None}}}, 10, False), 'listing')
        self.assertEqual(dash.runner_status({'lanes': {}}, 10, True), 'hunting')
        self.assertEqual(dash.runner_status({'lanes': {}}, 10, False), 'idle')
        self.assertEqual(dash.runner_status({'lanes': lanes}, dash.STALE + 1, False), 'gone')
        self.assertEqual(dash.runner_status({'mode': 'done'}, dash.STALE + 1, False), 'done')

    def test_the_stack_changes_read_as_events(self):
        before = {'s/wlo': slot('listing'), 'r/oracle1': {'beat': 1}}
        after = {'s/wlo': WLO, 'r/oracle1': {'beat': 2, 'mode': 'done'}, 'r/northflank1': {'beat': 1}}
        kinds = [(s, r, k) for s, r, k, _ in dash.diff_events(before, after)]
        self.assertIn((None, 'northflank1', 'runner'), kinds)
        self.assertIn((None, 'oracle1', 'runner'), kinds)
        self.assertIn(('wlo', 'northflank2', 'slot'), kinds)
        self.assertIn(('wlo', 'oracle1', 'wall'), kinds)
        self.assertIn(('wlo', 'oracle3', 'hunt'), kinds)
        self.assertIn(('wlo', 'northflank1', 'join'), kinds)
        msgs = [m for *_, m in dash.diff_events(before, after)]
        self.assertIn('northflank2 gets through via pool (own Tor)', msgs)
        self.assertEqual(dash.diff_events(after, after), [])


class Collecting(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.now = [1761000100.0]
        self.c = dash.Collector(':memory:', self.tmp / 'cache', KEY, clock=lambda: self.now[0])

    def runner_doc(self, beat, n_req, events=()):
        t = telemetry.Telemetry(clock=lambda: self.now[0])
        for _ in range(n_req):
            t.request('wlo.wat.edu.pl', 'pool', 200, 500, 1000)
        for e in events:
            t.event(e)
        return {'runner': 'northflank1', 'nonce': 'n1', 'beat': beat, 'mode': 'run',
                'lanes': {'wat-edge': {'slot': 'wlo', 'chunk': 2, 'tick': 1}},
                'tel': telemetry.seal(t.snapshot(), KEY)}

    def test_a_pass_seen_live_is_recorded_with_rates_events_and_samples_then_finished_when_swept(self):
        listed = {P + 's/wlo', P + 'r/northflank1'}
        self.c.ingest({P + 's/wlo': WLO, P + 'r/northflank1': self.runner_doc(1, 10, ['[wlo] one'])}, listed)
        self.now[0] += 30
        self.c.ingest({P + 'r/northflank1': self.runner_doc(2, 40, ['[wlo] one', 'egress: Tor up'])}, listed)
        st = self.c.state()
        p = st['live'][0]
        r = p['runners'][0]
        self.assertEqual((r['status'], r['tel'], r['ppm'], r['totals']['n']), ('crawling', True, 60.0, 40))
        logs = [e['msg'] for e in st['events'] if e['kind'] in ('log', 'egress')]
        self.assertEqual(sorted(logs), ['[wlo] one', 'egress: Tor up'])  # each line once, across heartbeats
        self.assertEqual(len(st['timeline']), 2)
        self.c.ingest({}, set())  # the report job swept it
        st = self.c.state()
        self.assertEqual(st['live'], [])
        self.assertEqual(st['last']['done'], 24)
        hist = self.c.history(days=60)
        self.assertEqual(hist['passes'][0]['source'], 'live')
        self.assertEqual(hist['passes'][0]['util'], {'northflank1': {'crawling': 2}})

    def test_a_pass_left_on_the_stack_after_its_run_ended_is_not_live(self):
        self.c.ingest({P + 's/wlo': WLO}, {P + 's/wlo'})
        self.c.runs = [{'id': 42, 'status': 'completed'}]
        self.assertEqual(self.c.state()['live'], [])
        self.c.runs = [{'id': 42, 'status': 'in_progress'}]
        self.assertEqual(len(self.c.state()['live']), 1)
        self.c.runs = []
        self.now[0] += 4 * 3600  # no word of its run, and hours old
        self.assertEqual(self.c.state()['live'], [])

    def test_without_the_key_telemetry_stays_sealed(self):
        c = dash.Collector(':memory:', self.tmp / 'c2', '', clock=lambda: self.now[0])
        c.ingest({P + 'r/northflank1': self.runner_doc(1, 5)}, {P + 'r/northflank1'})
        r = c.state()['live'][0]['runners'][0]
        self.assertEqual((r['sealed'], r['tel'], r['totals']), (True, False, {}))

    def test_an_archived_pass_fills_history_but_never_replaces_one_seen_live(self):
        arch = {'s/wlo': WLO, 'r/northflank1': self.runner_doc(9, 3)}
        self.c.ingest({'refs/planwat/archive/1760000000-7': arch}, {'refs/planwat/archive/1760000000-7'})
        old = self.c.history(days=60)['passes']
        self.assertEqual((old[0]['run'], old[0]['source'], old[0]['runners'][0]['totals']['n']), (7, 'archive', 3))
        self.assertEqual(self.c.state()['live'], [])
        self.c.ingest({P + 's/wlo': WLO}, {P + 's/wlo'})
        self.c.ingest({}, set())
        self.c.ingest({'refs/planwat/archive/1761000000-42': {'s/wlo': slot('closed')}}, set())
        mine = [p for p in self.c.history(days=60)['passes'] if p['run'] == 42][0]
        self.assertEqual((mine['source'], mine['done']), ('live', 24))


class Serving(unittest.TestCase):
    def setUp(self):
        self.c = dash.Collector(':memory:', Path(tempfile.mkdtemp()), '')
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), dash.make_handler(self.c, 0))
        self.port = self.srv.server_address[1]
        self.srv.RequestHandlerClass = dash.make_handler(self.c, self.port)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def get(self, path, host=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        conn.request('GET', path, headers={'Host': host or f'127.0.0.1:{self.port}'})
        r = conn.getresponse()
        return r.status, r.getheader('Content-Security-Policy'), r.read()

    def test_it_answers_only_to_this_machines_own_names(self):
        self.assertEqual(self.get('/api/state', host=f'evil.example:{self.port}')[0], 421)
        self.assertEqual(self.get('/', host=f'localhost:{self.port}')[0], 200)

    def test_the_page_and_its_data(self):
        status, csp, body = self.get('/')
        self.assertEqual(status, 200)
        self.assertIn("script-src 'self'", csp)
        self.assertIn(b'/dash.js', body)
        self.assertEqual(json.loads(self.get('/api/state')[2])['live'], [])
        self.assertEqual(json.loads(self.get('/api/history?days=x')[2])['passes'], [])
        self.assertEqual(self.get('/../dash.py')[0], 404)


class ReadingGit(unittest.TestCase):
    def test_it_reads_a_pass_from_the_remote_into_a_cache_of_its_own(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        remote, work = tmp / 'remote.git', tmp / 'work'
        subprocess.run(['git', 'init', '-q', '--bare', str(remote)], check=True)
        subprocess.run(['git', 'init', '-q', str(work)], check=True)
        subprocess.run(['git', '-C', str(work), 'remote', 'add', 'origin', str(remote)], check=True)
        store = board.GitStore(work, '1761000000-42')
        store.put('r/oracle1', {'beat': 1, 'lanes': {}})
        store.update('s/wlo', lambda d: WLO)
        c = dash.Collector(':memory:', tmp / 'cache', '', remote=str(remote), clock=lambda: 1761000100.0)
        changed, listed = c.read_refs()
        self.assertEqual(set(changed), {P + 'r/oracle1', P + 's/wlo'})
        c.ingest(changed, listed)
        self.assertEqual(c.read_refs()[0], {})  # nothing moved: nothing fetched again
        self.assertEqual(c.state()['live'][0]['slots'][0]['done'], 24)
        self.assertFalse((work / 'refs' / 'dash').exists())


if __name__ == '__main__':
    unittest.main()
