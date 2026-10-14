# Crawler intelligence: retry, blocks, pacing, state, drivers, scheduling

Audit of `tools/refresh/refresh.py`, `core.py`, `drivers/` (plansoft, wml, wcy, wtc),
`sources.json`, the refresh workflow/action and `tests/test_refresh.py`.
Read-only; no code touched, no live crawling. References are `file:line`.

## 1. Retry/backoff: transient classification is too narrow and conflated with blocks

### Takeaway
`get_with_retry` retries only exceptions + 429/500/502/503/504, treats every other
non-200/304/404 as an instant verdict, and on retry exhaustion raises something the
caller counts as a *block* — so flaky-transport episodes get learned as Incapsula
cooldowns and 408/425/empty-200/chunked cases fall through the cracks.

### Cited findings
- Retry set is `(429, 500, 502, 503, 504)`; 200/304/404 return at once, anything else
  returns at once as a "verdict, never retried" (`refresh.py:59-64`).
- Transport exceptions are caught and retried (`refresh.py:56-57`) — TLS truncation /
  chunked-encoding errors surface as exceptions from curl_cffi, so they *are* retried.
  But HTTP 408 and 425 are not in the retry set: they return immediately, then
  `core.is_blocked(408|425, …)` is True (`core.py:85`) and the faculty is deferred as
  blocked (`refresh.py:238-243`). Same for 206/301/302 (a redirect or partial body is
  scored as a wall).
- Backoff is `backoff * 2**attempt + uniform(0,1)`, defaults retries=3, backoff=2.0
  (`refresh.py:65-66`, `298-311`): sleeps ≈ 2–3, 4–5, 8–9 s (≈ 15 s worst case per page).
  Jitter is only +0–1 s, not proportional/full jitter, and there is no cap parameter
  (fine at current values, but any backoff tuning upward has no ceiling).
- On exhaustion `raise last` re-raises whatever failed last — for an HTTP status that
  is `core.Blocked('HTTP 429|5xx')` (`refresh.py:62,67`). The caller catches it under
  `except Exception → BLOCKED/NETWORK` and marks the faculty blocked with `blocked_at`
  (`refresh.py:222-227`). A sustained 429/5xx burst therefore (a) parks the faculty in
  the block path with index probing, and (b) teaches `BlockModel` a bogus multi-hour
  "Incapsula cooldown" via `note_blocked` (`refresh.py:359`) that is never labelled by cause.
- Empty-200 bodies are neither retried nor blocked: `is_blocked(200, '')` is False
  (`core.py:85-89`), then `driver.page_ok('')` is False, so the group is counted
  `failed += 1` and the run stays `complete=True` (`refresh.py:244-247`). A faculty
  serving truncated empty pages looks like a clean run with "skipped" groups.
- `robots_allows` does one un-retried fetch; any exception means "allows"
  (`refresh.py:124-137`). A transient robots.txt 500 therefore silently proceeds (good
  default), but a persistent robots 403 body is parsed normally — fine.

### Inferences (upgrade proposals)
1. Split the error taxonomy three ways: `transient` (retry with backoff: timeouts,
   resets, TLS/chunked errors, 408, 425, 429, 500, 502, 503, 504) vs `block`
   (Incapsula markers, 403, unexpected statuses on index) vs `verdict` (404 gone,
   robots-disallow). Return/raise distinct types so `refresh_faculty` never records a
   retry-exhausted 429 as `blocked_at` and never feeds it to `BlockModel`.
2. Add empty/short-body guard: treat 200 with `len(content)` below a per-driver floor
   (or `page_ok == False` on a second conditional fetch) as transient, not "skipped".
3. Cap and jitter properly: `sleep = min(cap, backoff * 2**attempt) + uniform(0, cap_jitter)`
   with `--retry-cap`; keep total per-page retry cost visible in logs.
4. Add a per-faculty retry budget / circuit breaker (e.g. max ~10 transient retries per
   faculty per run, then mark incomplete-but-not-blocked and move on) so one flaky
   faculty cannot burn hundreds of requests; export the count for the workflow.
5. Log the retry reason at INFO with faculty+group+attempt, and include transient counts
   in `fac['run']` so the egress report distinguishes "flaky" from "walled".

