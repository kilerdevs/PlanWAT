# Plebania egress robustness upgrades

## Pool selection vs DeadDropMGMT parity

### Takeaway
`pick()` matches DeadDropMGMT's ok → new → fail + latency ordering at a high level, but omits consecutive-failure penalties, latency decay, rated-vs-unrated preference, and the wholesale-failure circuit breaker — and it tries only one candidate per connection instead of walking the pool.

### Cited Findings
- PlanWAT tiers as `{'ok': 0, 'new': 1}.get(status, 2)` with latency tie-break, and `pick()` uses `(0, host-ms)` for host-verified, `(1, global-ms)` for globally-alive-but-untried, skipping host-failed in cooldown — `tools/egress/pool.py:127-130,189-210`.
- DeadDropMGMT sorts the same way: `match last_status {'ok'=>0,'new'=>1,default=>2}` then `latency_ms` comparison, fastest-first — `includes/proxy.php:991-1002` in `C:\Users\Jakub\AppData\Local\Temp\opencode\ddmgmt`.
- DeadDropMGMT per-attempt bookkeeping updates `last_status` + `latency_ms` on every try with write-coalescing (skip write when same status, latency within 500 ms, checked <60 s ago) — `includes/proxy.php:857-879`.
- PlanWAT `mark()` freezes the first global latency (`if latency_ms is not None and e.get('latency_ms') is None`) and `mark_alive()` overwrites each Round-1 probe; `fails` is incremented on host-fail but never read by `pick()` — `tools/egress/pool.py:212-244`.
- PlanWAT `_sort_key()` is defined but never called by `pick()`/`verified()` (dead code); `verified()` sorts only by `via_ms` — `tools/egress/pool.py:127-130,180-187`.
- DeadDropMGMT discovery tracks `rated` per source (proxifly rated JSON trusted; unrated HTTP must pass a live header-echo judge), and `proxy_filter_anonymity()` drops all unproven unrated HTTP when the judge is unreachable (fail-closed) — `includes/proxy.php:1221-1235,1479-1531`.
- PlanWAT `LIST_SOURCES` drops the `rated` flag entirely and `normalize_list()`/`parse_proxy_url()` accept any public IP without an anonymity gate — `tools/egress/pool.py:34-44,54-124`.
- DeadDropMGMT has a pool circuit breaker (`pool_down_until` + pool fingerprint, 60 s trip, implicit clear on membership change, explicit clear on success) plus a 10 s whole-request budget and 2 s per-attempt timeout with client-disconnect bail-out — `includes/proxy.php:932-956,1004-1043`.
- PlanWAT `ProxyHandler._open()` tries only the single best `pick()` result once, then falls back to direct; there is no walk of N candidates, no overall budget, no trip — `tools/egress/server.py:249-274`.
- DeadDropMGMT `PROXY_DISCOVERY_SOURCES` carries `rated` metadata distinguishing anonymity-rated vs unrated HTTP lists — [proxifly/monosans/thespeedx/roosterkid source table](https://github.com/lexiforest/curl_cffi/blob/main/README.md) is not the source; see `includes/proxy.php:1221-1235` locally; rated-concept documented in code comments.
- cURL proxy-type semantics (`socks5://` local DNS vs `socks5h://` proxy DNS, `socks4a://` proxy DNS) are defined in libcurl — [CURLOPT_PROXY docs](https://github.com/curl/curl/blob/master/docs/libcurl/opts/CURLOPT_PROXY.md).

### Inferences
- Add: consecutive-failure counter with exponential backoff per proxy (global + per-host), EWMA latency with periodic re-measurement instead of freeze-on-first, `rated` preference (SOCKS + proxifly-anonymous first), and a DeadDropMGMT-style circuit breaker (fingerprint + 60 s trip + 10 s CONNECT budget) to avoid re-probing a dead pool under burst.
- Change `pick()` to return top-N (e.g., 3) fastest qualifying candidates and make `_open()` walk them with short per-attempt timeouts before fallback, mirroring `osm_fetch()`'s fastest-first walk.
- Remove or wire `_sort_key()`; unify `verified()`/`pick()` ranking so global latency cannot mask a stale fast entry.

### Gaps
- `maps_pick_proxy()` body (`includes/maps.php:1256`+) was not fully read; parity claim for "ok → new → fail + latency sort as osm_proxy_pool()/maps_pick_proxy()" relies on `osm_fetch()` sort + code comment in `pool.py:12-13`. Need to confirm `maps_pick_proxy()` does not add extra filtering (e.g., `forCli` HTTP-only constraint).
- No reliable source found for optimal failure-penalty constants for faculty/Incapsula hosts; DDMGMT constants (60 s trip, 10 s budget, 2 s attempt) are OSM-tile-tuned, not faculty-tuned.

## Probing: Round 1 + Round 2 split, timeouts, workers, caps, continuous vs batch

### Takeaway
The Round 1 (neutral OSM tile) + Round 2 (faculty index) split is the right call for Incapsula-fronted hosts, but timeouts/workers/slice caps are loosely tuned, list fetching is sequential, and verification is batch-only with no continuous revalidation.

### Cited Findings
- Round 1 target `https://a.tile.openstreetmap.org/13/4051/2749.png` is identical in PlanWAT and DeadDropMGMT (`tools/egress/pool.py:47`; `includes/proxy.php:1464,1797`).
- Round 2 targets are each chain host's own index + content marker (`<?xml` for XML indexes, `None` for WCY/WML HTML) — `tools/egress/server.py:56-72`; probe requires 200 + len>500 + marker in first 400 bytes — `tools/egress/pool.py:308-317`.
- Defaults: `max_probe=150`, `probe_timeout=8`, `max_age=6h`, `min_alive=25`, `min_verified=5`, `workers=20`, `round2_cap=40` — `tools/egress/pool.py:136-146,319`; `maintain()` interval 600 s — `tools/egress/server.py:461-470`.
- DeadDropMGMT discovery defaults: `max_test=400`, `timeout_s=4`, latency cutoff `<3000 ms`, unrated slice capped at 100 (CLI) / 10 (budgeted) — `includes/proxy.php:1398,1468-1485`.
- PlanWAT `probe_alive()` has no latency cutoff (any ms with 200 + len>1000 passes) — `tools/egress/pool.py:300-306`.
- PlanWAT list fetching is sequential with 30 s timeout per list (`for name,url...: fetcher(url) if fetcher else _direct_get(url)`) — `tools/egress/pool.py:325-330,383-389`; DeadDropMGMT fetches all 9 lists in one parallel round with 2 MiB cap — `includes/proxy.php:1365-1380`.
- PlanWAT `refresh()` prunes first, shuffles fresh candidates, slices to `max_probe`, Round-1s them, then Round-2s only thin hosts cheapest-first — `tools/egress/pool.py:319-380`; DeadDropMGMT shuffles + slices similarly — `includes/proxy.php:1458-1461`.
- DeadDropMGMT revalidates stalest 3 entries older than 7 days even without traffic (`osm_proxy_revalidate_stale`) and heals on live failure via detached `cron/proxy_heal.php` with lock + 600 s cooldown + replace-never-delete rule — `includes/proxy.php:892-922,1770-1801` and `cron/proxy_heal.php:1-40`.
- PlanWAT learning between reseeds is only `mark()` on real use + `needs_refresh()` (stale age or coverage thin) + `prune()` after 24 h fail — `tools/egress/pool.py:212-229,273-290`; no stale re-probe, no heal-kick, no lock/cooldown.
- Offline tests cover `refresh()` merge with stubbed `probe_alive`/`probe_host` — `tests/test_egress.py:92-102`.

### Inferences
- Keep the two-round split (neutral aliveness is insufficient against network-level datacenter-IP drops; faculty-index verification is the load-bearing check).
- Tune: add `<3000 ms` (or faculty-measured p95) cutoff to Round 1, parallelise list fetches with per-list timeout + 2 MiB cap, cap per-source contribution to `max_probe` slice for diversity, and enforce a global refresh deadline so `maintain` cannot stall past its 600 s interval.
- Add continuous verification: stale re-probe (e.g., oldest-N unchecked per maintain pass), latency re-measurement (EWMA), and failure-triggered fast re-probe of the failed entry (DeadDropMGMT `heal_kick` equivalent) instead of waiting for coverage to go thin.
- `round2_cap=40` × up to 7 thin hosts = up to 280 Round-2 probes per refresh; with `workers=20` and 8 s timeout worst-case ~112 s — fits in 600 s interval but blocks pool improvement visibility; consider per-host caps scaled by deficit (`min_verified - n`) rather than flat 40.

### Gaps
- No measurement of faculty-index p50/p95 through public proxies, so 8 s vs 4 s vs 3 s cutoff and 20 workers cannot be optimally set from cited sources; needs egress-box probing data.
- Unknown whether OSM tile Round 1 is rate-limited when hit by 150 parallel probes; no source found on tile-host abuse limits for health-check use.

## Chaining transport: chain_connect() + relay() correctness

### Takeaway
HTTP CONNECT and SOCKS5-remote-DNS paths are broadly correct, but SOCKS4a reply validation is over-strict, `https://` upstream proxies are accepted yet never TLS-wrapped, handshake readers lack absolute deadlines and size caps, overlong hostnames can escape the `OSError`-only fallback, and `relay()` kills long-lived active tunnels at a fixed 120 s deadline while spawning 3 threads per tunnel.

### Cited Findings
- `chain_connect()` supports `http`/`https` (same cleartext CONNECT), `socks5` (DOMAIN remote DNS), `socks4` (4a form with `0.0.0.1` + hostname) — `tools/egress/server.py:112-154`.
- HTTP CONNECT request is `CONNECT host:port` with no `Proxy-Authorization`; response accepted only on `HTTP/1.1 200` / `HTTP/1.0 200` prefix — `tools/egress/server.py:118-129`; DeadDropMGMT sends `Proxy-Authorization` when credentials exist and parses status via `/^HTTP\/\S+\s+(\d{3})/` with 32 KiB head cap and absolute deadline — `includes/proxy.php:144-150,177-190,331-364,476-482`.
- SOCKS5 greeting is no-auth-only (`\x05\x01\x00`, expect `\x05\x00`); `socks5_connect` always uses DOMAIN type with `host.encode('idna')` — `tools/egress/server.py:130-142`; DeadDropMGMT documents "SOCKS always resolves AT THE PROXY (DOMAIN), never via local resolver" — `includes/proxy.php:99-103,161-164`.
- SOCKS5 reply tail draining (IPv4 6 / domain len+2 / IPv6 18) mirrors DeadDropMGMT `match` on `\x01`/`\x04`/`\x03` — `tools/egress/server.py:139-142` vs `includes/proxy.php:522-542`.
- SOCKS4a request uses `0.0.0.1` sentinel (`\x04\x01` + port + `\x00\x00\x00\x01` + `anonymous\x00` + host) and requires reply exactly `b'\x00\x5a\x00\x00\x00\x00\x00\x00'` — `tools/egress/server.py:143-147`; DeadDropMGMT uses `0.0.0.255` sentinel and checks only `rep[0]==\x00 && rep[1]==\x5a`, ignoring bind address — `includes/proxy.php:166-175,545-554`.
- libcurl documents `socks4a://` as "Proxy resolves URL hostname" and `socks5h://` as "Proxy resolves URL hostname" vs plain `socks5://` — [CURLOPT_PROXY](https://github.com/curl/curl/blob/master/docs/libcurl/opts/CURLOPT_PROXY.md); cURL `--socks5-hostname` lets the proxy resolve — [curl docs](https://curl.se/cvssource/docs/cmdline-opts/socks5-hostname.md).
- `https://` proxy scheme falls through to cleartext CONNECT with no TLS-to-proxy; DeadDropMGMT explicitly TLS-wraps to the proxy first for `https` scheme — `includes/proxy.php:460-467`.
- `_recv_exact()` uses per-`recv` 10 s timeout with no overall deadline and no head-size cap; HTTP head loop accumulates unbounded until `\r\n\r\n` — `tools/egress/server.py:101-129`.
- Overlong SOCKS5 hostname: `bytes([len(hb)])` raises `ValueError` for len>255, but `ProxyHandler._open()` catches only `OSError` and `do_CONNECT` catches only `OSError` — `tools/egress/server.py:135,249-285`.
- `relay()` spawns 2 copy threads per tunnel plus a polling loop with fixed `deadline = monotonic + TUNNEL_IDLE` (120 s), `select` + `MSG_PEEK` closure check, `shutdown(SHUT_RDWR)` on either-direction end — `tools/egress/server.py:157-199` with `TUNNEL_IDLE=120`, `BUF=65536` — `tools/egress/server.py:47-49`.
- `SUPPORTED_SCHEMES = ('http','https','socks5','socks4')` with no `socks5h`/`socks4a` normalisation — `tools/egress/pool.py:49`; DeadDropMGMT normalises `socks5→socks5h`, `socks4→socks4a` for cURL — `includes/proxy.php:41-45`.

### Inferences
- Fix SOCKS4a reply check to accept any bind address on 90 (`rep[0]==0x00 and rep[1]==0x5A`), matching DeadDropMGMT; this alone recovers compliant proxies currently discarded.
- Decide `https://` proxies: either TLS-wrap before CONNECT (DDMGMT parity) or drop `roosterkid-https` from `LIST_SOURCES` / reject `https` in `parse_proxy_url` so probing (curl_cffi handles it) and chaining agree; current mix wastes pool slots on entries that probe OK but can never chain.
- Add absolute handshake deadlines + 32 KiB head cap (DDMGMT `proxy_read_until` pattern), `Proxy-Authorization` support if manual authenticated proxies are ever allowed, robust status-code regex, and widen `_open`/`do_CONNECT` to `except Exception` (or validate hostname length upfront) so a single bad hostname cannot kill a handler thread without a client response.
- Rework `relay()`: sliding idle deadline refreshed on activity, single `select`-driven bidirectional loop or 2-thread with shared event instead of 2 threads + polling thread, half-close awareness for CONNECT tunnels, and per-faculty idle tuning if Incapsula is slow.

### Gaps
- No packet-level test of `0.0.0.1` vs `0.0.0.255` sentinel acceptance across the actual free-list SOCKS4a population; strict-server behaviour is inferred from RFC 4a convention, not measured.
- No source confirming faculty hosts need >120 s tunnels; 120 s adequacy for slow faculty index fetches is unmeasured.

## ThreadingHTTPServer burst load and backpressure

### Takeaway
Both proxy (`:8888`) and GUI (`:8080`) servers are unbounded-thread `ThreadingHTTPServer`s with no connection cap, queue tuning, or circuit breaker — each tunnel costs 3 threads for up to 120 s, so concurrent crawl jobs can exhaust the `pids_limit: 128` / 256 MiB container quickly.

### Cited Findings
- `ProxyServer(ThreadingHTTPServer)` and `GuiServer(ThreadingHTTPServer)` with `daemon_threads=True`, no thread-pool, no semaphore — `tools/egress/server.py:327-335,456-458`.
- Python `ThreadingMixIn` spawns a new thread per request with no built-in limit; only `ForkingMixIn.max_children` exists for process capping — [socketserver docs](https://docs.python.org/3/library/socketserver.html); `ThreadingHTTPServer` is documented as "uses threads to handle requests by using ThreadingMixIn" — [http.server docs](https://docs.python.org/3/library/http.server.html).
- Per CONNECT cost: 1 handler thread + 2 `relay` copy threads, held until close or fixed 120 s deadline — `tools/egress/server.py:157-199,276-295`.
- Compose caps: `mem_limit: 256m`, `pids_limit: 128`, `nofile: 4096`, no CPU limit, no `healthcheck` — `tools/egress/compose.fragment.yml:16-20`.
- DeadDropMGMT equivalent backpressure: pool circuit breaker fails fast without re-probing for 60 s, 10 s whole-request budget, client-disconnect bail-out — `includes/proxy.php:1004-1043`; PlanWAT has no equivalent trip/budget.
- `maintain()` runs `pool.refresh()` (up to ~60-170 s of probing) on a daemon thread with no lock against concurrent `/api/refresh` triggered refreshes — `tools/egress/server.py:439-470`; two overlapping `refresh()` calls can double probe load.

### Inferences
- Add a bounded tunnel semaphore (e.g., 32-64 concurrent tunnels, deny with 502/429 + `Retry-After` beyond it), raise `request_queue_size` explicitly instead of relying on default 5, and add a pool-down circuit breaker so dead-pool bursts fail fast instead of each holding a `chain_connect` 10 s timeout.
- Serialize `refresh()` with a non-blocking lock (return 409/202-already-running on `/api/refresh` when held), and consider a separate low-priority executor for probes so crawl traffic never waits on probe threads.
- Set compose `healthcheck` (GUI `/api/status`), `cpus` limit, and raise/test `pids_limit` against measured threads-per-tunnel (3× cap must exceed semaphore + probe workers + GUI).

### Gaps
- No load measurement of concurrent refresh jobs through the egress (connections/job, tunnel lifetime distribution); semaphore size cannot be finalised without it.
- No source for Python thread stack default inside `python:3.13-slim` (typically 8 MiB virtual, less resident); 256 MiB adequacy under 100+ threads is untested.

## Fail-open fallback accounting and per-host policy

### Takeaway
Per-host fallback counting exists but is racy and the GUI's top-level ROTATING-vs-DIRECT signal is global, not per-host — and the single global fail-open switch with single-try-then-direct means one flaky best proxy leaks operator IP where DeadDropMGMT would fail closed.

### Cited Findings
- Empty-pool/no-qualify path returns `None` from `pick()` and `_fallback()` dials direct when `PLANWAT_EGRESS_DIRECT_FALLBACK in ('1','true','yes')`, else raises `proxy_empty` → 403 — `tools/egress/pool.py:189-210` and `tools/egress/server.py:249-274`; default is fail-open per operator choice, documented in `docs/EGRESS.md:29-31` and `tools/egress/server.py:12-14`.
- DeadDropMGMT is fail-closed: empty pool or all-fail returns false / `code:proxy_empty`, never silent direct — `includes/proxy.php:13-15,976-980` and `includes/maps.php:664-665,859-862`.
- `fallbacks` is a plain dict incremented without a lock (`self.server.fallbacks[host] = ... + 1`) and `blocks += 1` likewise; GUI copies via `dict(...)` on another thread — `tools/egress/server.py:272,283-284,304-305,389-391`.
- GUI top `mode` is `ROTATING` if any proxy has `status=='ok'` globally, while per-host `host_modes` is DIRECT when that host has 0 verified — `tools/egress/server.py:377-388`.
- `_open()` marks pool success/fail per real use (`osm_proxy_mark` equivalent) — `tools/egress/server.py:261-268` and `tools/egress/pool.py:212-229`; host-fail does not touch global `status` (stays `ok`), only `fails += 1` — `tests/test_egress.py:86-90` pins this.
- Tests pin fail-open-adjacent routing (`route()` direct/chain/deny, `split_target` ports 80/443 only) — `tests/test_egress.py:105-128`.

### Inferences
- Make counters atomic (per-host `Lock` or `collections.Counter` + lock, or sharded atomics) and fix GUI mode to be per-host truthful (top mode = DIRECT unless all chain hosts have ≥1 verified; or show worst-host).
- Add per-host fail-closed list (env `EGRESS_FAIL_CLOSED_HOSTS`, e.g., sensitive faculties) and a fallback budget (e.g., N direct-fallbacks per host per hour, then 502 + alert) so transient pool gaps degrade gracefully but sustained gaps stop leaking egress IP.
- Retry N verified candidates per CONNECT (not one) before counting a fallback, and record fallback cause (`empty` vs `chain-failed` vs `denied`) for GUI/alerting.

### Gaps
- No operator statement found on which faculties (if any) must never go direct; per-host fail-closed set cannot be chosen without that decision.
- No alerting channel defined for fallback spikes (GUI only, 30 s refresh); whether LAN GUI polling suffices vs log-based alert is undecided.

## Locking, persistence, clock, IPv6, Docker hardening

### Takeaway
`pool.json` atomic replace is good but unsynchronised with validation/fsync, the single global lock is held across disk I/O, wall-clock drives cooldowns, IPv6/link-local filtering has holes, and the image/compose lack digest pin + healthcheck.

### Cited Findings
- `ProxyPool.lock = threading.Lock()` guards `pick`/`verified`/`mark`/`coverage`/`stats`/`prune`; `mark()` calls `_save_throttled()` → `save()` (mkdir + JSON dump + tmp write + replace) while still holding the lock — `tools/egress/pool.py:146,189-244,163-177`.
- `save()` uses tmp + `replace` (atomic on POSIX) but no `fsync`, no schema validation on `load()` beyond `version == POOL_VERSION`, silent swallow of `OSError` — `tools/egress/pool.py:154-177`; `RunLog.add()` same pattern while holding its own lock — `tools/egress/server.py:203-228`.
- Cooldowns/ages use `time.time()`: `FAIL_COOLDOWN=15min`, `PRUNE_AFTER=24h`, `max_age=6h`, `last_checked`/`checked`/`last_refresh` — `tools/egress/pool.py:50-51,136-148,189-290`.
- `parse_proxy_url()` rejects private/loopback via `is_private`/`is_loopback` and rejects non-IP hostnames entirely — `tools/egress/pool.py:54-85`; tests pin private/loopback rejection — `tests/test_egress.py:21-23`.
- Python `ipaddress` distinctions (`is_private` vs `is_reserved`/`is_multicast`/`is_link_local`/`is_unspecified`) mean multicast/reserved/link-local/unspecified can pass a private+loopback-only check — general `ipaddress` behaviour (verify in stdlib docs for deployment Python).
- `socket.create_connection((phost, pport))` + `host.encode('idna')` path assumes IPv4/DNS; IPv6 proxy/target handling (bracketed dial, ATYP `0x04`) like DeadDropMGMT `dial` + `match` tail logic is absent — `tools/egress/server.py:115-145` vs `includes/proxy.php:119-137,522-542`.
- `Dockerfile.egress` is `FROM python:3.13-slim` with no digest, `pip install -r requirements.txt` with single pin `curl_cffi==0.13.0`, `USER 10002`, `VOLUME /data`, no `HEALTHCHECK` — `tools/egress/Dockerfile.egress:1-18`, `tools/egress/requirements.txt:1`.
- Compose sets `read_only: true`, `cap_drop: [ALL]`, `no-new-privileges`, `mem_limit/pids_limit/nofile`, `tmpfs /tmp`, LAN GUI `18080:8080`, no `healthcheck:` — `tools/egress/compose.fragment.yml:13-41`; Docker `read_only` + `healthcheck` semantics — [Compose services reference](https://docs.docker.com/reference/compose-file/services/) and [tmpfs mounts](https://docs.docker.com/engine/storage/tmpfs/).
- GUI binds `0.0.0.0:8080` + proxy `0.0.0.0:8888` inside container; LAN restriction relies solely on compose port mapping comment — `tools/egress/server.py:478-481`.

### Inferences
- Locking: use RW-style split (short critical section copying candidates, network/disk I/O outside lock), background debounced saver thread, and atomic counters for `fallbacks`/`blocks`.
- Persistence: validate `load()` schema (drop malformed entries, cap size), `fsync` tmp file + dir before `replace`, keep `pool.json.bak` rotation, and cap `entries` size (e.g., 2000) to bound `pick()` O(N) + GUI rendering (currently slices 200/100 but `stats()`/`coverage()` scan all).
- Clock: use `monotonic()` for cooldown/age/prune intervals; keep wall-clock only for persisted display fields with monotonic delta recomputed on load.
- IPv6/filtering: switch to explicit allow (`is_global` or `not (is_private or is_reserved or is_multicast or is_loopback or is_link_local or is_unspecified)`) and add IPv6 SOCKS ATYP handling or explicitly reject IPv6 proxies with a logged reason until supported.
- Docker: pin `python:3.13-slim` by digest (dependabot/renovate), add `HEALTHCHECK CMD python -c "urllib.../api/status"` or compose `healthcheck: test: ["CMD","python","-c",...]` hitting `/api/status`, add `cpus:` limit, document LAN-bind tightening (`127.0.0.1:18080:8080` + SSH tunnel) as default for non-home-LAN.

### Gaps
- No crash-consistency test for `pool.json`/`runs.json` under power loss / disk-full; `fsync` necessity is inferred from POSIX semantics, not measured on plebania filesystem.
- No inventory of IPv6 presence in the 9 free lists; whether IPv6 support matters (vs explicit reject) is unknown without sampling lists.

## curl_cffi probe DNS leak (socks5 vs socks5h)

### Takeaway
`fetch_via()` passes `socks5://` verbatim to curl_cffi/libcurl, which resolves faculty and OSM hostnames locally — leaking lookup intent to local DNS — where DeadDropMGMT explicitly rewrites to `socks5h://`/`socks4a://` for proxy-side resolution; live `chain_connect()` traffic is not affected (it already sends DOMAIN).

### Cited Findings
- Probe path: `cr.get(target, proxies={'http': url, 'https': url})` with `url` like `socks5://1.2.3.4:1080` unchanged — `tools/egress/pool.py:293-298`.
- In cURL, `socks5://` resolves destination locally then sends IP to proxy; `socks5h://` sends hostname for proxy-side resolution — [HighProxies SOCKS5 vs SOCKS5h comparison](https://highproxies.com/socks5-vs-socks5h/); libcurl `socks5h://` = "Proxy resolves URL hostname" — [CURLOPT_PROXY](https://github.com/curl/curl/blob/master/docs/libcurl/opts/CURLOPT_PROXY.md); `--socks5-hostname` lets the proxy resolve — [curl docs](https://curl.se/cvssource/docs/cmdline-opts/socks5-hostname.md); recommended practice "use socks5h:// instead of socks5:// to resolve DNS through the proxy, prevents DNS leaks" — [cURL proxy setup](https://www.proxies.sx/use-cases/developers/curl).
- DeadDropMGMT comment: "cURL resolves TARGET locally for socks5:// and socks4:// ... opposite of routing through a proxy" and `proxy_curl_url()` rewrites `socks5://→socks5h://`, `socks4://→socks4a://`; socket engine always uses DOMAIN (socks5h behaviour) — `includes/proxy.php:37-45,99-103`.
- PlanWAT `chain_connect()` SOCKS5 always sends DOMAIN (`\x05\x01\x00\x03` + hostname), i.e., proxy-side DNS like `socks5h` — `tools/egress/server.py:130-142`, so live faculty tunnels do not leak via target resolution.
- Proxy-hostname caveat still applies: if a proxy URL itself used a hostname, the egress box must resolve the proxy host locally before connecting — noted in [SOCKS5 vs SOCKS5h DNS handling](https://highproxies.com/socks5-vs-socks5h/); PlanWAT currently rejects proxy hostnames (`return None # free lists are IP-based`) — `tools/egress/pool.py:80-84`, so this sub-leak is closed by accident.
- curl_cffi documents `proxies={"https": "http://..."}` / `socks://` passthrough to libcurl behaviour (README excerpt via search); `socks5h://` is a libcurl-level scheme, not a curl_cffi extension.

### Inferences
- Add `proxy_curl_url()` equivalent in `pool.py` (rewrite `socks5://→socks5h://`, `socks4://→socks4a://` before `fetch_via`/`_direct_get` probe calls) and accept/normalise `socks5h`/`socks4a` in `SUPPORTED_SCHEMES` + `parse_proxy_url` so manually added `h` URLs are not rejected.
- Verify with a verbose libcurl trace or local DNS spy that faculty hostnames no longer hit the egress resolver when probing via SOCKS; add an offline unit test pinning the rewrite (DDMGMT `ProxyTest` pins its decision table — same pattern).
- No change needed in `chain_connect()` for target DNS (already remote); audit only proxy-host resolution if hostname proxies are ever allowed.

### Gaps
- curl_cffi's exact `socks5://` vs `socks5h://` handling was not traced live (no live faculty crawling per constraints; README fetch returned 503); inference relies on libcurl semantics passing through curl_cffi, which needs a local unmodified-code probe test to confirm.
- Whether local DNS exposure matters for OSM tile (neutral) vs faculty index (sensitive) differently was not decided; faculty Round-2 leak is the material one.
