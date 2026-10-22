"""Offline tests of the volunteer crawlers (tools/volunteer): assignment, bundles and the coordinator.

Forks are local bare repositories, so the whole fetch -> check -> vote -> file path runs without a network.
"""
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tools' / 'refresh'))
sys.path.insert(0, str(ROOT / 'tools' / 'volunteer'))
sys.path.insert(0, str(ROOT / 'tests'))

import assign  # noqa: E402
import build  # noqa: E402
import bundle  # noqa: E402
import collect  # noqa: E402
import manage  # noqa: E402
import core  # noqa: E402
import refresh  # noqa: E402

TID = '2026-27-zima'
CODE = 'WCY26KY3S1'
REL = f'timetables/{TID}/{CODE}.ics'
SOURCE = (ROOT / 'timetables' / TID / f'{CODE}.ics').read_bytes().decode('utf-8')
NOW = dt.datetime(2026, 10, 20, 12, 0, 0)
VERSION = bundle.version()


def changed_plan(tag='A'):
    """The same calendar with one lesson moved to another room: a different plan that still validates."""
    head, sep, rest = SOURCE.partition('LOCATION:')
    line, nl, tail = rest.partition('\r\n')
    return head + sep + f'Sala {tag}' + nl + tail


def registry(*volunteers, quorum=2, min_version='0.0.1'):
    return assign.check_registry({'quorum': quorum, 'window_hours': 12, 'min_version': min_version,
                                  'volunteers': [dict(v) for v in volunteers]})