### Gaps
- Whether curl_cffi surfaces truncated-TLS / chunked errors as exceptions vs short 200s
  was not verified (no live crawling per constraints); proposal 1–2 covers both shapes.

## 2. Block learning (BlockModel + wait_for_recovery): per-faculty key is wrong for the shared policy

### Takeaway
WLO and WEL share one Incapsula policy (`refresh.py:36-38`, `docs/REFRESH.md`), but
learning, estimation and probing are all keyed per faculty — the model will learn the
same wall twice, probe it twice, and mis-estimate when only one faculty has history.
The default estimate (2 h) also exceeds the default wait budget (90 min), so a
history-less block *never* gets its full probe schedule.

### Cited findings
- `BlockModel` stores `durations` + `blocked_at` per faculty name, estimate =
  clamped median, `BLOCK_DEFAULT = 2h`, `BLOCK_MIN = 20min`, `BLOCK_MAX = 12h`,
  `BLOCK_KEEP = 10` (`core.py:29-74`). Pinned by `BlockModelTest` (`test_refresh.py:488-524`).
- Quadratic probe offsets `est * (i/max_probes)^2`, budget-capped
  (`refresh.py:99-121`); schedule pinned by `WaitForRecovery` tests
  (`test_refresh.py:539-586`). With defaults (est 7200 s, 5 probes) probes land at
  288/1152/2592/4608/7200 s — but `--max-block-wait-minutes` defaults to 90 min
  (`refresh.py:312-313`), so the 5th probe at 120 min is unreachable; the
  budget-exhaustion test shows ≤2 probes inside 1000 s (`test_refresh.py:567-576`).
- `note_recovered` only learns when `blocked_at` was recorded (`core.py:59-74`); a
  probe success without a recorded episode learns nothing (pinned at
  `test_refresh.py:554`). `main` records `note_blocked` for main-pass and ahead-pass
  blocks (`refresh.py:359,364`) but a rerun that re-blocks records again without ever
  closing the first episode — durations then measure rerun-to-recovery, not wall time.
- `wait_for_recovery` treats *any* probe exception as "still blocked" (`refresh.py:110-112`):
  a transient DNS blip during a probe extends the sleep to the next quadratic slot.
- Median-of-10: robust to outliers but slow to track regime changes (Incapsula policy
  tightening/loosening); with ≤2 samples the median is just the middle of noise, yet it
  drives sleeps of hours. Clamp hides this (`BLOCK_MIN/MAX`).

### Inferences (upgrade proposals)
1. Key learning per-policy-group, not per-faculty: add `"policy": "wat-incapsula"` (WLO,
   WEL, plausibly WTC/WIM subdomains behind the same wall) vs per-host for the rest in
   `sources.json`; `BlockModel` estimates per policy group, `note_blocked` records the
   group once even if two member faculties block in the same run.
2. Probe the *group*, not each faculty: one probe schedule per wall; on recovery rerun
   all deferred members. Halves wasted index requests for the WLO/WEL pair.
3. Fix the budget/estimate mismatch: either default `--max-block-wait-minutes` ≥ default
   estimate (e.g. 150 min) or scale probe count to the budget (`max_probes` such that
   the last probe ≤ budget). Log "budget covers k/n probes" at wait start.
4. Make the estimator adaptive: keep median as the robust center but (a) weight recent
   recoveries higher (e.g. EWMA over the last 10, or median of last 5 + overall median),
   (b) record the *outcome* of each wait (recovered at probe k / gave up) so a wrong
   estimate shortens next time instead of being forgotten (currently give-ups learn
   nothing — `test_refresh.py:576` pins that).
5. Distinguish probe-transient from probe-blocked: retry a probe once on exception
   before scoring "still blocked", and record cause-labelled episodes
   (`incapsula` vs `http-429` vs `http-5xx`) so rate-limit bursts stop polluting the
   Incapsula cooldown history (ties to §1).

### Gaps
- Which hosts truly share one Incapsula policy (only WLO+WEL is documented) needs one
  confirmation pass from response headers/history; until then group at least WLO+WEL.

## 3. Main-loop orchestration: defer-and-resume has starvation and silent paths

