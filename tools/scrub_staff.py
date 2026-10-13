#!/usr/bin/env python3
"""Remove staff personal data from published calendars (one-off migration).

The pre-scrub converters wrote CONTACT lines and DESCRIPTION instructor
(`Prowadzący:`) segments naming staff (names, surnames, academic titles).
Current converters no longer emit them and build.py refuses them, but
calendars published earlier (the `data` branch) still carry them. This
rewrites such files:

- drop every CONTACT line,
- drop every `Prowadzący:` segment of DESCRIPTION (other segments stay;
  a DESCRIPTION that would still name staff is dropped whole, since
  build.py refuses the file otherwise — CATEGORIES keeps the category),
- normalize line endings to CRLF (the project standard, enforced by CI).

Only touched lines change: every other line keeps its exact bytes (no
re-folding), so the transform is byte-stable on already-clean files
(verify: `--apply` on the repository timetables rewrites nothing).

Usage: python tools/scrub_staff.py [--check | --apply] <tree>
`<tree>` holds timetables/<term>/<GROUP>.ics. `--check` (default) reports
files with hits and exits 1 when there are any; `--apply` rewrites them,
verifying each file first (same event count, still passes build.load_term,
no staff names left) and refusing to write otherwise.
"""
import argparse
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE / 'refresh'))
import build  # noqa: E402
from wlo2ics import fold_line  # noqa: E402 (the shared 75/74-octet folding)


def staff_free(value):
    """build.py's rule: no CONTACT, no instructor segment in DESCRIPTION."""
    return 'prowadzący:' not in value.lower()


def scrub_description(line):
    """An unfolded DESCRIPTION line -> (line, changed) or (None, True) when
    the whole line must go (it would still name staff)."""
    head, _, value = line.partition(':')
    segs = [s for s in value.split('\\n')
            if not s.strip().lower().startswith('prowadzący:')]
    if not segs or not staff_free('\\n'.join(segs)):
        return None, True  # still names staff: drop the line whole
    if len(segs) != len(value.split('\\n')):
        return head + ':' + '\\n'.join(segs), True
    return line, False


def scrub_text(text):
    """A whole calendar -> scrubbed calendar (CRLF), or None when the file
    is already clean and CRLF. Only touched lines change bytes."""
    bom = text.startswith('\ufeff')
    raw = text.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n').split('\n')
    if raw and raw[-1] == '':
        raw.pop()  # the final newline, re-added on write
    out, removed = [], 0
    i = 0
    while i < len(raw):
        line = raw[i]
        key = line.split(':', 1)[0].split(';', 1)[0].upper()
        if key == 'CONTACT':
            removed += 1
            i += 1
            continue
        if key == 'DESCRIPTION':
            j = i + 1
            while j < len(raw) and raw[j][:1] in (' ', '\t'):
                j += 1
            logical = raw[i] + ''.join(l[1:] for l in raw[i + 1:j])
            new, changed = scrub_description(logical)
            removed += changed
            if changed:
                if new is not None:
                    out.extend(fold_line(new).split('\r\n'))
            else:
                out.extend(raw[i:j])  # untouched: byte-identical passthrough
            i = j
            continue
        out.append(line)
        i += 1
    canonical = ('\ufeff' if bom else '') + '\r\n'.join(out) + '\r\n'
    if canonical == text:
        return None
    return canonical, removed


def verify(path, before, after):
    """(ok, reason): the scrub kept the plan and the file builds name-free."""
    if after.count('BEGIN:VEVENT') != before.count('BEGIN:VEVENT'):
        return False, 'event count changed'
    if re.search(r'^CONTACT:', after, re.M):
        return False, 'CONTACT left'
    import tempfile
    group = re.search(r'^X-PLAN-GROUP:(.*)$', after, re.M)
    with tempfile.TemporaryDirectory() as tmp:
        # load_term wants the file under a valid term folder.
        probe = Path(tmp) / 't' / ((group.group(1).strip() if group else 'probe') + '.ics')
        probe.parent.mkdir()
        probe.write_text(after, encoding='utf-8')
        try:
            build.load_term(probe)
        except build.BuildError as err:
            return False, f'rejected: {err}'
    return True, ''


def files_in(tree):
    return sorted(Path(tree).glob('timetables/*/*.ics'))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('tree', help='checkout holding timetables/<term>/<GROUP>.ics')
    ap.add_argument('--check', action='store_true', help='report only (default)')
    ap.add_argument('--apply', action='store_true', help='rewrite files in place')
    args = ap.parse_args(argv)
    if args.check == args.apply:
        ap.error('one of --check or --apply is required')
    files = files_in(args.tree)
    if not files:
        print(f'no calendars in {args.tree}/timetables/*/*.ics')
        return 2
    hits, endings, rewritten, failed = 0, 0, 0, 0
    for path in files:
        try:
            before = path.read_bytes().decode('utf-8')
        except UnicodeDecodeError:
            print(f'{path}: not UTF-8, skipped')
            failed += 1
            continue
        result = scrub_text(before)
        if result is None:
            continue
        after, removed = result
        if args.check:
            if removed:
                hits += 1
                print(f'{path}: names staff')
            else:
                endings += 1
            continue
        ok, why = verify(path, before, after)
        if not ok:
            print(f'{path}: REFUSED ({why}), left untouched')
            failed += 1
            continue
        path.write_bytes(after.encode('utf-8'))
        rewritten += 1
    if args.check:
        if endings:
            print(f'{endings} of {len(files)} calendars only need CRLF endings')
        print(f'{hits} of {len(files)} calendars name staff')
        return 1 if hits else 0
    print(f'rewrote {rewritten} of {len(files)} calendars, {failed} refused')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