def git(*args, cwd):
    return subprocess.run(['git', *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


class AssignTest(unittest.TestCase):
    PEERS = [{'login': f'peer{i}', 'trust': 'peer'} for i in range(5)]

    def test_registry_refuses_a_fork_of_somebody_else(self):
        with self.assertRaises(assign.RegistryError):
            registry({'login': 'alice', 'fork': 'mallory/PlanWAT'})

    def test_registry_refuses_duplicates_bad_trust_and_a_quorum_of_one(self):
        for bad in ({'quorum': 2, 'volunteers': [{'login': 'a'}, {'login': 'A'}]},
                    {'quorum': 2, 'volunteers': [{'login': 'a', 'trust': 'root'}]},
                    {'quorum': 1, 'volunteers': []},
                    {'quorum': 2, 'volunteers': [{'login': '../x'}]}):
            with self.assertRaises(assign.RegistryError):
                assign.check_registry(bad)

    def test_the_answer_is_the_same_for_everybody(self):
        reg = registry(*self.PEERS)
        self.assertEqual(assign.assignees(reg, 'wcy', CODE, TID, 7), assign.assignees(reg, 'wcy', CODE, TID, 7))

    def test_peers_come_in_quorums_and_a_trusted_volunteer_alone(self):
        reg = registry(*self.PEERS, {'login': 'anchor', 'trust': 'trusted'})
        sizes = Counter()
        for n in range(400):
            got = assign.assignees(reg, 'wcy', f'G{n}', TID, 1)
            sizes[len(got)] += 1
            if 'anchor' in got:
                self.assertEqual(got, ['anchor'])
            else:
                self.assertEqual(len(got), 2)
        self.assertGreater(sizes[1], 0)
        self.assertGreater(sizes[2], 0)

    def test_too_few_peers_for_a_faculty_fall_back_to_a_trusted_volunteer_or_nobody(self):
        lone = registry({'login': 'solo', 'trust': 'peer'}, {'login': 'p2', 'trust': 'peer', 'faculties': ['wel']})
        self.assertEqual(assign.assignees(lone, 'wcy', CODE, TID, 1), [])
        backed = registry({'login': 'solo', 'trust': 'peer'},
                          {'login': 'anchor', 'trust': 'trusted', 'faculties': ['wcy']})
        self.assertEqual(assign.assignees(backed, 'wcy', CODE, TID, 1), ['anchor'])

    def test_faculties_and_suspension_limit_who_is_asked(self):
        reg = registry({'login': 'wel-only', 'trust': 'trusted', 'faculties': ['wel']},
                       {'login': 'gone', 'trust': 'suspended'}, *self.PEERS[:2])
        for n in range(50):
            got = assign.assignees(reg, 'wcy', f'G{n}', TID, 1)
            self.assertNotIn('wel-only', got)
            self.assertNotIn('gone', got)

    def test_shares_rotate_between_windows_and_spread_evenly(self):
        reg = registry(*self.PEERS)
        load = Counter()
        moved = 0
        for n in range(500):
            first = assign.assignees(reg, 'wcy', f'G{n}', TID, 1)
            second = assign.assignees(reg, 'wcy', f'G{n}', TID, 2)
            moved += first != second
            load.update(first)
        self.assertGreater(moved, 300)
        self.assertLess(max(load.values()) / min(load.values()), 1.5)

    def test_windows_are_two_hours(self):
        self.assertEqual(assign.window_of(NOW + dt.timedelta(hours=2)), assign.window_of(NOW) + 1)


class StateMergeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def test_an_accepted_volunteer_check_makes_a_group_fresh_for_the_home_runner(self):
        (self.tmp / core.VOLUNTEER_STATE_FILE).write_text(json.dumps(
            {'version': 1, 'groups': {f'{CODE}@{TID}': {'checked': '2026-10-20T11:30:00'}}}))
        state = core.State(self.tmp / core.STATE_FILE)
        self.assertTrue(state.fresh(CODE, NOW, 1, TID))
        self.assertFalse(state.fresh(CODE, NOW, 1, '2026-27-lato'))
        self.assertFalse(state.fresh('OTHER', NOW, 1, TID))

    def test_the_site_shows_the_newer_of_both_stamps(self):
        (self.tmp / 'refresh-state.json').write_text(json.dumps({'groups': {
            CODE: {'checked': '2026-10-19T10:00:00', 'changed': '2026-10-01T10:00:00', 'term': TID},
            'NEWER': {'checked': '2026-10-20T10:00:00', 'term': TID}}}))
        (self.tmp / 'volunteer-state.json').write_text(json.dumps({'groups': {
            f'{CODE}@{TID}': {'checked': '2026-10-20T11:00:00'},
            f'NEWER@{TID}': {'checked': '2026-10-20T09:00:00'},
            f'{CODE}@2027-28-zima': {'checked': '2026-10-20T11:00:00'}}}))
        groups = build.load_refresh_state(self.tmp / 'refresh-state.json')
        self.assertEqual(groups[CODE]['checked'], '2026-10-20T11:00:00')
        self.assertEqual(groups[CODE]['changed'], '2026-10-01T10:00:00')
        self.assertEqual(groups['NEWER']['checked'], '2026-10-20T10:00:00')
        self.assertIn(f'{CODE}@2027-28-zima', groups)


class VolunteerRefreshTest(unittest.TestCase):
    """refresh.py in volunteer mode: only the assigned share, at the volunteer pace, with outcomes."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)

    def reg_file(self, *volunteers):
        path = self.tmp / 'volunteers.json'
        path.write_text(json.dumps({'quorum': 2, 'volunteers': list(volunteers)}))
        return path

    def test_volunteer_mode_forces_the_gentle_pace_and_needs_a_login(self):
        path = self.reg_file({'login': 'alice', 'trust': 'trusted'})
        args = refresh.parse(['--out', str(self.tmp), '--profile', 'selfhosted', '--assign', str(path), '--as', 'alice'])
        self.assertEqual(args.delay, refresh.PROFILES['volunteer'])
        with self.assertRaises(SystemExit):
            refresh.parse(['--out', str(self.tmp), '--assign', str(path)])

    def test_somebody_not_in_the_registry_is_turned_away(self):
        path = self.reg_file({'login': 'alice', 'trust': 'trusted'})
        os.environ['PLANWAT_EGRESS_STATUS'] = os.environ['PLANWAT_EGRESS_PROGRESS'] = ''
        self.assertEqual(refresh.main(['--out', str(self.tmp), '--assign', str(path), '--as', 'mallory']), 2)

    def test_only_the_assigned_groups_are_fetched_and_their_outcomes_recorded(self):
        import test_refresh as tr
        base = 'https://example.test/plan/zima/'
        routes = {base + 'index.xml': tr.Resp(200, tr.INDEX.encode()),
                  base + 'WLO26AX1S1.htm': tr.Resp(200, tr.page('WLO26AX1S1.htm'))}
        mine = self.reg_file({'login': 'alice', 'trust': 'trusted'})
        args = refresh.parse(['--out', str(self.tmp), '--force', '--assign', str(mine), '--as', 'alice'])
        args.window = 5
        state = core.State(self.tmp / core.STATE_FILE)
        changed, _, _ = refresh.refresh_faculty('wlo', tr.WLO_CFG, args, state, tr.TODAY,
                                                tr.SequenceSession(routes), sleep=lambda s: None)
        self.assertEqual(changed, ['WLO26AX1S1'])
        self.assertEqual(args.outcomes_log['WLO26AX1S1@2026-27-zima']['status'], 'changed')
        # Nobody but a peer without a partner: nothing is assigned, nothing fetched.
        other = self.reg_file({'login': 'alice', 'trust': 'peer'})
        args = refresh.parse(['--out', str(self.tmp), '--force', '--assign', str(other), '--as', 'alice'])
        args.window = 5
        session = tr.SequenceSession(routes)
        refresh.refresh_faculty('wlo', tr.WLO_CFG, args, state, tr.TODAY, session, sleep=lambda s: None)
        self.assertFalse(any(u.endswith('.htm') for u in session.seen))


class Harness(unittest.TestCase):
    """A data repository with one published calendar, and bare repositories standing in for the forks."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.data = self.tmp / 'data'
        (self.data / 'timetables' / TID).mkdir(parents=True)
        (self.data / REL).write_bytes(SOURCE.encode('utf-8'))
        git('init', '-q', cwd=self.data)
        git('-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false', 'add', '-A', cwd=self.data)
        git('-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false',
            'commit', '-q', '-m', 'seed', cwd=self.data)
        self.forks = self.tmp / 'forks'
        self.forks.mkdir()
        self.seq = 1792000000

    def remote(self, login):
        path = self.forks / f'{login}.git'
        if not path.exists():
            git('init', '-q', '--bare', str(path), cwd=self.tmp)
        return str(path)

    def push_files(self, login, files, symlink=None):
        tree = Path(tempfile.mkdtemp(dir=self.tmp))
        bundle.write_tree(tree, json.loads(files.pop('manifest.json')), {})
        for rel, raw in files.items():
            (tree / rel).parent.mkdir(parents=True, exist_ok=True)
            (tree / rel).write_bytes(raw)
        if symlink:
            os.symlink('/etc/passwd', tree / symlink)
        bundle.push(tree, f'{login}/PlanWAT', login, '', self.remote(login))

    def offer(self, who, status='changed', ics=None, ended=NOW, **manifest):
        """Push a one-group bundle from `who` the way bundle.py would."""
        self.seq += 1
        ics = changed_plan() if ics is None and status == 'changed' else ics or SOURCE
        body = {'format': 1, 'version': VERSION, 'login': who, 'seq': self.seq, 'started': ended.isoformat(),
                'ended': ended.isoformat(), 'window': 1, 'faculties': {},
                'groups': {f'{CODE}@{TID}': {'status': status, 'plan': core.plan_hash(ics), 'at': ended.isoformat()}}}
        body.update(manifest)
        files = {'manifest.json': json.dumps(body)}
        if status == 'changed':
            files[REL] = ics.encode('utf-8')
        self.push_files(who, files)

    def collect(self, reg, now=NOW, dry_run=False):
        return collect.collect(reg, self.data, now, lambda v: self.remote(v['login']), dry_run=dry_run)

    def published(self):
        return (self.data / REL).read_bytes().decode('utf-8')

    def state(self):
        return collect.load_state(self.data / core.VOLUNTEER_STATE_FILE)


class BundleTest(Harness):
    def test_only_changed_calendars_travel_and_the_manifest_round_trips(self):
        work = self.tmp / 'work'
        shutil.copytree(self.data, work)
        (work / REL).write_bytes(changed_plan().encode('utf-8'))
        outcomes = {'started': '2026-10-20T11:00:00', 'ended': '2026-10-20T11:40:00', 'window': 1,
                    'groups': {f'{CODE}@{TID}': {'status': 'changed', 'at': '2026-10-20T11:10:00'},
                               f'WCY20IT1S0@{TID}': {'status': 'unchanged', 'at': '2026-10-20T11:11:00'},
                               f'WCY99XX1S1@{TID}': {'status': 'not_ready', 'at': '2026-10-20T11:12:00'}},
                    'faculties': {'wcy': {'blocked': False, 'cause': None}}}
        manifest, files = bundle.build_bundle(work, outcomes, 'alice')
        self.assertEqual(list(files), [REL])
        self.assertEqual(manifest['groups'][f'{CODE}@{TID}']['plan'], core.plan_hash(changed_plan()))
        self.assertNotIn(f'WCY20IT1S0@{TID}', manifest['groups'])  # nothing filed to vouch for
        self.assertEqual(manifest['groups'][f'WCY99XX1S1@{TID}']['status'], 'not_ready')
        tree = self.tmp / 'tree'
        tree.mkdir()
        bundle.write_tree(tree, manifest, files)
        bundle.push(tree, 'alice/PlanWAT', 'alice', '', self.remote('alice'))
        commit, fetched = collect.fetch_bundle(self.remote('alice'), self.tmp / 'scratch.git')
        self.assertEqual(set(fetched), {'manifest.json', REL})
        self.assertEqual(json.loads(fetched['manifest.json'])['login'], 'alice')

    def test_a_volatile_line_does_not_change_the_plan(self):
        moved = SOURCE.replace('X-PLAN-GENERATED:', 'X-PLAN-GENERATED:1', 1)
        self.assertEqual(core.plan_hash(moved), core.plan_hash(SOURCE))
        self.assertNotEqual(core.plan_hash(changed_plan()), core.plan_hash(SOURCE))


class CollectTest(Harness):
    def test_a_trusted_volunteer_is_accepted_alone(self):
        reg = registry({'login': 'alice', 'trust': 'trusted'})
        self.offer('alice')
        summary = self.collect(reg)
        self.assertEqual(summary['changed'], [f'{CODE}@{TID}'])
        self.assertEqual(self.published(), changed_plan())
        group = self.state()['groups'][f'{CODE}@{TID}']
        self.assertEqual((group['by'], group['checked'], group['changed']), (['alice'], NOW.isoformat(), NOW.isoformat()))

    def test_one_peer_waits_for_a_second_that_agrees(self):
        reg = registry({'login': 'bob', 'trust': 'peer'}, {'login': 'carol', 'trust': 'peer'})
        self.offer('bob')
        self.assertEqual(self.collect(reg)['changed'], [])
        self.assertEqual(self.published(), SOURCE)
        self.offer('carol', ended=NOW + dt.timedelta(minutes=30))
        self.assertEqual(self.collect(reg, NOW + dt.timedelta(minutes=31))['changed'], [f'{CODE}@{TID}'])
        self.assertEqual(self.published(), changed_plan())

    def test_two_peers_that_disagree_publish_nothing(self):
        reg = registry({'login': 'bob', 'trust': 'peer'}, {'login': 'carol', 'trust': 'peer'})
        self.offer('bob', ics=changed_plan('A'))
        self.offer('carol', ics=changed_plan('B'))
        self.assertEqual(self.collect(reg)['changed'], [])
        self.assertEqual(self.published(), SOURCE)

    def test_votes_expire_with_the_window(self):
        reg = registry({'login': 'bob', 'trust': 'peer'}, {'login': 'carol', 'trust': 'peer'})
        self.offer('bob')
        self.collect(reg)
        later = NOW + dt.timedelta(hours=13)
        self.offer('carol', ended=later)
        self.assertEqual(self.collect(reg, later)['changed'], [])

    def test_unchanged_votes_cannot_veto_a_change(self):
        reg = registry(*({'login': n, 'trust': 'peer'} for n in ('bob', 'carol', 'dave', 'erin')))
        self.offer('dave', status='unchanged')
        self.offer('erin', status='unchanged')
        self.offer('bob')
        self.offer('carol')
        self.collect(reg)
        self.assertEqual(self.published(), changed_plan())

    def test_unchanged_quorum_only_stamps_the_check(self):
        reg = registry({'login': 'bob', 'trust': 'peer'}, {'login': 'carol', 'trust': 'peer'})
        self.offer('bob', status='unchanged')
        self.offer('carol', status='unchanged')
        self.assertEqual(self.collect(reg)['changed'], [])
        self.assertEqual(self.state()['groups'][f'{CODE}@{TID}']['checked'], NOW.isoformat())
        self.assertNotIn('changed', self.state()['groups'][f'{CODE}@{TID}'])

    def test_a_peer_that_keeps_losing_is_benched(self):
        reg = registry(*({'login': n, 'trust': 'peer'} for n in ('bob', 'carol', 'liar')))
        for n in range(3):
            moment = NOW + dt.timedelta(hours=n)
            good = changed_plan(f'good{n}')
            self.offer('bob', ics=good, ended=moment)
            self.offer('carol', ics=good, ended=moment)
            self.offer('liar', ics=changed_plan(f'bad{n}'), ended=moment)
            summary = self.collect(reg, moment)
        self.assertEqual(summary['benched'], ['liar'])
        self.offer('liar', ics=changed_plan('again'), ended=NOW + dt.timedelta(hours=3))
        self.assertNotIn('liar', self.collect(reg, NOW + dt.timedelta(hours=3))['read'])
        collect.main(['--registry', str(self.tmp / 'r.json'), '--data', str(self.data), '--unbench', 'liar'])
        self.assertNotIn('liar', self.state()['benched'])

    def test_dry_run_writes_nothing(self):
        reg = registry({'login': 'alice', 'trust': 'trusted'})
        self.offer('alice')
        self.collect(reg, dry_run=True)
        self.assertEqual(self.published(), SOURCE)
        self.assertFalse((self.data / core.VOLUNTEER_STATE_FILE).exists())

    def test_revert_puts_back_what_a_volunteer_got_accepted(self):
        reg = registry({'login': 'alice', 'trust': 'trusted'})
        self.offer('alice')
        self.collect(reg)
        keys = collect.revert(self.data / core.VOLUNTEER_STATE_FILE, self.data, 'alice', '2026-10-20T00:00:00', NOW)
        self.assertEqual(keys, [f'{CODE}@{TID}'])
        self.assertEqual(self.published(), SOURCE)
        self.assertNotIn('checked', self.state()['groups'][f'{CODE}@{TID}'])

    def test_a_bundle_already_read_is_not_counted_twice(self):
        reg = registry({'login': 'bob', 'trust': 'peer'}, {'login': 'carol', 'trust': 'peer'})
        self.offer('bob')
        self.collect(reg)
        self.assertEqual(self.collect(reg)['read'], [])
        self.assertEqual(self.published(), SOURCE)


class RefusalTest(Harness):
    def setUp(self):
        super().setUp()
        self.reg = registry({'login': 'alice', 'trust': 'trusted'}, min_version='1.0.0')

    def refused(self):
        summary = self.collect(self.reg)
        self.assertEqual(self.published(), SOURCE)
        return summary['refused'].get('alice', '')

    def test_a_manifest_signed_by_somebody_else(self):
        self.offer('alice', login='bob')
        self.assertIn('signed', self.refused())

    def test_an_old_crawler(self):
        self.offer('alice', version='0.9.0')
        self.assertIn('older', self.refused())

    def test_a_replayed_bundle(self):
        self.offer('alice', seq=10)
        self.collect(self.reg)
        (self.data / REL).write_bytes(SOURCE.encode('utf-8'))
        self.seq = 0
        self.offer('alice', seq=10, ics=changed_plan('B'))
        self.assertIn('replayed', self.refused())

    def test_a_stale_or_future_bundle(self):
        self.offer('alice', ended=NOW - dt.timedelta(hours=13))
        self.assertIn('stale', self.refused())
        self.offer('alice', ended=NOW + dt.timedelta(hours=1))
        self.assertIn('end time', self.refused())

    def test_a_term_that_is_not_running(self):
        body = {'groups': {f'{CODE}@2030-31-zima': {'status': 'unchanged', 'plan': '0' * 64, 'at': NOW.isoformat()}}}
        self.offer('alice', status='unchanged', **body)
        self.assertIn('term', self.refused())

    def test_a_symlink_or_a_stray_file(self):
        self.offer('alice')
        tree_files = {'manifest.json': json.dumps({'format': 1, 'version': VERSION, 'login': 'alice', 'seq': 5,
                                                   'ended': NOW.isoformat(), 'groups': {}})}
        self.push_files('alice', dict(tree_files), symlink='timetables')
        self.assertIn('not a plain file', self.refused())
        self.push_files('alice', {**tree_files, 'run.sh': b'echo hi'})
        self.assertIn('not a manifest or a calendar', self.refused())

    def test_a_calendar_the_manifest_does_not_mention(self):
        self.push_files('alice', {'manifest.json': json.dumps({'format': 1, 'version': VERSION, 'login': 'alice',
                                                               'seq': 5, 'ended': NOW.isoformat(), 'groups': {}}),
                                  REL: changed_plan().encode()})
        self.assertIn('disagree', self.refused())

    def test_an_oversized_file(self):
        self.offer('alice', ics=changed_plan() + 'X' * collect.MAX_FILE)
        self.assertIn('too big', self.refused())

    def test_calendars_that_fail_the_gate_are_dropped_one_by_one(self):
        cases = {
            'staff': changed_plan().replace('END:VEVENT', 'CONTACT:Jan Kowalski\r\nEND:VEVENT', 1),
            'other group': changed_plan().replace(f'X-PLAN-GROUP:{CODE}', 'X-PLAN-GROUP:WCY20IT1S0'),
            'shrunk': SOURCE.split('BEGIN:VEVENT')[0] + 'BEGIN:VEVENT' + SOURCE.split('BEGIN:VEVENT')[1]
                      .split('END:VCALENDAR')[0] + 'END:VCALENDAR\r\n',
        }
        for why, ics in cases.items():
            with self.subTest(why):
                self.offer('alice', ics=ics)
                summary = self.collect(self.reg)
                self.assertEqual(summary['changed'], [], why)
                self.assertEqual(self.published(), SOURCE)

    def test_a_calendar_that_does_not_hash_to_its_claim(self):
        self.offer('alice', groups={f'{CODE}@{TID}': {'status': 'changed', 'plan': core.plan_hash(SOURCE),
                                                       'at': NOW.isoformat()}})
        self.assertEqual(self.collect(self.reg)['changed'], [])
        self.assertEqual(self.published(), SOURCE)


class ManageTest(unittest.TestCase):
    """The permissions panel: its git side (unsigned here, signed for real) and its HTTP guards."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.origin = self.tmp / 'origin.git'
        git('init', '-q', '--bare', str(self.origin), cwd=self.tmp)
        self.work = self.tmp / 'work'
        git('init', '-q', str(self.work), cwd=self.tmp)
        git('remote', 'add', 'origin', str(self.origin), cwd=self.work)
        for name, value in (('user.name', 't'), ('user.email', 't@t')):
            git('config', name, value, cwd=self.work)
        self.repo = manage.Repo(self.work, sign=False)

    def registry(self, *volunteers, **rules):
        return {'quorum': 2, 'window_hours': 12, 'min_version': '1.2.0', 'volunteers': list(volunteers), **rules}

    def test_the_first_save_creates_the_branch_and_later_saves_build_on_it(self):
        self.assertIsNone(self.repo.head())
        self.assertEqual(self.repo.registry()['volunteers'], [])
        first = manage.save(self.repo, {'registry': self.registry({'login': 'alice'}), 'base': None})
        self.assertEqual(first['base'], first['commit'])
        self.assertEqual(manage.assign.find(self.repo.registry(), 'alice')['trust'], 'peer')
        second = manage.save(self.repo, {'registry': self.registry({'login': 'alice', 'trust': 'trusted'}),
                                         'base': first['base'], 'note': 'known in person'})
        self.assertIn('alice: zaufany', second['message'])
        parent = git('rev-parse', f'{second["commit"]}^', cwd=self.work).strip()
        self.assertEqual(parent, first['commit'])
        self.assertEqual(git('ls-tree', '--name-only', second['commit'], cwd=self.work).split(), ['volunteers.json'])
        self.assertIn('known in person', git('log', '-1', '--format=%B', second['commit'], cwd=self.work))

    def test_a_stale_page_cannot_overwrite_a_newer_registry(self):
        first = manage.save(self.repo, {'registry': self.registry({'login': 'alice'}), 'base': None})
        manage.save(self.repo, {'registry': self.registry({'login': 'bob'}), 'base': first['base']})
        with self.assertRaises(manage.SaveError) as caught:
            manage.save(self.repo, {'registry': self.registry({'login': 'carol'}), 'base': first['base']})
        self.assertEqual(caught.exception.status, 409)

    def test_an_invalid_or_unchanged_registry_is_not_saved(self):
        with self.assertRaises(manage.SaveError):
            manage.save(self.repo, {'registry': self.registry({'login': 'alice', 'fork': 'mallory/PlanWAT'}), 'base': None})
        first = manage.save(self.repo, {'registry': self.registry({'login': 'alice'}), 'base': None})
        with self.assertRaises(manage.SaveError):
            manage.save(self.repo, {'registry': self.registry({'login': 'alice'}), 'base': first['base']})
        self.assertEqual(self.repo.head(), first['commit'])

    def test_the_summary_names_every_kind_of_change(self):
        old = assign.check_registry(self.registry({'login': 'alice'}, {'login': 'bob', 'trust': 'trusted'}))
        new = assign.check_registry(self.registry({'login': 'alice', 'trust': 'suspended', 'faculties': ['wcy']},
                                                  {'login': 'carol'}, quorum=3))
        text = manage.describe(old, new)
        for part in ('alice: wstrzymany', 'alice: wcy', '+carol (równorzędny)', '-bob', 'kworum 3'):
            self.assertIn(part, text)

    def test_status_comes_from_the_coordinator_state_on_data(self):
        data = self.tmp / 'data'
        git('init', '-q', '-b', 'data', str(data), cwd=self.tmp)
        (data / 'volunteer-state.json').write_text(json.dumps({
            'groups': {'A@t': {'by': ['alice', 'bob']}, 'B@t': {'by': ['alice']}},
            'seen': {'alice': {'ended': '2026-10-20T10:00:00'}},
            'strikes': {'bob': ['2026-10-19T10:00:00']}, 'benched': {'bob': '2026-10-19T10:00:00'}}))
        git('-c', 'user.name=t', '-c', 'user.email=t@t', 'add', '-A', cwd=data)
        git('-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false', 'commit', '-q', '-m', 's', cwd=data)
        git('push', '-q', str(self.origin), 'data', cwd=data)
        self.repo.fetch()
        got = self.repo.status()
        self.assertEqual((got['alice']['accepted'], got['alice']['last']), (2, '2026-10-20T10:00:00'))
        self.assertEqual((got['bob']['strikes'], got['bob']['accepted']), (1, 1))
        self.assertTrue(got['bob']['benched'])

    def serve(self):
        import http.client
        import http.server
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), manage.make_handler(self.repo, 'sekret'))
        threading = __import__('threading')
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        def request(method, path, body=None, headers=None):
            conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
            conn.request(method, path, body=body, headers=headers or {})
            r = conn.getresponse()
            out = (r.status, r.read(), dict(r.getheaders()))
            conn.close()
            return out
        return request

    def test_the_page_answers_only_its_own_token_on_localhost(self):
        request = self.serve()
        status, body, headers = request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn(b'Wolontariusze', body)
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertEqual(request('GET', '/api/state')[0], 403)
        self.assertEqual(request('GET', '/api/state', headers={'X-Token': 'zgadywanka'})[0], 403)
        self.assertEqual(request('GET', '/api/state', headers={'X-Token': 'sekret', 'Host': 'evil.example'})[0], 403)
        status, body, _ = request('GET', '/api/state', headers={'X-Token': 'sekret'})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)['registry']['volunteers'], [])
        save = json.dumps({'registry': self.registry({'login': 'alice'}), 'base': None})
        self.assertEqual(request('POST', '/api/save', save, {'X-Token': 'sekret', 'Content-Type': 'text/plain'})[0], 415)
        self.assertEqual(request('POST', '/api/save', save, {'Content-Type': 'application/json'})[0], 403)
        status, body, _ = request('POST', '/api/save', save, {'X-Token': 'sekret', 'Content-Type': 'application/json'})
        self.assertEqual(status, 200, body)
        self.assertEqual(self.repo.head(), json.loads(body)['commit'])


if __name__ == '__main__':
    unittest.main()