### Takeaway
Deferral works for the headline case, but the shared sequential wait budget starves
later faculties, ahead-pass blocks trigger wasteful main-pass reruns, and several
non-block failure modes return "not complete" with no alarm while mass-404 / mass-skip
returns "complete" with no alarm either.

### Cited findings
- Main pass defers on `was_blocked`, covers the rest, then waits sequentially off one
  shared `wait_budget` (`refresh.py:349-366`, `366-397`). First deferred faculty can
  consume the whole 90 min; the rest hit `if wait_budget <= 0: break` and stay blocked
  until the next cron — no per-faculty fairness, no re-queue.
- `tallies['blocked']` recompute after each recovery only looks at `deferred`
  (`refresh.py:387`); a faculty that blocked in the *ahead* pass but recovered is
  rerun via full `refresh_faculty(today)` + `refresh_ahead` (`refresh.py:388-397`) —
  i.e. an ahead-pass block costs a whole extra main pass (mostly `fresh()`-skipped, but
  still index + 304 traffic) and `fac['run']` ends with `ahead=True` overwritten by the
  main rerun's record.
- `max_minutes` mid-faculty returns `([], False, False)` (`refresh.py:212-214`):
  indistinguishable from robots-disallow / empty-discover / discover-exception, all of
  which are `complete=False` but `blocked=False` → exit 4 with no issue filed
  (`action.yml:97-109` only acts on `blocked`). Operators cannot tell "cut short by
  time" from "faculty redesigned its index".
- Silent-never-retried paths (all `complete=False`, none deferred, none alarmed):
  `discover` non-Blocked exception (`refresh.py:191-193`), `items == []`
  (`refresh.py:194-196` — includes WML "embed taken down"), robots-disallow
  (`refresh.py:197-199`). Next cron retries from scratch, but nothing pages anyone.
- Silent-success paths (all `complete=True`, nothing published, no alarm): per-group
  404 (`refresh.py:235-237`), `page_ok` False (`refresh.py:244-247`), convert/validate
  failures (`refresh.py:255-269`). A faculty-wide redesign that breaks every page
  (index still 200) exits 0. `skipped`/`failed` counts live only in logs
  (`refresh.py:284-286`), not in `export()`/outputs (`refresh.py:402`) nor the issue
  logic.
- `state.save()` is skipped on dry-run (fine) but also only periodic every 25 *changed*
  writes (`refresh.py:279-280`) plus end-of-run (`refresh.py:399-400`): a long no-change
  run that crashes loses all `checked` marks and re-crawls everything next time.

### Inferences (upgrade proposals)
1. Split budgets: per-faculty wait cap (e.g. `--max-block-wait-minutes` total +
   `--max-wait-per-faculty`) and round-robin probes across deferred faculties instead
   of sequential drain; log remaining budget per faculty.
2. Rerun only what blocked: if the main pass completed and only the ahead pass blocked,
   re-probe + rerun *ahead only*; preserve separate `run` / `run_ahead` records instead
   of overwriting `fac['run']`.
3. Make incomplete causes machine-readable: return/tally `incomplete_why` per faculty
   (`time-budget`, `discover-error`, `empty-index`, `robots`, `awaiting-block-budget`)
   and export it via `GITHUB_OUTPUT`; file/keep the issue for `awaiting-block-budget`
   and `discover-error`, not just `blocked`.
4. Add mass-failure alarms: if a faculty yields 0 items, >50% `page_ok` failures, or
   >50% convert/validate failures, mark the faculty `degraded` (distinct from blocked),
   export it, and open/update an issue — this is the redesign early-warning (§6).
5. Save state incrementally by *checked* count (e.g. every 25 groups) and always on
   faculty completion, not only on changed writes; fsync-tmp-rename already exists
   (`core.py:212-216`) so this is cheap.

### Gaps
- None in code reading; interplay with `--limit` + stalest-first is already tested
  (`test_refresh.py:219-233`) and sound.

## 4. Pacing: fixed profiles, one shared session, one mutated Referer

### Takeaway
One sequential session with a fixed uniform pause is the right polite baseline (and the
WLO/WEL comment shows it was earned the hard way), but delays never adapt to 429s or
latency, and two session-hygiene bugs — WTC's global `Referer` mutation and a shared
cookie jar across unrelated hosts after a block — raise the WAF score the pacing is
trying to keep low.

