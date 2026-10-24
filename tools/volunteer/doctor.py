#!/usr/bin/env python3
"""`planwat-crawler doctor`: every check a volunteer crawler depends on, each with what to do about it.

    runner.py doctor [--offline] [--no-probe] [--installing]

Run inside the crawler container (the egress proxy is its only way out, exactly as for a real pass). Each line
is ✓ (fine), ! (works, but look at it) or ✗ (this stops the crawler from helping), followed by the fix. Exit 0
when nothing is ✗. --offline skips everything that needs the network (CI); --no-probe skips the faculty sites;
--installing (the installer) reports not being in the registry yet as ! instead of ✗.
"""
import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'refresh'))
sys.path.insert(0, str(HERE))
import assign  # noqa: E402
import bundle  # noqa: E402
import core  # noqa: E402
import registry  # noqa: E402
import runner  # noqa: E402

OK, WARN, FAIL = '✓', '!', '✗'
SOURCES = ROOT / 'tools' / 'refresh' / 'sources.json'
MIN_FREE = 500 * 2**20   # the data clone, a crawl's calendars and the bundle fit comfortably in this


def faculty_hosts():
    """{faculty: https://host/} for every enabled faculty, from the crawler's own sources.json."""
    hosts = {}
    for name, cfg in json.loads(SOURCES.read_text(encoding='utf-8')).items():
        if not cfg.get('enabled'):
            continue
        url = next((cfg[k] for k in ('index', 'landing', 'base', 'page') if isinstance(cfg.get(k), str)), '')
        parts = urllib.parse.urlsplit(url)
        if parts.scheme == 'https' and parts.hostname:
            hosts[name] = f'https://{parts.hostname}/'
    return hosts


def classify(status, text):
    """'ok', 'blocked' or 'down' for one answer of a faculty site (or status None: no answer at all)."""
    if status is None or status >= 500:
        return 'down'
    if status in (401, 403, 429) or (status == 200 and core.is_blocked(200, text)):
        return 'blocked'
    return 'ok'


def probe_faculties(session=None, hosts=None):
    """{faculty: 'ok' | 'blocked' | 'down'}: one request to each faculty's front page, through the egress."""
    if session is None:
        from curl_cffi import requests as cr
        session = cr.Session(impersonate='chrome')
        session.headers['Accept-Language'] = 'pl-PL,pl;q=0.9'
    found = {}
    for name, url in (hosts or faculty_hosts()).items():
        try:
            r = session.get(url, timeout=25, allow_redirects=True)
            found[name] = classify(r.status_code, r.text[:20000])
        except Exception:
            found[name] = classify(None, '')
    return found


def get_json(url, token=None):
    """(status, parsed JSON or None); status None when GitHub could not be reached."""
    try:
        status, body = registry.http_get(url, token)
    except (registry.Unavailable, assign.RegistryError):
        return None, None
    if status != 200:
        return status, None
    try:
        return status, json.loads(body.decode('utf-8'))
    except (UnicodeDecodeError, ValueError):
        return status, None


def check_work(work, report, free_warn=MIN_FREE):
    """The crawler keeps its status, the data clone and the bundle in `work`: it must be writable, with room."""
    probe = Path(work) / '.doctor-probe'
    try:
        Path(work).mkdir(parents=True, exist_ok=True)
        probe.write_text('ok', encoding='utf-8')
        probe.unlink()
        free = shutil.disk_usage(work).free
    except OSError as err:
        report.line(FAIL, f'katalog roboczy {work} nie przyjmuje zapisu ({err.strerror or err})',
                    'sprawdź wolne miejsce na dysku i wolumen work; potem planwat-crawler restart')
        return
    if free < free_warn:
        report.line(WARN, f'mało miejsca na katalog roboczy {work}: {free // 2**20} MB',
                    'zwolnij miejsce na dysku (np. docker system prune)')


