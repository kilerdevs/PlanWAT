#!/usr/bin/env python3
"""Build the static site from the timetables in timetables/<term>/<GROUP>.ics.

Output (default: site/):
    index.html            group list (redirects straight to the group while there is only one)
    <GROUP>/index.html    the timetable page; it fetches ./plan.ics and renders it in the browser
    <GROUP>/plan.ics      the group's current term, byte-for-byte
    404.html

Every page carries a hash-pinned Content-Security-Policy in a <meta> tag (GitHub Pages cannot send
headers). For the Docker/nginx deployment, --nginx writes the union of those hashes (plus
frame-ancestors, which only works as a header) into the given nginx.conf; the Dockerfile does this on
its own copy of deploy/nginx.conf, so no tracked file is ever rewritten.

    python3 build.py                                  # site/, terms picked for today
    python3 build.py --base-path /PlanWAT --today 2026-10-15
    python3 build.py --out /site --nginx deploy/nginx.conf   # inside the Docker build
"""
import argparse
import base64
import dataclasses
import datetime as dt
import hashlib
import html
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
MARKER = '.planwat-site'
GROUP_RE = re.compile(r'^[A-Za-z0-9_]{2,32}$')
TERM_RE = re.compile(r'^[a-z0-9][a-z0-9-]{0,47}$')
FONT_CSS = 'https://fonts.googleapis.com'
FONT_FILES = 'https://fonts.gstatic.com'

# Canonical faculties offered on the front page (code -> Polish / English names).
# A group belongs to the faculty matching the first three letters of its code;
# anything else is listed under "Pozostałe grupy".
FACULTIES = [
    ('WCY', 'Wydział Cybernetyki', 'Faculty of Cybernetics'),
    ('WEL', 'Wydział Elektroniki', 'Faculty of Electronics'),
    ('WIG', 'Wydział Inżynierii Lądowej i Geodezji', 'Faculty of Civil Engineering and Geodesy'),
    ('WML', 'Wydział Mechatroniki, Uzbrojenia i Lotnictwa', 'Faculty of Mechatronics, Armament and Aviation'),
    ('WTC', 'Wydział Nowych Technologii i Chemii', 'Faculty of New Technologies and Chemistry'),
]
FACULTY_CODES = {code for code, _, _ in FACULTIES}


def faculty_of(group):
    prefix = group[:3].upper()
    return prefix if prefix in FACULTY_CODES else 'OTHER'


def plural_grup(n):
    if n == 1:
        return '1 grupa'
    m10, m100 = n % 10, n % 100
    if 2 <= m10 <= 4 and not 12 <= m100 <= 14:
        return f'{n} grupy'
    return f'{n} grup'


class BuildError(Exception):
    """A timetable or the output directory is not usable; the message says which and why."""


@dataclasses.dataclass
class Term:
    term_id: str
    path: Path | None
    start: dt.date
    end: dt.date
    meta: dict = dataclasses.field(default_factory=dict)


# ---------------------------------------------------------------- calendars

def _unescape(value):
    return re.sub(r'\\([\\;,nN])', lambda m: '\n' if m.group(1) in 'nN' else m.group(1), value).strip()


def _ymd(value):
    m = re.match(r'(\d{4})(\d{2})(\d{2})', value.strip())
    if not m:
        return None
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def read_calendar(path):
    """Check a calendar's structure and return its calendar-level properties and event dates."""
    try:
        text = path.read_bytes().decode('utf-8')
    except UnicodeDecodeError as err:
        raise BuildError(f'{path}: not UTF-8 ({err})') from None
    lines = [l for l in re.sub(r'\r?\n[ \t]', '', text.lstrip('\ufeff')).splitlines() if l]
    if not lines or lines[0] != 'BEGIN:VCALENDAR' or lines[-1] != 'END:VCALENDAR':
        raise BuildError(f'{path}: must start with BEGIN:VCALENDAR and end with END:VCALENDAR')

    props, dates, stack, event = {}, [], [], None
    for line in lines:
        name, _, value = line.partition(':')
        key = name.split(';', 1)[0].upper()
        if key == 'BEGIN':
            stack.append(value.upper())
            if value.upper() == 'VEVENT':
                event = set()
        elif key == 'END':
            if not stack or stack[-1] != value.upper():
                raise BuildError(f'{path}: END:{value} does not close {stack[-1] if stack else "anything"}')
            stack.pop()
            if value.upper() == 'VEVENT':
                missing = {'UID', 'DTSTART', 'SUMMARY'} - event
                if missing:
                    raise BuildError(f'{path}: an event has no {", ".join(sorted(missing))}')
                event = None
        elif stack and stack[-1] == 'VEVENT':
            event.add(key)
            if key == 'DTSTART' and _ymd(value):
                dates.append(_ymd(value))
        elif stack == ['VCALENDAR']:
            props.setdefault(key, _unescape(value))
    if stack:
        raise BuildError(f'{path}: unclosed {stack[-1]}')
    return props, dates


