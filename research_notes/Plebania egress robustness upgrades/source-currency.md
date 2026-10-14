# Source currency — faculty indexes vs sources.json (2026-10-14 probe)

Probe date (UTC): 2026-10-14. Season on probe date: `zima 2026` (`season_of` = Sep–Feb winter), current term `2026-27-zima`, window `20260901..20270229`; `upcoming_reference(Oct)` = None.
Egress for this probe: datacenter address seen in block pages as `cip=77.222.244.154`. All fetches: plain GET, normal browser User-Agent, sequential with ~5 s pauses, index/landing pages and `robots.txt` only, no group pages, no bypass attempts. TOTAL: 14 small fetches (7 faculty indexes/landings + 7 robots.txt). Blocked-host content could not be verified from this egress; those items are gaps for the self-hosted runner (home address), not evidence of staleness.
Local config read: `tools/refresh/sources.json` (7 enabled faculties: wlo, wel, wim, ioe, wcy, wml, wtc), `tools/refresh/drivers/plansoft.py`, `drivers/wml.py`, `drivers/wcy.py`, `drivers/wtc/__init__.py`, `tools/refresh/core.py`, `docs/REFRESH.md`.

## 1) Does each configured index/landing still exist and list current-semester groups?

### Takeaway
Only WIM could be verified live from this egress (200, current `zima 2026-27` group list); the other six hosts answered with Incapsula walls (302 `Loading` or 403 incident pages), which proves nothing about URL staleness — bases must be re-checked from the self-hosted runner before any URL change.

