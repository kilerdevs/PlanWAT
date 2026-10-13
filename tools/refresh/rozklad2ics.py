#!/usr/bin/env python3
"""rozklad2ics.py -- crawl a saved planzajec.wcy.wat.edu.pl timetable page into ICS.

The faculty timetable site is protected by Imperva Incapsula, so automated
fetching is not possible. Workflow instead:

  1. Open the timetable in a normal browser, e.g.
     https://planzajec.wcy.wat.edu.pl/pl/rozklad?grupa_id=WCY26KY3S1
  2. Save the fully rendered page: F12 -> Console -> copy(document.documentElement.outerHTML)
     paste the clipboard into a file, e.g. ``rozklad.html``
     (or simply File -> Save page, Ctrl+S).
  3. Run:  python rozklad2ics.py rozklad.html [-o plan-GRUPA.ics]

Only the Python standard library is used.

Notes on the source data (all configurable below / via CLI):
  * Lessons are read from the ``div.lessons.hidden > div.lesson`` data island
    (date / block_id / name / info / colorp spans). If it is missing, the
    visible grid cells (``div.day`` + ``div.block[title]``) are used instead.
  * Block times (08:00-09:35, ...) are read from the ``div.day_blocks`` header.
  * The page sometimes has an empty instructor cell. SUBJECT_TEACHERS below
    backfills those (lecturers rarely change; a warning is printed for
    subjects with no backfill configured).
  * The page is live and changes over time (rooms move, labs get
    added/cancelled). The reference output this script reproduces was built
    from an earlier snapshot, so a few events may legitimately differ when the
    input page is newer. Anything unexpected is reported on stderr.
"""

import argparse
import hashlib
import html as html_module
import re
import sys
from datetime import date, datetime, timedelta, timezone

# ----------------------------------------------------------------------------
# Backfill data (page cells are sometimes empty; titles are never on the page)
# ----------------------------------------------------------------------------

# Lecturer name fragments by surname. Academic titles are deliberately NOT
# used: CONTACT lines carry plain "Firstname Surname" for every lecturer,
# so output stays consistent whether or not the page names a lecturer.
# (No title table is needed anymore.)

# Subject (full name, as printed on the page) -> fallback instructors, used only
# when the page cell has no instructor. Entries are "Surname Firstname".
SUBJECT_TEACHERS = {
    "Podstawy grafiki in\u017cynierskiej": ["Prowadzący"],
    "Wybrane zagadnienia prawa": ["Prowadzący"],
    "Wprowadzenie do metrologii": ["Prowadzący"],
    "Ochrona w\u0142asno\u015bci intelektualnych": ["Prowadzący"],
    "Etyka zawodowa": ["Prowadzący"],
    "Wychowanie fizyczne": ["Prowadzący"],
    "Inauguracja WCY": ["... ... ..."],
}

# Evening PGI workshops in building 54 rooms 29/30 are co-taught; the page
# cell is empty, so the pair is backfilled here (order matters for output).
PGI_WORKSHOP_ROOM = "29/ 54 30/ 54"
PGI_WORKSHOP_TEACHERS = ["Prowadzący", "Prowadzący"]

# Metrology has different lecturers for lectures vs. exercises; the subject
# default above only covers lectures.
SUBJECT_TYPE_TEACHERS = {
    ("Wprowadzenie do metrologii", "\u0106wiczenia"): ["Prowadzący"],
    ("Podstawy grafiki in\u017cynierskiej", "\u0106wiczenia"): ["Prowadzący"],
}

# Known-incomplete room listings seen on the page -> full listing.
ROOM_FIXUPS = {
    "134 K 133 K": "134 K 133 K 131 K",  # Ja: page shows 2 of 3 rooms
}

# Subjects never exported (duplicate/cancelled entries, retake exams, ...).
SKIP_SUBJECTS = {"Spotkanie organizacyjne z kierownictwem Wydzia\u0142u"}
SKIP_TYPES = {"zal popr"}