def load_term(path):
    term_id, group = path.parent.name, path.stem
    if not TERM_RE.match(term_id):
        raise BuildError(f'{path}: term folder "{term_id}" must be lowercase letters, digits and dashes')
    if not GROUP_RE.match(group):
        raise BuildError(f'{path}: group code "{group}" must be 2-32 letters, digits and underscores')
    props, dates = read_calendar(path)
    declared = props.get('X-PLAN-GROUP')
    if declared and declared != group:
        raise BuildError(f'{path}: file is named {group} but X-PLAN-GROUP is {declared}')
    start = _ymd(props.get('X-PLAN-SEMESTER-START', '')) or (min(dates) if dates else None)
    end = _ymd(props.get('X-PLAN-SEMESTER-END', '')) or (max(dates) if dates else None)
    if not start or not end:
        raise BuildError(f'{path}: no X-PLAN-SEMESTER-START/END and no events to infer the term from')
    if dates:
        start, end = min(start, min(dates)), max(end, max(dates))
    end += dt.timedelta(days=6 - end.weekday())  # a term runs to the Sunday of its last week
    meta = {
        'group': group,
        'faculty': props.get('X-PLAN-FACULTY', ''),
        'term': props.get('X-PLAN-TERM', ''),
        'semester_start': _ymd(props.get('X-PLAN-SEMESTER-START', '')) or start,
        'semester_end': _ymd(props.get('X-PLAN-SEMESTER-END', '')) or end - dt.timedelta(days=1),
        'generated': _ymd(props.get('X-PLAN-GENERATED', '')),
    }
    return group, Term(term_id, path, start, end, meta)


def pick_term(terms, today):
    """The term running today; between terms the next one; after the last term the latest one."""
    running = [t for t in terms if t.start <= today <= t.end]
    if running:
        return max(running, key=lambda t: t.start)
    upcoming = [t for t in terms if t.start > today]
    if upcoming:
        return min(upcoming, key=lambda t: t.start)
    return max(terms, key=lambda t: t.start)


# ---------------------------------------------------------------- pages

def _sha(text):
    return "'sha256-" + base64.b64encode(hashlib.sha256(text.encode('utf-8')).digest()).decode() + "'"


def inline_hashes(page):
    scripts = [_sha(s) for s in re.findall(r'<script>(.*?)</script>', page, re.S)]
    styles = [_sha(s) for s in re.findall(r'<style>(.*?)</style>', page, re.S)]
    return scripts, styles


def csp(scripts, styles, connect, frame_ancestors=False):
    parts = [
        "default-src 'none'",
        'script-src ' + (' '.join(scripts) if scripts else "'none'"),
        'style-src ' + ' '.join(styles + [FONT_CSS]),
        f'font-src {FONT_FILES}',
        'img-src data:',
        'connect-src ' + ("'self'" if connect else "'none'"),
        "base-uri 'none'",
        "form-action 'none'",
    ]
    if frame_ancestors:  # header only
        parts.append("frame-ancestors 'none'")  # browsers ignore it in a meta tag
        # Redundant in the meta CSP (every source is https or 'self'), where WebKit would also apply it to
        # http://127.0.0.1 and break local previews; the header (always served over https) keeps it.
        parts.append('upgrade-insecure-requests')
    return '; '.join(parts)


