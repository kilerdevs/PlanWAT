# Third-party notices

PlanWAT ships no third-party code at runtime except the icons below. The typeface is loaded from Google Fonts, not
redistributed. Development tools are listed for completeness; they are never part of the built site.

## Shipped

### Lucide icons

The line icons in `src/group.html` (chevrons, map pin, user, clock, close, rotate, calendar, alert, download) are paths
from [Lucide](https://lucide.dev), used under the ISC License:

```
ISC License

Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as part of Feather (MIT). All other copyright (c)
for Lucide are held by Lucide Contributors 2022.

Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is hereby granted,
provided that the above copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE INCLUDING ALL
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
```

## Loaded at runtime

| Component | Source | License |
|---|---|---|
| Inter typeface (fallback where SF Pro is not installed) | Google Fonts (`fonts.googleapis.com`, `fonts.gstatic.com`) | SIL Open Font License 1.1 |

## Development only

| Tool | Used for | License |
|---|---|---|
| [@playwright/test](https://playwright.dev) | Browser tests | Apache-2.0 |
| [@axe-core/playwright](https://github.com/dequelabs/axe-core-npm), [axe-core](https://github.com/dequelabs/axe-core) | Accessibility checks | MPL-2.0 |
| `python:3.13-alpine`, `nginxinc/nginx-unprivileged` | Docker build and runtime images | See each image |
