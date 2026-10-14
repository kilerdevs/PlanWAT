# Plebania egress robustness upgrades — ops-observability

## Monitoring GUI (server.py GuiHandler + dashboard template)

### Takeaway
The GUI proves mode/pool/runs at a glance but misleads when most faculties are DIRECT, has no per-host percentiles, no probe/refresh history, no runner connectivity, is LAN-open with no auth, and 30s full-page meta-refresh gives no event indication.

### Cited Findings
- Dashboard template is a static HTML string with `%MODE%`, `%TOTAL%/%OK%/%NEW%/%FAIL%`, `%MED%`, `%REFRESH%`, `%FALLBACKS%`, `%BLOCKS%`, `%HOST_ROWS%`, `%PROXY_ROWS%`, `%RUN_ROWS%` and `<meta http-equiv="refresh" content="30">` — no JS, no SSE/websocket, no auth check anywhere in `GuiHandler` (local: `tools/egress/server.py:339-359`, `362-437`).
- `/api/status` returns global `median_ok_ms` only, top-200 proxies sorted by latency, per-host `{mode, verified, fallbacks}` where mode is `ROTATING if verified>0 else DIRECT`, plus last-10 runs and `denied` counter; no p50/p95/p99 per host, no pool age vs `max_age`, no coverage-vs-threshold progress, no probe-history series (local: `tools/egress/server.py:376-396`, `pool.py:260-271 stats()`).
- Run table shows only `received/started/ended/exit/faculties(changed+blocked-mark)` for last 10; no in-progress run, no duration, no next-scheduled-run, no link to GitHub Actions run URL even though the refresh action knows `RUN_URL` and does not send it (local: `tools/egress/server.py:411-421`, `.github/actions/refresh/action.yml:94-109`, `tools/refresh/refresh.py:404-409`).
- `RunLog` caps at 30 reports kept in `/data/runs.json` with atomic tmp-replace; a dead GUI never fails a crawl (`post_run_report` best-effort, proxy-less opener, empty URL disables) (local: `tools/egress/server.py:203-228`, `tools/refresh/refresh.py:70-85`, `docs/EGRESS.md:43-45`).
- Live `/api/status` (2026-10-14, via read-only SSH curl) reported `mode: ROTATING` globally while 4/7 hosts were `DIRECT` (`wlo:0, wcy:0, wml:0, wtc:0` verified; `wel:1, wim:6, ioe:6`), `total:600 (577 fail, 23 ok)`, `median_ok_ms:4427`, `fallbacks_total:5`, `denied:2`, `last_error:null` (local observation: `curl http://127.0.0.1:18080/api/status` on plebania).
- GUI binds `0.0.0.0:8080` in-container, published as `0.0.0.0:18080->8080` on the box; `ss -tlnp` shows `0.0.0.0:18080`, `0.0.0.0:8080` (cAdvisor), `0.0.0.0:9090/9115/3030/9000`, only the site container is loopback-bound (`127.0.0.1:8088->8080`); `POST /api/run` and `POST /api/refresh` accept any LAN caller with no token (local: `tools/egress/server.py:480-481`, `compose.fragment.yml:34-38`, live `docker ps` + `ss -tlnp`).
- Egress access log shows `GET /` every ~30s from `172.23.0.1` (docker gateway — consistent with an existing Prometheus/Blackbox scraper polling HTML, not `/api/status`), plus `GET /api/status` bursts and `GET /favicon.ico 404` (local observation: `docker logs plebania-runner-egress-1`).
- Docs describe the GUI as LAN-only `http://plebania:8080`, auto-refresh 30s, showing mode/pool/median/fallbacks/denies, per-proxy table, and recent runs (local: `docs/EGRESS.md:33-45`).

