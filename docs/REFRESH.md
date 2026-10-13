# Automatic timetable refresh

The plans are re-read from the faculty sites by a scheduled GitHub Actions workflow and published without a commit to
`master` or `dev`.

```
refresh.yml   daily, off-hours, on the self-hosted runner: crawl → convert → validate → push to `data`
data branch   timetables/<term>/<GROUP>.ics and refresh-state.json
pages.yml     checks out `data` and lays its timetables over prod/ and dev/ before build.py
```

## How a run behaves

- One session, one request at a time, a random pause between pages (2.5–6 s on the self-hosted runner, 4–9 s with `--profile hosted`), `robots.txt`
  honoured, conditional revalidation (`If-Modified-Since`/`ETag` remembered per group, so unchanged pages answer
  `304` without a body), groups checked less than 20 hours ago skipped.
- **The first block stops the crawl.** Any status other than 200 (304 excluded), or an Incapsula incident page, ends that run: nothing
  is retried and nothing half-converted is published. The last good calendars stay, a GitHub issue is opened, and the
  self-hosted job tries later from the same state. (`_Incapsula_Resource` script tags on good pages are not blocks.)
  WLO and WEL share one Incapsula policy: crawling either too fast blocks both addresses for hours. After a block,
  leave that faculty alone for 24–48 h before resuming (the state keeps the last good calendars meanwhile).
- A page is only published when the calendar passes the site's own validation (`build.load_term`), carries its file's
  group code and has not lost more than 40% of its events. Otherwise the old calendar is kept and the group is logged.
- A calendar is rewritten only when the plan changed (the generation date is ignored), so `data` history shows real
  plan changes.

## Faculties

`tools/refresh/sources.json` lists them. Each points at a driver in `tools/refresh/drivers/`:

| Faculty | Driver | State |
|---|---|---|
| WLO, WEL, WIM | `plansoft` | enabled |
| WML | `wml` (Plansoft pages; the live `index.xml` is resolved via the landing-page iframe, since the faculty republishes under revisioned directories) | enabled |
| WCY | `wcy` | disabled until a dry run proves plain HTTP works (the old crawler used a browser) |
| WTC | `wtc` | enabled; `index.xml` lists one Plansoft PDF per group, converted with `pymupdf` (installed by the refresh action) |

Pages named like `1PL26KP` get the faculty prefix (`WEL1PL26KP`) so the file name, `X-PLAN-GROUP` and the front-page
section agree. Pages that are not group codes (courses such as `Kurs_-_…`) are skipped. WML groups keep the
faculty's own `WMT` codes (only `^WMT` pages are crawled) and are listed under the WML section.

WTC notes: the site sits behind Incapsula, so the PDFs are fetched with the
index page as Referer on the shared cookie-keeping session, one at a time;
the converter needs `pip install pymupdf` on any machine running the crawl
(the daily action installs it). Converted calendars carry no staff names
(see the privacy rule below).

Pages named like `1PL26KP` get the faculty prefix (`WEL1PL26KP`) so the file name, `X-PLAN-GROUP` and the front-page
section agree. Pages that are not group codes (courses such as `Kurs_-_…`) are skipped.

## No staff names in calendars

The published calendars hold no personal data of staff: converters never
write `CONTACT` lines or instructor (`Prowadzący:`) lines — teacher names
from the faculty pages are parse intermediates only (they steer the
room/teacher split) and are dropped before the calendar is written.
`build.py` refuses any calendar that names staff, so a regression fails the
build instead of publishing names.

## One-time setup

1. Create the `data` branch from the current valid timetables:
   `git switch --orphan data && git checkout dev -- timetables && git commit -m "Seed timetables" && git push -u origin data`
   (leave only calendars that pass `python build.py`).
2. Settings → Actions → General: allow GitHub Actions to create issues and run workflows (workflow permissions
   "Read and write"), and set "Fork pull request workflows" to require approval.
3. Try it: Actions → *Refresh timetables* → Run workflow, faculty `wim`.

## Self-hosted runner (the only runner)

The faculty sites' Incapsula wall blocks GitHub's datacenter addresses on the first request (seen on the first hosted
run: `index.xml` answered 403), so the crawl runs only on the self-hosted runner, whose home address works.

The runner makes only outbound connections to GitHub; the machine needs **no open inbound port**. Anyone able to
trigger a workflow on the repository can run code on it, so:

- the workflow runs it only for `schedule` and `workflow_dispatch` (never pull requests), and only people with write
  access can dispatch;
- run it in a container as an unprivileged user, with no host mounts, no Docker socket and no secrets other than its
  own registration; register it at repository level with the label `planwat`;
- block all inbound traffic on the host and allow outbound only to GitHub and the faculty hosts.

## If GitHub itself is compromised

The design assumes the repository (code, Actions, the `data` branch, `GITHUB_TOKEN`) may fall into hostile hands
while the runner host must stay clean and the published site must stay safe:

- The runner lives on an internal Docker network with no route out; its only egress is a proxy that allows
  `CONNECT ...:443` solely to GitHub, PyPI and the faculty hosts (anything else, including bare IPs, gets `403
  Filtered`). Stealing the per-job token still cannot reach an attacker's server directly; exfiltration is limited
  to pushing to GitHub, which is auditable in the repo history.
- The job token carries only `contents:write` (push the `data` branch) and `issues:write` (file the blocked notice).
  There is deliberately no `actions:write`: refreshed calendars are picked up by the daily `pages.yml` rebuild, so a
  stolen token cannot trigger or approve other workflows.
- `master` is protected (signed commits, required CI) and `pages.yml` builds production only from `master`, overlaying
  `data` calendars that must each pass `build.load_term` validation and are HTML-escaped into hash-pinned CSP pages.
  A poisoned `data` branch therefore cannot inject script or promote content to the site root — at worst it shows
  wrong lesson times until reverted. Also protect the `data` branch (Settings → Branches → Add rule for `data`:
  require pull requests for humans, allow only the Actions bot to bypass) so a compromised web session cannot push
  to it silently.
- The runner keeps no long-lived secrets besides its own registration, and its work directory should be treated as
  disposable: anyone who ran code on it may have left files behind. Prefer ephemeral (one-job) runners; with a
  persistent runner, wipe `/home/runner/_work` after jobs and re-register from a fresh token when in doubt.
- Watch for the tell-tale sign of runner abuse: unexpected workflow files targeting `runs-on: [self-hosted, planwat]`
  or edits to `refresh.yml` / `.github/actions/refresh`. Alert on those paths with a CODEOWNERS rule or a
  branch-protection required review.

## What the site shows

Every group page shows **Zaktualizowano** (when the plan last changed) and **Sprawdzono** (when the crawler last verified
it), taken from `refresh-state.json` at build time; groups never refreshed show the calendar's own generation date.
