"""The volunteer registry (volunteers.json) and who checks which group when.

Every group is handed out per two-hour window by rendezvous hashing over the volunteers allowed to crawl its
faculty: the top-ranked one alone when it is trusted, otherwise the top `quorum` peers, so the load on a faculty
site stays about `quorum` fetches per group and window however many volunteers join, and pairs of peers rotate
every window. Everybody computes the same answer from the public registry; nothing is coordinated live.
"""
import datetime as dt
import hashlib
import json
import re
from pathlib import Path

TRUST = ('trusted', 'peer', 'suspended')
WINDOW_HOURS = 2
LOGIN_RE = re.compile(r'^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$')
REPO_RE = re.compile(r'^[A-Za-z0-9._-]{1,100}$')
VERSION_RE = re.compile(r'^\d+\.\d+\.\d+$')


class RegistryError(ValueError):
    pass


def version_tuple(text):
    if not isinstance(text, str) or not VERSION_RE.match(text):
        raise RegistryError(f'not a version: {text!r}')
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
        volunteers.append({'login': login, 'fork': f'{login}/{repo}', 'trust': trust,
                           'faculties': [f.lower() for f in faculties]})
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


def _rank(login, key):
    return int(hashlib.sha256(f'{login.lower()}|{key}'.encode('utf-8')).hexdigest()[:16], 16)


def assignees(registry, faculty, code, tid, window):
    """The logins that should check `code` (of `faculty`, term `tid`) in `window`; [] when nobody can."""
    able = [v for v in registry['volunteers']
            if v['trust'] != 'suspended' and (not v['faculties'] or faculty.lower() in v['faculties'])]
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


def is_assigned(registry, login, faculty, code, tid, window):
    return str(login).lower() in (a.lower() for a in assignees(registry, faculty, code, tid, window))
