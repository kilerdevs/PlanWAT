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
import registry as registry_reader  # noqa: E402
import runner  # noqa: E402
import wizard  # noqa: E402
import doctor  # noqa: E402
from unittest import mock  # noqa: E402
import io  # noqa: E402
import urllib.error  # noqa: E402

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


class HealthAwareAssignTest(unittest.TestCase):
    PEERS = [{'login': f'peer{i}', 'trust': 'peer'} for i in range(4)]

    def setUp(self):
        self.window = assign.window_of(NOW)
        self.opens = assign.window_start(self.window)

    def share(self, reg, health, me=None, code=CODE):
        return assign.assignees(reg, 'wcy', code, TID, self.window, health, me)

    def test_offline_volunteers_are_passed_over_and_a_volunteer_always_counts_itself(self):
        reg = registry(*self.PEERS)
        fresh = (self.opens - dt.timedelta(hours=1)).isoformat()
        stale = (self.opens - dt.timedelta(hours=7)).isoformat()
        health = {'peer0': {'ended': fresh}, 'peer1': {'ended': fresh}, 'peer2': {'ended': stale},
                  'peer3': {'ended': stale}}
        for n in range(40):
            self.assertLessEqual(set(self.share(reg, health, code=f'G{n}')), {'peer0', 'peer1'})
        mine = [n for n in range(40) if 'peer2' in self.share(reg, health, me='peer2', code=f'G{n}')]
        self.assertTrue(mine)

    def test_a_new_volunteer_has_a_grace_period_after_it_was_added(self):
        late = dict(self.PEERS[0], added=(self.opens - dt.timedelta(hours=30)).date().isoformat())
        new = dict(self.PEERS[1], added=self.opens.date().isoformat())
        reg = registry(late, new, *self.PEERS[2:])
        fresh = {'peer2': {'ended': self.opens.isoformat()}, 'peer3': {'ended': self.opens.isoformat()}}
        seen = Counter(v for n in range(60) for v in self.share(reg, fresh, code=f'G{n}'))
        self.assertNotIn('peer0', seen)
        self.assertIn('peer1', seen)

    def test_a_blocked_faculty_goes_to_the_others_until_the_block_is_old(self):
        reg = registry(*self.PEERS)
        live = {f'peer{i}': {'ended': self.opens.isoformat()} for i in range(4)}
        live['peer0']['blocked'] = {'wcy': (self.opens - dt.timedelta(hours=1)).isoformat()}
        self.assertFalse(any('peer0' in self.share(reg, live, code=f'G{n}') for n in range(40)))
        live['peer0']['blocked'] = {'wcy': (self.opens - dt.timedelta(hours=7)).isoformat()}
        self.assertTrue(any('peer0' in self.share(reg, live, code=f'G{n}') for n in range(40)))

    def test_nobody_working_falls_back_to_everybody(self):
        reg = registry(*self.PEERS[:2])
        gone = {'peer0': {'ended': '2026-01-01T00:00:00'}, 'peer1': {'ended': '2026-01-01T00:00:00'}}
        self.assertEqual(len(self.share(reg, gone)), 2)

    def test_the_registry_checks_the_added_date(self):
        with self.assertRaises(assign.RegistryError):
            registry({'login': 'bob', 'added': 'yesterday'})


