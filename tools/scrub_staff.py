#!/usr/bin/env python3
"""Remove staff personal data from published calendars (one-off migration).

The pre-scrub converters wrote CONTACT lines and DESCRIPTION instructor
(`Prowadzący:`) segments naming staff (names, surnames, academic titles).
Current converters no longer emit them and build.py refuses them, but
calendars published earlier (the `data` branch) still carry them. This
rewrites such files:

- drop every CONTACT, ORGANIZER and ATTENDEE line, at any level,
- drop every part of a LOCATION that names a person (a title and a name, or a lecturer alias such as `AKowalski`;
  the real rooms beside it stay, and a LOCATION with nothing left goes whole),
- drop every segment of an event's DESCRIPTION that build.py does not allow
  (`Prowadzący:` and any other line that is not the class type, an
  `Uwaga:` note or the `Grupy:` list) or that names someone (other
  segments stay; a DESCRIPTION with nothing left goes whole — CATEGORIES
  keeps the category),
- cut a SUMMARY, CATEGORIES, COMMENT or calendar-level text (X-WR-CALNAME,
  X-WR-CALDESC, ...) where a title before a name starts ("Podstawy
  toksykologii plk dr Wachna Piotr" -> "Podstawy toksykologii"),
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
    """build.py's rule for free text: no instructor label, no title before a name."""
    return 'prowadzący:' not in value.lower() and not build._TITLED.search(value)


def scrub_description(line, kinds):
    """An unfolded DESCRIPTION line -> (line, changed) or (None, True) when
    the whole line must go (nothing build.py accepts is left). A segment
    stays when it is one build.py allows (`kinds`: the event's CATEGORIES)
    and names no one."""
    head, _, value = line.partition(':')
    segs = [s for s in value.split('\\n')
            if staff_free(s) and build.description_line_ok(build._unescape(s), kinds)]
    if not segs or not staff_free('\\n'.join(segs)):
        return None, True  # still names staff: drop the line whole
    if len(segs) != len(value.split('\\n')):
        return head + ':' + '\\n'.join(segs), True
    return line, False


def scrub_titled(line):
    """An unfolded free-text line (SUMMARY, a calendar name) -> (line, changed),
    or (None, True) when nothing is left. A name follows the subject
    ('Podstawy toksykologii plk dr Wachna Piotr'), so the text is cut where
    the title starts; a SUMMARY cut to nothing goes, and verify refuses it."""
    head, _, value = line.partition(':')
    if staff_free(value):
        return line, False
    m = build._TITLED.search(value) or re.search('(?i)prowadzący:', value)
    value = re.sub(r'[\s,;:(\\-]+$', '', value[:m.start()])
    return (head + ':' + value if value else None), True


def event_kinds(raw, i):
    """The CATEGORIES of the event whose BEGIN:VEVENT is raw[i], as build.event_kinds gives them."""
    for j in range(i + 1, len(raw)):
        key = raw[j].split(':', 1)[0].split(';', 1)[0].upper()
        if key == 'END':
            break
        if key == 'CATEGORIES':
            k = j + 1
            while k < len(raw) and raw[k][:1] in (' ', '\t'):
                k += 1
            return build.event_kinds((raw[j] + ''.join(l[1:] for l in raw[j + 1:k])).partition(':')[2])
    return set()


def scrub_location(line):
    """An unfolded LOCATION line -> (line, changed) or (None, True) when no room is left.

    The value is split on ';' and ',' (escaped or not) and every part naming a person is dropped together with
    one neighbouring separator; the surviving parts keep their own bytes."""
    head, _, value = line.partition(':')
    pieces = re.split(r'(\\[;,]|[;,])', value)  # part, sep, part, sep, ..., part
    parts, seps = pieces[0::2], pieces[1::2]
    keep = [i for i, part in enumerate(parts) if not build._names_person(part)]
    if len(keep) == len(parts):
        return line, False
    kept = [(parts[i], seps[i] if i < len(seps) else '') for i in keep if parts[i].strip()]
    if not kept:
        return None, True
    text = ''.join(part + sep for part, sep in kept[:-1]) + kept[-1][0]
    return head + ':' + text, True


def scrub_text(text):
    """A whole calendar -> scrubbed calendar (CRLF), or None when the file
    is already clean and CRLF. Only touched lines change bytes."""
    bom = text.startswith('\ufeff')
    raw = text.lstrip('\ufeff').replace('\r\n', '\n').replace('\r', '\n').split('\n')
    if raw and raw[-1] == '':
        raw.pop()  # the final newline, re-added on write
    out, removed = [], 0
    i, stack, kinds = 0, [], set()
    while i < len(raw):
        line = raw[i]
        key = line.split(':', 1)[0].split(';', 1)[0].upper()
        if key == 'BEGIN':
            stack.append(line.partition(':')[2].strip().upper())
            if stack[-1] == 'VEVENT':
                kinds = event_kinds(raw, i)
        elif key == 'END' and stack:
            stack.pop()
        if key in build.STAFF_PROPS:
            j = i + 1
            while j < len(raw) and raw[j][:1] in (' ', '\t'):
                j += 1
            removed += 1
            i = j
            continue
        if key == 'LOCATION' or key in build.TEXT_PROPS or stack == ['VCALENDAR'] and key not in ('BEGIN', 'END'):
            j = i + 1
            while j < len(raw) and raw[j][:1] in (' ', '\t'):
                j += 1
            logical = raw[i] + ''.join(l[1:] for l in raw[i + 1:j])
            if key == 'DESCRIPTION' and stack[-1:] == ['VEVENT']:
                new, changed = scrub_description(logical, kinds)
            elif key == 'LOCATION':
                new, changed = scrub_location(logical)
            else:
                new, changed = scrub_titled(logical)
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