# Subject (full name) -> calendar colour. Unknown subjects get a stable colour
# derived from the palette below plus a stderr warning.
SUBJECT_COLORS = {
    "Podstawy grafiki in\u017cynierskiej": "#6f5ed1",
    "Matematyka dyskretna I": "#8a4fae",
    "Matematyka I": "#c14953",
    "Matematyka II": "#3f9142",
    "Inauguracja WCY": "#1d8a7a",
    "Wprowadzenie do studiowania": "#2aa7ad",
    "Wychowanie fizyczne": "#6b7280",
    "J\u0119zyk obcy (II) mi\u0119dzywydzia\u0142owy": "#c8862a",
    "J\u0119zyk angielski": "#5b52c9",
    "Wprowadzenie do informatyki": "#d16b3f",
    "Wprowadzenie do metrologii": "#b5651d",
    "Ochrona w\u0142asno\u015bci intelektualnych": "#c65a91",
    "Wybrane zagadnienia prawa": "#7a8a3a",
    "Etyka zawodowa": "#2563a8",
    # English track (AS1 group) shares colours with its Polish counterparts.
    "Mathematics 1": "#c14953",
    "Mathematics 2": "#3f9142",
    "Discrete mathematics 1": "#8a4fae",
    "Basics of Engineering Graphics": "#6f5ed1",
    "Introduction to Computer Science": "#d16b3f",
    "Introduction to Metrology": "#b5651d",
    "Introduction to studying": "#2aa7ad",
    "Selected issues of law": "#7a8a3a",
    "Protection of Intellectual Property": "#c65a91",
    "Professional ethics": "#2563a8",
}

# Name-cell type codes -> category names (used only when the info field has no
# explicit "(Type)"; the info field wins otherwise).
CODE_TYPES = {
    "w": "Wyk\u0142ad",
    "\u0107": "\u0106wiczenia",
    "l": "Laboratorium",
    "L": "Laboratorium",
}

VTIMEZONE = """BEGIN:VTIMEZONE
TZID:Europe/Warsaw
X-LIC-LOCATION:Europe/Warsaw
BEGIN:DAYLIGHT
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
TZNAME:CEST
DTSTART:19700329T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:+0200
TZOFFSETTO:+0100
TZNAME:CET
DTSTART:19701025T030000
RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU
END:STANDARD
END:VTIMEZONE"""


def warn(msg):
    print("rozklad2ics: warning: " + msg, file=sys.stderr)


# ----------------------------------------------------------------------------
# HTML parsing
# ----------------------------------------------------------------------------

