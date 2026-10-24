"""The volunteer registry (volunteers.json) and who checks which group when.

Every group is handed out per two-hour window by rendezvous hashing over the volunteers allowed to crawl its
faculty: the top-ranked one alone when it is trusted, otherwise the top `quorum` peers, so the load on a faculty
site stays about `quorum` fetches per group and window however many volunteers join, and pairs of peers rotate
every window. Everybody computes the same answer from the public registry; nothing is coordinated live.

The answer also heeds the volunteers' health that the coordinator publishes in volunteer-state.json on the data
branch (`volunteers`): a volunteer whose last bundle is more than LIVE_HOURS old is offline, and one that reported
a faculty blocked within the last BLOCK_HOURS is skipped for that faculty, so quorums form among the volunteers who
are actually working. Health is judged at the start of the window, so everybody who read the same data commit
agrees; a never-seen volunteer counts as live for GRACE_HOURS after the `added` date of its registry entry, and a
volunteer always counts itself as live (otherwise one back from a break would never be heard from again).
"""
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

TRUST = ('trusted', 'peer', 'suspended')
WINDOW_HOURS = 2
LIVE_HOURS = 6
BLOCK_HOURS = 6
GRACE_HOURS = 24
LOGIN_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$')
REPO_RE = re.compile(r'^[A-Za-z0-9._-]{1,100}$')
VERSION_RE = re.compile(r'^\d{1,9}\.\d{1,9}\.\d{1,9}$')  # bounded, so int() never chokes on a forged one
DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2})?)?$')


class RegistryError(ValueError):
    pass


def version_tuple(text):
    if not isinstance(text, str) or not VERSION_RE.match(text):
        raise RegistryError(f'not a version: {text!r:.40}')
    return tuple(int(p) for p in text.split('.'))


def check_registry(data):
    """The registry, normalised; RegistryError on anything malformed (the whole file is refused, never half-read)."""
    if not isinstance(data, dict):
        raise RegistryError('the registry is not an object')
    quorum = data.get('quorum', 2)
    window = data.get('window_hours', 12)
    if not isinstance(quorum, int) or isinstance(quorum, bool) or not 2 <= quorum <= 5:
        raise RegistryError('quorum must be an integer from 2 to 5')
    if not isinstance(window, (int, float)) or isinstance(window, bool) or not 2 <= window <= 48:
        raise RegistryError('window_hours must be between 2 and 48')
    version_tuple(data.get('min_version', '0.0.0'))
    volunteers, seen = [], set()
    for v in data.get('volunteers', []):
        if not isinstance(v, dict):
            raise RegistryError('a volunteer entry is not an object')
        login = v.get('login')
        if not isinstance(login, str) or not LOGIN_RE.match(login):
            raise RegistryError(f'bad login: {login!r}')
        if login.lower() in seen:
            raise RegistryError(f'{login} is listed twice')
        seen.add(login.lower())
        fork = v.get('fork', f'{login}/PlanWAT')
        owner, _, repo = str(fork).partition('/')
        # The fork must belong to the login: nobody can enrol somebody else's repository.
        if owner.lower() != login.lower() or not REPO_RE.match(repo):
            raise RegistryError(f'{login}: the fork must be {login}/<repository>')
        trust = v.get('trust', 'peer')
        if trust not in TRUST:
            raise RegistryError(f'{login}: trust must be one of {", ".join(TRUST)}')
        faculties = v.get('faculties', [])
        if not isinstance(faculties, list) or not all(isinstance(f, str) for f in faculties):
            raise RegistryError(f'{login}: faculties must be a list of names')
        added = v.get('added')
        if added is not None and not (isinstance(added, str) and DATE_RE.match(added)):
            raise RegistryError(f'{login}: added must be a date (YYYY-MM-DD)')
        entry = {'login': login, 'fork': f'{login}/{repo}', 'trust': trust,
                 'faculties': [f.lower() for f in faculties]}
        if added:
            entry['added'] = added
        volunteers.append(entry)
    return {'quorum': quorum, 'window_hours': float(window),
            'min_version': data.get('min_version', '0.0.0'), 'volunteers': volunteers}