### Cited findings
- Profiles `hosted=(4.0,9.0)`, `selfhosted=(2.5,6.0)` s, uniform pause between pages
  (`refresh.py:35`, `215-216`, `317`); single session, fully sequential
  (`refresh.py:346,354`). `docs/REFRESH.md` documents the 20 h + conditional-request
  regime on top.
- No adaptation: 429s are retried at fixed backoff (§1) but the inter-page delay never
  grows; low-latency 200 streaks never shrink it. No per-host delay state exists.
- `new_session`: curl_cffi `impersonate='chrome'`, `Accept-Language: pl-PL`
  (`refresh.py:140-146`) — deliberate, with a comment against pinning old releases.
- WTC `discover` sets `session.headers['Referer'] = <wtc index>` on the *shared*
  session (`drivers/wtc/__init__.py:36-40`); every later faculty (WLO/WEL/WCY/…) then
  sends `Referer: https://wtc.wat.edu.pl/…` — a cross-faculty anomaly Incapsula can
  score, and the test only asserts the header was set, not scoped
  (`test_refresh.py:295-298`). Iteration order over `sources.json` decides who is
  affected.
- One cookie jar for all hosts: fine for `.wat.edu.pl` Incapsula cookies, but after a
  block the same jar (possibly holding incident/poisoned cookies) is reused for probes
  and reruns (`refresh.py:346,372-389`). No jar reset/rotation on block or per-host
  isolation.
- WML two-leg affinity (landing → index → pages on the same session) is correct and
  tested (`test_refresh.py:348-381`); WCY plain-HTTP + Drupal menu needs no special
  headers (documented in `drivers/wcy.py:1-4`).

### Inferences (upgrade proposals)
1. Adaptive pacing: AIMD limiter per policy-group — on 429/5xx or p95 latency spike,
   multiply the delay (e.g. ×1.5 up to a cap like 30 s); on N consecutive clean 200/304s,
   decay back toward the profile floor. Persist the current delay in state so the next
   run starts where the last one learned.
2. Scope WTC's Referer: send it per-request (`session.get(url, headers={'Referer': …})`)
   or save/restore the session default around WTC page fetches; never mutate global
   headers in a driver. Same rule for any future driver header needs.
3. Per-host cookie jars (or at least per-policy-group jars): share within `.wat.edu.pl`
   Incapsula scope, isolate WCY's Drupal host; drop incident cookies and re-create the
   session (or clear jar) after a block before probing, so probes test the wall, not a
   poisoned jar.