### Inferences
- Global ROTATING banner is misleading when the majority of faculties have zero verified proxies and are in DIRECT-fallback; per-host mode rows exist but are visually subordinate and lack latency percentiles to judge whether ROTATING is actually usable.
- Unauthenticated `POST /api/refresh` lets any LAN host trigger expensive 150-candidate × 20-worker refresh loops; unauthenticated `POST /api/run` lets any LAN host inject fake run rows that persist into `runs.json`.
- 30s meta-refresh is adequate for human glance but loses scroll, polls hidden tabs, and gives no event cue (no banner/flash/diff when mode flips, pool empties, or a refresh fails); machines should poll `/api/status`, not scrape HTML.

### Gaps
- No source for who polls `GET /` every 30s from `172.23.0.1` (Prometheus scrape config and Blackbox targets on the box were not inspected — outside allowed read-only commands); confirm before adding a JSON scrape.
- No measurement of GUI page weight/latency with 600-entry pool (only top-100 rendered) or of behavior when `pool.json` grows unbounded.

## Alerting (what has NO alert; cheapest fit)

### Takeaway
Only crawl blocks get an alert (GitHub issue open/close); empty pool for hours, egress down, runner offline, disk filling, and GUI unreachable have no alert, while Prometheus + Blackbox + Grafana already on the box are the cheapest notifiers.

