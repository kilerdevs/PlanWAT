#!/usr/bin/env python3
"""`planwat-crawler setup`: the first-run wizard of a volunteer crawler. Writes /config/.env.

    docker compose run --rm --user "$(id -u):$(id -g)" -v "$PWD:/config" crawler setup

The installers run this; it can be run again any time (a new token, other faculties), and keeps whatever else
.env holds (the verified image digests, for one). Step by step: GitHub login, the fork (it waits while you create
it), a fine-grained token limited to the fork (a prefilled link, then the token is checked: push access, not a
classic token, its expiry), one polite request to each faculty site to see which ones your line reaches, your
entry in the registry (or a prefilled application when there is none yet), and whether to update automatically.

Without a terminal (CI, scripts) every answer comes from the flags or the environment instead:
--login, --fork, --token (or PLANWAT_SETUP_TOKEN), --faculties, --auto-update on|off, and --skip-github-checks
to write .env without asking GitHub anything. --keep-token uses (and checks) the token already in .env: the
installer asks for it on the host, because it needs it to verify the images before anything runs in them.
"""
import argparse
import getpass
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools' / 'refresh'))
sys.path.insert(0, str(HERE))
import assign  # noqa: E402
import bundle  # noqa: E402
import doctor  # noqa: E402
import registry  # noqa: E402
import runner  # noqa: E402

UPSTREAM = runner.UPSTREAM
KEYS = ('PLANWAT_LOGIN', 'PLANWAT_FORK', 'PLANWAT_FORK_TOKEN', 'PLANWAT_AUTO_UPDATE')


def token_url(login, fork):
    """A fine-grained token form, prefilled as far as GitHub allows (name, owner, expiry, Contents: write)."""
    query = urllib.parse.urlencode({
        'name': f'PlanWAT crawler ({fork})', 'description': 'Pushes crawl bundles to my PlanWAT fork only.',
        'target_name': login, 'expires_in': '90', 'contents': 'write'})
    return f'https://github.com/settings/personal-access-tokens/new?{query}'


def issue_url(upstream, fork, faculties, where=''):
    """The project's volunteer application, prefilled (the issue form's field ids)."""
    query = {'template': 'volunteer.yml', 'title': f'[Volunteer]: {fork.partition("/")[0]}', 'fork': fork,
             'mode': 'Docker (compose.volunteer.yml)', 'faculties': ', '.join(faculties)}
    if where:
        query['where'] = where
    return f'https://github.com/{upstream}/issues/new?{urllib.parse.urlencode(query)}'


def read_env(path):
    """(ordered lines, {key: value}) of an existing .env (missing file: nothing)."""
    try:
        lines = Path(path).read_text(encoding='utf-8').splitlines()
    except OSError:
        return [], {}
    values = {}
    for line in lines:
        m = re.match(r'^\s*([A-Z0-9_]+)\s*=(.*)$', line)
        if m:
            values[m.group(1)] = m.group(2).strip()
    return lines, values


def write_env(path, updates):
    """Set `updates` in .env, keeping every other line (comments, image digests) as it was; mode 0600."""
    lines, _ = read_env(path)
    done, out = set(), []
    for line in lines:
        m = re.match(r'^\s*#?\s*([A-Z0-9_]+)\s*=', line)
        key = m.group(1) if m else None
        if key in updates and key not in done:
            if updates[key] is not None:
                out.append(f'{key}={updates[key]}')
            done.add(key)
        else:
            out.append(line)
    if not lines:
        out.append('# PlanWAT volunteer crawler (planwat-crawler setup). Keep this file private: it holds your token.')
    out += [f'{k}={v}' for k, v in updates.items() if k not in done and v is not None]
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(out) + '\n')
    os.replace(tmp, path)


