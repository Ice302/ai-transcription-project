# Design system

Version 3 of the interface is built from three references, combined into one system:

| Reference | What it contributed |
| --- | --- |
| **Flat "TODU" app** (lime + black, 扁平风) | Lime/near-black palette; very rounded cards; black pill tabs; round black icon buttons; big-number stat tiles; check circles for selection; a Gantt-style board, which became the scene/voice track; a dark variant |
| **Calendar app** (sajon.co) | Huge display numerals (the live clock, durations, scene numbers); an info column beside a hairline (Source / Model / Delay); pill toggles; stacked pastel cards with darker chips, used for scenes and library cards |
| **Editorial collage** ("people / platforms / products") | Paper background with grain; serif accent words in boxes; a red-orange signal colour and small red squares; thin network lines with dots; dot and grid patterns |

The collage's idea of things connected by lines became the app's own illustration: **speech, screen, people → notes**, joined around a waveform, captioned *cross-checked*.

## Tokens

All colours are CSS variables on `:root` with a dark override on `[data-theme="dark"]`, exposed to Tailwind through `@theme inline` (`frontend/src/index.css`). Write classes such as `bg-paper`, `text-ink-2` or `bg-lime`; never write hex values in components.

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `paper` / `paper-2` | `#ecebe4` / `#e2e0d6` | `#0f0f0e` / `#161614` | Page, recessed areas |
| `surface` / `surface-2` | `#f7f6f1` / `#ffffff` | `#1b1b19` / `#232320` | Cards, inputs |
| `ink`, `ink-2`, `ink-3` | `#131312` … `#85827a` | `#f1efe8` … `#7d7a70` | Text; `ink` also fills black pills/tiles |
| `on-ink` | `#f4f3ee` | `#131312` | Text on `ink` fills |
| `line`, `line-2` | `#d3d0c4`, `#c2beb0` | `#2f2e2a`, `#3d3c37` | Hairlines, borders |
| `lime` (`-strong`, `-pale`) | `#bcdb6b` | same | Primary accent, "You", success, active word |
| `signal` (`-pale`) | `#e1462b` | `#ff6646` | Recording, suggested fixes, destructive actions |
| `p1`–`p6` (+ `-ink`) | mustard, slate, lavender, rose, teal, sage | same | Scenes, library cards, speakers |

Text on lime and on pastels always uses the dark ink (`#131312` or the pastel's `-ink`), so it stays readable in both themes.

## Typography

Bundled with `@fontsource` (no CDN, works offline):

- **Geist** (variable): UI and display. The `display` class sets 600 weight, `-0.045em` tracking and 0.9 line height, for the big numerals and headlines.
- **Instrument Serif**: accent words in italic (`serif-accent`): "*heard* & *seen*", "Notes *assistant*", "The *library*", and the track labels *screen* / *voices*.
- **Geist Mono**: timestamps, eyebrows (`eyebrow`: 11 px, uppercase, 0.14em tracking) and technical labels.

## Components (`frontend/src/components/ui.jsx`)

| Component | Notes |
| --- | --- |
| `Button` | Tones: `ink` (black pill), `lime`, `ghost`, `soft`, `signal`, `danger`; sizes `sm`/`md`/`lg`; optional `icon`, `loading` |
| `IconButton` | Round; requires `label` (used for `aria-label` and the tooltip) |
| `Segmented` | Pill tabs with a black active pill; `role="tablist"`; optional icons and badges |
| `StatTile` | Mono label + big number; tones `surface`, `lime`, `ink`, `signal` |
| `Chip`, `Switch`, `ProgressBar`, `Kbd`, `Dialog` (native `<dialog>`), `Menu`, `EmptyNote` | |

Patterns:

- **Pastel card:** `rounded-card p-5 ${pastel(i).bg} ${pastel(i).ink}`. Class names come from `lib/palette.js`, written out in full so Tailwind can find them.
- **Dark card:** `bg-ink text-on-ink`. The assistant panel switches to `surface-2` in dark mode so it doesn't turn light.
- **Hairline info column:** `border-l border-line-2 pl-6` next to a big numeral.
- **Red square marker:** `size-2 bg-signal` as a bullet for on-screen lines and screen-change cards.

## Motion and accessibility

- One entrance animation (`animate-rise`), the streaming caret, and pulses for live states. `prefers-reduced-motion` turns all of them off.
- Visible focus ring (2 px ink outline) on everything focusable. Icon buttons always have labels. The live feed is an `aria-live` region. There's a skip link.
- Keyboard: <kbd>/</kbd> search, <kbd>K</kbd>/<kbd>Space</kbd> play, <kbd>J</kbd>/<kbd>L</kbd> ±5 s, <kbd>C</kbd> captions, <kbd>?</kbd> help.
- Print: only the notes document (`PrintView`) prints. Everything with `no-print` is hidden.
