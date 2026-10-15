"""Plan profiles: what a group's week looks like, and how it compares with every other group's.

Built next to the site from the same calendars (see build.build_data), written to data/profiles.json and read by the
group page's "Mapa planów". Everything here is plain arithmetic on the published lessons, nothing is trained or fitted
to anything but those plans:

  features    13 numbers per group, averaged over the weeks that have classes (hours, gaps, day length, ...)
  z-scores    each feature against all groups; the page ranks, explains and searches with them
  load        a weighted sum of the z-scores that read as "heavier", as a percentile among the groups
  map         the first two principal components of the z-scores, so similar weeks lie close together
  archetypes  k-means on the z-scores, each named after the traits that set its centre apart

Deterministic: the same calendars give the same file (a fixed seed, ties broken by order).
"""
import math
import random
import re
from collections import Counter

MIN_LESSONS = 8       # a plan with fewer lessons says nothing about a week
LONG_GAP = 90         # minutes: a gap this long is "a long window"
MARATHON = 8 * 60     # minutes from first start to last end: a "marathon" day
EARLY = 9 * 60        # a day starting before this is an early start
LATE = 18 * 60        # a day ending after this ends late
K = 8                 # archetypes
SEED = 20260915

# key, what a high value is called, what a low one is called, weight in the load (0: describes, does not weigh),
# unit the page shows it in (h, min, n, pct), definition
FEATURES = [
    ('hours',    'dużo zajęć',               'mało zajęć',               1.0, 'h',
     'Suma godzin zajęć w typowym tygodniu.'),
    ('days',     'zajęcia prawie codziennie', 'mało dni na uczelni',     0.4, 'n',
     'Ile dni w tygodniu masz zajęcia.'),
    ('gaps',     'dużo okienek',             'prawie bez okienek',       0.8, 'min',
     'Suma przerw między zajęciami tego samego dnia (okienek), na tydzień.'),
    ('longgaps', 'częste długie okienka',    'bez długich okienek',      0.7, 'n',
     'Ile razy w tygodniu przerwa między zajęciami trwa co najmniej 90 minut.'),
    ('span',     'długie dni na uczelni',    'krótkie dni na uczelni',   1.0, 'min',
     'Średnia długość dnia: od początku pierwszych do końca ostatnich zajęć.'),
    ('marathon', 'dni-maratony',             'bez dni-maratonów',        0.8, 'n',
     'Ile dni w tygodniu trwa co najmniej 8 godzin od pierwszych do ostatnich zajęć.'),
    ('early',    'wczesne starty',           'późne starty',             0.8, 'pct',
     'Jaka część dni z zajęciami zaczyna się przed 9:00.'),
    ('late',     'zajęcia do wieczora',      'wcześnie po zajęciach',    0.6, 'pct',
     'Jaka część dni z zajęciami kończy się po 18:00.'),
    ('weekend',  'zajęcia w weekendy',       'bez weekendów',            0.6, 'pct',
     'Jaka część dni z zajęciami przypada na sobotę lub niedzielę.'),
    ('moves',    'częste zmiany budynków',   'jeden budynek dziennie',   0.5, 'n',
     'Ile razy w tygodniu przechodzisz między budynkami w ciągu dnia.'),
    ('fixed',    'zajęcia w stałych salach', 'zajęcia w wielu salach',   0.0, 'pct',
     'Jaka część zajęć odbywa się w trzech najczęstszych salach grupy. Nie waży we współczynniku.'),
    ('practice', 'dużo ćwiczeń i laboratoriów', 'głównie wykłady',       0.0, 'pct',
     'Jaki udział mają ćwiczenia, laboratoria, projekty i seminaria wśród zajęć. Nie waży we współczynniku.'),
    ('subjects', 'wiele przedmiotów',        'mało przedmiotów',         0.3, 'n',
     'Ile różnych przedmiotów ma grupa w semestrze.'),
]
KEYS = [f[0] for f in FEATURES]
NAMES = {  # the noun each feature is listed under on the page
    'hours': 'Godziny zajęć', 'days': 'Dni na uczelni', 'gaps': 'Okienka', 'longgaps': 'Długie okienka',
    'span': 'Długość dnia', 'marathon': 'Dni-maratony', 'early': 'Wczesne starty', 'late': 'Zajęcia wieczorem',
    'weekend': 'Weekendy', 'moves': 'Zmiany budynków', 'fixed': 'Stałe sale', 'practice': 'Ćwiczenia i laboratoria',
    'subjects': 'Przedmioty',
}

_PRACTICE = re.compile(r'ćwicz|laborat|projekt|seminar|lektorat', re.I)


def building_of(location):
    """The building of a room text: "308 S" -> "S", "0.24/ 135" -> "135", "Teams" -> ''. Only the first room counts."""
    first = (location or '').split(';')[0].strip()
    if not first:
        return ''
    tokens = first.split()
    head = tokens[0]
    if '/' in head and not head.endswith('/'):
        return head.split('/', 1)[1].strip('/. ').upper()
    if '/' in first:
        tail = first.rsplit('/', 1)[1].strip()
        return tail.split()[0].upper() if tail else ''
    if len(tokens) >= 2 and re.fullmatch(r'[A-Za-zĄĆĘŁŃÓŚŹŻ]{1,3}|\d{1,3}[A-Za-z]?', tokens[1]):
        return tokens[1].upper()
    return ''


