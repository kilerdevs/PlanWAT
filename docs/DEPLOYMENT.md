# Deployment

PlanWAT is a static site. It runs on GitHub Pages (the target) or on the self-hosted Docker image behind a Cloudflare
tunnel. The examples use `plan.example.org` for the custom domain.

## GitHub Pages

[`.github/workflows/pages.yml`](../.github/workflows/pages.yml) builds `site/` and deploys it:

- on every push to `master` (protected: signed commits and passing CI);
- every day at 03:17 UTC, so a new term goes live on its first day without a commit;
- manually, from the Actions tab (**Run workflow**).

The site is then available at <https://kilerdevs.github.io/PlanWAT/>. All links are relative, so it works both there and
on a custom domain; only the 404 page needs the base path, which the workflow takes from `actions/configure-pages`.

> [!NOTE]
> GitHub disables scheduled workflows in public repositories after 60 days without activity. If that happens, re-enable
> **Pages** in the Actions tab (or push any commit).

### Moving a custom domain to Pages

1. Repository **Settings → Pages → Custom domain**: enter `plan.example.org` and save. GitHub stores this setting
   itself; with Actions-based deployment no `CNAME` file is needed.
2. In Cloudflare DNS, replace the tunnel route for `plan` with a `CNAME plan → kilerdevs.github.io`. Keep it **DNS only**
   (grey cloud) until GitHub shows the certificate as issued, then turn on **Enforce HTTPS** in the Pages settings.
3. The next Pages build picks up the new base path (empty) automatically. Check `https://plan.example.org/` and a group
   page, then remove the Public Hostname from the Cloudflare tunnel and stop the container
   (`docker compose down` in the project folder).

### Security headers on Pages

GitHub Pages cannot send custom headers. What still applies, and how to restore the rest:

| Protection | On Pages |
|---|---|
| Content-Security-Policy (scripts, styles, fetch, base-uri, form-action) | Yes: every page carries it in a `<meta>` tag. |
| HTTPS, HSTS | Yes on `*.github.io`; on a custom domain once **Enforce HTTPS** is on. |
| `frame-ancestors` / `X-Frame-Options` (no framing) | No: browsers ignore `frame-ancestors` in a meta tag. |
| `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP | No (each page sets `referrer` to `no-referrer` via meta). |

If the custom domain is proxied through Cloudflare (orange cloud), add the missing headers with a **Rules → Transform
Rules → Modify Response Header** rule for the domain:

```
X-Frame-Options: DENY
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
Permissions-Policy: accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()
Cross-Origin-Opener-Policy: same-origin
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

Proxying a GitHub Pages site through Cloudflare needs SSL/TLS mode **Full (strict)**. Also turn off Cloudflare's
"JavaScript detections" / Bot Fight Mode for this hostname: it injects a script that the page's CSP blocks (harmless, but
it logs a console error).

## Docker (self-hosted)

```bash
docker compose up -d --build
```

The [`Dockerfile`](../Dockerfile) builds in two stages:

1. `python:3.13-alpine` runs `build.py`, which writes `site/` and pins the CSP hashes of every page into a copy of
   [`deploy/nginx.conf`](../deploy/nginx.conf) (header CSP, including `frame-ancestors`).
2. `nginx-unprivileged` (digest-pinned, `apk upgrade`d) serves only those files.

[`docker-compose.yml`](../docker-compose.yml) runs it read-only, as a non-root user, with all capabilities dropped,
`no-new-privileges`, memory/CPU/PID limits, and the port bound to `127.0.0.1:8088` only; public traffic arrives through
the Cloudflare tunnel. nginx allows only `GET`/`HEAD`, rate-limits per client IP (taken from `CF-Connecting-IP`), and sends
the security headers listed above.

Terms are picked when the image is built, so **rebuild when a new term starts** (or switch to Pages, which rebuilds
daily).
