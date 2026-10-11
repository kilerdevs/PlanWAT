# Changelog

[![Keep a Changelog](https://img.shields.io/badge/changelog-Keep%20a%20Changelog-E05735?style=flat)](https://keepachangelog.com/en/1.1.0/)
[![SemVer](https://img.shields.io/badge/versioning-SemVer-3F4551?style=flat)](https://semver.org/spec/v2.0.0.html)
[![Latest tag](https://img.shields.io/github/v/tag/kilerdevs/PlanWAT?style=flat&label=latest)](https://github.com/kilerdevs/PlanWAT/tags)

All notable changes to PlanWAT are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/); versioning is semver.

## [Unreleased]

### Added
- Timetables for groups WCY26KY1S1, WCY26KY2S1, WCY26KY4S1, WCY26KY5S1, WCY26KY6S1 and WCY26KYAS1 (semestr zimowy
  2026/27).
  With several groups, the root page now lists them instead of redirecting.
- Timetables for 16 more groups (e.g. `WCY26_M1`, `WCY26_Fiz1a`, `WCY26IB1bS6`): group codes may now contain
  lowercase letters and underscores, and each file's `X-PLAN-GROUP` matches its file name.
- Front page: pick a faculty first (WCY, WEL, WIG, WML, WTC — Polish and English names), then search the group.
  The choice is shareable via `#wydzial=<CODE>` and survives back/forward navigation.
- Group page: on Saturday/Sunday with no weekend lessons planned, the next week opens straight away.
- Browser tests for the faculty picker, group search, weekend rollover and the front-page accessibility scan;
  the WCY26KY3S1 timetable is pinned in `tests/fixtures/wcy26ky3s1.plan.json` instead of the first export.

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