4. Keep single-session sequential as the default (rotation would burn the self-hosted
   address's trust); only consider per-host sessions if adaptive pacing (§4.1) proves
   one slow host head-of-line-blocks the others — and then keep the shared delay budget
   for the shared-policy group.
5. Cache `robots.txt` per host per run (it is fetched once per faculty today,
   `refresh.py:197` → `robots_allows` fetch per faculty) to cut redundant requests.

### Gaps
- Whether the egress proxy pools multiple IPs ("each host has its own egress through
  the proxy pool", `refresh.py:351-352`) vs one stable address matters for session
  strategy; code comment asserts per-host egress but this was not verifiable offline.

## 5. State (refresh-state.json): corruption reset, clock-skew, validators, hash-vs-same_plan, ahead keys

### Takeaway
State handling is careful (atomic tmp-rename, validators, dual change checks) but has
five concrete holes: corrupt state silently triggers a full recrawl, `fresh()` trusts
the wall clock, current-semester keys are term-less (stale-term checks leak across
semesters), and the hash/`same_plan` pair is redundant in the expensive direction.

### Cited findings
- Corruption → silent empty state: `State.__init__` swallows `OSError/ValueError` and
  resets to `{'version':1,…}` (`core.py:190-198`); version mismatch also resets. No
  backup, no log, no metric — a truncated upload means next run re-fetches *everything*
  at once (worst moment: right after a blocked run).
- `fresh(code, now, hours)` compares naive-UTC `now - checked < timedelta(hours)`
  (`core.py:208-210`); `now_utc()` is wall-clock (`core.py:219-220`). Runner clock jump
  forward → everything stale (thundering recrawl); jump back → nothing refreshes for
  hours. `--fresh-hours` default 20 h with daily cron leaves ~4 h slack
  (`refresh.py:306`, `refresh.yml:11`), so small skew is absorbed, large skew is not.
- Validators are generic and sent for every driver (`refresh.py:149-160,219`): WLO/WEL/
  WIM static pages honor `If-Modified-Since`/`ETag` (304 path tested,
  `test_refresh.py:235-256`); WTC PDFs and WCY Drupal pages go through the same code
  but nothing verifies those servers honor conditional requests — if they ignore them,
  every run downloads full bodies for zero benefit while believing it is being polite.
  `remember_validators` is best-effort over `response.headers.get` (`refresh.py:163-173`);
  header-name case handling depends on curl_cffi's mapping.
- Double change check: raw-bytes `sha256` short-circuit before conversion
  (`refresh.py:249-254`), then `validate` + `same_plan(old, ics)` (volatile-stripped ICS
  compare, `core.py:49-56`) after conversion (`refresh.py:265-272`). A raw change with
  identical lessons (footer date, whitespace, reordered grid) pays full convert +
  validate before being discarded — the expensive direction. `VOLATILE` covers only
  `X-PLAN-GENERATED/DTSTAMP/X-PLAN-UPDATED` (`core.py:20`).
- Ahead keys are `CODE@tid`, current keys are bare `CODE` (`refresh.py:201`): the
  current-semester entry carries `term` inside but `fresh()` ignores it, so a group
  checked in the winter term still counts fresh when the summer term starts (different
  `tid`, same key) — the new semester's first days can be skipped up to `fresh_hours`.
  `CODE@tid` itself cannot collide with real codes (`GROUP_RE` allows no `@`,
  `build.py:40`), and the ahead test pins key separation (`test_refresh.py:165-175`).
- `fac['last_ok']` is only written on the non-ahead path (`refresh.py:281-283`) —
  correct — but a faculty whose *ahead* pass keeps failing never surfaces, since
  ahead failures fold into the same `changed/blocked` tallies without a label (§3).

### Inferences (upgrade proposals)
1. Corruption recovery: on load failure, rename the bad file to
   `refresh-state.json.corrupt-<ts>` (keep one backup of the last good state too) and
   export `state_recovered=true` so the workflow can alarm; never silently start empty.
2. Clock-skew hardening: store a monotonic `checked_mono` alongside wall time, or
   clamp `fresh()` so a `checked` timestamp in the future counts as fresh (not stale);
   log a warning when skew > 1 h is detected.
3. Term-scope current keys or term-aware `fresh()`: compare `entry.term == tid` before
   honoring `checked`, or key current entries as `CODE@tid` uniformly and migrate once.
4. Verify conditional support per driver once (log response 304-rate per faculty per run);
   for servers that ignore validators, fall back to HEAD/`Range` probing or reduce
   frequency rather than sending dead headers. Assert header case-insensitivity in a
   unit test with a case-mismatched fixture.
5. Cheapen the double check: keep raw-hash fast path, but widen `VOLATILE`/normalization
   (or hash the *normalized* ICS from the previous run) so cosmetic raw changes skip
   conversion; alternatively compare raw-hash first, convert, then `same_plan` — already
   the order — but skip `validate`'s temp-dir `build.load_term` cost when `same_plan`
   is true (validate before compare today).

### Gaps
- 304-rate per faculty (i.e. whether WTC/WCY honor validators) is unknowable without
  run logs; proposal 4 makes it observable first.

## 6. Driver fragility: regex parsing everywhere, silent redesign failure

### Takeaway
Every driver parses with regexes and fails *silent-clean*: index-shape changes yield
empty lists or mass skips while the run still exits 0/4. The first thing to break per
driver is known, and none of it has a canary.

### Cited findings
- Plansoft index: `re.findall(r'<gro href="([^"]+)"', text)` (`drivers/plansoft.py:44`);
  breaks on single quotes, namespaces, attribute reordering across lines, uppercase
  tags, or a CMS emitting JSON. WTC duplicates the pattern for `.pdf`
  (`drivers/wtc/__init__.py:42`). `page_ok` is `'mergeWith' in text and 'Plansoft' in
  text` (`drivers/plansoft.py:54-55`) — any generator upgrade/rename flips every page
  to "skipped", `complete=True`, exit 0.
- WML iframe discovery: `<iframe[^>]+src="([^"]+)"` + `'index.xml' in src`
  (`drivers/wml.py:27`); breaks on single-quoted attrs, JS-injected embeds, `<object>`/
  `<embed>` replacements, or revisioned dirs whose index has a new name. "No embed"
  returns `[]` = "not a block" (`drivers/wml.py:28-29`), which becomes
  `complete=False` exit 4 with no alarm (§3) — better than silent-0, but still no issue.
- WCY: group menu `<option … value="…grupa_id=…">` (`drivers/wcy.py:26`), health gate
  `'rozklad_container' and 'lessons hidden'` plus max-lesson-date ≥ term start
  (`drivers/wcy.py:36-41`), hidden-data-island regex
  `<div class="lessons hidden">…</div> <div class="rozklad_container">`
  (`rozklad2ics.py:163-165`). A Drupal theme update, class rename, or JSON-API move
  breaks discovery *and* the gate simultaneously; stale-semester content is then
  indistinguishable from a redesign (both → skip, old calendar stays — by design,
  `sources.json:40`, `drivers/wcy.py:33-36`).
- WTC PDF: `page_ok` = text starts with `%PDF` (`drivers/wtc/__init__.py:52-53`),
  `convert` raises `ValueError` on non-PDF (`:56-57`) → caught as `failed += 1`
  (`refresh.py:255-260`). A broken PDF pipeline (pymupdf upgrade, scanned-image PDFs,
  layout change in `wtc/parse.py…emit.py`) degrades group-by-group to exit 0. The
  converter-entry contract differs per driver and is unchecked: `wlo2ics.main(argv)`
  raises `SystemExit` on unreadable pages (explicitly caught, `refresh.py:261-264`)
  while `rozklad2ics.main` *returns* 1 and WCY ignores the return value
  (`drivers/wcy.py:43-50`, `rozklad2ics.py:431-483`) — a "no lessons" page falls
  through to reading a never-written `out.ics` (`FileNotFoundError` → skipped).
- Encoding handling (`plansoft.decode` utf-8→windows-1250, `plansoft.py:13-19`) is a
  quiet strength; `wlo2ics` documents the lying-META/FFFD hazard (`wlo2ics.py:53-61`)
  and repairs the `(ć)` type slot (`:228-230`). These are the kind of assertions to
  replicate elsewhere.

### Inferences (upgrade proposals)
1. Parse defensively: accept single/double quotes and case-insensitive tags in the
   three index regexes today (cheap); medium-term use a real XML parser for
   `index.xml` with regex fallback, and a tolerant HTML parser for the WCY menu.
2. Add per-driver canaries that turn redesigns into alarms (ties to §3.4): assert
   `len(items) >= max(1, 50% of last run's count)` after discover; assert page_ok-rate
   and convert-success-rate floors per faculty; any trip → `degraded` + issue, never
   exit 0. Store last-run counts in state (already have `fac['run']` with
   checked/changed/skipped — add `listed`).
3. Normalize converter contracts: every `driver.convert` raises on failure (never
   returns partial/empty silently); wrap `rozklad2ics.main`'s return code into an
   exception in the WCY driver; add a shared post-convert assertion
   (`event_count > 0`, group code present) before `validate`.
4. Pin page-shape fixtures per driver in tests (WLO/WML/WTC/IOE exist;
   `test_refresh.py:100-128,311-435,463-485`): add a WCY page_ok/convert fixture test
   and a "redesigned index" negative test per driver (single-quoted attrs, namespaced
   XML, renamed CSS classes) documenting what is/isn't tolerated.
5. Version-gate the PDF toolchain: record `pymupdf` version in run logs/state
   (action pins `pymupdf==1.28.2`, `action.yml:52`); on upgrade, diff event counts vs
   previous run and alarm on systematic drops before publishing.

### Gaps
- No WCY HTML fixture in `tests/` was inspected (only code paths); fixture existence
  would strengthen proposal 4 into exact test names.

## 7. Scheduling: daily cron + 20 h freshness is right on average, blind at the margins

### Takeaway
Daily off-hours crawling with 20 h freshness, stalest-first resume, and a 200 min cap
under a 240 min timeout is a coherent steady-state — but it over-crawls stable
mid-semester weeks and under-reacts during publication windows, with no per-faculty
differentiation.

### Cited findings
- `23 1 * * *` daily (~03:00 Warsaw in summer; ~02:20 in winter), self-hosted runner
  only, `max-minutes: 200`, job `timeout-minutes: 240` (`refresh.yml:9-11,32,49`);
  action default `max-minutes: 100` (`action.yml:18`). Concurrency group `refresh`,
  no cancel (`refresh.yml:23-25`) — a half-finished crawl resumes via state.
- `fresh_hours` default 20 h (`refresh.py:306`): with a 24 h cadence each group is
  rechecked daily with ~4 h slack for overruns; `--force` and `--limit` exist for
  manual catch-up (`refresh.py:304-307`). Stalest-first ordering makes cut-short runs
  cover the longest-unseen groups (`refresh.py:203-208`, tested).
- Change reality per docs: "the plans rarely change, so once a day is plenty"
  (`refresh.yml:9`); ahead passes only in August + Jan–Feb (`core.py:106-115`,
  `docs/REFRESH.md:125-132`). Publication windows are exactly when daily is *least*
  sufficient (faculties trickle out groups over days) and mid-semester is when daily
  is *most* wasteful (nothing changes for weeks; every run still pays index + 304s).
- Exit-3/4 are results piped through outputs (`action.yml:61-69`, `refresh.py:401-402`);
  only `blocked` opens an issue (`action.yml:97-109`). A faculty that publishes its
  winter plans over 5 days in August gets at most 5 looks — with `fresh_hours=20 h`
  each group is checked once, so late-published groups wait a full day.

### Inferences (upgrade proposals)
1. Keep daily as the baseline; add window-aware cadence: during August/Jan–Feb (or
   whenever ahead-pass `listed` counts are still growing run-over-run) run twice daily
   or drop `fresh_hours` to ~8 h for faculties with week-over-week change rates above a
   threshold; mid-semester with zero changes for N runs, relax to every 2–3 days per
   faculty. Drive it by measured change frequency per faculty, stored in state.
2. Per-faculty `fresh_hours` overrides in `sources.json` (e.g. volatile publishers
   12 h, stable ones 48 h) instead of one global flag; the stalest-first queue already
   handles the rest.
3. Right-size the time budget: `max-minutes: 200` with 7 faculties × hundreds of groups
   × ~4 s + retries is tight on a bad-latency day; keep 200 but add the per-faculty
   `incomplete_why=time-budget` export (§3.3) so chronic under-budget shows up as data,
   then tune per measured run durations rather than guessing.
4. Consider event-driven tightening later (cheap): a daily index-only job that compares
   `index.xml` hashes per faculty and triggers full crawls only on change — most days
   would cost 7 index fetches instead of 7 full revalidations.

### Gaps
- Real change-frequency per faculty (how many calendars change per week, per month)
  needs `data`-branch history mining; proposals 1–2 are designed to consume exactly
  that once measured.

## Cross-cutting priority (fewest requests, fewest missed changes)

1. Three-way error taxonomy + per-policy-group block learning (§1.1, §2.1–2.2) — stops
   learning rate-limits as Incapsula walls and halves WLO/WEL probe traffic.
2. `degraded` signal + mass-failure alarms + machine-readable incomplete causes
   (§3.3–3.4, §6.2) — converts silent redesigns into issues; the single biggest
   missed-change risk in the current design.
3. State hardening: corrupt-backup, term-aware freshness, check-driven saves
   (§5.1–5.3, §3.5) — each is small, each prevents a full-recrawl thundering herd.
4. Session hygiene + adaptive pacing (§4.1–4.3) — scope the WTC Referer, isolate jars,
   AIMD delays per policy group.
5. Window-aware scheduling (§7.1–7.2, §7.4) — spend the request budget where plans
   actually change.
