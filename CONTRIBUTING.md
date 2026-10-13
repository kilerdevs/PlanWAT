<div align="center">

# Contributing to PlanWAT

**Thanks for helping.** Timetable additions and corrections, bug fixes, accessibility and documentation improvements are
all welcome.

[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat)](#pull-requests)
[![CI](https://github.com/kilerdevs/PlanWAT/actions/workflows/ci.yml/badge.svg)](https://github.com/kilerdevs/PlanWAT/actions/workflows/ci.yml)
[![Code of Conduct](https://img.shields.io/badge/code%20of%20conduct-Contributor%20Covenant%202.1-blueviolet?style=flat)](CODE_OF_CONDUCT.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green?style=flat)](LICENSE)

</div>

---

## Contents

- [Ways to contribute](#ways-to-contribute)
- [Reporting a security vulnerability](#reporting-a-security-vulnerability)
- [Development setup](#development-setup)
- [Checks before you open a PR](#checks-before-you-open-a-pr)
- [Conventions](#conventions)
- [Signed commits](#signed-commits)
- [Pull requests](#pull-requests)
- [Code of conduct](#code-of-conduct)

---

## Ways to contribute

| You want to… | Do this |
|---|---|
| **Add a group or a new term** | Add `timetables/<term>/<GROUP>.ics` following [docs/ICS-FORMAT.md](docs/ICS-FORMAT.md) and open a PR, or open a [timetable issue](https://github.com/kilerdevs/PlanWAT/issues/new?template=timetable.yml) with a link to the official plan |
| **Fix a wrong class** (room, time, teacher) | Edit the event in the group's `.ics`, keep its `UID`, and open a PR, or open a timetable issue |
| **Fix a bug** | Open a [bug report](https://github.com/kilerdevs/PlanWAT/issues/new?template=bug_report.yml), or go straight to a PR for small fixes |
| **Propose a feature** | Open a [feature request](https://github.com/kilerdevs/PlanWAT/issues/new?template=feature_request.yml) first for anything non-trivial |
| **Improve the docs** | README, `docs/`, this file, or a comment where a non-obvious decision deserves one |

The project is [MIT licensed](LICENSE). By submitting a pull request you agree that your contribution is provided under
the same license.

## Reporting a security vulnerability

> [!CAUTION]
> **Please do not open a public issue for a vulnerability.** Use private reporting; the policy, scope and response times
> are in [SECURITY.md](SECURITY.md).

## Development setup

You need Python 3.12+ and Node.js 22+.

```bash
git clone https://github.com/kilerdevs/PlanWAT.git && cd PlanWAT
git switch dev
npm ci
npx playwright install chromium        # add firefox webkit to run the whole browser matrix
python3 build.py && node tests/e2e/serve.js    # preview on http://127.0.0.1:4173
```

## Checks before you open a PR

```bash
npm test        # calendar reader + build tests, then the browser tests against a fresh build
```

CI runs the same checks plus Firefox and WebKit, the Docker image scan and smoke test, and CodeQL. For UI changes, also
look at the result on a real phone, and with reduced motion turned on.

## Conventions

- **Write the test first.** Reader changes get a case in `tests/ics.test.js`, plan-insight changes one in
  `tests/insights.test.js`, build changes one in `tests/test_build.py`,
  behaviour in the browser one in `tests/e2e/site.spec.js`. Watch it fail, then make it pass.
- **No runtime dependencies and no third-party scripts.** The site is plain HTML, CSS and JavaScript. npm packages are
  test tooling only.
- **The CSP stays strict.** All script and style live in the templates' `<script>` / `<style>` blocks, which the build
  hashes. No inline `style="…"` attributes or `on…=` handlers; set dynamic values with `element.style.setProperty`.
  Render calendar data with `textContent`, never `innerHTML`.
- **Design:** follow [DESIGN.md](DESIGN.md) (tokens, one accent colour, motion rules, 44 px touch targets) and keep it
  smooth on ordinary phones: animate `transform` and `opacity`, respect `prefers-reduced-motion`.
- **Copy:** the interface is Polish; code, comments and docs are English.
- **Calendars** keep CRLF line endings and stable `UID`s.
- Style: 2-space indentation in HTML/CSS/JS, 4 spaces in Python; see [.editorconfig](.editorconfig).

## Signed commits

`master` accepts only signed commits. An SSH key is the simplest way:

```bash
git config gpg.format ssh
git config user.signingkey ~/.ssh/id_ed25519.pub
git config commit.gpgsign true
git config tag.gpgsign true
```

Then add the same public key on GitHub under **Settings → SSH and GPG keys → New SSH key**, with key type **Signing Key**,
and commit with an email address verified on your account. GPG keys work too.

## Pull requests

- Branch from `dev` and open the PR against **`dev`**. Releases are PRs from `dev` into `master`, which deploys.
- Keep one topic per PR, and fill in the template.
- Add a line under **Unreleased** in [CHANGELOG.md](CHANGELOG.md) for anything a user would notice.
- Commit messages: a short imperative summary, optionally prefixed with the area (`Reader: …`, `Build: …`, `CI: …`,
  `Timetable: …`).

## Code of conduct

This project follows the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md). Report conduct concerns privately through
[security advisories](https://github.com/kilerdevs/PlanWAT/security/advisories/new) with a title starting
"Conduct report".