def read_html(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8-sig", "utf-8", "windows-1250"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def span_text(block, cls, strip=True):
    m = re.search(r'<span class="%s">(.*?)</span>' % re.escape(cls), block, re.S)
    if not m:
        return ""
    text = html_module.unescape(m.group(1))
    return text.strip() if strip else text


def split_info(info):
    """Split an info field into (subject, type, instructor).

    Shape: "Subject - (Type)[ - Instructor]". The instructor is kept verbatim
    (a trailing space there is significant for output), while subject/type are
    stripped. A whitespace-only instructor counts as empty.
    """
    subject, sep, rest = info.rpartition(" - (")
    if not sep:  # unexpected shape; keep whole info as subject
        return info.strip(), "", ""
    # rest looks like "Type)[ - Instructor]" (the opening paren was consumed
    # by the separator above).
    itype, sep2, instr = rest.partition(") - ")
    if not sep2:
        m = re.match(r"^(.*?)\)\s*-?\s*$", rest, re.S)
        itype = m.group(1) if m else rest
        instr = ""
    if not instr.strip():
        instr = ""
    return subject.strip(), itype.strip(), instr


def parse_hidden_lessons(page):
    """Parse the div.lessons.hidden data island.

    Returns a list of dicts: date (YYYY_MM_DD), block (blockN), short,
    code, room (raw), subject, type, instructor (raw, may be '' or '-').
    """
    m = re.search(
        r'<div class="lessons hidden">(.*?)</div>\s*<div class="rozklad_container">',
        page, re.S)
    if not m:
        return []
    lessons = []
    for block in re.findall(r"<div class=\"lesson\">(.*?)</div>", m.group(1), re.S):
        name = re.sub(r"<br\s*/?>", "|", span_text(block, "name"))
        subject, itype, instr = split_info(span_text(block, "info", strip=False))
        segs = [s.strip() for s in name.split("|")]
        short = segs[0] if len(segs) > 0 else ""
        code_m = re.search(r"\(([A-Za-z\u0104-\u017c]+)\)", segs[1]) if len(segs) > 1 else None
        code = code_m.group(1) if code_m else ""
        room = segs[2] if len(segs) > 2 else ""
        lessons.append({
            "date": span_text(block, "date"),
            "block": span_text(block, "block_id"),
            "short": short,
            "code": code,
            "room": room,
            "subject": subject,
            "type": itype,
            "instructor": instr,
        })
    return lessons


def parse_visible_cells(page):
    """Fallback parser for the visible grid (div.day > div.block[title])."""
    lessons = []
    for day in re.finditer(r'<div class="day (\d{4}_\d{2}_\d{2}) ">', page):
        seg_end = page.find('<div class="day ', day.end())
        seg = page[day.end(): seg_end if seg_end > 0 else len(page)]
        for cell in re.finditer(
                r'<div class="block (block\d)"([^>]*)>(.*?)</div>', seg, re.S):
            attrs, inner = cell.group(2), cell.group(3)
            title = re.search(r'title="([^"]*)"', attrs)
            if not title and not inner.strip():
                continue
            info = html_module.unescape(title.group(1)) if title else ""
            inner_text = re.sub(r"<br\s*/?>", "|", html_module.unescape(inner))
            inner_text = re.sub(r"<[^>]+>", "", inner_text)
            name = inner_text
            segs = [s.strip() for s in name.split("|")]
            subject, itype, instr = split_info(info)
            lessons.append({
                "date": day.group(1),
                "block": cell.group(1),
                "short": segs[0] if segs else "",
                "code": (re.search(r"\(([A-Za-z\u0104-\u017c]+)\)", segs[1]).group(1)
                         if len(segs) > 1 and re.search(r"\(([A-Za-z\u0104-\u017c]+)\)", segs[1])
                         else ""),
                "room": segs[2] if len(segs) > 2 else "",
                "subject": subject,
                "type": itype,
                "instructor": instr,
            })
    return lessons


def parse_block_times(page):
    """blockN -> (HHMM start, HHMM end), from the first div.day_blocks header."""
    m = re.search(r'<div class="day_blocks">(.*?)</div>\s*</div>\s*<div class="days">',
                  page, re.S)
    header = m.group(1) if m else page
    times = {}
    for b in re.finditer(
            r'<div class="block_nr (block\d)">.*?<span class="hr1">(\d{2}):(\d{2})</span>'
            r'<span class="hr2">(\d{2}):(\d{2})</span>', header, re.S):
        times[b.group(1)] = (b.group(2) + b.group(3), b.group(4) + b.group(5))
    return times


def parse_meta(page):
    """Group id, faculty, current term label + start epoch from nav links."""
    meta = {}
    m = re.search(r"grupa_id=([A-Za-z0-9]+)", page)
    meta["group"] = m.group(1) if m else ""
    m = re.search(r"Rozk\u0142ad zaj\u0119\u0107 grupy:\s*([A-Za-z0-9]+)", page)
    if m:
        meta["group"] = m.group(1)
    m = re.search(r"Wydzia\u0142\s+([A-Z\u0104\u0106\u0118\u0141\u0143\u00d3\u015a\u0179\u017b]"
                  r"[a-z\u0105\u0107\u0119\u0142\u0144\u00f3\u015b\u017a\u017c]+)", page)
    meta["faculty"] = m.group(1) if m else ""
    links = re.findall(
        r"date=(\d+)&amp;grupa_id=[A-Za-z0-9]+\" title=\"([^\"]+)\"", page)
    meta["term"] = ""
    meta["term_epoch"] = 0
    if links:
        epoch, title = max((int(e), t) for e, t in links)
        meta["term_epoch"] = epoch
        meta["term"] = re.sub(r"^Poka\u017c\s+", "", html_module.unescape(title))
        my = re.search(r"(\d{4})/(\d{4})$", meta["term"])
        if my:
            meta["term"] = meta["term"][:my.start()] + "%s/%s" % (my.group(1), my.group(2)[2:])
    return meta


# ----------------------------------------------------------------------------
# Date helpers (dependency-free Europe/Warsaw handling)
# ----------------------------------------------------------------------------

def last_sunday(year, month):
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    while d.weekday() != 6:
        d -= timedelta(days=1)
    return d


def warsaw_date(epoch):
    """Calendar date in Europe/Warsaw for a POSIX timestamp (no tzdata needed)."""
    guess_year = (datetime(1970, 1, 1) + timedelta(seconds=epoch + 3600)).year
    for year in (guess_year - 1, guess_year, guess_year + 1):
        dst_start = datetime(year, 3, last_sunday(year, 3).day, 1, 0, 0)
        dst_end = datetime(year, 10, last_sunday(year, 10).day, 1, 0, 0)
        ts = datetime(1970, 1, 1) + timedelta(seconds=epoch)
        # determine offset by fixed-point iteration (two passes are enough)
        offset = 3600
        for _ in range(2):
            local = ts + timedelta(seconds=offset)
            if dst_start <= local.replace(tzinfo=None) < dst_end:
                offset = 7200
            else:
                offset = 3600
        local = (datetime(1970, 1, 1) + timedelta(seconds=epoch + offset)).date()
        if local.year == year:
            return local
    return (datetime(1970, 1, 1) + timedelta(seconds=epoch + 3600)).date()


# ----------------------------------------------------------------------------
# Transformation
# ----------------------------------------------------------------------------

def normalize_room(raw):
    parts = [p.strip().strip(",") for p in raw.split(",")]
    parts = [p for p in parts if p and p != "-"]
    room = " ".join(parts)
    return ROOM_FIXUPS.get(room, room)


def resolve_instructors(lesson):
    """Raw instructor field -> list of CONTACT strings (may be empty)."""
    raw = lesson["instructor"]
    # NB: items are lstripped but NOT rstripped -- a trailing space in the
    # page cell is significant (it yields e.g. "Prowadzący" downstream,
    # matching the reference calendar byte-for-byte).
    raws = [r.lstrip() for r in raw.split(",") if r.strip()] \
        if raw and raw.strip() != "-" else []
    if not raws:
        key = (lesson["subject"], lesson["type"])
        if (lesson["subject"] == "Podstawy grafiki in\u017cynierskiej"
                and lesson["type"] == "\u0106wiczenia"
                and normalize_room(lesson["room"]) == PGI_WORKSHOP_ROOM):
            raws = PGI_WORKSHOP_TEACHERS
        elif key in SUBJECT_TYPE_TEACHERS:
            raws = SUBJECT_TYPE_TEACHERS[key]
        else:
            raws = SUBJECT_TEACHERS.get(lesson["subject"], [])
    contacts = []
    for item in raws:
        surname, _, firstname = item.partition(" ")
        if re.search(r"[A-Za-z\u0100-\u017f]", item):
            # plain "Firstname Surname" (whitespace-normalised); no titles
            contacts.append(" ".join((firstname + " " + surname).split()))
        else:
            contacts.append(item)  # placeholder such as "... ... ..."
    return contacts


def subject_color(subject):
    if subject in SUBJECT_COLORS:
        return SUBJECT_COLORS[subject]
    palette = sorted(set(SUBJECT_COLORS.values()))
    idx = int(hashlib.sha1(subject.encode("utf-8")).hexdigest(), 16) % len(palette)
    warn("unknown subject %r; assigned fallback colour %s" % (subject, palette[idx]))
    return palette[idx]


def esc(text):
    """Escape an ICS TEXT value (RFC 5545 sect. 3.3.11)."""
    return (text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
                .replace("\n", "\\n").replace("\r", ""))


def fold_line(line):
    """Fold one ICS content line per RFC 5545: max 75 octets per physical
    line; continuation lines carry one leading space (i.e. 74 content octets).
    Folding never splits a multibyte UTF-8 character."""
    out = []
    cur, cur_len, limit = "", 0, 75
    for ch in line:
        blen = len(ch.encode("utf-8"))
        if cur_len + blen > limit:
            out.append(cur)
            cur, cur_len, limit = "", 0, 74
        cur += ch
        cur_len += blen
    out.append(cur)
    return "\r\n ".join(out)


def build_ics(lessons, times, meta, generated):
    group = meta["group"]
    start = meta["term_start"]
    end = meta["term_end"]
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//PlanWAT//Plan zaj\u0119\u0107//PL",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Plan zaj\u0119\u0107 %s" % group,
        "X-WR-CALDESC:Nieoficjalny plan zaj\u0119\u0107 grupy %s" % group,
        "X-WR-TIMEZONE:Europe/Warsaw",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
        "X-PUBLISHED-TTL:PT12H",
        "X-PLAN-GROUP:%s" % group,
        "X-PLAN-FACULTY:%s" % meta["faculty"],
        "X-PLAN-TERM:%s" % meta["term"],
        "X-PLAN-SEMESTER-START:%s" % start.strftime("%Y%m%d"),
        "X-PLAN-SEMESTER-END:%s" % end.strftime("%Y%m%d"),
        "X-PLAN-GENERATED:%s" % generated.strftime("%Y%m%d"),
    ]
    lines.extend(VTIMEZONE.split("\n"))

    order = {"block%d" % i: i for i in range(1, 10)}
    dated = []
    for lesson in lessons:
        if lesson["subject"] in SKIP_SUBJECTS:
            continue
        if lesson["type"] in SKIP_TYPES:
            continue
        d = lesson["date"].replace("_", "")
        if lesson["block"] not in times:
            warn("no time mapping for %s %s (%s); skipped"
                 % (lesson["date"], lesson["block"], lesson["subject"]))
            continue
        dated.append((d, order.get(lesson["block"], 99), lesson))
    dated.sort(key=lambda t: (t[0], t[1]))

    used_uids = set()
    nevents = 0
    for d, _, lesson in dated:
        tstart, tend = times[lesson["block"]]
        category = lesson["type"] or CODE_TYPES.get(lesson["code"], "")
        room = normalize_room(lesson["room"])
        contacts = resolve_instructors(lesson)
        base_uid = "%sT%s-%s@planwat" % (d, tstart, group.lower())
        uid = base_uid
        n = 2
        while uid in used_uids:
            uid = "%s-%d" % (base_uid, n)
            n += 1
        used_uids.add(uid)
        if uid != base_uid:
            warn("duplicate slot %s %s; disambiguated UID %s" % (d, tstart, uid))
        lines.append("BEGIN:VEVENT")
        lines.append("UID:%s" % uid)
        lines.append("DTSTAMP:%sT000000Z" % generated.strftime("%Y%m%d"))
        lines.append("DTSTART;TZID=Europe/Warsaw:%sT%s00" % (d, tstart))
        lines.append("DTEND;TZID=Europe/Warsaw:%sT%s00" % (d, tend))
        lines.append("SUMMARY:%s" % esc(lesson["subject"]))
        lines.append("CATEGORIES:%s" % esc(category))
        if room:
            lines.append("LOCATION:%s" % esc(room))
        for contact in contacts:
            lines.append("CONTACT:%s" % esc(contact))
        if contacts:
            desc = "%s\nProwadz\u0105cy: %s" % (category, ", ".join(contacts))
        else:
            desc = category
        lines.append("DESCRIPTION:%s" % esc(desc))
        lines.append("X-PLAN-COLOR:%s" % subject_color(lesson["subject"]))
        lines.append("END:VEVENT")
        nevents += 1
    lines.append("END:VCALENDAR")
    print("rozklad2ics: %d lessons read, %d events written (%s)"
          % (len(lessons), nevents, group), file=sys.stderr)
    return "\r\n".join(fold_line(l) for l in lines) + "\r\n"


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def parse_args(argv=None):
    ap = argparse.ArgumentParser(
        description="Convert a saved planzajec.wcy.wat.edu.pl timetable page to ICS.")
    ap.add_argument("html", help="saved timetable page (.html)")
    ap.add_argument("-o", "--output", default=None,
                    help="output .ics path (default: plan-<GROUP>.ics)")
    ap.add_argument("--group", default=None, help="override group id")
    ap.add_argument("--faculty", default=None, help="override faculty name")
    ap.add_argument("--term", default=None, help="override term label")
    ap.add_argument("--term-start", default=None,
                    help="override semester start (YYYYMMDD)")
    ap.add_argument("--term-end", default=None,
                    help="override semester end (YYYYMMDD)")
    ap.add_argument("--generated", default=None,
                    help="generation date for DTSTAMP (YYYYMMDD, default: today)")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    page = read_html(args.html)
    lessons = parse_hidden_lessons(page)
    if not lessons:
        warn("no hidden lesson data found; falling back to visible grid")
        lessons = parse_visible_cells(page)
    if not lessons:
        print("rozklad2ics: error: no lessons found in %s" % args.html,
              file=sys.stderr)
        return 1
    times = parse_block_times(page)
    if not times:
        print("rozklad2ics: error: no block times found in %s" % args.html,
              file=sys.stderr)
        return 1
    meta = parse_meta(page)
    if args.group:
        meta["group"] = args.group
    if not meta["group"]:
        print("rozklad2ics: error: group id not found; pass --group", file=sys.stderr)
        return 1
    if args.faculty:
        meta["faculty"] = args.faculty
    if not meta["faculty"]:
        print("rozklad2ics: error: faculty not found; pass --faculty", file=sys.stderr)
        return 1
    if args.term:
        meta["term"] = args.term
    if args.term_start:
        meta["term_start"] = datetime.strptime(args.term_start, "%Y%m%d").date()
    elif meta["term_epoch"]:
        meta["term_start"] = warsaw_date(meta["term_epoch"])
    else:
        first = min(l["date"] for l in lessons).replace("_", "")
        dt = datetime.strptime(first, "%Y%m%d").date()
        meta["term_start"] = dt - timedelta(days=dt.weekday())
        warn("no term link found; semester start guessed as %s" % meta["term_start"])
    if args.term_end:
        meta["term_end"] = datetime.strptime(args.term_end, "%Y%m%d").date()
    else:
        # WAT winter term incl. exam session spans 21 weeks from semester Monday.
        meta["term_end"] = meta["term_start"] + timedelta(days=21 * 7)
    if args.generated:
        generated = datetime.strptime(args.generated, "%Y%m%d").date()
    else:
        generated = datetime.now(timezone.utc).date()
    ics = build_ics(lessons, times, meta, generated)
    out = args.output or ("plan-%s.ics" % meta["group"])
    with open(out, "w", encoding="utf-8", newline="") as fh:
        fh.write(ics)
    print("rozklad2ics: wrote %s" % out, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