def finish(page, connect):
    """Pin the page's inline code into its meta CSP and sanity-check the result."""
    if 'style="' in page:
        raise BuildError('inline style attributes would be blocked by the CSP')
    scripts, styles = inline_hashes(page)
    page = page.replace('@@CSP@@', f'<meta http-equiv="Content-Security-Policy" content="{csp(scripts, styles, connect)}">')
    left = re.findall(r'@@[A-Z_]+@@', page)
    if left:
        raise BuildError(f'unfilled template placeholders: {sorted(set(left))}')
    return page, scripts, styles


def _date(d):
    return d.strftime('%d.%m.%Y')


def render_group(template, ics_js, term):
    m = term.meta
    e = lambda v: html.escape(v, quote=True)  # noqa: E731
    description = f'Plan zajęć grupy {m["group"]}' + (f' — Wydział {m["faculty"]}' if m['faculty'] else '') + \
        (f', {m["term"]}' if m['term'] else '') + '.'
    values = {
        '@@GROUP@@': e(m['group']),
        '@@DESCRIPTION@@': e(description),
        '@@TERM_LINE@@': 'Plan zajęć &middot; ' + e(m['term']) if m['term'] else 'Plan zajęć',
        '@@FACULTY@@': e(m['faculty']),
        '@@HIDE_FACULTY@@': '' if m['faculty'] else ' hidden',
        '@@SEMESTER@@': f'{_date(m["semester_start"])} &ndash; {_date(m["semester_end"])}',
        '@@GENERATED@@': _date(m['generated']) if m['generated'] else '',
        '@@HIDE_GENERATED@@': '' if m['generated'] else ' hidden',
    }
    page = template.replace('@@ICS_JS@@', ics_js)  # first: the reader's own text is never substituted into
    for key, value in values.items():
        page = page.replace(key, value)
    return finish(page, connect=True)


def render_index(template, current):
    names = {code: (pl, en) for code, pl, en in FACULTIES}
    order = {code: i for i, (code, _, _) in enumerate(FACULTIES)}
    groups = sorted(current.items(), key=lambda kv: (order.get(faculty_of(kv[0]), len(order)), kv[0]))

    counts = {}
    for code, _ in groups:
        counts[faculty_of(code)] = counts.get(faculty_of(code), 0) + 1

    picker = ['  <div class="fac-grid" role="group" aria-label="Wybierz wydział">']
    picker.append('    <button class="fac is-all" type="button" data-facbtn="ALL" aria-pressed="true">'
                  f'<span class="fac-code">Wszystkie</span>'
                  f'<span class="fac-pl">Wszystkie wydziały</span>'
                  f'<span class="fac-n">{plural_grup(len(groups))}</span></button>')
    for code, pl, en in FACULTIES:
        n = counts.get(code, 0)
        picker.append(f'    <button class="fac" type="button" data-facbtn="{code}" aria-pressed="false">'
                      f'<span class="fac-code">{code}</span>'
                      f'<span class="fac-pl">{html.escape(pl)}</span>'
                      f'<span class="fac-en">{html.escape(en)}</span>'
                      f'<span class="fac-n">{plural_grup(n)}</span></button>')
    picker.append('  </div>')

    sections, fac, rows = [], None, []

    def flush():
        if rows:
            if fac == 'OTHER':
                title = 'Pozostałe grupy'
            else:
                title = f'{fac} &middot; {html.escape(names[fac][0])}'
            sections.append(f'  <section data-fac-section="{fac}">\n  <h2>{title}</h2>\n  <ul>\n'
                            + '\n'.join(rows) + '\n  </ul>\n  </section>')

    for code, term in groups:
        if faculty_of(code) != fac:
            flush()
            fac, rows = faculty_of(code), []
        label = html.escape(term.meta['term'] or term.term_id)
        rows.append(f'    <li data-group="{code}" data-fac="{faculty_of(code)}">'
                    f'<a class="group" href="{code}/"><span><span class="code">{code}</span>'
                    f'<span class="term">{label}</span></span><svg class="chev" viewBox="0 0 24 24" aria-hidden="true">'
                    '<path d="m9 18 6-6-6-6"/></svg></a></li>')
    flush()
    redirect = f'<meta http-equiv="refresh" content="0; url={groups[0][0]}/">' if len(groups) == 1 else ''
    page = template.replace('@@FACULTIES@@', '\n'.join(picker)).replace('@@GROUPS@@', '\n'.join(sections))
    page = page.replace('@@REDIRECT@@', redirect)
    return finish(page, connect=False)


