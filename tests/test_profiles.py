"""Tests for profiles.py: the numbers behind "Mapa planów" (plan features, load, map, archetypes)."""
import datetime as dt
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import profiles  # noqa: E402

MONDAY = dt.date(2026, 10, 5)


def lesson(week, weekday, start, end, summary='Matematyka', category='Wykład', room='314 S'):
    return (MONDAY + dt.timedelta(days=7 * week + weekday), start, end, summary, category, room)


def plan(weeks=6, days=(0, 1, 2), start=8 * 60, blocks=2, gap=0, category='Wykład', room='314 S'):
    out = []
    for w in range(weeks):
        for d in days:
            t = start
            for b in range(blocks):
                out.append(lesson(w, d, t, t + 95, f'Przedmiot {b}', category, room))
                t += 95 + gap
    return out


class BuildingOf(unittest.TestCase):
    def test_reads_the_building_from_a_room(self):
        self.assertEqual(profiles.building_of('308 S'), 'S')
        self.assertEqual(profiles.building_of('0.24/ 135'), '135')
        self.assertEqual(profiles.building_of('1.9/ 16;1.10/ 16'), '16')
        self.assertEqual(profiles.building_of('Teams'), '')
        self.assertEqual(profiles.building_of(''), '')


class WeekFeatures(unittest.TestCase):
    def feature(self, lessons, key):
        return profiles.week_features(lessons)[profiles.KEYS.index(key)]

    def test_too_few_lessons_say_nothing(self):
        self.assertIsNone(profiles.week_features(plan(weeks=1, days=(0,), blocks=2)))

    def test_hours_days_and_gaps_are_per_teaching_week(self):
        p = plan(weeks=5, days=(0, 2), blocks=2, gap=120)
        self.assertAlmostEqual(self.feature(p, 'hours'), 2 * 2 * 95 / 60)
        self.assertEqual(self.feature(p, 'days'), 2)
        self.assertEqual(self.feature(p, 'gaps'), 2 * 120)
        self.assertEqual(self.feature(p, 'longgaps'), 2)

    def test_day_length_marathons_early_starts_and_weekends(self):
        long = plan(weeks=4, days=(0, 5), start=8 * 60, blocks=6)   # 8:00 to 17:30, Saturdays too
        self.assertEqual(self.feature(long, 'marathon'), 2)
        self.assertEqual(self.feature(long, 'early'), 1.0)
        self.assertEqual(self.feature(long, 'weekend'), 0.5)
        late = plan(weeks=4, days=(0, 1), start=17 * 60, blocks=2)
        self.assertEqual(self.feature(late, 'early'), 0.0)
        self.assertEqual(self.feature(late, 'late'), 1.0)

    def test_a_stray_lesson_is_not_a_teaching_week(self):
        p = plan(weeks=4, days=(0, 1), blocks=2) + [lesson(9, 2, 8 * 60, 8 * 60 + 95)]
        self.assertAlmostEqual(self.feature(p, 'days'), 2)

    def test_building_changes_and_room_habits(self):
        p = []
        for w in range(5):
            p.append(lesson(w, 0, 480, 575, 'A', 'Wykład', '314 S'))
            p.append(lesson(w, 0, 590, 685, 'B', 'Ćwiczenia', '12 65'))
            p.append(lesson(w, 0, 700, 795, 'C', 'Wykład', '12 65'))
        self.assertEqual(self.feature(p, 'moves'), 1)
        self.assertAlmostEqual(self.feature(p, 'practice'), 1 / 3)
        self.assertEqual(self.feature(p, 'fixed'), 1.0)
        self.assertEqual(self.feature(p, 'subjects'), 3)


class Statistics(unittest.TestCase):
    def test_standardize_centres_and_scales_and_tolerates_a_constant_column(self):
        rows = [[1.0] * len(profiles.KEYS), [3.0] * len(profiles.KEYS)]
        rows[0][0], rows[1][0] = 1.0, 3.0
        for r in rows:
            r[1] = 5.0
        z, means, stds = profiles.standardize(rows)
        self.assertEqual(means[0], 2.0)
        self.assertAlmostEqual(z[0][0], -1.0)
        self.assertEqual(z[0][1], 0.0)

    def test_percentiles_count_the_strictly_lower(self):
        self.assertEqual(profiles.percentiles([5, 1, 3]), [100, 0, 50])
        self.assertEqual(profiles.percentiles([2, 2, 2]), [0, 0, 0])
        self.assertEqual(profiles.percentiles([7]), [0])

    def test_jacobi_finds_the_eigenvalues_of_a_symmetric_matrix(self):
        values, _ = profiles._jacobi([[2.0, 1.0], [1.0, 2.0]])
        self.assertAlmostEqual(sorted(values)[0], 1.0)
        self.assertAlmostEqual(sorted(values)[1], 3.0)

    def test_kmeans_separates_two_obvious_groups_the_same_way_every_time(self):
        rng = random.Random(3)
        rows = [[rng.gauss(0, 0.1)] * 2 for _ in range(15)] + [[rng.gauss(5, 0.1)] * 2 for _ in range(15)]
        a, _ = profiles.kmeans(rows, k=2)
        b, _ = profiles.kmeans(rows, k=2)
        self.assertEqual(a, b)
        self.assertEqual(len(set(a[:15])), 1)
        self.assertEqual(len(set(a[15:])), 1)
        self.assertNotEqual(a[0], a[15])


