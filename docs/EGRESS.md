# Egress rotator (runner backend)

One `HTTP_PROXY` for the runner, with per-destination policy. Replaces tinyproxy's job:

| destination | policy |
|---|---|
| infra (GitHub, PyPI, proxy lists, … — parity with `allow.txt`) | direct egress |
| faculties (`*.wat.edu.pl`) | chained through a rotating pool of public proxies, a different egress IP per connection |
| anything else | 403 (same default-deny as tinyproxy) |

Why the pool lives here and not in `refresh.py`: the runner container has no direct
route out — everything funnels through the proxy tier, which 403s anything not
allowlisted (bare proxy IPs included). A process in the runner *cannot reach* public
proxies, so rotation must happen at the egress layer. `refresh.py` only needed
retry/backoff (`--retries/--retry-backoff`) and a run report for the GUI.

## Parts

- `tools/egress/pool.py` — proxy pool (DeadDropMGMT pattern): fetches the same 9 GitHub
  proxy lists (proxifly, monosans, thespeedx, roosterkid), probes candidates *through
  themselves* at a faculty index page (no third-party judge: 200 + marker = healthy),
  sorts ok → new → fail by latency, persists `pool.json`. Failed proxies sit out 15 min.
- `tools/egress/server.py` — forward proxy `:8888` (CONNECT + plain HTTP, ports 443/80
  only) with HTTP/SOCKS5/SOCKS4a upstream chaining, plus the LAN monitoring GUI `:8080`
  (host `:18080`, `:8080` is taken by cAdvisor on the runner host)
  (`/` dashboard, `GET /api/status`, `POST /api/run` report inbox, `POST /api/refresh` force-refresh).
  POSTs carry `Authorization: Bearer $EGRESS_API_TOKEN` when `EGRESS_API_TOKEN` is set.
- `Dockerfile.egress`, `requirements.txt` (curl_cffi, same pin as refresh),
  `compose.fragment.yml` (service snippet for the runner host compose file).
- `tools/egress/prometheus-alerts.yml`, `tools/egress/blackbox-snippet.yml` — drop-in
  alert + Blackbox probe template for the box Prometheus (not yet wired).

Empty-pool policy is fail-open by operator choice: faculty traffic goes direct and the
GUI shows DIRECT mode (`PLANWAT_EGRESS_DIRECT_FALLBACK=1`). Set it to `0` for
DeadDropMGMT-style fail-closed (faculty requests get 403 until the pool recovers).

## Monitoring GUI

LAN-only `http://<egress-host>:18080/` (container `:8080`; tighten the bind if the box
is more exposed than a home LAN). Auto-refreshes every 30 s. Shows:

- mode ROTATING vs DIRECT, pool size/health/median latency, fallback + deny counters;
- per-host ROTATING/DIRECT rows (`/api/status` `.hosts.<host>`: `verified` count + fallbacks;
  0 verified = that faculty rides direct);
- per-proxy table (url, status, latency, source);
- recent refresh runs as reported by `refresh.py` (`started/ended/exit` + per-faculty
  checked/changed/skipped/blocked, plus `degraded` when mass skips trip). Reports also
  persist in `/data/runs.json`.

Healthcheck: `GET /api/status` (200 = GUI alive; add as compose `healthcheck:`, unhealthy
alone never restarts — pair with an autoheal-style restarter).

`refresh.py` reports best-effort over the inner network (`PLANWAT_EGRESS_STATUS`,
default `http://<egress-ip>:8080/api/run`, empty disables); a dead GUI never fails a crawl.
Per-faculty run stats also land in `refresh-state.json` (`faculties.<name>.run`).
A degraded-but-not-blocked run opens/updates the `zdegradowane` issue (see refresh action).

Alerting (template, not yet wired): `prometheus-alerts.yml` (egress down 5m critical,
host stuck DIRECT 2h, pool alive <5, box disk >85%, runner offline) fed by the
`blackbox-snippet.yml` probe (`http_2xx`, 60s, `http://<egress-host>:18080/api/status`).

## Deploy checklist (runner host) — do NOT run until approved

1. `scp -r tools/egress <user>@<host>:/opt/planwat-egress/` (needs password SSH: flip
   `PasswordAuthentication` in `/etc/ssh/sshd_config.d/00-hardening.conf` + `systemctl restart ssh`).
2. Merge `compose.fragment.yml` into `<runner dir>/compose.yml` (adds `egress` on
   `<egress-ip>`, keeps tinyproxy untouched as rollback).
3. `docker compose up -d --build egress`, open `:18080`, wait for pool refresh → ROTATING.
4. Cutover: runner `HTTP_PROXY/HTTPS_PROXY/http_proxy/https_proxy` →
   `http://<egress-ip>:8888` with `NO_PROXY` covering the inner subnet
   (`localhost,127.0.0.1,<inner-subnet>`, so GUI/status polls skip the proxy),
   `docker compose up -d runner`.
5. Run a small refresh (`--faculty wcy --limit 5 --dry-run`), watch the GUI mode + runs table.
6. Rollback (any doubt): point the runner back at `http://<proxy-ip>:8888`, `up -d runner`.

No `allow.txt` change is needed: list fetching and probing happen inside the egress
container over its own direct route, and refresh traffic keeps flowing through one
allowlisted-in-spirit proxy that enforces the same policy.