def render_404(template, base_path):
    return finish(template.replace('@@BASE@@', html.escape(base_path.rstrip('/'), quote=True)), connect=False)


# ---------------------------------------------------------------- build

def _prepare_out(out):
    if out.exists():
        if any(out.iterdir()) and not (out / MARKER).exists():
            raise BuildError(f'{out} is not empty and was not created by build.py; refusing to delete it')
        shutil.rmtree(out)
    out.mkdir(parents=True)
    (out / MARKER).write_text('generated by build.py\n')


def update_nginx(conf_path, scripts, styles):
    policy = csp(sorted(set(scripts)), sorted(set(styles)), connect=True, frame_ancestors=True)
    conf, n = re.subn(r'add_header Content-Security-Policy "[^"]*"',
                      f'add_header Content-Security-Policy "{policy}"', conf_path.read_text())
    if n != 1:
        raise BuildError(f'{conf_path}: expected exactly one Content-Security-Policy add_header line, found {n}')
    conf_path.write_text(conf)


def build(timetables, out, today, base_path='', nginx_conf=None):
    files = sorted(Path(timetables).glob('*/*.ics'))
    if not files:
        raise BuildError(f'no calendars found in {timetables}/<term>/<GROUP>.ics')
    by_group = {}
    for path in files:
        group, term = load_term(path)
        by_group.setdefault(group, []).append(term)
    current = {group: pick_term(terms, today) for group, terms in by_group.items()}

    group_tpl = (SRC / 'group.html').read_text(encoding='utf-8')
    ics_js = (SRC / 'ics.js').read_text(encoding='utf-8')
    if '@@' in ics_js:
        raise BuildError('src/ics.js must not contain "@@"')

    out = Path(out)
    _prepare_out(out)
    all_scripts, all_styles = [], []

    def write(rel, page_scripts_styles):
        page, scripts, styles = page_scripts_styles
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(page.replace('\r\n', '\n'), encoding='utf-8')
        all_scripts.extend(scripts)
        all_styles.extend(styles)

    for group, term in sorted(current.items()):
        write(f'{group}/index.html', render_group(group_tpl, ics_js, term))
        shutil.copyfile(term.path, out / group / 'plan.ics')
    write('index.html', render_index((SRC / 'index.html').read_text(encoding='utf-8'), current))
    write('404.html', render_404((SRC / '404.html').read_text(encoding='utf-8'), base_path))

    if nginx_conf:
        update_nginx(Path(nginx_conf), all_scripts, all_styles)
    return {group: term.term_id for group, term in current.items()}


def _today_in_warsaw():
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo('Europe/Warsaw')).date()
    except Exception:  # no tz database: the UTC date is off by at most one night
        return dt.datetime.now(dt.timezone.utc).date()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--timetables', default=ROOT / 'timetables', type=Path)
    ap.add_argument('--out', default=ROOT / 'site', type=Path)
    ap.add_argument('--today', type=dt.date.fromisoformat, help='pick terms as of this date (YYYY-MM-DD)')
    ap.add_argument('--base-path', default='', help='URL path the site is served under, e.g. /PlanWAT')
    ap.add_argument('--nginx', type=Path, help='nginx.conf whose CSP header to pin (Docker build only)')
    args = ap.parse_args(argv)
    try:
        picked = build(args.timetables, args.out, args.today or _today_in_warsaw(), args.base_path, args.nginx)
    except BuildError as err:
        print(f'build failed: {err}', file=sys.stderr)
        return 1
    for group, term_id in sorted(picked.items()):
        print(f'{group}: {term_id}')
    print(f'built {len(picked)} group page(s) into {args.out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
