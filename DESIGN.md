---
name: Plan zajęć WCY26KY3S1
description: Phone-first dark timetable for WAT study groups, in an iOS dark-mode idiom.
colors:
  accent: "#0a84ff"
  accent-text: "#4da3ff"
  ground: "#000000"
  surface-1: "#111113"
  surface-2: "#1c1c1e"
  surface-2-hover: "#232326"
  surface-3: "#2c2c2e"
  surface-4: "#3a3a3c"
  label: "#f5f5f7"
  label-secondary: "#a1a1a6"
  label-tertiary: "#86868b"
  label-quaternary: "#6e6e73"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"SF Pro Text\", \"Inter\", system-ui, sans-serif"
    fontSize: "4rem"
    fontWeight: 700
    lineHeight: 1.04
    letterSpacing: "-0.04em"
  display-compact:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"SF Pro Text\", \"Inter\", system-ui, sans-serif"
    fontSize: "2.5rem"
    fontWeight: 700
    lineHeight: 1.04
    letterSpacing: "-0.035em"
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"SF Pro Text\", \"Inter\", system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 600
    lineHeight: 1.22
    letterSpacing: "-0.02em"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"SF Pro Text\", \"Inter\", system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 600
    lineHeight: 1.28
    letterSpacing: "-0.012em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"SF Pro Text\", \"Inter\", system-ui, sans-serif"
    fontSize: "0.9375rem"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"SF Pro Display\", \"SF Pro Text\", \"Inter\", system-ui, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 500
    lineHeight: 1.3
    fontFeature: "\"tnum\""
rounded:
  control: "12px"
  card: "16px"
  group: "20px"
  sheet: "24px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  2xl: "32px"
  3xl: "48px"
  4xl: "64px"
components:
  button-round:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.label}"
    rounded: "{rounded.pill}"
    size: "44px"
  button-round-hover:
    backgroundColor: "{colors.surface-3}"
  chip:
    backgroundColor: "{colors.surface-2}"
    textColor: "{colors.label-secondary}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "6px 14px 6px 12px"
  chip-hover:
    backgroundColor: "{colors.surface-3}"
    textColor: "{colors.label}"
  list-group:
    backgroundColor: "{colors.surface-2}"
    rounded: "{rounded.group}"
  lesson-row:
    textColor: "{colors.label}"
    typography: "{typography.title}"
    padding: "14px 16px"
  lesson-tile:
    backgroundColor: "{colors.surface-2}"
    rounded: "{rounded.card}"
    padding: "14px 16px 16px 14px"
  lesson-tile-hover:
    backgroundColor: "{colors.surface-2-hover}"
  live-card:
    backgroundColor: "{colors.surface-2}"
    rounded: "{rounded.group}"
    padding: "16px 24px 16px 16px"
  floating-pill:
    textColor: "{colors.label}"
    rounded: "{rounded.pill}"
    height: "48px"
    padding: "0 20px 0 16px"
  sheet:
    backgroundColor: "{colors.surface-2}"
    rounded: "{rounded.sheet}"
---

# Design System: Plan zajęć WCY26KY3S1

## Overview

**Creative North Star: "The Pocket Live Activity"**

The timetable behaves like something iOS would ship: a black ground, greys that rise in lightness as surfaces come forward, one blue that means "now / today / you are here", and system type set tight and confident. The page is read in a hurry, on a phone, between buildings, so every surface answers *what, when, where* before it says anything about itself.

Density is calm rather than sparse. On phones each day is an inset grouped list (one rounded container, rows separated by inset hairlines); on desktop the same rows become tiles placed in a true day × block grid, so the whole week sits in one viewport. The memorable move is the subject capsule: a 4px colour bar that names the subject and, for the class in progress, fills top to bottom as the class elapses, in the rows and in the Live card at the top.

Motion is physical and short: expo-out arrivals, springs on press and on the floating pill, View Transitions that slide the week sideways in the direction you moved, a bottom sheet that rides the iOS sheet curve. Movement is reserved for state changes; nothing loops except the live dot of the class that is on now.

**Key Characteristics:**
- Pure black ground; depth from surface lightness and a 6% top edge-light, not drop shadows.
- One accent, used for now, today, focus and selection only.
- System SF / Inter, sentence case, tabular numerals; no monospace, no all-caps labels.
- Subject colour lives only in the capsule and legend dots.
- Frosted glass only where something floats over content: the stuck week bar and the "Bieżący tydzień" pill.

