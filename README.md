<div align="center">

# PlanWAT

**Phone-first timetables for WAT study groups, one link per group, rendered from iCalendar files.**

[![CI](https://github.com/kilerdevs/PlanWAT/actions/workflows/ci.yml/badge.svg)](https://github.com/kilerdevs/PlanWAT/actions/workflows/ci.yml)
[![SAST](https://github.com/kilerdevs/PlanWAT/actions/workflows/sast.yml/badge.svg)](https://github.com/kilerdevs/PlanWAT/actions/workflows/sast.yml)
[![Pages](https://github.com/kilerdevs/PlanWAT/actions/workflows/pages.yml/badge.svg)](https://github.com/kilerdevs/PlanWAT/actions/workflows/pages.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat)](LICENSE)
[![Last commit](https://img.shields.io/github/last-commit/kilerdevs/PlanWAT?style=flat&logo=github)](https://github.com/kilerdevs/PlanWAT/commits)

</div>

## Disclaimer

PlanWAT is an **unofficial student project**. It is not affiliated with or endorsed by Wojskowa Akademia Techniczna,
and it uses no WAT branding. The official plan and e-dziekanat stay authoritative for changes and extra dates; the site
says so whenever a week has no regular classes.

## Contents

- [Overview](#overview)
- [Features](#features)
- [How it works](#how-it-works)
- [Adding or updating a timetable](#adding-or-updating-a-timetable)
- [Development](#development)
- [Deployment](#deployment)
- [Security](#security)
- [Branches and releases](#branches-and-releases)
- [License](#license)

## Overview

The official timetable is a large table built for desktop. PlanWAT turns the same data into a week view that reads well
on a phone, shows what is on **now** and **next** at a glance, and gives every group one stable link that always opens
the current week.

| | |
|---|---|
| Group page | `https://kilerdevs.github.io/PlanWAT/<GROUP>/`, for example [`/WCY26KY3S1/`](https://kilerdevs.github.io/PlanWAT/WCY26KY3S1/) |
| Calendar file | `…/<GROUP>/plan.ics`: download it, or subscribe to it in a calendar app |
| All groups | `https://kilerdevs.github.io/PlanWAT/`: lists every group, and goes straight to the group while there is only one |

The interface is Polish; the code and documentation are English.

## Features

- **Live card:** the class on now (or next today), its room, time and progress; tapping it jumps to the class.
- **Week view:** on phones each day is a grouped list; on wide screens the week becomes a day × time-slot grid. Past days
  and finished classes recede; the class in progress fills its colour capsule as it runs.
- **Navigation:** arrows, swipe, keyboard (`←` `→` `T` `Esc`), a week picker sheet, and a "Bieżący tydzień" pill to jump
  back. Phones scroll to the current class on open.
- **Three views:** Tydzień, **Lista** (today onwards, past days on request) and **Miesiąc** (tap a day to open its week);
  breaks of 30 minutes or more show as "Okienko" between classes.
- **Subject legend** that highlights one subject across the week, and **subject progress** (classes done out of the
  total, the next one, the count per class type).
- **Gdzie odrobić?** finds the same class in the other groups of the year, marking the ones that clash with your plan.
- **Porównaj grupy:** up to four plans side by side, week by week, with the time all of them are free.
- **Statystyki:** hours per week, per weekday and per class type, earliest start, latest end, longest day, breaks.
- **Download, subscribe** (Google Calendar, Apple Calendar via webcal, a copyable feed link) and **share** the plan;
  **print / PDF** the shown week or list.
- **Favourites and recent groups** on the front page, and a notice when the plan changed since your last visit. These
  live only in the browser's storage: no account, no tracking, everything is free.
- **Accessible and fast:** WCAG 2.1 AA contrast, keyboard and screen-reader support, `prefers-reduced-motion` respected,
  no framework and no third-party scripts.

The visual system (iOS-style dark theme, one blue accent, SF / Inter) is recorded in [DESIGN.md](DESIGN.md); product
facts and constraints are in [PRODUCT.md](PRODUCT.md).

## How it works

```
timetables/<term>/<GROUP>.ics          source of truth: one iCalendar file per group and term
            │
            ▼  python3 build.py        validates every calendar, picks each group's current term,
            │                          writes pages with a hash-pinned Content-Security-Policy
            ▼
site/index.html                        group list (redirects while there is only one group)
site/<GROUP>/index.html                the timetable page
site/<GROUP>/plan.ics                  byte-for-byte copy of the group's current term
site/data/groups.json,                group list and each year's classes, read on demand
     year/<PREFIX>.json                by "Porównaj grupy" and "Gdzie odrobić?"
site/404.html
            │
            ▼  GitHub Pages            deployed on every push to master and rebuilt daily,
                                       so a new term goes live on its first day
```

In the browser, the group page fetches `plan.ics` and renders it with [`src/ics.js`](src/ics.js), a small RFC 5545 reader
(folded lines, escaping, time zones, weekly repeats, excluded dates). Nothing is pre-rendered into the page, so the
calendar file and the page can never disagree. [`src/insights.js`](src/insights.js) computes the statistics, subject
progress, plan changes, shared free time, and catch-up classes; it is pure and unit-tested like the reader.

## Adding or updating a timetable

1. Put the calendar at `timetables/<term>/<GROUP>.ics`, for example `timetables/2027-lato/WCY26KY3S1.ics`.
   - `<term>`: lowercase letters, digits and dashes. `<GROUP>`: the WAT group code, letters, digits and underscores.
   - The file must be UTF-8 with CRLF line endings (`.gitattributes` keeps them intact).
2. Follow the [calendar format](docs/ICS-FORMAT.md): standard events plus a few `X-PLAN-*` properties for the header
   (group, faculty, term, semester dates).
3. Run `python3 build.py` (it refuses a malformed calendar and says why) and `npm test`.
4. Open a pull request against `dev`.

A group can have several terms. The build serves the term that is running on the build date; between terms, the next
one; after the last term, the latest. Older terms stay in the repository as history.

Not comfortable with Git? Open a [timetable issue](https://github.com/kilerdevs/PlanWAT/issues/new?template=timetable.yml)
with the group code and a link to the official plan.

## Development

Requirements: **Python 3.12+** (build, standard library only) and **Node.js 22+** (tests only; the site ships no npm
packages).

```bash
npm ci                                  # test tooling: Playwright and axe-core
npx playwright install chromium         # once; add firefox webkit for the full matrix

python3 build.py                        # build site/ for today
npm run test:unit                       # calendar reader (node:test) + build tests (unittest)
npm run build && npm run test:e2e       # browser tests against site/ with a frozen clock
npm test                                # all of the above
```

Preview the built site with `node tests/e2e/serve.js` (http://127.0.0.1:4173), which serves it the way GitHub Pages does.

```
build.py                 static site generator (standard library only)
src/group.html           group page template: markup, styles and app script (inlined, CSP-hashed)
src/ics.js               iCalendar reader, inlined into every group page
src/insights.js          statistics, progress, comparison and catch-up, inlined into every group page
src/index.html, 404.html group list and not-found page
timetables/              <term>/<GROUP>.ics, the data
tests/                   ics.test.js (reader), insights.test.js, test_build.py (build), e2e/ (Playwright), fixtures/
tools/export_ics.py      one-time export of the original page's data into the first calendar
deploy/nginx.conf        nginx template for the self-hosted Docker image
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for conventions and the pull-request checklist.

## Deployment

- **GitHub Pages** (primary): [`.github/workflows/pages.yml`](.github/workflows/pages.yml) builds and deploys on every
  push to `master` or `dev`, on a daily schedule (term changes) and on demand. It publishes production from `master`
  at the site root plus a preview of `dev` under `/dev/` (linked from the front page footer).
- **Docker** (self-hosted): `docker compose up -d --build` builds the site inside the image and serves it from a
  read-only, unprivileged nginx on `127.0.0.1:8088`, with security headers.

Moving a custom domain from the Docker host to GitHub Pages, and the Cloudflare rules that restore the security
headers Pages cannot send, are described in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Security

- Every page carries a **hash-pinned Content-Security-Policy**: only its own inline script and style run, it may fetch
  only its own `plan.ics`, and the only external origin is Google Fonts.
- Calendar text is rendered with `textContent` in the browser and HTML-escaped at build time; colours are accepted only as
  `#rrggbb`.
- CI runs CodeQL (JavaScript, Python, workflows), a Grype scan of the Docker image, and dependency audits. Actions are
  pinned to commit SHAs and base images to digests.

Please report vulnerabilities privately; see [SECURITY.md](SECURITY.md).

## Branches and releases

- Work lands on **`dev`**; releases are pull requests from `dev` into **`master`**, which deploys.
- `master` requires **signed commits** and passing checks (unit, build, browser tests, Docker image, CodeQL).
- Changes are recorded in [CHANGELOG.md](CHANGELOG.md) ([Keep a Changelog](https://keepachangelog.com/), SemVer).

## License

[MIT](LICENSE). Icons are from [Lucide](https://lucide.dev) (ISC); the Inter typeface is loaded from Google Fonts (SIL
OFL 1.1). See [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md).
