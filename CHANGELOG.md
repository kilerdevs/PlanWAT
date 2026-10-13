# Changelog

[![Keep a Changelog](https://img.shields.io/badge/changelog-Keep%20a%20Changelog-E05735?style=flat)](https://keepachangelog.com/en/1.1.0/)
[![SemVer](https://img.shields.io/badge/versioning-SemVer-3F4551?style=flat)](https://semver.org/spec/v2.0.0.html)
[![Latest tag](https://img.shields.io/github/v/tag/kilerdevs/PlanWAT?style=flat&label=latest)](https://github.com/kilerdevs/PlanWAT/tags)

All notable changes to PlanWAT are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versioning is semver.

## [Unreleased]

### Added
- Group page: "Zaktualizowano" and "Sprawdzono" dates from the refresh, and a pledge by the maintainer that PlanWAT stays free
  (also in the front page footer).
- Automatic refresh: a scheduled workflow re-reads the WLO, WEL and WIM timetable pages (WCY and WTC drivers are
  prepared, disabled), validates the calendars and publishes them through a `data` branch that the Pages build overlays.
  It runs on a self-hosted runner only, because the faculty sites block GitHub's datacenter addresses. See docs/REFRESH.md.
- Front page: "Teraz w Twoich grupach" cards (what is on now or next in the favourite groups), faculty filter chips,
  intake-year headings, star buttons on every group row, expand/collapse all, `/` to search, `?q=` links, clear buttons,
  a rewritten footer (unofficial project, no cookies).
- Timetables for 23 WTC groups (e.g. `WTC26NX1S1`, `WTC22CO1S0`), converted from the
  WTC Plansoft timetables (`WTC zima 2026/2027`, semestr zimowy 2026/27).
- Group page: list and month views, breaks between classes, subject progress, statistics, comparing groups
  (with shared free time), "Gdzie odrobić?" (the same class in other groups of the year), free rooms, calendar
  subscription (Google, Apple, link), sharing, print / PDF, and a notice when the plan changed since the last visit.
  Everything is free and stored only in the browser.
- Front page: favourite and recently viewed groups; Enter opens the only matching group.
- Build: site/data/ (group list, room bookings, each year's classes) for the tools above.
- Timetables for groups WCY26KY1S1, WCY26KY2S1, WCY26KY4S1, WCY26KY5S1, WCY26KY6S1 and WCY26KYAS1 (semestr zimowy
  2026/27).
  With several groups, the root page now lists them instead of redirecting.
- Timetables for 16 more groups (e.g. `WCY26_M1`, `WCY26_Fiz1a`, `WCY26IB1bS6`): group codes may now contain
  lowercase letters and underscores, and each file's `X-PLAN-GROUP` matches its file name.
- Front page: search the group; faculty lists are collapsed by default and open on matching search.
- Group page: on Saturday/Sunday with no weekend lessons planned, the next week opens straight away.
- Browser tests for the faculty picker, group search, weekend rollover and the front-page accessibility scan;
  the WCY26KY3S1 timetable is pinned in `tests/fixtures/wcy26ky3s1.plan.json` instead of the first export.
- Dev preview: every Pages deploy publishes the tip of `dev` under `/dev/`, cross-linked with production.

### Changed
- Tests follow the groups in `timetables/` instead of assuming one: every group must get a page and a byte-identical
  calendar, and every group page must render in the browser without errors or CSP violations. The single-group
  redirect is covered by a synthetic build test.

## [1.0.0] - 2026-10-11

First public release.

### Added
- Group timetable page: Live card for the class on now or next (room, time, teacher, progress), grouped day lists on
  phones and a day × time-slot grid on wide screens, week picker sheet, arrows / swipe / keyboard navigation,
  "Bieżący tydzień" pill, subject legend, phones scroll to the current class, `.ics` download.
- Timetables as iCalendar files in `timetables/<term>/<GROUP>.ics`, read in the browser by `src/ics.js` (folded lines,
  escaping, local and UTC times, weekly and daily repeats, excluded dates, cancelled and all-day events skipped).
- `build.py`: one page per group at `/<GROUP>/` with its current term (picked by date), a group list at the root that
  redirects while there is only one group, a 404 page, and a hash-pinned Content-Security-Policy in every page.
- GitHub Pages deployment on every push to `master` and daily, so a new term goes live on its first day.
- Self-hosted Docker image: two-stage build, read-only unprivileged nginx, security headers, header CSP generated from
  the built pages.
- CI: calendar-reader tests with coverage floors, build tests, Playwright browser tests (Chromium, Firefox, WebKit;
  desktop and phone) with an axe WCAG scan, Docker image scan (Grype) and smoke test, CodeQL, Dependabot.

[Unreleased]: https://github.com/kilerdevs/PlanWAT/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/kilerdevs/PlanWAT/releases/tag/v1.0.0