## Colors

A near-monochrome dark ramp with a single systemBlue accent; subject colours come from the timetable data and are confined to small marks.

### Primary
- **System Blue** (`accent`): the "now / today" signal. Live dot, "Teraz" state ring, today's column outline, focus rings, selected week check, semester progress fill.
- **Link Blue** (`accent-text`): the same hue lifted for text on dark surfaces ("Teraz · do 11:25", "Dziś", "Bieżący tydzień"), keeping ≥4.5:1.

### Neutral
- **Black Ground** (`ground`): the page.
- **Raised Grey 1–4** (`surface-1` … `surface-4`): skeletons and fallbacks (1), cards, groups, sheet (2), pressed and secondary controls (3), handles and hover on small controls (4). `surface-2-hover` is the hover lift for tiles and the Live card.
- **Label ramp** (`label`, `label-secondary`, `label-tertiary`): primary text, supporting text (dates, types, meta), quiet text (counts, hints). `label-quaternary` is reserved for disabled or decorative use; it fails AA for small text.
- **Hairline** (`rgba(255,255,255,0.08)`, strong `0.14`): separators and outlines. **Edge-light** (`inset 0 1px 0 rgba(255,255,255,0.06)`): the top highlight on every raised surface.
- **Accent tints**: `rgba(10,132,255,0.14)` soft fill (today pill), `0.5` ring (now row and Live card outline), `0.35` ring and `0.05` wash (today column on desktop), `0.24` flash (jump-to-class highlight), `0.45` text selection.

### Named Rules
**The One Blue Rule.** Blue means "now, today, or focused" and nothing else. Never use it for decoration, headings or inactive states.

**The Capsule Rule.** Subject colour appears only as the 4px capsule and the 10px legend dot. Never tint text, card backgrounds or borders with a subject colour.

**The Receding Past Rule.** Past days and finished classes step down one text token (label → secondary, secondary → tertiary) and dim their capsule to 45%. They never drop below `label-tertiary`, so they stay AA-legible.

## Typography

**Display Font:** SF Pro Display (with Inter, then system-ui)
**Body Font:** SF Pro Text (with Inter, then system-ui)

**Character:** One family doing every job, Apple-style: heavy, tightly tracked large titles over small, comfortable text. Weight contrast (400/500/600/700) carries hierarchy, not extra faces.

### Hierarchy
- **Display** (700, 4rem desktop / 2.5rem phone, 1.04, −0.04em / −0.035em): the group code only.
- **Headline** (600, 1.25rem, −0.02em): day names in the phone list, the Live card subject, the week label on tablet and up, the sheet title.
- **Title** (600, 1.0625rem, −0.012em): subject names in rows, week label on phones, legend summary, sheet week labels. Tiles step down to 0.9375rem.
- **Body** (400, 0.9375rem, 1.45): dates, Live card details, empty-week message.
- **Label** (500/600, 0.8125rem, tabular): times, rooms, counts, status lines, chips, meta. 0.75rem only for durations and key caps.

### Named Rules
**The Tabular Time Rule.** Every time, date, count and room is set with tabular numerals so columns of times align.

**The Sentence Case Rule.** No uppercase labels or eyebrows anywhere; status lines read as sentences ("Następne · za 25 min").

## Layout

Mobile first on an 8px grid (4px half-steps). Content sits in a centred column of `max-width: 720px` with gutters of `max(16px, safe-area)` on phones and `max(32px, safe-area)` from 768px; at 1080px the column widens to 1240px and the week becomes a grid of equal day columns (Saturday, in both layouts, only if some Saturday in the semester has classes), one row per distinct start time, so blocks line up across days and empty slots stay empty. The header is one column on phones and splits title / Live card from 1080px. Breakpoints: 370px (compact rows), 768px (tablet: larger title, week label left with arrows right, centred sheet), 1080px (timetable grid). Touch targets are 44px minimum on coarse pointers; the floating pill and the hint footer respect the bottom safe area.

## Elevation & Depth