class Build(unittest.TestCase):
    def per_group(self):
        rng = random.Random(11)
        out = {}
        for i in range(40):
            heavy = i % 2
            out[f'WCY26A{i:02d}1S1'] = plan(weeks=6, days=(0, 1, 2, 3, 4) if heavy else (0, 2),
                                            start=(8 if heavy else 11) * 60, blocks=5 if heavy else 2,
                                            gap=rng.choice((0, 100)) if heavy else 0, room=f'{300 + i} S')
        out['WCY26TINY1S1'] = plan(weeks=1, days=(0,), blocks=1)
        return out

    def test_a_profile_file_has_the_documented_shape(self):
        data = profiles.build(self.per_group(), lambda g: g[:3], '2026-10-15')
        self.assertEqual(data['asof'], '2026-10-15')
        self.assertEqual([f['key'] for f in data['features']], profiles.KEYS)
        self.assertEqual(len(data['groups']), 40)          # the plan with one lesson is left out
        self.assertNotIn('WCY26TINY1S1', [r[0] for r in data['groups']])
        for r in data['groups']:
            self.assertEqual(len(r), 7 + len(profiles.KEYS))
            self.assertTrue(0 <= r[2] <= 1000 and 0 <= r[3] <= 1000 and 0 <= r[4] <= 100)
            self.assertTrue(0 <= r[5] < len(data['archetypes']))
        self.assertEqual(sum(a['n'] for a in data['archetypes']), 40)

    def test_every_number_comes_with_its_definition_unit_and_average(self):
        data = profiles.build(self.per_group(), lambda g: 'WCY', None)
        self.assertEqual(len(data['features']), len(profiles.KEYS))
        for f in data['features']:
            self.assertTrue(f['name'] and f['def'].endswith('.'), f['key'])
            self.assertIn(f['unit'], ('h', 'min', 'n', 'pct'))
            self.assertIsInstance(f['mean'], float)
            self.assertGreaterEqual(f['std'], 0)
        self.assertEqual([f['w'] > 0 for f in data['features']].count(True), 11)  # fixed rooms and practice share only describe
        for a in data['archetypes']:
            self.assertEqual(len(a['typical']), 4)
            self.assertTrue(all(isinstance(x, float) for x in a['typical']))
        # a plan's real value is mean + z * std: the hours of a known plan come back
        raw = profiles.week_features(self.per_group()['WCY26A011S1'])
        row = next(r for r in data['groups'] if r[0] == 'WCY26A011S1')
        hours = data['features'][0]
        self.assertAlmostEqual(hours['mean'] + row[7] / 100 * hours['std'], raw[0], delta=0.2)

    def test_heavier_weeks_get_a_higher_coefficient_and_sit_to_the_right(self):
        data = profiles.build(self.per_group(), lambda g: 'WCY', None)
        rows = {r[0]: r for r in data['groups']}
        heavy = [rows[g] for g in rows if int(g[6:8]) % 2]
        light = [rows[g] for g in rows if not int(g[6:8]) % 2]
        self.assertGreater(min(r[4] for r in heavy), max(r[4] for r in light))
        self.assertGreater(sum(r[2] for r in heavy) / len(heavy), sum(r[2] for r in light) / len(light))

    def test_the_same_calendars_give_the_same_file(self):
        a = profiles.build(self.per_group(), lambda g: 'WCY', None)
        b = profiles.build(self.per_group(), lambda g: 'WCY', None)
        self.assertEqual(a, b)

    def test_too_few_plans_to_compare_gives_nothing(self):
        few = dict(list(self.per_group().items())[:5])
        self.assertIsNone(profiles.build(few, lambda g: 'WCY', None))

    def test_archetypes_are_named_after_their_strongest_traits_and_numbered_light_to_heavy(self):
        data = profiles.build(self.per_group(), lambda g: 'WCY', None)
        names = [a['name'] for a in data['archetypes']]
        self.assertEqual(len(set(names)), len(names))
        self.assertTrue(all(names))
        self.assertEqual(profiles.name_archetype([0.0] * len(profiles.KEYS)), 'przeciętny rozkład')
        c = [0.0] * len(profiles.KEYS)
        c[profiles.KEYS.index('gaps')] = 1.2
        c[profiles.KEYS.index('early')] = -0.9
        self.assertEqual(profiles.name_archetype(c), 'dużo okienek · późne starty')


if __name__ == '__main__':
    unittest.main()