class LineStateTest(unittest.TestCase):
    def test_a_volunteer_keeps_its_own_line_learning_and_ignores_the_home_runners(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        (tmp / core.STATE_FILE).write_text(json.dumps({'version': 1, 'groups': {}, 'faculties': {'wcy': {'last_ok': 'home'}},
                                                        'blocks': {'wcy': {'durations': [999]}}, 'pacing': {'wcy': 3.0}}))
        state = core.State(tmp / core.STATE_FILE)
        refresh.load_line_state(state, tmp / 'mine.json')
        self.assertEqual((state.faculties, state.data['blocks'], state.data['pacing']), ({}, {}, {}))
        state.data['pacing']['wcy'] = 1.5
        refresh.save_line_state(state, tmp / 'mine.json')
        again = core.State(tmp / core.STATE_FILE)
        refresh.load_line_state(again, tmp / 'mine.json')
        self.assertEqual(again.data['pacing'], {'wcy': 1.5})


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
        # The forks here are local paths, a transport the coordinator refuses for real forks.
        protocols, collect.PROTOCOLS = collect.PROTOCOLS, ('https', 'file')
        self.addCleanup(setattr, collect, 'PROTOCOLS', protocols)
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


class StaleVoteTest(Harness):
    PEERS = ({'login': 'bob', 'trust': 'peer'}, {'login': 'carol', 'trust': 'peer'}, {'login': 'dave', 'trust': 'peer'})

    def home_checked(self, moment):
        (self.data / core.STATE_FILE).write_text(json.dumps(
            {'version': 1, 'faculties': {}, 'groups': {CODE: {'term': TID, 'checked': moment.isoformat()}}}))

    def test_votes_older_than_a_home_runner_check_never_overwrite_it(self):
        reg = registry(*self.PEERS)
        self.offer('bob', ended=NOW)
        self.collect(reg, NOW)
        self.home_checked(NOW + dt.timedelta(minutes=30))  # the home runner looked again after bob's crawl
        self.offer('carol', ended=NOW + dt.timedelta(minutes=10))
        later = NOW + dt.timedelta(minutes=40)
        self.assertEqual(self.collect(reg, later)['changed'], [])
        self.assertEqual(self.published(), SOURCE)
        self.assertEqual(self.state()['strikes'], {})
        self.assertNotIn(f'{CODE}@{TID}', self.state()['votes'])

    def test_a_vote_from_before_the_plan_changed_is_not_a_strike(self):
        reg = registry(*self.PEERS)
        self.offer('dave', ics=changed_plan('old'), ended=NOW)  # saw the page before the faculty changed it
        self.offer('bob', ended=NOW + dt.timedelta(hours=1))
        self.offer('carol', ended=NOW + dt.timedelta(hours=1))
        self.assertEqual(self.collect(reg, NOW + dt.timedelta(hours=1))['changed'], [f'{CODE}@{TID}'])
        self.assertEqual(self.state()['strikes'], {})

    def test_a_loser_while_the_winner_was_seen_is_struck_and_a_newer_vote_waits(self):
        reg = registry(*self.PEERS, {'login': 'erin', 'trust': 'peer'})
        self.offer('bob', ended=NOW)
        self.offer('dave', ics=changed_plan('other'), ended=NOW + dt.timedelta(minutes=5))
        self.offer('carol', ended=NOW + dt.timedelta(minutes=10))
        self.offer('erin', ics=changed_plan('next'), ended=NOW + dt.timedelta(minutes=20))
        self.collect(reg, NOW + dt.timedelta(minutes=21))
        state = self.state()
        self.assertEqual(list(state['strikes']), ['dave'])
        self.assertEqual(list(state['votes'][f'{CODE}@{TID}'].values())[0]['voters'], {'erin': '2026-10-20T12:20:00'})


class HealthTest(Harness):
    def test_a_refused_bundle_is_remembered_and_its_author_told_why(self):
        reg = registry({'login': 'bob', 'trust': 'peer'})
        self.offer('bob', login='mallory')
        self.assertIn('bob', self.collect(reg)['refused'])
        self.assertIn('signed', self.state()['volunteers']['bob']['refused']['reason'])
        again = self.collect(reg)
        self.assertEqual((again['refused'], again['rows'][0]['result']), ({}, 'same'))
        self.offer('bob', ended=NOW + dt.timedelta(minutes=1))
        self.assertEqual(self.collect(reg, NOW + dt.timedelta(minutes=2))['read'], ['bob'])
        self.assertNotIn('refused', self.state()['volunteers']['bob'])

    def test_blocks_token_expiry_and_counts_are_published(self):
        reg = registry({'login': 'alice', 'trust': 'trusted'})
        self.offer('alice', token_expires='2026-11-01', faculties={'wcy': {'blocked': True}, 'wim': {'blocked': False}})
        summary = self.collect(reg)
        record = self.state()['volunteers']['alice']
        self.assertEqual(record['blocked'], {'wcy': NOW.isoformat()})
        self.assertEqual(record['token_expires'], '2026-11-01')
        self.assertEqual(record['days'], {'2026-10-20': [1, 0, 1]})
        table = collect.summary_table(summary, NOW, False)
        self.assertIn('alice (trusted)', table)
        self.assertIn('wygasa 2026-11-01', table)
        self.offer('alice', ended=NOW + dt.timedelta(minutes=5), faculties={'wcy': {'blocked': False}})
        self.collect(reg, NOW + dt.timedelta(minutes=6))
        self.assertEqual(self.state()['volunteers']['alice']['blocked'], {})

    def test_a_fork_serving_a_huge_pack_is_cut_off(self):
        reg = registry({'login': 'bob', 'trust': 'peer'})
        limit, collect.FETCH_LIMIT = collect.FETCH_LIMIT, 64 * 1024
        self.addCleanup(setattr, collect, 'FETCH_LIMIT', limit)
        self.push_files('bob', {'manifest.json': '{}', f'timetables/{TID}/HUGE.ics': os.urandom(400 * 1024)})
        self.assertIn('grew past', self.collect(reg)['refused']['bob'])

    def test_a_fork_on_another_transport_is_never_contacted(self):
        collect.PROTOCOLS = ('https',)
        self.offer('bob')
        self.assertEqual(collect.gather(self.remote('bob'), {})[0], 'none')


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


class RegistryReaderTest(unittest.TestCase):
    SHA = 'a' * 40
    GOOD = json.dumps({'quorum': 2, 'volunteers': [{'login': 'alice', 'trust': 'trusted'}]}).encode()

    def fake(self, verified=True, committer='kilerdevs', head=200, raw=None):
        asked = []

        def get(url, token=None):
            asked.append(url)
            if url.startswith(registry_reader.API):
                body = {'sha': self.SHA, 'commit': {'verification': {'verified': verified}},
                        'committer': {'login': committer}}
                return head, json.dumps(body).encode()
            return 200, self.GOOD if raw is None else raw
        return get, asked

    def test_a_verified_commit_by_an_editor_is_read_at_that_commit(self):
        get, asked = self.fake(committer='KilerDevs')
        reg, _, sha, who = registry_reader.fetch_verified('kilerdevs/PlanWAT', 'kilerdevs', get=get)
        self.assertEqual((reg['volunteers'][0]['login'], sha, who), ('alice', self.SHA, 'kilerdevs'))
        self.assertEqual(asked[1], f'{registry_reader.RAW}/kilerdevs/PlanWAT/{self.SHA}/volunteers.json')

    def test_unsigned_or_foreign_commits_and_bad_files_are_refused(self):
        for get in (self.fake(verified=False)[0], self.fake(committer='mallory')[0], self.fake(raw=b'{"quorum": 1}')[0]):
            with self.assertRaises(assign.RegistryError):
                registry_reader.fetch_verified('kilerdevs/PlanWAT', 'kilerdevs', get=get)

    def test_a_rejected_token_falls_back_to_reading_anonymously(self):
        good, _ = self.fake()
        seen = []

        def get(url, token=None):
            seen.append(token)
            return (401, b'') if token else good(url, token)
        reg, _, _, _ = registry_reader.fetch_verified('kilerdevs/PlanWAT', 'kilerdevs', token='github_pat_old', get=get)
        self.assertEqual((reg['volunteers'][0]['login'], seen[:2]), ('alice', ['github_pat_old', None]))

    def test_a_missing_branch_and_an_outage_are_told_apart(self):
        with self.assertRaises(registry_reader.Missing):
            registry_reader.fetch_verified('kilerdevs/PlanWAT', 'kilerdevs', get=self.fake(head=404)[0])
        with self.assertRaises(registry_reader.Unavailable):
            registry_reader.fetch_verified('kilerdevs/PlanWAT', 'kilerdevs', get=self.fake(head=503)[0])


class FakeResponse(io.BytesIO):
    def __init__(self, body, headers=None, status=200):
        super().__init__(json.dumps(body).encode())
        self.headers, self.status = headers or {}, status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TokenTest(unittest.TestCase):
    def opener(self, body=None, headers=None, error=None):
        def open_(req, timeout=None):
            if error:
                raise urllib.error.HTTPError(req.full_url, error, 'x', {}, None)
            return FakeResponse(body or {'permissions': {'push': True}}, headers)
        return open_

    def test_a_classic_token_is_refused_without_asking_github(self):
        problem, _ = bundle.token_report('alice/PlanWAT', 'ghp_abc', opener=None)
        self.assertIn('classic', problem)

    def test_a_working_token_reports_its_expiry(self):
        hdr = {'github-authentication-token-expiration': '2026-11-01 12:00:00 UTC'}
        self.assertEqual(bundle.token_report('alice/PlanWAT', 'github_pat_x', self.opener(headers=hdr)),
                         ('', '2026-11-01T12:00:00'))

    def test_no_push_rights_an_unseen_fork_and_a_dead_token_are_explained(self):
        self.assertIn('Contents', bundle.token_report('a/P', 'github_pat_x', self.opener({'permissions': {'push': False}}))[0])
        self.assertIn('cannot see', bundle.token_report('a/P', 'github_pat_x', self.opener(error=404))[0])
        self.assertIn('expired', bundle.token_report('a/P', 'github_pat_x', self.opener(error=401))[0])


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.cfg = runner.config({'PLANWAT_LOGIN': 'alice', 'PLANWAT_FORK_TOKEN': 'github_pat_x',
                                  'PLANWAT_WORK': str(self.tmp)})
        self.status = runner.Status(self.tmp)
        for name, value in (('measure_offset', lambda: 0.0),):
            patcher = mock.patch.object(runner, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def with_registry(self, *volunteers, min_version='0.0.1'):
        reg = registry(*volunteers, min_version=min_version)
        raw = json.dumps({'quorum': 2, 'min_version': min_version, 'volunteers': list(volunteers)}).encode()
        patcher = mock.patch.object(runner.registry, 'fetch_verified', lambda *a, **k: (reg, raw, 'b' * 40, 'kilerdevs'))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_somebody_not_registered_waits_and_is_shown_the_application(self):
        self.with_registry({'login': 'bob'})
        self.assertEqual(runner.run_pass(self.cfg, self.status), runner.POLL)
        self.assertEqual(self.status.data['state'], 'not_registered')
        self.assertIn('issues/new', self.status.data['join'])

    def test_an_outdated_crawler_does_not_crawl(self):
        self.with_registry({'login': 'alice'}, min_version='99.0.0')
        self.assertEqual(runner.run_pass(self.cfg, self.status), runner.POLL)
        self.assertEqual(self.status.data['state'], 'update_needed')

    def test_a_benched_volunteer_does_not_crawl_and_the_verdict_is_logged(self):
        self.with_registry({'login': 'alice'})
        data = self.tmp / 'data'
        data.mkdir()
        (data / core.VOLUNTEER_STATE_FILE).write_text(json.dumps({'benched': {'Alice': NOW.isoformat()}, 'volunteers': {
            'alice': {'read': 'x', 'ended': 'y', 'last': {'votes': 3, 'rejected': 1, 'reasons': ['lost too many events']},
                      'days': {'2026-10-20': [3, 1, 2]}, 'token_expires': '2000-01-01T00:00:00'}}}))
        with mock.patch.object(runner, 'sync_data', lambda *a: data):
            self.assertEqual(runner.run_pass(self.cfg, self.status), runner.POLL)
        self.assertEqual(self.status.data['state'], 'benched')
        self.assertIn('2 accepted in 7 days', runner.describe_verdict(runner.verdict(
            json.loads((data / core.VOLUNTEER_STATE_FILE).read_text()), 'alice')[0]))

    def test_one_pass_per_window_starting_a_little_after_it_opens(self):
        window = assign.window_of(NOW)
        self.assertEqual(runner.next_wait(NOW, None), 0)
        self.assertEqual(runner.next_wait(NOW, window - 1), 0)
        pause = runner.next_wait(NOW, window)
        opens = assign.window_start(window + 1)
        self.assertTrue((opens - NOW).total_seconds() + 300 <= pause <= (opens - NOW).total_seconds() + 2100)

    def test_the_health_check_follows_the_status_file(self):
        self.assertEqual(runner.health(self.cfg), 1)
        self.status.set(state='done')
        self.assertEqual(runner.health(self.cfg), 0)
        self.assertEqual(runner.health(self.cfg, core.now_utc() + dt.timedelta(hours=4)), 1)

    def test_a_skewed_clock_is_corrected_for_the_whole_pass(self):
        warnings = []
        with mock.patch.dict(os.environ, {}):
            runner.set_clock(600.0, warnings)
            self.assertEqual(os.environ['PLANWAT_CLOCK_OFFSET'], '600')
            skew = core.now_utc() - dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
            self.assertAlmostEqual(skew.total_seconds(), 600, delta=2)
            runner.set_clock(5.0, warnings)
            self.assertEqual(os.environ['PLANWAT_CLOCK_OFFSET'], '0')
        self.assertEqual(len(warnings), 1)

    def test_the_data_clone_is_fetched_incrementally(self):
        upstream = self.tmp / 'up'
        upstream.mkdir()
        git('init', '-q', '-b', 'data', cwd=upstream)
        (upstream / 'a').write_text('1')
        git('-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false', 'add', '-A', cwd=upstream)
        git('-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false', 'commit', '-qm', '1', cwd=upstream)
        with mock.patch.object(runner, 'git', lambda *a, cwd=None, timeout=600: runner.subprocess.run(
                ['git', *[str(upstream) if str(x).startswith('https://github.com/') else x for x in a]], cwd=cwd,
                check=True, capture_output=True, text=True).stdout):
            data = runner.sync_data(self.tmp, 'x/y', 1)
            (data / 'stray').write_text('left behind by a crawl')
            (upstream / 'a').write_text('2')
            git('-c', 'user.name=t', '-c', 'user.email=t@t', '-c', 'commit.gpgsign=false', 'commit', '-qam', '2', cwd=upstream)
            runner.sync_data(self.tmp, 'x/y', 10)
        self.assertEqual((data / 'a').read_text(), '2')
        self.assertFalse((data / 'stray').exists())


class WizardTest(unittest.TestCase):
    def test_env_updates_keep_every_other_line(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        env = tmp / '.env'
        env.write_text('# mine\nPLANWAT_CRAWLER_IMAGE=ghcr.io/x@sha256:abc\nPLANWAT_LOGIN=old\n# PLANWAT_FORK=x/y\n')
        wizard.write_env(env, {'PLANWAT_LOGIN': 'alice', 'PLANWAT_FORK': 'alice/Fork', 'PLANWAT_FORK_TOKEN': 'github_pat_x',
                               'PLANWAT_AUTO_UPDATE': None})
        text = env.read_text()
        self.assertEqual(text, '# mine\nPLANWAT_CRAWLER_IMAGE=ghcr.io/x@sha256:abc\nPLANWAT_LOGIN=alice\n'
                               'PLANWAT_FORK=alice/Fork\nPLANWAT_FORK_TOKEN=github_pat_x\n')
        self.assertEqual(env.stat().st_mode & 0o777, 0o600)

    def test_a_non_interactive_setup_writes_env_from_flags(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        out = io.StringIO()
        with mock.patch('sys.stdout', out):
            code = wizard.main(['--env', str(tmp / '.env'), '--login', 'alice', '--token', 'github_pat_x',
                                '--faculties', '', '--auto-update', 'off', '--skip-github-checks', '--non-interactive'])
        self.assertEqual(code, 0)
        self.assertEqual(wizard.read_env(tmp / '.env')[1],
                         {'PLANWAT_LOGIN': 'alice', 'PLANWAT_FORK_TOKEN': 'github_pat_x', 'PLANWAT_AUTO_UPDATE': '0'})

    def test_a_classic_token_is_refused_by_the_wizard(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        with mock.patch('sys.stdout', io.StringIO()), self.assertRaises(SystemExit):
            wizard.main(['--env', str(tmp / '.env'), '--login', 'alice', '--token', 'ghp_x', '--faculties', '',
                         '--auto-update', 'on', '--skip-github-checks', '--non-interactive'])

    def test_the_links_are_prefilled(self):
        self.assertIn('target_name=alice', wizard.token_url('alice', 'alice/PlanWAT'))
        self.assertIn('contents=write', wizard.token_url('alice', 'alice/PlanWAT'))
        url = wizard.issue_url('kilerdevs/PlanWAT', 'alice/PlanWAT', ['wcy'])
        self.assertIn('template=volunteer.yml', url)
        self.assertIn('fork=alice%2FPlanWAT', url)

    def test_faculty_answers_are_classified(self):
        self.assertEqual(doctor.classify(200, '<html>WAT</html>'), 'ok')
        self.assertEqual(doctor.classify(404, ''), 'ok')
        self.assertEqual(doctor.classify(200, 'Request unsuccessful. Incapsula incident ID: 1'), 'blocked')
        self.assertEqual(doctor.classify(403, ''), 'blocked')
        self.assertEqual(doctor.classify(None, ''), 'down')
        self.assertEqual(set(doctor.faculty_hosts()), {'wlo', 'wel', 'wim', 'ioe', 'wcy', 'wml', 'wtc'})

    def test_the_offline_doctor_runs_without_a_network(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        report = doctor.Report(io.StringIO())
        doctor.run(runner.config({'PLANWAT_LOGIN': 'alice', 'PLANWAT_FORK_TOKEN': 'ghp_x', 'PLANWAT_WORK': str(tmp)}),
                   report, offline=True)
        self.assertEqual(report.failed, 1)  # the classic token


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