### Cited Findings
- Refresh action opens/comments/closes exactly one issue titled `Odświeżanie planów zablokowane (Incapsula)` when `blocked=true`, closes it after a clean non-incomplete run; incomplete-only runs neither open nor close; push of `data` happens even from blocked runs (local: `.github/actions/refresh/action.yml:96-109`).
- No workflow, container, or GUI code emits alerts for: pool empty/DIRECT for hours (`DIRECT` is a display string, not an alert), egress container down/unhealthy, runner offline (no queue check), disk filling, or GUI unreachable (local: `tools/egress/server.py:376-396 status()`, `compose.fragment.yml` (no alerting keys), `refresh.yml:1-49`).
- Box already runs `prom/prometheus` (`0.0.0.0:9090`), `prom/blackbox-exporter` (`0.0.0.0:9115`), `grafana/grafana` (`0.0.0.0:3030`), `gcr.io/cadvisor/cadvisor` (`0.0.0.0:8080`) — all `Up 11 hours` alongside the plebania stack (local observation: `docker ps`).
- Blackbox Exporter exposes `probe_success == 0` as the canonical down signal and `probe_duration_seconds` / `probe_ssl_earliest_cert_expiry` for latency/cert alerts — [blackbox rules](https://docs.ping7.io/docs/exporters/blackbox/rules.html), [probe + alert example](https://docs.appuio.cloud/user/how-to/monitor-http-endpoints.html), [config reference](https://github.com/prometheus/blackbox_exporter/blob/master/CONFIGURATION.md).
- Docker `HEALTHCHECK` alone only flips status to `unhealthy`; standalone Compose `restart` reacts to exit codes, not health — an unhealthy-but-running container is not restarted without Swarm or an external supervisor like autoheal — [healthcheck vs restart](https://yurtbay.dev/blog/docker-healthcheck-restart-policy/en/), [restart + depends_on](https://techearl.com/docker-restart-policies-health-checks), [forum: unhealthy does not restart](https://forums.docker.com/t/unhealthy-container-does-not-restart/105822).
- Live failure with no alert today: `maintain()` crashes every cycle with `pool refresh failed: too many values to unpack (expected 2)` yet `/api/status.last_error` stays `null` and no issue/workflow fires (local observation: `docker logs plebania-runner-egress-1`; local: `tools/egress/server.py:461-470` vs `pool.py:380` returning 3 values).

### Inferences
- Cheapest alerting that fits is: add Blackbox HTTP probes for `http://egress:8080/api/status` (or host `:18080`) with `probe_success==0 for 5m → critical`, plus Prometheus rules on `probe_http_status_code`, pool-derived metrics (DIRECT-host count, `verified==0`, `median_ok_ms`), `node/filesystem` disk, and `up{job}` for runner/exporters; route via existing Grafana contact points rather than introducing Uptime Kuma (no Kuma container was observed in `docker ps`).
- Next-cheapest after probes: container `healthcheck` on `/api/status` + `depends_on: service_healthy` for the runner, paired with an autoheal-style restarter, since health status alone will not restart egress.
- GitHub-issues alerting should stay for crawl blocks only; infra alerts (disk, down, empty pool) belong in Prometheus/Grafana to avoid issue spam and to cover periods when Actions cannot run (runner offline).

### Gaps
- Prometheus scrape/alertmanager configuration on the box was not read (outside allowed commands); unknown whether `probe_success` alerts or mail/Slack receivers already exist.
- No evidence for who should receive pages (single operator?); cheapest receiver (email vs Grafana OnCall vs GitHub issue) could not be chosen from code alone.

## Logging (one-line-per-tunnel, rotation, structured vs text, correlation, curl visibility)

### Takeaway
One line per tunnel keeps logs small but destroys forensics: no request IDs linking crawl jobs to tunnels, no curl error text, text-only unstructured logs, and pool-refresh crashes leave no queryable trace.

### Cited Findings
- `ProxyHandler.log_message` is a no-op with comment `keep docker logs to one line per tunnel, not per chunk`; each CONNECT/plain-HTTP emits one `print(f'tunnel {host}:{port} via {via}')` or `print(f'{METHOD} http://{host}{raw} via {via}')` (local: `tools/egress/server.py:236-237`, `294`, `317`).
- Live egress logs are dominated by `tunnel <github/actions/blob hosts>:443 via direct` and `GET /` / `GET /api/status` lines; faculty `chain` tunnels are absent from the tail, and the only pool signal is `pool refresh failed: too many values to unpack (expected 2)` plus a `BrokenPipeError` traceback from `GuiHandler._send` on a dropped client (local observation: `docker logs --tail 60 plebania-runner-egress-1`).
- Container log rotation is `json-file max-size 10m max-file 3` (≈30 MB cap) for egress; runner/proxy log rotation was not confirmed from allowed inspection (local: `compose.fragment.yml:22-26`).
- `pool.py` probing swallows transport detail: `probe_alive`/`probe_host` return `ms or None` on any `Exception`; `fetch_via` uses `curl_cffi` with a fixed `PlanWAT-healthcheck` UA and no request/correlation ID; `mark()` records only `ok/ms/fails/last_checked/source/hosts` (local: `pool.py:212-244`, `293-317`).
- `refresh.py` retry helper logs nothing per attempt (sleeps with jitter, raises last error); `post_run_report` logs only `run report not delivered ({err}); continuing` (local: `tools/refresh/refresh.py:45-67`, `70-85`).
- Counters exist but are coarse: `blocks` increments only on deny/`proxy_empty`/502 paths, `fallbacks[host]` counts DIRECT-fallback uses, no per-tunnel latency/bytes/status-code/error-string (local: `tools/egress/server.py:281-285`, `302-306`, `327-335`).

### Inferences
- Correlating a crawl job with the egress tunnels it used is currently impossible: no `X-Request-ID`/job ID is generated in `refresh.py`, forwarded as a header, or logged in `server.py`; simultaneous jobs or manual curls are indistinguishable.
- Curl-level forensics (DNS, TLS, Incapsula body marker, SOCKS handshake stage) are lost at the point of failure; `None` erases whether the list fetch, Round-1 tile, or Round-2 faculty index failed and why.
- JSON-structured access/error logs (timestamp, job/request ID, host, via-proxy URL, ms, bytes, verdict) would make `docker logs` greppable and shippable to Prometheus/Loki without increasing volume much beyond one line per tunnel.

### Gaps
- No sample of a successful `chain` tunnel log line or of Round-2 failure detail was captured in the inspected tail; whether chain successes are even logged with proxy URL + ms could not be confirmed live.
- Log retention on the box (`/var` 28% vs Docker json-file caps) and whether Prometheus/Loki scrapes container logs at all is unknown from allowed commands.

## Deployment (scp, no CI gate, compose drift, unpinned digest, missing healthcheck)

### Takeaway
Egress ships by manual `scp` with no CI gate, so the live crash (`maintain` unpacking 3-tuple as 2-tuple) passed tests; compose is a hand-merged fragment, the base image is unpinned, and there is no healthcheck to even mark the container unhealthy.

### Cited Findings
- Deploy checklist is manual: `scp -r tools/egress`, hand-merge `compose.fragment.yml` into `~/plebania-runner/compose.yml`, `docker compose up -d --build egress`, wait for ROTATING, then point runner proxy env and `up -d runner`; rollback is pointing back at tinyproxy `172.30.77.2:8888` (local: `docs/EGRESS.md:47-57`, `compose.fragment.yml:1-5`, `47-50`).
- CI (`ci.yml`) runs Node unit, Python `python -m unittest discover -s tests`, browser e2e, and a site-image Grype+smoke job; nothing builds, lints, scans, or compose-validates `tools/egress` (local: `.github/workflows/ci.yml:18-167`).
- Existing offline tests do cover `pool.refresh` returning `(alive, tried, verified)` 3-tuple and routing/report round-trip, but no test imports or calls `maintain()` — so the `ok, tried = pool.refresh()` 2-unpack crash was not caught (local: `tests/test_egress.py:92-103`, `185-213`, `tools/egress/server.py:461-470`, `pool.py:319-380`).
- SAST is CodeQL over JS/Python/Actions on push/PR/weekly; no image scan for egress, unlike the site image which gets Grype `high/only-fixed/fail-build` (local: `.github/workflows/sast.yml:1-43`, `ci.yml:134-141`).
- `Dockerfile.egress` pins `FROM python:3.13-slim` with no digest and `curl_cffi==0.13.0` only in `requirements.txt`; the site `Dockerfile` digest-pins both stages (`python:3.14-alpine@sha256:…`, `nginx-unprivileged@sha256:…`) and Dependabot proposes bumps (local: `tools/egress/Dockerfile.egress:1-18`, `Dockerfile:1-16`).
- `compose.fragment.yml` sets `image: plebania/egress:1`, `restart: unless-stopped`, `read_only:true`, `cap_drop:[ALL]`, `mem_limit:256m`, `pids_limit:128`, `tmpfs /tmp`, `egress-data:/data`, `inner 172.30.77.4`; it defines no `healthcheck`, and `server.py` exposes no `/healthz` (only `/`, `/api/status`, `/api/run`, `/api/refresh`) — live `docker ps` shows `proxy` as `(healthy)` but `egress` with no health state (local: `compose.fragment.yml:6-42`, `tools/egress/server.py:398-453`, `Dockerfile` site healthcheck `Dockerfile:28`).
- Live images are mutable tags rebuilt recently (`plebania/egress:1` 40 min ago, `plebania/runner:1` + `plebania/proxy:1` 24 h ago, all `:1`/`:latest` with no digest in `docker images`) (local observation: `docker images`).

### Inferences
- What breaks next: any `pool.refresh()` signature change, Python 3.13-slim breaking change, or hand-merge typo in networks/ports/env will ship straight to the box; without a compose-validation gate (`docker compose config`) and an egress build+test+scan job, the next failure mode is another silent runtime crash like the current `maintain` bug.
- Minimal pipeline fix: CI job that (1) builds `Dockerfile.egress` with pinned digest, (2) runs `tests/test_egress.py` plus a `maintain`-unpack regression test, (3) runs `docker compose config` on the merged file, (4) Grype-scans the egress image like the site image; keep `scp` only until a push-based deploy (git pull on box or registry pull) replaces it.
- Missing healthcheck matters twice: Compose cannot order `runner depends_on egress healthy`, and Prometheus/Blackbox has no lightweight `/healthz` to probe without parsing JSON.

### Gaps
- Remote `~/plebania-runner/compose.yml` was not diffed against the fragment (file read outside allowed `docker ps/logs, df, ss` + `stats`); exact drift (runner mem/env/networks, proxy vs egress cutover flags) could not be confirmed.
- Whether Dependabot covers `tools/egress/requirements.txt` (`curl_cffi`) or Docker digests is unknown from local config inspected.

## Reliability of one box (disk, backup, SPOF, reboot, limits vs usage)

### Takeaway
One home-LAN box is the SPOF with `/` at 84% and `/srv` (volume backing) at 98%; volumes have no backup, restart policies do survive reboot, and egress/runner limits fit current use — but box-wide contention and disk exhaustion are the near-term killers.

### Cited Findings
- `df -h`: `/dev/nvme0n1p2 11G 8.3G 1.7G 84% /`, `/dev/nvme0n1p3 4.2G 1.1G 2.9G 28% /var`, `/dev/nvme0n1p5 101G 93G 2.8G 98% /srv`; inodes healthy (26%/3%/3%) (local observation: `df -h; df -i` on plebania).
- Docker volumes live under `/srv/docker/volumes/` (egress mount `Source: /srv/docker/volumes/plebania-runner_egress-data/_data → /data`); named volumes observed: `plebania-runner_egress-data` (pool.json/runs.json), `plebania-runner_runner-home` (runner credentials/work), plus deaddrop/portainer volumes; no backup job, snapshot, or off-box copy was visible in `docker ps` or repo docs (local observation: `docker volume ls` + `docker inspect --format {{json .Mounts}}`).
- All three plebania containers report `restart=unless-stopped` (`egress`, `runner`, `proxy`), so a clean box reboot brings them back unless manually stopped — but health-gating is absent and Docker-daemon enablement was not verified (local observation: `docker inspect --format RestartPolicy`; [restart semantics](https://yurtbay.dev/blog/docker-healthcheck-restart-policy/en/), [restart + healthchecks](https://techearl.com/docker-restart-policies-health-checks)).
- Live uptimes after a recent restart cycle: `egress Up 40 min`, `runner Up 28 min`, `proxy Up 2 h (healthy)`, everything else `Up 11 h (healthy/unhealthy)` — `deaddrop-app-1` is `unhealthy`, showing the box already tolerates an unhealthy neighbor (local observation: `docker ps`).
- `docker stats --no-stream`: `egress 0.05% CPU 77.5MiB/256MiB (30%)`, `runner 0.08% 71.1MiB/2GiB`, `proxy 0.00% 1.75MiB/64MiB`; box neighbors dominate RAM (`grafana 1002MiB`, `prometheus 293MiB`, `jellyfin 377MiB`, `adguard 336MiB`) with `cadvisor 4.24% CPU` (local observation: `docker stats`).
- Fragment hardens egress (`read_only`, `cap_drop ALL`, `no-new-privileges`, `mem 256m`, `pids 128`, `nofile 4096`, `tmpfs /tmp`, `user 10002`) consistent with live mem-ratio headroom (local: `compose.fragment.yml:12-26`, `Dockerfile.egress:10-15`).

### Inferences
- `/srv` at 98% (2.8 GB free on 101 GB) is the most urgent single-box risk: pool persistence, run reports, runner workdirs, image pulls, and json-file logs all compete for the same nearly-full filesystem; a single large pull or jellyfin/media write can tip egress writes into `ENOSPC`/`EROFS`-style save failures that `save()` silently swallows (`except OSError: pass`).
- SPOF assessment: box loss/reboot without backup loses `pool.json` (600 learned entries), `runs.json` (30-run history), and `runner-home` credentials (re-registration needed); faculty crawl halts (no second runner — `refresh.yml` is `runs-on: [self-hosted, planwat]` only) and Pages keeps serving stale `data` until the box returns.
- What survives reboot today: containers (unless-stopped) and volumes (local driver) do; what does not: in-flight crawls (240-min timeout, resumed from `refresh-state.json` only if `data` push happened), pool coverage for 4 DIRECT hosts, and any unauthenticated-GUI assumption if the LAN is reconfigured.

### Gaps
- What fills `/` vs `/srv` (Docker root on `/var` vs volumes on `/srv` vs jellyfin/media) and per-volume sizes (`du -sh /srv/docker/volumes/*`) were not measured (outside allowed commands); the 84% vs 98% split needs a follow-up disk-triage pass.
- Docker daemon `Enabled` at boot (`systemctl is-enabled docker`) and static-IP collision handling for `172.30.77.4` after reboot were not verified.

## Runner hygiene (cleanup hook, work-dir growth, version pin, NO_PROXY)

### Takeaway
Cutover to egress is done and a cleanup hook is wired, but work-dir growth is unmeasured, the runner version is a mutable `:1` tag, and `NO_PROXY` omits the inner network/GUI.

### Cited Findings
- Runner env (live inspect): `HTTP_PROXY/HTTPS_PROXY/http_proxy/https_proxy=http://172.30.77.4:8888` (egress cutover complete, tinyproxy `172.30.77.2:8888` retained only as rollback per docs), `NO_PROXY/no_proxy=localhost,127.0.0.1` only, `ACTIONS_RUNNER_HOOK_JOB_COMPLETED=/usr/local/bin/job-cleanup.sh`, `RUNNER_URL=https://github.com/kilerdevs/PlanWAT`, `RUNNER_NAME=plebania` (local observation: `docker inspect --format {{json .Config.Env}} plebania-runner-runner-1`; local: `compose.fragment.yml:47-50`, `docs/EGRESS.md:54-56`).
- Refresh reporting bypasses the proxy via a proxy-less `urllib` opener, so GUI `POST /api/run` works despite minimal `NO_PROXY`; any other in-job HTTP client that honors `*_PROXY` (curl, git, `curl_cffi` without `trust_env=False`) reaching `172.30.77.4:8080` or inner hosts would be sent to the egress proxy and `403` (`route()` denies non-direct/non-chain hosts and bare IPs) (local: `tools/refresh/refresh.py:70-85`, `tools/egress/server.py:75-84`).
- Runner daemon reports `Current runner version: 2.338.0`, `Listening for Jobs`, with recent `refresh` jobs `Succeeded/Failed/Succeeded` on 2026-10-14; images are `plebania/runner:1` + `plebania/proxy:1` built 24 h ago, `plebania/egress:1` 40 min ago — all mutable tags, no digest pin observed (local observation: `docker logs --tail plebania-runner-runner-1`, `docker images`).
- Docs prescribe treating the workdir as disposable (`wipe /home/runner/_work` after jobs, re-register on doubt; prefer ephemeral runners) and note the self-hosted venv workaround (`$RUNNER_TEMP` throwaway venv because baked `/opt/venv` is read-only) with per-job `curl_cffi==0.13.0 pymupdf==1.28.2` install (local: `docs/REFRESH.md:113-118`, `.github/actions/refresh/action.yml:47-53`).
- Hook presence only was verified (`ACTIONS_RUNNER_HOOK_JOB_COMPLETED` set); script body, workdir size trends, and whether `_work` is actually wiped were not inspected under read-only limits.

### Inferences
- `NO_PROXY` should be extended to `localhost,127.0.0.1,172.30.77.0/24` (or at minimum `172.30.77.4`) plus any Prometheus/Blackbox scrape targets, otherwise future GUI polling or artifact uploads from jobs risk proxy-loop 403s that look like crawl blocks.
- Mutable `:1` tags mean a box-side `docker compose build` can silently change the runner version under a pinned workflow; pin by digest in the box compose and record `2.338.0` in the repo so hosted-vs-selfhosted drift is visible.
- Without workdir size monitoring, stale `_work` growth on the 84%-full `/` (or `/srv`-backed home volume) will first appear as flaky `ENOSPC` during `pip install`/venv creation or `git checkout`, not as a clear runner alert.

### Gaps
- Job-cleanup script adequacy (`/usr/local/bin/job-cleanup.sh` content, exit-code handling, `_work` + `$RUNNER_TEMP` coverage) and current `_work` size could not be verified (file read/`du`/`exec` outside allowed `docker ps/logs, df, ss, stats`); needs a follow-up inspection.
- Runner registration-token age, auto-update policy for `2.338.0`, and whether failed jobs (e.g. 16:41 `Failed`) leave residue are unknown from daemon logs alone.
