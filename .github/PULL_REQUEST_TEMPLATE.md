<!--
Thanks for contributing! Fill in what applies and delete the rest. Open the PR against `dev`.
Security vulnerability? Do NOT describe it here — use private reporting:
https://github.com/kilerdevs/PlanWAT/security/advisories/new
-->

## Summary

<!-- What does this change, in a sentence or two? -->

## Why

<!-- The problem or motivation. Link the issue: Closes #123 -->

## Type of change

- [ ] Timetable (new group, new term or a correction)
- [ ] Bug fix
- [ ] New feature
- [ ] Accessibility or design
- [ ] Refactor / cleanup (no behavior change)
- [ ] Documentation only
- [ ] Tests / CI / tooling

## How was this tested?

- [ ] `npm test` passes (reader + build tests, then the browser tests)
- [ ] Added or updated a test that fails without this change
- [ ] Looked at the result on a phone, and with reduced motion on (UI changes)

## Timetable checklist

- [ ] File is `timetables/<term>/<GROUP>.ics`, UTF-8 with CRLF line endings
- [ ] `X-PLAN-GROUP` matches the file name; semester start and end are set
- [ ] Corrected events keep their `UID`
- [ ] Not applicable

## Security and design checklist

- [ ] No inline `style="…"` attributes or `on…=` handlers; script and style stay in the hashed blocks
- [ ] Calendar data is rendered with `textContent`, never `innerHTML`
- [ ] No new runtime dependency, third-party script or external origin
- [ ] Follows DESIGN.md (tokens, one accent colour, 44 px touch targets, transform/opacity motion)
- [ ] Not applicable

## Documentation

- [ ] `CHANGELOG.md` entry under **Unreleased**
- [ ] README / docs updated if behavior or the calendar format changed

## Screenshots

<!-- UI changes: before / after, phone and desktop. -->
