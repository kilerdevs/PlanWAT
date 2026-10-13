---
version: 1
slug: "src-group-html"
primary_target: "src/group.html"
related_targets: ["src/index.html", "src/404.html"]
---

# Timetable page

Scope: the group timetable page (src/group.html → site/<GROUP>/index.html). Visitor mode: Operate.

Audience and job: WAT students on phones, opened from the group chat, checking what is on now/next, where (room), and the rest of the week. Desktop is secondary but should show the whole week at once.

Constraints: Polish copy unchanged; dark theme only (owner's brief); strict hash-pinned CSP (no inline style attributes, CSSOM only); smooth on mid-range phones (transform/opacity motion, one backdrop blur on the sticky bar and floating pill only); prefers-reduced-motion respected.

Pinned direction (owner brief): "Apple, but dark" — calm, precise, premium, iOS dark mode / visionOS; one accent; Inter fallback for SF; lucide-style line icons; spring/expo easing; View Transitions.

## Direction contract

THESIS: The timetable as an iOS-native object: a Live Activity for the class happening now, inset-grouped day lists on the phone, and a true day × block timetable grid on desktop. Refuses the default stack of identical shadowed cards with coloured left borders.

OWN-WORLD: Pure black ground; elevated greys #111113 / #1c1c1e / #2c2c2e / #3a3a3c; text #f5f5f7 / #a1a1a6 / #86868b; white hairlines 8–14%; one accent #0a84ff for today, now, focus, selection. Subject colours appear only as a 4px capsule and chip dots. System SF / Inter, tabular numerals, sentence case, no monospace, no all-caps.

STORY: Open the link → see the group, the semester position, and (when relevant) what is on now or next and in which room; scan the week; jump weeks by arrows, swipe, keys, or the week sheet; highlight a subject from the legend.

FIRST VIEWPORT: Phone: large-title group code top-left, one line of context, thin semester progress, the Live card (now/next with room and capsule progress) when today has classes left, then the frosted week bar (‹ label⌄ ›) and the first day group. Desktop: title block left, Live card right, full-width frosted bar, the week grid filling the rest.

FORM: Pinned by brief (no concept roll); iOS/visionOS product language translated to the web. Signature move: the subject capsule that doubles as the live progress track, in rows and in the Live card. Seed key: none (brief-pinned direction).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved

- Whether to self-host Inter (would let the CSP drop Google Fonts).
- Light theme removed per brief; revisit only if the owner asks.