### Cited Findings
- `sources.json` configures: WLO `https://wlo.wat.edu.pl/planzajec/{season}/`, WEL `https://wel.wat.edu.pl/planyzajec/{season}/`, WIM `https://www.wim.wat.edu.pl/wp-content/uploads/rozklady/{season}/`, IOE pinned `https://ioe.wat.edu.pl/plany/lato/`, WCY index `https://planzajec.wcy.wat.edu.pl/pl/rozklad`, WML landing `https://wml.wat.edu.pl/rozklady-zajec/`, WTC `https://wtc.wat.edu.pl/Plany/{season}/` — [sources.json](file:///F:/PlanWAT/tools/refresh/sources.json)
- WLO `https://wlo.wat.edu.pl/planzajec/zima/index.xml` answered `302`, `text/html`, 122 bytes, body `<HTML><HEAD><TITLE>Loading</TITLE>…` (Incapsula cookie/JS check, curl without `-L` did not follow) — [WLO index](https://wlo.wat.edu.pl/planzajec/zima/index.xml)
- WEL `https://wel.wat.edu.pl/planyzajec/zima/index.xml` answered `403`, 885 bytes, body `main-iframe … incident_id=519000730083562700… Request unsuccessful. Incapsula incident ID` — [WEL index](https://wel.wat.edu.pl/planyzajec/zima/index.xml)
- WIM `https://www.wim.wat.edu.pl/wp-content/uploads/rozklady/zima/index.xml` answered `200` XML (`windows-1250`), header `<period name="WIM - zima 2026-27">`, entries e.g. `<gro href="WME22MC1S0.htm"`, `<gro href="WME23BE1S1.htm"`, plus a `SDRMXCSS24Z_-_Ceg.htm` course page — [WIM index](https://www.wim.wat.edu.pl/wp-content/uploads/rozklady/zima/index.xml)
- IOE `https://ioe.wat.edu.pl/plany/lato/index.xml` answered `302`, 122 bytes, same `Loading` body as WLO — [IOE index](https://ioe.wat.edu.pl/plany/lato/index.xml)
- WTC `https://wtc.wat.edu.pl/Plany/zima/index.xml` answered `403`, 885 bytes, same Incapsula `main-iframe … incident_id=519000730083565191…` pattern — [WTC index](https://wtc.wat.edu.pl/Plany/zima/index.xml)
- WCY `https://planzajec.wcy.wat.edu.pl/pl/rozklad` answered `302`, 122 bytes, same `Loading` body — [WCY rozklad](https://planzajec.wcy.wat.edu.pl/pl/rozklad)
- WML `https://wml.wat.edu.pl/rozklady-zajec/` answered `403`, 885 bytes, Incapsula `main-iframe … incident_id=519000730083566752…` — [WML landing](https://wml.wat.edu.pl/rozklady-zajec/)
- Driver URL construction is `base + 'index.xml'` for plansoft/WTC, Drupal `grupa_id=` list for WCY, landing-iframe resolution for WML — [plansoft.py](file:///F:/PlanWAT/tools/refresh/drivers/plansoft.py); [wtc driver](file:///F:/PlanWAT/tools/refresh/drivers/wtc/__init__.py); [wcy.py](file:///F:/PlanWAT/tools/refresh/drivers/wcy.py); [wml.py](file:///F:/PlanWAT/tools/refresh/drivers/wml.py)

### Inferences
- WIM base/index are current and list the running semester; no URL change needed.
- 302 `Loading` (WLO, IOE, WCY) vs 403 incident page (WEL, WTC, WML) are two Incapsula postures on the same wall, not 404s — none of these URLs can be called stale from this evidence.
- The `planzajec` (WLO) vs `planyzajec` (WEL) spelling split in `sources.json` remains as-configured; it was not testable from here.

### Gaps
- From this egress I could not verify group counts, generation dates, or winter-vs-summer content for WLO/WEL/IOE/WTC/WCY/WML — needs one `index.xml`/landing fetch each from the self-hosted runner (home address), where `sources.json` notes say plain HTTP worked on 2026-10-13/14.
- I deliberately did not fetch `https://ioe.wat.edu.pl/plany/zima/index.xml` to stay within the fetch budget, so the "zima/ 404s" claim in the IOE note is unverified today.

## 2) Season handling and early/late publishing (incl. IOE pinned lato)

### Takeaway
The `Sep–Feb zima / Mar–Aug lato` rollover and the `August + Jan–Feb` upcoming-window logic still match the observed WIM period tag; IOE must stay pinned to `lato/` until the self-hosted runner sees a live `zima/` dir.

### Cited Findings
- `season_of`: month ≥ 9 → `zima` same year; month ≤ 2 → `zima` previous year; else `lato` previous year; `upcoming_reference`: August → Sep 1, Jan/Feb → Mar 1, else None — [core.py](file:///F:/PlanWAT/tools/refresh/core.py)
- WIM live header on 2026-10-14 is `<period name="WIM - zima 2026-27">`, exactly what `season_of(2026-10-14)` predicts — [WIM index](https://www.wim.wat.edu.pl/wp-content/uploads/rozklady/zima/index.xml)
- IOE note in config: "the winter plans live under the stale lato/ dir (…/plany/zima/ 404s), so the base is pinned, not seasonal" (enabled 2026-10-14) — [sources.json](file:///F:/PlanWAT/tools/refresh/sources.json)
- WCY note: "shows last semester's lessons until the new plan is published; the driver skips such pages" with a `max(dates) >= begins` (`zima`: `YYYY0901`, `lato`: `YYYY+1-0201`) freshness gate — [sources.json](file:///F:/PlanWAT/tools/refresh/sources.json); [wcy.py](file:///F:/PlanWAT/tools/refresh/drivers/wcy.py)
- WML note: "live index.xml is resolved via the landing page iframe (revisioned dirs)"; driver returns `[]` (not a block) when the embed is down — [sources.json](file:///F:/PlanWAT/tools/refresh/sources.json); [wml.py](file:///F:/PlanWAT/tools/refresh/drivers/wml.py)
- Two-semester runs in August and Jan–Feb refresh running + coming terms side by side into separate `timetables/<term>/` folders; a calendar is accepted only when most lessons fall in `term_window` — [REFRESH.md](file:///F:/PlanWAT/docs/REFRESH.md)

### Inferences
- No change to `season_of`/`upcoming_reference`/`term_window` is indicated; October is a single-term month (`upcoming_reference` = None), consistent with only `zima` being live at WIM.
- Faculties publishing the coming semester early (August winter, Jan–Feb summer) are already handled; WCY's late-publish case is handled by the driver skip + `validate` term-window check rather than config.
- Unpinning IOE now would be wrong without a self-hosted 200 + current-period check on both `lato/` and `zima/` index URLs.

### Gaps
- Whether any faculty this year publishes the coming semester earlier/later than `upcoming_reference` assumes (e.g. WIM/WEL/WLO lead times, WCY cutover date, WML revisioned-dir switch date) could not be observed from one October snapshot behind a WAF; needs self-hosted index fetches in late July–August and January.

## 3) Faculties/institutes not covered by sources.json

### Takeaway
WAT has eight teaching units; seven are covered and the eighth — WIG (Inżynierii Lądowej i Geodezji) — publishes timetables behind a login, so it is correctly out of scope for anonymous crawling.

### Cited Findings
- WAT teaching is done by eight units: Instytut Optoelektroniki, Wydział Nowych Technologii i Chemii, Wydział Mechatroniki Uzbrojenia i Lotnictwa, Wydział Inżynierii Mechanicznej, Wydział Inżynierii Lądowej i Geodezji, Wydział Elektroniki, Wydział Cybernetyki, Wydział Bezpieczeństwa Logistyki i Zarządzania — [WAT Kształcenie](http://www.wat.edu.pl/ksztalcenie/)
- Unit→portal mapping: WLO `https://wlo.wat.edu.pl/`, WML `http://www.wml.wat.edu.pl/`, WEL `https://wel.wat.edu.pl/`, WIG `https://www.wig.wat.edu.pl/`, WCY `https://wcy.wat.edu.pl/`, IOE `https://ioe.wat.edu.pl/`, WTC `http://www.wtc.wat.edu.pl/` — [IRK units](https://irk.wat.edu.pl/pl/offer/S2_LATO_25_26/units/)
- WIG timetable hub states current group/lecturer schedules are "available only after logging into E-DZIEKANAT", with base schedules valid "until they appear in E-DZIEKANAT", per-year pages labelled "Rok akademicki 2026/2027 zima" but file slots "Widoczne po zalogowaniu" — [WIG Rozkłady zajęć](https://wig.wat.edu.pl/cpp/index.php/studenci/plany-rozklady-terminy/rozklady-zajec); [WIG I R. Budow. stac.](https://wig.wat.edu.pl/cpp/index.php/studenci/plany-rozklady-terminy/rozklady-zajec/6-budow-stac/7-i-r-budow-stac)
- Non-faculty teaching units (Studium Języków Obcych, Studium Wychowania Fizycznego, Studium Szkolenia Wojskowego) handle languages/PE/military training, with no separate anonymous plan system found in this pass — [WAT Kształcenie](http://www.wat.edu.pl/ksztalcenie/)

### Inferences
- Coverage is complete for anonymously crawlable faculties: WLO/WEL/WIM/IOE/WCY/WML/WTC configured; WIG excluded by authentication, not by omission.
- Proposed config action is documentation-only: record WIG as intentionally uncovered (auth-walled E-DZIEKANAT/CPP) rather than adding a driver; no new base URL to propose.

### Gaps
- I did not probe WIG anonymously beyond search-result snippets (per the no-scraping-beyond-indexes constraint and login wall); a logged-in check of whether WIG exposes any public iCal/anonymous mirror was out of scope.

## 4) Per-host WAF posture from datacenter egress (status + page type only)

### Takeaway
From datacenter egress only `www.wim.wat.edu.pl` answers plain GET with 200; every other faculty host challenges or blocks (302 `Loading` or 403 Incapsula incident), confirming the crawler must stay on the self-hosted runner — no bypass was attempted.

### Cited Findings
- `wlo.wat.edu.pl` index: `302`, 122-byte `Loading` page — [WLO index](https://wlo.wat.edu.pl/planzajec/zima/index.xml)
- `wel.wat.edu.pl` index: `403` Incapsula incident (`main-iframe`, `incident_id=…-176352942050710083`, `cip=77.222.244.154`) — [WEL index](https://wel.wat.edu.pl/planyzajec/zima/index.xml)
- `www.wim.wat.edu.pl` index: `200` XML Plansoft list — [WIM index](https://www.wim.wat.edu.pl/wp-content/uploads/rozklady/zima/index.xml)
- `ioe.wat.edu.pl` index: `302`, 122-byte `Loading` page — [IOE index](https://ioe.wat.edu.pl/plany/lato/index.xml)
- `wtc.wat.edu.pl` index: `403` Incapsula incident (`incident_id=519000730083565191…`) — [WTC index](https://wtc.wat.edu.pl/Plany/zima/index.xml)
- `planzajec.wcy.wat.edu.pl` rozklad: `302`, 122-byte `Loading` page — [WCY rozklad](https://planzajec.wcy.wat.edu.pl/pl/rozklad)
- `wml.wat.edu.pl` landing: `403` Incapsula incident (`incident_id=519000730083566752…`) — [WML landing](https://wml.wat.edu.pl/rozklady-zajec/)
- Refresh docs already record: Incapsula blocks datacenter addresses on first request (`index.xml` 403 on hosted run), so the crawl runs only self-hosted; WLO+WEL share one policy; WTC behind Incapsula with cookie/Referer session; WCY plain HTTP worked from the crawling machine on 2026-10-14 — [REFRESH.md](file:///F:/PlanWAT/docs/REFRESH.md); [sources.json](file:///F:/PlanWAT/tools/refresh/sources.json); [wtc driver](file:///F:/PlanWAT/tools/refresh/drivers/wtc/__init__.py)

### Inferences
- Datacenter-capable today: WIM only. Never datacenter-capable without a policy change: WLO/WEL/IOE/WTC/WCY/WML (all challenged at index/landing level, before any group page).
- The 302-vs-403 split looks like two Incapsula challenge variants, not a live-vs-dead signal; both mean "blocked here, retry from home egress".
- No host showed a non-WAF error (no 404/500/DNS failure), so no URL can be declared dead from this probe.

### Gaps
- Posture from the self-hosted runner's home address was not re-probed here; per config notes WCY plain HTTP and the Incapsula-cookie session worked there on 2026-10-13/14 and must be re-confirmed per run via the block-probe logic.

## 5) robots.txt today

### Takeaway
Only WIM's `robots.txt` is readable from this egress and it permits crawling (only `/wp-admin/` disallowed); all other hosts' `robots.txt` fetches were swallowed by the same Incapsula wall, so the runner must keep honouring the live file at crawl time.

### Cited Findings
- `https://www.wim.wat.edu.pl/robots.txt` → `200`, 119 bytes: `User-agent: *`, `Disallow: /wp-admin/`, `Allow: /wp-admin/admin-ajax.php`, plus sitemap line — [WIM robots](https://www.wim.wat.edu.pl/robots.txt)
- `https://wlo.wat.edu.pl/robots.txt` → `403` Incapsula incident page — [WLO robots](https://wlo.wat.edu.pl/robots.txt)
- `https://wel.wat.edu.pl/robots.txt` → `403` Incapsula incident page — [WEL robots](https://wel.wat.edu.pl/robots.txt)
- `https://ioe.wat.edu.pl/robots.txt` → `403` Incapsula incident page — [IOE robots](https://ioe.wat.edu.pl/robots.txt)
- `https://wtc.wat.edu.pl/robots.txt` → `403` Incapsula incident page — [WTC robots](https://wtc.wat.edu.pl/robots.txt)
- `https://planzajec.wcy.wat.edu.pl/robots.txt` → `403` Incapsula incident page — [WCY robots](https://planzajec.wcy.wat.edu.pl/robots.txt)
- `https://wml.wat.edu.pl/robots.txt` → `403` Incapsula incident page — [WML robots](https://wml.wat.edu.pl/robots.txt)
- The crawler honours `robots.txt` with polite pacing, conditional revalidation, and sparse-then-dense block probes — [REFRESH.md](file:///F:/PlanWAT/docs/REFRESH.md)

### Inferences
- No robots-based crawl prohibition was found; the one readable file (WIM) explicitly allows the plan paths.
- For WAF-walled hosts the effective robots posture must be evaluated on the self-hosted runner, where the wall is passable; a 403 here is a wall artefact, not a `Disallow`.

### Gaps
- Actual `Allow/Disallow` contents for WLO/WEL/IOE/WTC/WCY/WML as seen from the home egress remain unknown in this pass.

## 6) Driver fit — has any faculty changed its plan system?

### Takeaway
No format change was observed; WIM still matches `plansoft`, and there is no evidence to move any other faculty off its assigned driver — blocked hosts simply could not be re-verified from here.

### Cited Findings
- WIM index is still `<?xml … encoding="windows-1250"?>` + `<gro href="….htm">` Plansoft list with `WIM - zima 2026-27` period, matching `plansoft.Driver.discover` (`<gro href="([^"]+)"`) and `page_ok` (`mergeWith` + `Plansoft`) expectations at index level — [WIM index](https://www.wim.wat.edu.pl/wp-content/uploads/rozklady/zima/index.xml); [plansoft.py](file:///F:/PlanWAT/tools/refresh/drivers/plansoft.py)
- WCY rozklad content could not be inspected (302 wall); assigned `wcy` driver expects Drupal `grupa_id=` options and `rozklad_container` + `lessons hidden` markers with date-gated freshness — [WCY rozklad](https://planzajec.wcy.wat.edu.pl/pl/rozklad); [wcy.py](file:///F:/PlanWAT/tools/refresh/drivers/wcy.py)
- WML landing could not be inspected (403 wall); assigned `wml` driver expects a WordPress page with `<iframe … index.xml>` to a revisioned dir — [WML landing](https://wml.wat.edu.pl/rozklady-zajec/); [wml.py](file:///F:/PlanWAT/tools/refresh/drivers/wml.py)
- WTC index could not be inspected (403 wall); assigned `wtc` driver expects `index.xml` with `<gro href="….pdf">` Plansoft PDFs converted via pymupdf — [WTC index](https://wtc.wat.edu.pl/Plany/zima/index.xml); [wtc driver](file:///F:/PlanWAT/tools/refresh/drivers/wtc/__init__.py)
- WLO/WEL/IOE index bodies could not be inspected (302/403 walls); assigned `plansoft` with IOE pinned base + transposed-grid handling and WEL/IOE `groups_re` de-duplication (`^(?!IOE|WME)` / `^IOE`, WME skipped at IOE) — [sources.json](file:///F:/PlanWAT/tools/refresh/sources.json); [plansoft.py](file:///F:/PlanWAT/tools/refresh/drivers/plansoft.py)

### Inferences
- Keep all driver assignments: `plansoft` for WLO/WEL/WIM/IOE, `wcy`, `wml`, `wtc`. The only actionable driver-adjacent check is on the runner: confirm WML landing still yields exactly one `index.xml` iframe, WCY pages still carry `lessons hidden`, WTC index entries are still `.pdf`, and IOE grid is still the transposed SUBJ/type/room/alias variant.
- WIM's non-group `SDRMXCSS24Z_-_Ceg.htm` entry is already handled by `group_code` filtering (course pages skipped), no config change.

### Gaps
- A real format-change check for six faculties requires one index/landing fetch plus (only if the index looks different) a single group-page sample from the self-hosted runner; deliberately not done here.