Depth is tonal. Surfaces rise through `surface-1 → surface-4` with a 6% top edge-light; outlines are hairlines. The only shadows are a soft black under the floating pill (`0 16px 40px -12px rgba(0,0,0,0.8)`) and under the sheet, because those genuinely float. Glass (`rgba(22,22,24,0.72)` + `saturate(180%) blur(20px)`) appears only on the stuck week bar and the floating pill, and turns opaque when transparency is reduced or unsupported.

### Named Rules
**The No-Glow Rule.** No coloured or zero-offset halo shadows. State is shown with a 1px accent ring and a tinted fill, never a glow.

**The Glass-Only-When-Floating Rule.** Backdrop blur is allowed only on elements that sit over scrolling content. It is off while the bar rests in place.

## Shapes

Continuous, iOS-like rounding scaled to the object: 12px controls, 16px tiles, 20px groups and the Live card, 24px sheet, full pills for chips, today markers and the floating pill, circles for icon buttons. The capsule is a 4px bar with 2px radius. Icons are lucide line icons at 1.5 stroke (2 at 14–16px), drawn as inline SVG.

## Components

### Buttons
- **Shape:** 44px circles for previous / next (`rounded.pill`), 32px circle with a 44px hit area for sheet close.
- **Default:** `surface-2` with edge-light; icon in `label`.
- **Hover / Active / Disabled:** `surface-3` on hover (precise pointers only); press scales to 0.94 on a spring; disabled drops to 32% opacity.
- **Focus:** a 2px accent outline that settles from 6px to 2px offset.
- **Secondary pill (download link):** `surface-2` pill with edge-light, 13px semibold label in `label`, 18px icon in `label-secondary`; 36px tall (44px on touch), `surface-3` on hover, 0.97 press. Neutral on purpose: the accent stays reserved for now / today / focus.

### Chips
- **Style:** `surface-2` pill, label text in `label-secondary`, 10px subject dot.
- **State:** pressed fills with 22% of the subject colour plus an inset subject ring; the dot scales to 1.3.

### Cards / Containers
- **Corner Style:** 20px groups, 16px tiles.
- **Background:** `surface-2`; today's group gets a 1px accent ring; the row on now gets a 9% accent tint.
- **Internal Padding:** 14px × 16px rows; inset hairline separators start where the text starts.

### Navigation
- **Week bar:** sticky, transparent at rest, frosted with a hairline once it sticks. Phone: arrows flank a centred week label (with chevron) and its meta line. Tablet and up: label and meta left, arrows grouped right.
- **Week sheet:** bottom sheet on phones (drag handle, swipe down, Esc or backdrop to dismiss), centred dialog from 768px. A listbox of all weeks; the selected one shows a drawn check, the current one a blue dot with "Bieżący tydzień".
- **Floating pill:** "Bieżący tydzień" capsule that springs up from the bottom only when you are away from the current week.

### Live card (signature)
A button card at the top of the page, shown only when today has a class on now or still to come. It holds the status line (live dot + "Teraz · do HH:MM", or a clock + "Następne · za …"), the subject in Headline, then room, time and type, and the next class under a hairline. Its capsule fills with class progress, first animating from empty on load. Tapping jumps to that class in the week and flashes it.

## Do's and Don'ts

### Do:
- **Do** keep the ground pure `#000` and lift surfaces only through the `surface-*` ramp plus edge-light.
- **Do** use the accent only for now, today, focus and selection (The One Blue Rule).
- **Do** animate transform and opacity: 150ms feedback, 300ms state, 420–520ms transitions and sheets, expo-out (`cubic-bezier(0.22,1,0.36,1)`) for arrivals, `cubic-bezier(0.32,0.72,0,1)` for the sheet, springs for press and the floating pill.
- **Do** give every motion a reduced-motion path that keeps fades and drops travel.
- **Do** keep all styling in hashed `<style>` blocks and set dynamic values with CSSOM custom properties; the CSP blocks inline style attributes.

### Don't:
- **Don't** add coloured glows, gradient text, side stripes on card edges, or emoji or glyph icons.
- **Don't** use uppercase eyebrows or labels above headings, or a monospace face for data.
- **Don't** put backdrop blur on anything that does not float over content, or loop an animation on anything that is not live.
- **Don't** tint text or surfaces with subject colours (The Capsule Rule).
- **Don't** add WAT logos, crests or official-looking wording; the site is an unofficial student view.
