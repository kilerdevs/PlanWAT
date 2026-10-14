# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Students of WAT (Wojskowa Akademia Techniczna) study groups. It starts with one group, WCY26KY3S1 (Wydział Cybernetyki, semestr zimowy 2026/27), and is meant to grow to other WAT groups and years. They open it on their phones, usually from a link shared in the group chat. The job: find out which class is on now or next, where it is (room), and what the rest of the week looks like.

## Product Purpose

A fast, phone-first view of a group's official WAT timetable. Success means students open PlanWAT instead of the official plan or e-dziekanat when they want to know "what, when, where". The link they keep in the chat always lands on the current week.

## Positioning

The official WAT plan is a large table built for desktop. This site turns the same data into a week view that reads well on a phone. It shows what's on now and what's next at a glance, and one stable link always opens the current week. It should also be pleasant and good-looking enough that students prefer opening it.

## Operating Context

- Opened on phones, often in a hurry: between classes, on the way to a building, or from the group chat.
- The same URL is shared with the whole group and opened by anyone who has it. The site is public, with no logins.
- The authoritative source for changes and extra dates stays the official plan / e-dziekanat. The site points there when a week has no regular classes (exam session or break).
- The semester runs 28.09.2026 – 22.02.2027 as 22 weeks. The current data was generated on 28.09.2026.

## Capabilities and Constraints

- **Current capabilities:**
  - Week-by-week navigation: arrows, a week picker sheet, keyboard ←/→/T and swipe.
  - Opens on the current week, with a "today" marker and a "Bieżący tydzień" shortcut back to it.
  - A Live card at the top shows the class on now (or next today), its room and its progress; tapping it jumps to that class.
  - Live "Teraz" (now) and "Następne" (next) status with a countdown on today's classes.
  - Semester progress.
  - A subject legend that highlights one subject across the week.
  - Walking time between classes in different buildings, flagged when the walk is longer than the break.
  - Offline: a service worker keeps the opened pages and plans; each group can be installed as a home-screen app.
  - Calendar feed with a reminder 15 minutes before each class (`plan-przypomnienia.ics`).
  - Public-site basics: privacy notice and terms at `/prywatnosc/`, "PlanWAT never asks for your password" in the footer, `robots.txt`, `/.well-known/security.txt`.
  - Campus map at `/mapa/`: building markers by faculty, search, walking directions; rooms in the plan link to their building and each day opens its classes on the map.
  - Dark and light themes: the system's choice by default, with an Auto / Ciemny / Jasny switch (stored in the browser only). The map stays dark. This restores a switch the 2026-10-11 redesign had removed; dark remains the reference design.
- **Terminology** (keep in Polish): blok (one class slot), Wykład / Ćwiczenia / Laboratorium / Zaliczenie / Spotkanie organizacyjne, tydzień, sesja egzaminacyjna, e-dziekanat. Group codes follow the WAT format, e.g. `WCY26KY3S1`.
- **Technical setup:**
  - Timetables live in `timetables/<term>/<GROUP>.ics` (iCalendar, RFC 5545; format in `docs/ICS-FORMAT.md`). `build.py` validates them, picks each group's current term by date and writes `site/`: `/<GROUP>/index.html` + `/<GROUP>/plan.ics`, a group list at `/` (redirects while there is one group) and `404.html`. The group page fetches `plan.ics` and renders it in the browser with `src/ics.js` (tests: `tests/ics.test.js`, `tests/test_build.py`, `tests/e2e/`).
  - Group, faculty, term, semester range and generation date come from the calendar's `X-PLAN-*` properties; each class uses `SUMMARY` (subject), `CATEGORIES` (type), `LOCATION` (room) and `X-PLAN-COLOR` (subject colour).
  - `/<GROUP>/plan.ics` is public, so the same link also works as a calendar subscription.
  - Served by a hardened, read-only, non-root nginx container (`PLAN-WAT`, localhost:8088), for self-hosting behind a reverse proxy. GitHub Pages (repository kilerdevs/PlanWAT) is the target deployment.
- **Security** (the owner's explicit requirement: "as secure as possible, used by public"):
  - Strict Content-Security-Policy with hash-pinned inline script and style. The only external origin is Google Fonts (the campus map page alone adds SRI-pinned MapLibre from unpkg and OpenFreeMap tiles); `connect-src 'self'` lets the page fetch only its own `plan.ics`. Each page carries the CSP in a meta tag (GitHub Pages cannot send headers); the Docker image also sends it as a header.
  - Only GET/HEAD requests, rate limiting, and standard security headers.
  - Third-party scripts aren't banned outright, but any addition must fit the CSP and be justified.
- **Performance:** must stay smooth on ordinary phones. Heavy effects such as backdrop blur, continuous repaints and filters on many elements made the page lag on the owner's phone. Rich motion belongs on capable desktop devices only, and reduced-motion preferences are respected.
- **Open decisions:**
  - Who produces new calendars when the official plan changes (hand edits, a script, an official export). Updating means a pull request to `dev` that adds or edits `timetables/<term>/<GROUP>.ics`; Pages deploys from `master`.
  - Decided 2026-10-11: one URL per group (`/<GROUP>/`), always showing that group's current term.

## Brand Commitments

- Name: PlanWAT (repository kilerdevs/PlanWAT, container PLAN-WAT). The public domain is not named in the repository.
- The interface is Polish-only.
- Unofficial student project: no WAT logos, crest or wording that implies it is an official university page.

## Evidence on Hand

- Real timetable data for WCY26KY3S1: 22 weeks, 216 class blocks, with subjects, types, rooms and per-subject colours, in `timetables/2026-27-zima/WCY26KY3S1.ics`. It was exported once by `tools/export_ics.py` from the original page, which is kept as `tests/fixtures/v1-page.html`; the parser output for the current calendar is pinned in `tests/fixtures/wcy26ky3s1.plan.json`.
- None of the following exist; do not fabricate them: data for other groups, usage numbers, testimonials, endorsements, or any WAT-provided assets.

## Product Principles

1. **One glance answers what, when, where.** The current week, the class on now or next, and its room come before everything else.
2. **Phone-first and smooth.** Delight never costs scroll smoothness or load time on an ordinary phone.
3. **The link is the product.** One stable URL, opened from a chat, always shows the right week for whoever opens it.
4. **Honest and unofficial.** It is clearly a student-made view of the official plan, and it defers to e-dziekanat for authoritative changes.
5. **Grows to more groups without losing the single-group glance.**