def week_features(lessons):
    """The 13 raw features of one group from its lessons ((date, start, end, summary, category, location) tuples),
    averaged over the weeks that have classes, or None when there are too few lessons to say anything."""
    lessons = [l for l in lessons if l[2] > l[1]]
    if len(lessons) < MIN_LESSONS:
        return None
    by_day = {}
    for l in lessons:
        by_day.setdefault(l[0], []).append(l)
    weeks = {}
    for day, items in by_day.items():
        iso = day.isocalendar()
        weeks.setdefault((iso[0], iso[1]), []).append((day, sorted(items, key=lambda x: (x[1], x[2]))))
    totals = Counter()
    n_weeks = 0
    for days in weeks.values():
        if sum(len(items) for _, items in days) < 3:
            continue  # a stray lesson (an exam, a make-up) is not a teaching week
        n_weeks += 1
        spans = []
        for day, items in days:
            first, last = items[0][1], max(x[2] for x in items)
            span = last - first
            spans.append(span)
            totals['hours'] += sum(x[2] - x[1] for x in items) / 60
            totals['days'] += 1
            totals['marathon'] += span >= MARATHON
            totals['early'] += first < EARLY
            totals['late'] += last > LATE
            totals['weekend'] += day.weekday() >= 5
            for prev, nxt in zip(items, items[1:]):
                gap = nxt[1] - prev[2]
                if gap > 0:
                    totals['gaps'] += gap
                    totals['longgaps'] += gap >= LONG_GAP
                a, b = building_of(prev[5]), building_of(nxt[5])
                totals['moves'] += bool(a and b and a != b)
        totals['span'] += sum(spans) / len(spans)
    if not n_weeks:
        return None
    day_total = totals['days'] or 1
    rooms = Counter(r for l in lessons for r in [(l[5] or '').split(';')[0].strip()] if r)
    top = sum(c for _, c in rooms.most_common(3))
    return [
        totals['hours'] / n_weeks,
        totals['days'] / n_weeks,
        totals['gaps'] / n_weeks,
        totals['longgaps'] / n_weeks,
        totals['span'] / n_weeks,
        totals['marathon'] / n_weeks,
        totals['early'] / day_total,
        totals['late'] / day_total,
        totals['weekend'] / day_total,
        totals['moves'] / n_weeks,
        top / sum(rooms.values()) if rooms else 0.0,
        sum(1 for l in lessons if _PRACTICE.search(l[4] or '')) / len(lessons),
        len({l[3] for l in lessons}),
    ]


def standardize(rows):
    """(z-scores, means, stds): each column against all rows; a column that never varies is all zeros."""
    n = len(rows)
    means = [sum(r[j] for r in rows) / n for j in range(len(KEYS))]
    stds = [math.sqrt(sum((r[j] - means[j]) ** 2 for r in rows) / n) for j in range(len(KEYS))]
    z = [[(r[j] - means[j]) / stds[j] if stds[j] > 1e-9 else 0.0 for j in range(len(KEYS))] for r in rows]
    return z, means, stds


def load_scores(z):
    """One number per row: the weighted z-scores of the traits that make a week heavier."""
    weights = [f[3] for f in FEATURES]
    total = sum(weights)
    return [sum(w * v for w, v in zip(weights, row)) / total for row in z]


def percentiles(values):
    """For each value, the share (0-100) of the other values that are strictly lower."""
    order = sorted(values)
    n = len(values)
    if n < 2:
        return [0 for _ in values]
    import bisect
    return [round(100 * bisect.bisect_left(order, v) / (n - 1)) for v in values]


def _jacobi(matrix, sweeps=60):
    """Eigenvalues and eigenvectors (as columns) of a small symmetric matrix by Jacobi rotations."""
    n = len(matrix)
    a = [row[:] for row in matrix]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(sweeps):
        off = sum(a[i][j] ** 2 for i in range(n) for j in range(i + 1, n))
        if off < 1e-18:
            break
        for p in range(n):
            for q in range(p + 1, n):
                if abs(a[p][q]) < 1e-15:
                    continue
                theta = (a[q][q] - a[p][p]) / (2 * a[p][q])
                t = (1 if theta >= 0 else -1) / (abs(theta) + math.sqrt(theta * theta + 1))
                c = 1 / math.sqrt(t * t + 1)
                s = t * c
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p], a[k][q] = c * akp - s * akq, s * akp + c * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k], a[q][k] = c * apk - s * aqk, s * apk + c * aqk
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p], v[k][q] = c * vkp - s * vkq, s * vkp + c * vkq
    return [a[i][i] for i in range(n)], v