def load_registry(path):
    return check_registry(json.loads(Path(path).read_text(encoding='utf-8')))


def find(registry, login):
    """The registry entry of `login` (case-insensitive, as GitHub logins are), or None."""
    return next((v for v in registry['volunteers'] if v['login'].lower() == str(login).lower()), None)


def window_of(moment, hours=WINDOW_HOURS):
    """The number of the assignment window `moment` (naive UTC) falls in."""
    return int(moment.replace(tzinfo=dt.timezone.utc).timestamp() // (hours * 3600))


def window_start(window, hours=WINDOW_HOURS):
    """When window number `window` opens (naive UTC)."""
    return dt.datetime.fromtimestamp(window * hours * 3600, dt.timezone.utc).replace(tzinfo=None)


def load_health(path):
    """{login: record} published by the coordinator in volunteer-state.json; {} when there is none."""
    try:
        found = json.loads(Path(path).read_text(encoding='utf-8')).get('volunteers', {})
    except (OSError, ValueError, AttributeError):
        return {}
    return found if isinstance(found, dict) else {}


def _stamp(text):
    try:
        moment = dt.datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return moment.astimezone(dt.timezone.utc).replace(tzinfo=None) if moment.tzinfo else moment


def working(volunteer, faculty, health, opens):
    """Whether `volunteer` can be counted on for `faculty` in the window that `opens` then."""
    record = health.get(volunteer['login']) or health.get(volunteer['login'].lower()) or {}
    if not isinstance(record, dict):
        record = {}
    blocked = _stamp((record.get('blocked') or {}).get(faculty.lower(), '')) if isinstance(
        record.get('blocked'), dict) else None
    if blocked and opens - blocked < dt.timedelta(hours=BLOCK_HOURS):
        return False
    ended = _stamp(record.get('ended', ''))
    if ended:
        return opens - ended < dt.timedelta(hours=LIVE_HOURS)
    added = _stamp(volunteer.get('added', ''))
    return added is None or opens - added < dt.timedelta(hours=GRACE_HOURS)


def _rank(login, key):
    return int(hashlib.sha256(f'{login.lower()}|{key}'.encode('utf-8')).hexdigest()[:16], 16)


def assignees(registry, faculty, code, tid, window, health=None, me=None):
    """The logins that should check `code` (of `faculty`, term `tid`) in `window`; [] when nobody can.
    With `health`, offline volunteers and those blocked on the faculty are passed over (`me` never is), unless
    that would leave nobody at all."""
    able = [v for v in registry['volunteers']
            if v['trust'] != 'suspended' and (not v['faculties'] or faculty.lower() in v['faculties'])]
    if health:
        opens = window_start(window)
        fit = [v for v in able
               if (me and v['login'].lower() == str(me).lower()) or working(v, faculty, health, opens)]
        able = fit or able
    key = f'{code}@{tid}#{window}'
    ranked = sorted(able, key=lambda v: (_rank(v['login'], key), v['login'].lower()), reverse=True)
    if not ranked:
        return []
    if ranked[0]['trust'] == 'trusted':
        return [ranked[0]['login']]
    peers = [v['login'] for v in ranked if v['trust'] == 'peer'][:registry['quorum']]
    if len(peers) < registry['quorum']:
        # Too few peers to ever agree on this faculty: a trusted volunteer takes it, or nobody does.
        trusted = [v['login'] for v in ranked if v['trust'] == 'trusted']
        return trusted[:1]
    return peers


def is_assigned(registry, login, faculty, code, tid, window, health=None):
    return str(login).lower() in (a.lower() for a in assignees(registry, faculty, code, tid, window, health, login))