class Wizard:
    def __init__(self, args, out=None, ask=input, secret=getpass.getpass, sleep=time.sleep):
        self.args, self.out, self._ask, self._secret, self.sleep = args, out or sys.stdout, ask, secret, sleep
        self.interactive = args.interactive

    def say(self, text=''):
        print(text, file=self.out, flush=True)

    def ask(self, question, default=''):
        if not self.interactive:
            return default
        answer = self._ask(f'{question}{f" [{default}]" if default else ""}: ').strip()
        return answer or default

    def yes(self, question, default=True):
        if not self.interactive:
            return default
        answer = self._ask(f'{question} [{"T/n" if default else "t/N"}]: ').strip().lower()
        return default if not answer else answer in ('t', 'tak', 'y', 'yes')

    # --- the steps -----------------------------------------------------------------------------------------

    def login(self, current):
        while True:
            login = self.args.login or self.ask('Twój login na GitHubie', current)
            if not assign.LOGIN_RE.match(login or ''):
                if not self.interactive:
                    raise SystemExit('setup: --login is not a GitHub login')
                self.say('  To nie wygląda na login GitHub (litery, cyfry i myślniki).')
                continue
            if self.args.skip_github_checks:
                return login
            status, _ = doctor.get_json(f'{registry.API}/users/{login}')
            if status == 200 or status is None:  # None: GitHub unreachable; the next steps will say so
                return login
            if not self.interactive:
                raise SystemExit(f'setup: GitHub does not know {login}')
            self.say(f'  GitHub nie zna konta {login}.')
            self.args.login = None

    def fork(self, login, current):
        default = current if current.lower().startswith(f'{login.lower()}/') else f'{login}/PlanWAT'
        fork = self.args.fork or self.ask('Twój fork', default)
        if fork.partition('/')[0].lower() != login.lower():
            self.say(f'  Fork musi należeć do Twojego konta; używam {login}/PlanWAT.')
            fork = f'{login}/PlanWAT'
        if self.args.skip_github_checks:
            return fork
        upstream = self.args.upstream
        for attempt in range(120):
            _, repo = doctor.get_json(f'{registry.API}/repos/{fork}')
            parent = ((repo or {}).get('parent') or {}).get('full_name', '') if isinstance(repo, dict) else ''
            if isinstance(repo, dict) and repo.get('fork') and parent.lower() == upstream.lower():
                self.say(f'  ✓ fork {fork} jest gotowy')
                return fork
            if attempt == 0:
                self.say(f'  Nie ma jeszcze forka {fork}. Utwórz go jednym kliknięciem (Create fork):')
                self.say(f'    https://github.com/{upstream}/fork')
                if not self.interactive:
                    raise SystemExit(f'setup: {fork} is not a fork of {upstream}')
                self.say('  Czekam, aż się pojawi…')
            self.sleep(5)
        raise SystemExit('setup: the fork did not appear; run setup again once it exists')

    def token(self, login, fork, current):
        if self.args.keep_token and current and not self.args.token:
            # The installer already asked for it on the host (it verifies the images with it first): check it only.
            problem, expires = ('', None) if self.args.skip_github_checks else bundle.token_report(fork, current)
            if not problem:
                self.say(f'  ✓ token działa{f", wygasa {expires[:10]}" if expires else ""}')
                return current
            self.say(f'  ✗ {problem}')
            if not self.interactive:
                raise SystemExit(f'setup: {problem}')
            current = ''
        if self.args.token or (not self.interactive and current):
            token = self.args.token or current
            problem, expires = ('', None) if self.args.skip_github_checks else bundle.token_report(fork, token)
            if problem or token.startswith(bundle.BROAD_TOKENS):
                raise SystemExit(f'setup: {problem or "a classic or OAuth token is not accepted"}')
            return token
        if current and self.yes('Masz już token w .env. Zostawić go?'):
            problem, expires = bundle.token_report(fork, current)
            if not problem:
                self.say(f'  ✓ token działa{f", wygasa {expires[:10]}" if expires else ""}')
                return current
            self.say(f'  ✗ {problem}')
        self.say('  Crawler wypycha paczki tokenem, który ma dostęp wyłącznie do Twojego forka.')
        self.say('  1. Otwórz (formularz jest częściowo wypełniony):')
        self.say(f'     {token_url(login, fork)}')
        self.say(f'  2. Repository access: Only select repositories → {fork}.')
        self.say('  3. Permissions → Repository permissions → Contents: Read and write. Nic więcej.')
        self.say('  4. Generate token, skopiuj i wklej tutaj (nie będzie widoczny).')
        for _ in range(5):
            token = self._secret('  Token: ').strip()
            if not token:
                continue
            problem, expires = bundle.token_report(fork, token)
            if problem:
                self.say(f'  ✗ {problem}')
                continue
            self.say(f'  ✓ token działa{f", wygasa {expires[:10]} (ustaw sobie przypomnienie)" if expires else ""}')
            return token
        raise SystemExit('setup: no working token; run setup again when you have one')

    def faculties(self):
        if self.args.faculties is not None:
            return [f.strip().lower() for f in self.args.faculties.split(',') if f.strip()]
        if self.args.skip_github_checks:
            return []
        self.say('  Sprawdzam, do których wydziałów dociera Twoje łącze (po jednym zapytaniu)…')
        found = doctor.probe_faculties()
        for name, verdict in sorted(found.items()):
            mark = {'ok': '✓', 'blocked': '✗ blokuje (Incapsula)', 'down': '? nie odpowiada'}[verdict]
            self.say(f'    {name}: {mark}')
        reachable = [n for n, v in sorted(found.items()) if v == 'ok']
        if reachable and len(reachable) == len(found):
            return []  # every faculty: no restriction
        return reachable

    def registry_entry(self, login, fork, faculties):
        if self.args.skip_github_checks:
            return
        try:
            reg, _, _, _ = registry.fetch_verified(self.args.upstream, self.args.editors)
        except (registry.Missing, registry.Unavailable, assign.RegistryError) as err:
            self.say(f'  Nie udało się sprawdzić rejestru ({err}); crawler spróbuje sam.')
            return
        me = assign.find(reg, login)
        if me and me['trust'] != 'suspended':
            label = {'trusted': 'zaufany', 'peer': 'równorzędny'}[me['trust']]
            self.say(f'  ✓ jesteś w rejestrze ({label}; wydziały: {", ".join(me["faculties"]) or "wszystkie"})')
            return
        self.say('  Nie ma Cię jeszcze w rejestrze. Wyślij zgłoszenie (jest wypełnione, sprawdź i kliknij Submit):')
        self.say(f'    {issue_url(self.args.upstream, fork, faculties)}')
        self.say('  Crawler może już działać: zacznie sprawdzać plany, gdy opiekun Cię dopisze.')

    def run(self, path):
        _, current = read_env(path)
        self.say('PlanWAT: konfiguracja crawlera wolontariusza\n')
        self.say('1/5 Konto')
        login = self.login(current.get('PLANWAT_LOGIN', ''))
        self.say('2/5 Fork')
        fork = self.fork(login, current.get('PLANWAT_FORK', ''))
        self.say('3/5 Token')
        token = self.token(login, fork, current.get('PLANWAT_FORK_TOKEN', '') if
                           current.get('PLANWAT_LOGIN', '').lower() == login.lower() else '')
        self.say('4/5 Wydziały i rejestr')
        faculties = self.faculties()
        self.registry_entry(login, fork, faculties)
        self.say('5/5 Aktualizacje')
        if self.args.auto_update:
            auto = self.args.auto_update == 'on'
        else:
            auto = self.yes('Aktualizować crawler automatycznie (raz dziennie, tylko zweryfikowane obrazy)?',
                            current.get('PLANWAT_AUTO_UPDATE', '1') != '0')
        updates = {'PLANWAT_LOGIN': login, 'PLANWAT_FORK': fork if fork.lower() != f'{login}/planwat'.lower() else None,
                   'PLANWAT_FORK_TOKEN': token, 'PLANWAT_AUTO_UPDATE': '1' if auto else '0'}
        if self.args.upstream != UPSTREAM:
            updates['PLANWAT_UPSTREAM'] = self.args.upstream
        try:
            write_env(path, updates)
        except OSError as err:
            self.say(f'\nNie mogę zapisać {path} ({err}). Zapisz ręcznie jako .env (chmod 600):\n')
            for k, v in updates.items():
                if v is not None:
                    self.say(f'{k}={v}')
            return 1
        self.say(f'\n✓ zapisano {path}')
        return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--env', type=Path, default=Path('/config/.env'), help='the .env to write')
    ap.add_argument('--login')
    ap.add_argument('--fork')
    ap.add_argument('--token', default=os.environ.get('PLANWAT_SETUP_TOKEN'))
    ap.add_argument('--keep-token', action='store_true', help='use the token already in .env (checking it)')
    ap.add_argument('--faculties', help='comma-separated; empty string means all (skips the probe)')
    ap.add_argument('--auto-update', choices=('on', 'off'))
    ap.add_argument('--upstream', default=os.environ.get('PLANWAT_UPSTREAM') or UPSTREAM)
    ap.add_argument('--editors', default=os.environ.get('PLANWAT_REGISTRY_EDITORS') or registry.DEFAULT_EDITORS)
    ap.add_argument('--skip-github-checks', action='store_true', help='write .env without asking GitHub (CI)')
    ap.add_argument('--non-interactive', action='store_true')
    args = ap.parse_args(argv)
    args.interactive = not args.non_interactive and sys.stdin.isatty()
    try:
        return Wizard(args).run(args.env)
    except (KeyboardInterrupt, EOFError):
        print('\nprzerwano; nic nie zapisano')
        return 130


if __name__ == '__main__':
    sys.exit(main())