def check_data_branch(upstream, report):
    """The project's data branch, over the same git transport (and proxy) a pass clones it with."""
    try:
        heads = runner.git('ls-remote', '--heads', f'https://github.com/{upstream}.git', 'data', timeout=60)
    except (subprocess.SubprocessError, OSError) as err:
        report.line(FAIL, f'nie mogę pobrać gałęzi data projektu ({str(err)[:200]})',
                    'sprawdź połączenie i: planwat-crawler logs egress')
        return
    if heads.strip():
        report.line(OK, 'gałąź data projektu jest dostępna')
    else:
        report.line(FAIL, f'{upstream} nie ma gałęzi data', 'zgłoś to opiekunowi projektu (issue)')


class Report:
    def __init__(self, out=sys.stdout):
        self.out, self.failed, self.warned = out, 0, 0

    def line(self, mark, what, fix=''):
        self.failed += mark == FAIL
        self.warned += mark == WARN
        print(f' {mark} {what}', file=self.out)
        if fix:
            print(f'     → {fix}', file=self.out)


def run(cfg, report, offline=False, probe=True, now=None, installing=False):
    now = now or core.now_utc()
    login, fork, token, upstream = cfg['login'], cfg['fork'], cfg['token'], cfg['upstream']
    if not login:
        report.line(FAIL, 'brak PLANWAT_LOGIN w .env', 'uruchom: planwat-crawler setup')
        return
    report.line(OK, f'login {login}, fork {fork}, projekt {upstream}')
    if not token:
        report.line(FAIL if not cfg['dry_run'] else WARN, 'brak tokenu forka (PLANWAT_FORK_TOKEN)',
                    'uruchom: planwat-crawler setup')
    elif token.startswith(bundle.BROAD_TOKENS):
        report.line(FAIL, 'token jest klasyczny albo OAuth (dostęp do wszystkich Twoich repozytoriów)',
                    'utwórz token fine-grained tylko dla forka: planwat-crawler setup')
    status = runner.Status(cfg['work']).data
    if status:
        last = status.get('last_pass') or {}
        state = status.get('state')
        fixes = {'failed': 'szczegóły: planwat-crawler logs; następny przebieg spróbuje ponownie',
                 'benched': 'opiekun dostał issue; sprawdź wersję crawlera i odpisz tam',
                 'update_needed': 'planwat-crawler update',
                 'not_registered': f'zgłoś się: {status.get("join") or runner.JOIN.format(upstream=upstream)}',
                 'waiting': 'crawler sam spróbuje ponownie za 30 min; szczegóły: planwat-crawler logs'}
        mark = WARN if state == 'waiting' or (state == 'not_registered' and installing) else FAIL if state in fixes else OK
        report.line(mark, f'crawler: {runner.STATES.get(state, state)}'
                    + (f' ({status["message"]})' if status.get('message') else '')
                    + (f', ostatni przebieg {last["started"][:16].replace("T", " ")} UTC' if last.get('started') else ''),
                    fixes.get(state, '') if mark != OK else '')
        if last.get('pushed') is False and not last.get('dry_run'):
            report.line(WARN, 'paczka z ostatniego przebiegu nie dotarła do forka'
                        + (f': {last["push_error"]}' if last.get('push_error') else ''),
                        'sprawdź token i fork (niżej), nowy token: planwat-crawler setup; log: planwat-crawler logs')
        if runner.health(cfg, now):
            report.line(FAIL, 'crawler od ponad 3 h nie zapisał swojego stanu: nie działa albo się zawiesił '
                        '(powyższy stan jest nieaktualny)', 'planwat-crawler start; jeśli już działa: planwat-crawler logs')
    else:
        report.line(WARN, 'crawler jeszcze nie wystartował (brak status.json)', 'planwat-crawler start')
    check_work(cfg['work'], report)
    # `start` (compose up) picks up a changed .env; `restart` would keep the old environment.
    if cfg['dry_run']:
        report.line(WARN, 'tryb próbny (PLANWAT_DRY_RUN=1): crawler sprawdza plany, ale niczego nie wypycha',
                    'po teście usuń PLANWAT_DRY_RUN z .env i uruchom: planwat-crawler start')
    elif ((status or {}).get('last_pass') or {}).get('dry_run'):
        report.line(WARN, 'ostatni przebieg był próbny: nic nie zostało wypchnięte',
                    'jeśli PLANWAT_DRY_RUN jest już usunięty z .env, uruchom: planwat-crawler start')
    if offline:
        report.line(WARN, 'tryb offline: pominięto sprawdzenia sieciowe')
        return
    health = os.environ.get('PLANWAT_EGRESS_HEALTH')
    if health:
        try:
            with urllib.request.urlopen(urllib.request.Request(health), timeout=10):
                report.line(OK, 'proxy wyjściowe (egress) działa')
        except (urllib.error.URLError, OSError):
            report.line(FAIL, 'proxy wyjściowe (egress) nie odpowiada', 'planwat-crawler logs egress')
    offset = runner.measure_offset()
    if offset is None:
        report.line(FAIL, 'GitHub jest nieosiągalny', 'sprawdź połączenie i: planwat-crawler logs egress')
        return
    if abs(offset) > runner.SKEW_WARN:
        report.line(WARN, f'zegar odbiega od GitHuba o {abs(offset):.0f} s (crawler to koryguje)',
                    'włącz synchronizację czasu: sudo timedatectl set-ntp true')
    else:
        report.line(OK, f'zegar zgodny z GitHubem ({offset:+.0f} s)')
    try:
        reg, _, sha, who = registry.fetch_verified(upstream, cfg['editors'], token or None)
    except registry.Missing:
        report.line(FAIL, 'projekt nie ma jeszcze rejestru wolontariuszy', 'poczekaj na opiekuna')
        reg = None
    except registry.Unavailable as err:
        report.line(FAIL, f'nie udało się pobrać rejestru ({err})', 'spróbuj ponownie za chwilę')
        reg = None
    except assign.RegistryError as err:
        report.line(FAIL, f'rejestr odrzucony: {err}', 'zgłoś to opiekunowi projektu (issue)')
        reg = None
    if reg is not None:
        me = assign.find(reg, login)
        if me is None:
            # Right after installing, not being in the registry yet is the expected next step, not a fault.
            report.line(WARN if installing else FAIL, f'{login} nie ma w rejestrze (podpisany {sha[:12]} przez {who})',
                        f'zgłoś się: {runner.JOIN.format(upstream=upstream)}')
        elif me['trust'] == 'suspended':
            report.line(FAIL, f'{login} jest wstrzymany w rejestrze', 'zapytaj opiekuna w swoim zgłoszeniu')
        else:
            label = {'trusted': 'zaufany', 'peer': 'równorzędny'}[me['trust']]
            report.line(OK, f'w rejestrze jako {label}; wydziały: {", ".join(me["faculties"]) or "wszystkie"}')
        # The coordinator reads bundles only from the fork the registry names; pushing elsewhere is never seen.
        if me is not None and me['fork'].lower() != fork.lower():
            report.line(FAIL, f'crawler wypycha do {fork}, a rejestr (i koordynator) zna Twój fork jako {me["fork"]}',
                        f'uruchom planwat-crawler setup i podaj fork {me["fork"]} (albo poproś opiekuna o zmianę wpisu)')
        mine = bundle.version()
        if assign.version_tuple(mine) < assign.version_tuple(reg['min_version']):
            report.line(FAIL, f'crawler {mine} jest starszy niż wymagany {reg["min_version"]}',
                        'planwat-crawler update')
    check_data_branch(upstream, report)
    # The dev channel follows the dev branch; a release number says nothing about it.
    latest = None if os.environ.get('PLANWAT_CHANNEL') == 'dev' else get_json(
        f'{registry.API}/repos/{upstream}/releases/latest', token or None)[1]
    tag = (latest or {}).get('tag_name', '') if isinstance(latest, dict) else ''
    if tag.lstrip('v') and tag.lstrip('v') != bundle.version():
        try:
            newer = assign.version_tuple(tag.lstrip('v')) > assign.version_tuple(bundle.version())
        except assign.RegistryError:
            newer = False
        if newer:
            report.line(WARN, f'jest nowsza wersja: {tag} (masz {bundle.version()})', 'planwat-crawler update')
    if token and not token.startswith(bundle.BROAD_TOKENS):
        problem, expires = bundle.token_report(fork, token)
        if problem:
            report.line(FAIL, f'token: {problem}', 'planwat-crawler setup')
        elif expires:
            left = dt.datetime.fromisoformat(expires) - now
            mark = FAIL if left.total_seconds() <= 0 else WARN if left < dt.timedelta(days=14) else OK
            report.line(mark, f'token działa, wygasa {expires[:10]}',
                        'utwórz nowy i uruchom planwat-crawler setup' if mark != OK else '')
        else:
            report.line(OK, 'token działa (może pisać do forka)')
    answer, repo = get_json(f'{registry.API}/repos/{fork}', token or None)
    if not isinstance(repo, dict) and answer != 404:
        # No answer, or an error that says nothing about the fork: do not send anybody to create it.
        report.line(WARN, f'nie udało się sprawdzić forka {fork} (GitHub: {answer or "brak odpowiedzi"})',
                    'spróbuj ponownie za chwilę')
    elif not isinstance(repo, dict):
        report.line(FAIL, f'nie ma repozytorium {fork}', f'utwórz fork: https://github.com/{upstream}/fork')
    elif not repo.get('fork') or ((repo.get('parent') or {}).get('full_name') or '').lower() != upstream.lower():
        report.line(FAIL, f'{fork} nie jest forkiem {upstream}', f'utwórz fork: https://github.com/{upstream}/fork')
    else:
        report.line(OK, f'fork {fork} istnieje')
    _, state = get_json(f'{registry.RAW}/{upstream}/data/{core.VOLUNTEER_STATE_FILE}')
    record, benched = runner.verdict(state if isinstance(state, dict) else {}, login)
    if benched:
        report.line(FAIL, 'koordynator odsunął Cię (Twoje głosy kilka razy przegrały)',
                    'opiekun dostał issue; sprawdź wersję crawlera i odpisz tam')
    elif record.get('refused'):
        report.line(FAIL, f'ostatnia paczka odrzucona: {record["refused"].get("reason", "?")}',
                    'następny przebieg wyśle nową; jeśli to się powtarza, uruchom planwat-crawler update')
    elif record.get('read'):
        report.line(OK, runner.describe_verdict(record).replace('the coordinator ', 'koordynator: '))
        for name, since in sorted((record.get('blocked') or {}).items()):
            report.line(WARN, f'wydział {name} blokował Twoje łącze ({since[:16].replace("T", " ")} UTC)',
                        'przydziały tego wydziału przejmują na razie inni; nic nie musisz robić')
    else:
        report.line(WARN, 'koordynator nie przeczytał jeszcze żadnej Twojej paczki',
                    'pierwsza pojawi się do pół godziny po pierwszym przebiegu')
    if probe:
        for name, verdict in sorted(probe_faculties().items()):
            if verdict == 'ok':
                report.line(OK, f'{name}: strona wydziału odpowiada')
            elif verdict == 'blocked':
                report.line(WARN, f'{name}: strona wydziału blokuje Twoje łącze (Incapsula)',
                            'jeśli to się utrzymuje, poproś opiekuna o usunięcie tego wydziału z Twoich wydziałów')
            else:
                report.line(WARN, f'{name}: strona wydziału nie odpowiada', 'pewnie chwilowa awaria wydziału')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--offline', action='store_true', help='skip every check that needs the network')
    ap.add_argument('--no-probe', action='store_true', help='do not contact the faculty sites')
    ap.add_argument('--installing', action='store_true',
                    help="the installer's run: not being in the registry yet is a warning, not a failure")
    args = ap.parse_args(argv)
    report = Report()
    print(f'PlanWAT crawler {bundle.version()}: diagnostyka')
    run(runner.config(), report, offline=args.offline, probe=not args.no_probe, installing=args.installing)
    print(f'\n{report.failed} problemów, {report.warned} uwag.' if report.failed or report.warned
          else '\nWszystko w porządku.')
    return 1 if report.failed else 0


if __name__ == '__main__':
    sys.exit(main())