def project(z, load):
    """The first two principal components of the z-scores, each scaled to 0..1, with x turned so that it rises with
    the load (light weeks left, heavy right)."""
    n, m = len(z), len(KEYS)
    cov = [[sum(row[i] * row[j] for row in z) / n for j in range(m)] for i in range(m)]
    values, vectors = _jacobi(cov)
    order = sorted(range(m), key=lambda i: -values[i])[:2]
    axes = []
    for i in order:
        vec = [vectors[k][i] for k in range(m)]
        lead = next((x for x in vec if abs(x) > 1e-12), 1.0)
        axes.append([x if lead > 0 else -x for x in vec])
    pts = [[sum(a * b for a, b in zip(row, axis)) for axis in axes] for row in z]
    for axis in range(2):
        mx, ml = sum(p[axis] for p in pts) / n, sum(load) / n
        cov_load = sum((p[axis] - mx) * (l - ml) for p, l in zip(pts, load))
        if axis == 0 and cov_load < 0:
            for p in pts:
                p[0] = -p[0]
    out = []
    for axis in range(2):
        lo, hi = min(p[axis] for p in pts), max(p[axis] for p in pts)
        span = (hi - lo) or 1.0
        for p in pts:
            p[axis] = (p[axis] - lo) / span
    for p in pts:
        out.append((p[0], p[1]))
    explained = sum(values[i] for i in order) / (sum(v for v in values if v > 0) or 1.0)
    return out, explained


def _dist2(a, b):
    return sum((x - y) ** 2 for x, y in zip(a, b))


def kmeans(z, k=K, seed=SEED, rounds=40):
    """Cluster labels for the rows of z: k-means++ seeding from a fixed seed, then Lloyd rounds."""
    n = len(z)
    k = min(k, n)
    rng = random.Random(seed)
    centres = [z[int(rng.random() * n) % n][:]]
    while len(centres) < k:
        d = [min(_dist2(row, c) for c in centres) for row in z]
        total = sum(d)
        if total <= 0:
            centres.append(z[len(centres) % n][:])
            continue
        pick, acc = rng.random() * total, 0.0
        for i, w in enumerate(d):
            acc += w
            if acc >= pick:
                centres.append(z[i][:])
                break
        else:
            centres.append(z[-1][:])
    labels = [0] * n
    for _ in range(rounds):
        new = [min(range(k), key=lambda c: (_dist2(row, centres[c]), c)) for row in z]
        if new == labels and _ > 0:
            break
        labels = new
        for c in range(k):
            members = [z[i] for i in range(n) if labels[i] == c]
            if members:
                centres[c] = [sum(col) / len(members) for col in zip(*members)]
    return labels, centres


def name_archetype(centre):
    """A short name from the (up to two) traits that set a cluster's centre furthest from the average."""
    ranked = sorted(range(len(KEYS)), key=lambda i: (-abs(centre[i]), i))
    parts = [FEATURES[i][1] if centre[i] > 0 else FEATURES[i][2] for i in ranked[:2] if abs(centre[i]) >= 0.45]
    return ' · '.join(parts) if parts else 'przeciętny rozkład'


def build(per_group, faculty_of, asof=None):
    """data/profiles.json from {group: lessons}: None when there are too few plans to compare."""
    raw = {g: week_features(ls) for g, ls in per_group.items()}
    groups = sorted(g for g, r in raw.items() if r)
    if len(groups) < K + 2:
        return None
    z, means, stds = standardize([raw[g] for g in groups])
    load = load_scores(z)
    pct = percentiles(load)
    pts, explained = project(z, load)
    labels, centres = kmeans(z)
    # archetypes numbered from the lightest centre to the heaviest, so the numbering means something
    used = sorted(set(labels), key=lambda c: (load_scores([centres[c]])[0], c))
    index = {c: i for i, c in enumerate(used)}
    raw_rows = [raw[g] for g in groups]
    names, seen = [], Counter()
    for c in used:
        name = name_archetype(centres[c])
        seen[name] += 1
        names.append(name if seen[name] == 1 else f'{name} ({seen[name]})')
    archetypes = []
    for i, c in enumerate(used):
        members = [raw_rows[j] for j in range(len(groups)) if labels[j] == c]
        typical = [round(sum(r[KEYS.index(k)] for r in members) / len(members), 1) for k in ('hours', 'days', 'gaps', 'span')]
        archetypes.append({'name': names[i], 'n': len(members), 'typical': typical})
    rows = []
    for i, g in enumerate(groups):
        rows.append([g, faculty_of(g), round(pts[i][0] * 1000), round(pts[i][1] * 1000), pct[i], index[labels[i]],
                     round(load[i] * 100)] + [round(v * 100) for v in z[i]])
    return {
        'asof': asof,
        'features': [{'key': k, 'name': NAMES[k], 'high': hi, 'low': lo, 'w': w, 'unit': unit, 'def': text,
                      'mean': round(means[i], 3), 'std': round(stds[i], 3)}
                     for i, (k, hi, lo, w, unit, text) in enumerate(FEATURES)],
        'archetypes': archetypes,
        'explained': round(explained, 2),
        'groups': rows,
    }
