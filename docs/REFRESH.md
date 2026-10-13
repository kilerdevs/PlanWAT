# Automatic timetable refresh

The plans are re-read from the faculty sites by a scheduled GitHub Actions workflow and published without a commit to
`master` or `dev`.

```
refresh.yml   daily, off-hours, on the self-hosted runner: crawl → convert → validate → push to `data`
data branch   timetables/<term>/<GROUP>.ics and refresh-state.json
pages.yml     checks out `data` and lays its timetables over prod/ and dev/ before build.py
```

## How a run behaves

- One session, one request at a time, a random pause between pages (1–2.5 s on the self-hosted runner, 3–7 s with `--profile hosted`), `robots.txt`
  honoured, groups checked less than 20 hours ago skipped.
- **The first block stops the crawl.** Any status other than 200, or an Incapsula incident page, ends that run: nothing
  is retried and nothing half-converted is published. The last good calendars stay, a GitHub issue is opened, and the
  self-hosted job tries later from the same state. (`_Incapsula_Resource` script tags on good pages are not blocks.)
- A page is only published when the calendar passes the site's own validation (`build.load_term`), carries its file's
  group code and has not lost more than 40% of its events. Otherwise the old calendar is kept and the group is logged.
- A calendar is rewritten only when the plan changed (the generation date is ignored), so `data` history shows real
  plan changes.

## Faculties

`tools/refresh/sources.json` lists them. Each points at a driver in `tools/refresh/drivers/`:

| Faculty | Driver | State |
|---|---|---|
| WLO, WEL, WIM | `plansoft` | enabled |
| WCY | `wcy` | disabled until a dry run proves plain HTTP works (the old crawler used a browser) |
| WTC | `wtc` | disabled; add `drivers/wtc.py` with the contract in `drivers/__init__.py`, then enable |

Pages named like `1PL26KP` get the faculty prefix (`WEL1PL26KP`) so the file name, `X-PLAN-GROUP` and the front-page
section agree. Pages that are not group codes (courses such as `Kurs_-_…`) are skipped.

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

## What the site shows

Every group page shows **Zaktualizowano** (when the plan last changed) and **Sprawdzono** (when the crawler last verified
it), taken from `refresh-state.json` at build time; groups never refreshed show the calendar's own generation date.
