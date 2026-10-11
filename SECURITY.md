<div align="center">

# Security Policy

[![Report a vulnerability](https://img.shields.io/badge/report-privately%20via%20GitHub-critical?style=flat&logo=github)](https://github.com/kilerdevs/PlanWAT/security/advisories/new)
[![Acknowledgement](https://img.shields.io/badge/acknowledgement-48%20h-blue?style=flat)](#what-to-expect)
[![Fix target](https://img.shields.io/badge/fix%20target-30%20days-blue?style=flat)](#what-to-expect)
[![SAST](https://github.com/kilerdevs/PlanWAT/actions/workflows/sast.yml/badge.svg)](https://github.com/kilerdevs/PlanWAT/actions/workflows/sast.yml)

</div>

PlanWAT is a public static site with no accounts and no stored personal data. Its security goals are that nothing but
its own code runs in a visitor's browser, that a calendar file cannot inject markup or script, and that the self-hosted
image exposes only the built files.

## Contents

- [Supported versions](#supported-versions)
- [Reporting a vulnerability](#reporting-a-vulnerability)
- [What to expect](#what-to-expect)
- [Scope](#scope)
- [Safe harbor](#safe-harbor)

---

## Supported versions

| Version | Supported |
|---|---|
| The current head of `master` (what is deployed) | ✅ |
| Anything older | ❌ |

Fixes are developed on `dev` and land on `master` with the next release.

## Reporting a vulnerability

> [!IMPORTANT]
> **Please do not open a public GitHub issue for security problems.**

Preferred channel: GitHub Private Vulnerability Reporting.

> <https://github.com/kilerdevs/PlanWAT/security/advisories/new>

If you cannot use it, open a regular issue titled only `[security] please contact you privately`, with no technical
detail, and wait for the maintainer to reach out.

### What to include

- The affected file, page or URL, and the code path involved
- Step-by-step reproduction or a proof of concept (for example a crafted `.ics` file)
- The impact: what an attacker gains, and under what preconditions
- Browser and OS, or the deployment (GitHub Pages, Docker image)

## What to expect

| When | What happens |
|---|---|
| **48 hours** | Acknowledgement of your report |
| **7 days** | Initial assessment: confirmed / not a vulnerability / needs more info |
| **30 days** | Fix deployed or a documented mitigation, for confirmed issues |

You will be credited in the changelog and the advisory unless you prefer to remain anonymous. Please allow a reasonable
window (90 days is customary) before public disclosure.

## Scope

### In scope

| Area | Examples |
|---|---|
| `src/ics.js` | A calendar that makes the reader execute code, hang, or render attacker-controlled markup |
| `src/group.html`, `src/index.html`, `src/404.html` | XSS, DOM clobbering, CSP bypasses, unsafe use of calendar data |
| `build.py` | Metadata that escapes HTML escaping, path traversal through group or term names, a page shipped without its CSP |
| `deploy/nginx.conf`, `Dockerfile`, `docker-compose.yml` | A file served that should not be, missing headers, privilege or write access inside the container |
| `.github/workflows/` | Workflow injection, excessive token permissions, unpinned third-party code |

### Out of scope

- **Wrong timetable data** (a room, time or teacher): please open a
  [timetable issue](https://github.com/kilerdevs/PlanWAT/issues/new?template=timetable.yml) instead.
- Headers that GitHub Pages cannot send (`X-Frame-Options`, `frame-ancestors`, …): documented, with the Cloudflare
  rules that restore them, in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md#security-headers-on-pages).
- Scripts injected by an intermediary such as Cloudflare's bot detection: the page's CSP blocks them.
- Loading the Inter typeface from Google Fonts: a documented, deliberate third-party request.
- Denial of service against GitHub Pages or Cloudflare infrastructure, and automated scanner output without a
  demonstrated impact.

## Safe harbor

Research carried out in good faith under this policy is welcome: no legal action will be pursued for it. Please stay
within the scope above, do not degrade the service for other users, and do not access data that is not yours. Testing
against your own local build (`python3 build.py` and `node tests/e2e/serve.js`, or the Docker image) is always preferred.
