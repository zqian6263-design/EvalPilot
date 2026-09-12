# Design System

<!-- impeccable:design-schema 1 -->

DESIGN.md records what the console *is*, as built. PRODUCT.md records what the
product is for. Where the two disagree about intent, PRODUCT.md wins; where they
disagree about the interface, this file is the description of record.

## World

**The evaluation range.** EvalPilot's console is drawn as an instrument an
operator sits at: a dark room, a coordinate field, and luminous traces. Every
element is one of three things — a *field* (the graticule), a *signal* (a trace,
a rail, an index key), or an *annotation* (a bracket, a stamped word). A
regression is not a badge colour, it is a geometric event: the candidate trace
leaving the tolerance band, and the whole surface is organised so a reviewer can
watch that happen and then audit it.

The category default (near-black dashboard, signal-green trend line, KPI tiles,
one glowing accent, rounded translucent cards) is refused. Two things keep this
world off it:

1. **The chart and the room are one instrument.** The field the page sits on is
   the same graticule the run tape's chart is drawn on, locked to the viewport.
   A trace is not a widget on a page; it is the same measurement surface, seen
   through a window.
2. **The colour that owns structure is cyan, and the colour that carries a
   verdict is not.** Signal cyan draws rails, edges, index keys and the live
   lamp. A confirmed departure is red, a flag that has not been confirmed is
   amber, a tool call is violet, and anything *better* is cobalt — the same
   cobalt as the baseline trace. Verdict colour is a separate axis from
   structure colour.

Seed: `e24d54a1`, direction candidate 1 of the grounded list. Raises carried in
from the challengers it beat:

| Kept from | The discipline it donated |
| --- | --- |
| The strip-chart incumbent | The 0..1 field with a pre-printed tolerance band, so a departure stays a geometric event on a chart and never collapses into a red badge. |
| Teletext service | A character-lattice tick margin under the plot that doubles as the directly-keyed case index. |
| Bound analytical notebook | The stamped verdict and the initialled sign-off strip; the record is evidence, not decoration. |

## Palette

Six inks, three grounds, and one graphite that draws every aid. Nothing else.

| Token | Value | Role |
| --- | --- | --- |
| `--ground` | `#05080f` | The room. The page background, always. |
| `--ground-lit` | `#0a121f` | A raised plate: panels, readouts, the drawer. |
| `--ground-shade` | `#0d1727` | A plate in shadow: rails, row headers, the side column. |
| `--ground-raise` | `#111d30` | Hover and selected states. |
| `--rule` | `#1c2b42` | The aid hairline: separators, structural rules. |
| `--rule-soft` | `#152238` | The inner row rule, and only that. |
| `--signal` | `#34d8ea` | Structure. Rails, edges, live lamps, index keys, the plot's grid. |
| `--signal-bright` | `#67e8f5` | The hot core: focus rings, the primary key's hover. |
| `--signal-deep` | `#0e7f95` | A quieter rail, and the block-quote margin rule. Never text. |
| `--ink` | `#e6f0fb` | The readout: body text and primary numerals. |
| `--ink-soft` | `#9db2ce` | Secondary readout: descriptions, supporting prose. |
| `--ink-faint` | `#6d84a3` | Micro-labels and index numbers. **Nothing below this may be text.** |
| `--ink-lamp` | `#c6d8ee` | A lamp lit on a dark chassis. |
| `--baseline` | `#5b9cff` | The baseline trace, and every movement that is better. |
| `--candidate` | `#ff5f57` | The candidate trace, and a confirmed departure. |
| `--amber` | `#f2a33c` | A flag, a caveat, an unresolved reading. Never a verdict. |
| `--violet` | `#b08cff` | The tool channel: probes, calls, artefacts, a replay's set point. |
| `--graphite` | `#546880` | Non-text only: rules, focus rings, borders. Held above the 3:1 non-text floor. |
| `--graphite-faint` | `#26364f` | Minor graticule and inner row rules only. |
| `--chassis` | `#03060c` | The machine's body: the provenance bar, the tape chassis, the log. |

Colour strategy: **Committed**, on a dark ground. Cyan owns structure at scale —
every rail, every key, every plate's top edge, the index lattice — and it is
deliberately *not* the verdict colour, so the loudest thing on the screen is
never the accent. Red is rare and load-bearing: it appears on the departure
segment of the trace, the struck case, the stamp, and the market masthead, and
nowhere else.

**Rule: a value may only be a literal in `tokens.css`.** The two exceptions are
`tape.css` and `market.css`, which each declare a private block of `--plot-*` /
`--mkt-*` variables for their own SVG channel colours; an SVG `fill` resolves
against the element carrying the attribute, and a chart's channel colours are
the measurement's, not the page's. A literal anywhere else is a defect.

## Type

| Role | Stack | Used for |
| --- | --- | --- |
| `--face-panel` | Bahnschrift SemiCondensed → Franklin Gothic Medium → Arial Narrow | Headings, labels, status chips, controls. |
| `--face-readout` | Consolas → SF Mono → Cascadia Mono | Anything a device would print: ids, timestamps, scores, paths, log lines. |
| `--face-body` | Segoe UI → system-ui → Arial | Prose, descriptions, free-text fields. |

Scale: 10 / 11 / 13 / 15 / 21 / 30 / 38 px. Label tracking is `0.14em`;
micro-labels `0.20em`; headings `0.06em`. Every label is uppercase.

The split carries meaning: **instrument-printed information is condensed and
wide-tracked; machine-printed information is monospaced with tabular numerals;
human prose is the face the operator already reads their OS in.** A reviewer can
tell at a glance whether a value came from the tool or from a person. All three
stacks are system-resident — no web font is fetched, so the demo renders
identically offline.

## Rules, corners, elevation

1px hairlines, structural only. `--rule` separates, `--rule-soft` is an inner
row, `--signal-edge` (`rgba(52,216,234,.34)`) is a hard division and the top of
each plate's edge gradient.

**Corners are angular.** A plate is cut with `clip-path: polygon(0 0,
calc(100% - var(--cut)) 0, 100% var(--cut), 100% 100%, 0 100%)` — a single
diagonal at the top-right. One corner, not two: a plate can stack directly
against another (the investigation's column of panels does exactly that) and two
opposing notches read as a gap between slabs where there is none.

A `border-radius` appears in exactly one place: `--radius-ctl` (3px) on
controls, chips, table keys and the log. Everything that is a *plate* is cut;
everything that is a *control* is slightly rounded. That is the whole rule.

**Elevation is a hairline and a base shadow, never a halo.** `--elev-1` and
`--elev-2` are a 1px white top highlight plus a black offset shadow. The one
documented addition is `filter: drop-shadow(-1px 1px 0 var(--signal-edge))` on
every clipped plate: `clip-path` removes the border along the chamfer, so a
zero-blur hard-offset shadow traces that diagonal back and the cut reads as a
*cut* rather than as a corner that fell off. It is always 1px and always the
signal edge — a drawn edge, not a glow, and not the neobrutalist block shadow
because it never exceeds 1px.

Glow exists exactly twice, both on a lamp rather than on text: the live
provenance lamp, and the primary key's hover. Nothing in this console glows
around a glyph.

## The HUD material

`hud.css` owns the material; the page stylesheets own composition and never
re-declare a plate's chrome.

- **The field.** A horizontal rule cadence at `--hud-cell` (28px) with a vertical
  at four times the period, painted on `body` with `background-attachment:
  fixed`, so a long record scrolls *under* a stationary coordinate plane. The
  vertical is deliberately sparser than the horizontal; at equal weights the two
  read as graph paper rather than as a graticule.
- **The scan film.** One 1px line every 7px at 0.3 alpha over the whole
  viewport, on `body::before` at `z-index: 2` so it also crosses the drawer and
  its scrim. At that alpha it never touches glyph contrast.
- **The sweep.** A hairline crosses the title plate once every 9s, then waits.
  It is the console's single authored motion — it says the instrument is
  powered, it never moves data, and it is gone under reduced motion.

Everything above is CSS-only and consumes no DOM. **No class name in this
system was invented for a stylesheet**: every selector targets a class the TSX
already emits, and `hud.css` adds behaviour to existing elements rather than
markup to the app.

**Not built, and why:** a projected horizon floor. It was drawn, screenshotted,
and cut — a mask is painted in element space and cannot be sheared into
perspective, so a projective ground would either cost a texture (which this
brief forbids) or ship as a flat grid wearing a horizon it had not earned. The
flat graticule is the honest version of the same instrument, and the page
carries no decoration it cannot justify.

## Motion

One orchestrated moment — the header sweep — plus `--snap`
(`150ms cubic-bezier(0.2, 0, 0, 1)`) on control colour, border and shadow
changes. No entrance animations, no reveals, no bounce.

`prefers-reduced-motion: reduce` zeroes `--snap` and both sweep durations and
forces `animation-duration: 0.01ms` on everything, so the header rule and the
tape's mid-run seam both stop dead.

## Components

- **Tape** — the hero. Chassis bar, coordinate field, tolerance band, two
  traces, departure tag, tick lattice, legend. The y-axis is fixed to `0..1` so
  the band's position is comparable across runs. Inside tolerance the candidate
  is drawn 1.5px in a dimmed ink; where it departs it is repainted 3px at full
  departure red. The colour *is* the measurement.
- **Stamp** — `.stamp`, the verdict. Base state is a departure (2px red, tinted
  plate); `.stamp--clear` and `.stamp--better` override to cobalt at 1px. A
  `.u-micro` chip beside it states the same verdict in words.
- **Meter** — a two-ended bar with a fixed zero at centre. Left of centre is
  loss, right is gain. A proportional bar cannot show direction honestly, and
  direction is the entire question.
- **Record** — the case table. One status column (the candidate's), never two.
  Below 900px the wrapper scrolls rather than compressing, because a squeezed
  table puts one case's number under another case's label.
- **Evidence drawer** — a right-hand sheet that never navigates away. `.prompt`
  and `.rationale` carry a 3px margin rule: this is the one place a thick side
  border is correct, because the rule *is* the quotation mark.
- **Rocker** — a two-position switch pair used for every filter and the
  data-source toggle. The pressed position inverts to signal-on-dark.
- **Ledger** — a ruled `<dl>`, used for run metadata and the report header.
- **Sheet** — the report and findings layout: masthead, generated summary,
  ledger, tables, findings, sign-off.
- **Evidence ladder** (market) — seven ruled rungs, exactly one marked, because
  a percentage bar cannot express "a shipped product is not a pilot".

## Accessibility

All ratios below are computed against the plate the text actually sits on, not
against a nominal background.

| Pair | Ratio |
| --- | --- |
| `--ink` on `--ground` | 17.4:1 |
| `--ink-soft` on `--ground` | 9.3:1 |
| `--ink-faint` on `--ground-shade` (its worst case) | 4.7:1 — clears AA for normal text |
| `--signal` on `--ground` | 11.6:1 |
| `--baseline` on `--ground` | 7.3:1 |
| `--candidate` on `--ground` | 6.7:1 |
| `--amber` on `--ground` | 9.6:1 |
| `--violet` on `--ground` | 7.7:1 |
| `--chassis-label` on `--chassis` | 12.5:1 |
| `--graphite` on `--ground` | 3.5:1 — non-text only, above the 3:1 floor |

- Status is never conveyed by colour alone. Every status is a **labelled chip or
  word** whose border weight and style differ by meaning as well as its colour:
  solid 1px for a settled state, 2px for a confirmed or bad one, **dashed for a
  state that is still moving or an absence**. `passed` / `failed` / `error`,
  `critical` / `high` / `medium` / `low` / `info`, `measured` / `target` /
  `assumption` / `no data`, and every replay verdict (`root cause` / `partial` /
  `no effect` / `inconclusive`) are printed as words.
- Score deltas carry a sign as well as a colour, so they survive a monochrome
  screen and a colour-blind reviewer.
- Focus is a 2px `--signal-bright` outline on every interactive element. Nothing
  relies on `:hover` alone.
- The tape is an `<svg role="img">` with a `<title>` and `<desc>` carrying the
  verdict and summary as text, restated in the verdict block beneath it. No
  information exists only inside the chart.
- Every interactive control is a real `<button>`; nothing is a clickable `div`.
- Browser-owned surfaces are themed from the palette: `::selection` is
  signal-on-ground, `caret-color` is signal, scrollbars are rule-on-ground,
  links carry a signal underline at a 3px offset.

## Responsive

Desktop-first, because the demo is presented on a large screen, then verified
down to 360px.

- `> 1180px` — two columns: field and trace left, metrics and event index right.
- `≤ 1180px` — single column, tape first, then verdict, record, metrics, events.
- `≤ 900px` — the tape scrolls horizontally at a 720px minimum rather than being
  redrawn (**a squeezed chart is a lying chart**); the case table and the market
  tables scroll inside their own wrapper; the drawer takes `min(660px, 92vw)`.
- `≤ 720px` — the view key bank wraps onto a second row instead of overflowing.
- `@media print` — chrome, controls, the drawer, the field and the scan film are
  removed; the sheet prints clean at full width.

**The document does not scroll sideways at any width.** Measured with a
device-metrics override across all five surfaces at 1440 / 1180 / 900 / 420 /
360: `scrollWidth === clientWidth` everywhere — which is not something a
hand-check of the chrome would have established. Getting there needed two
structural fixes that are easy to lose again: `.shell` is
`grid-template-columns: minmax(0, 1fr)` (an implicit `auto` column takes its
minimum from its items' *min-content*, so one long unbreakable string anywhere
in the chrome — a title, a version, a provenance note — scrolls the whole
document before that item gets a chance to wrap), and the view key bank wraps
below 720px.

## Known gaps

- **Screenshot evidence is a placeholder.** `Evidence.kind = 'screenshot'`
  renders a ruled, dashed frame carrying the artifact URI and an explicit "NOT
  CAPTURED IN THIS BUILD" label. No browser capture runs in this worktree. The
  frame must never be mistaken for a real capture, so it says so in words.
- **The rubric judge is modelled, not real.** Deterministic checks are computed
  for real from the fixture answers; the LLM half of the rubric (`docs/SPEC.md`)
  is modelled as a small text-seeded jitter, labelled `rubric (modelled)`
  wherever it is shown. It is bounded to ±0.015 so it can shade a result but
  never create a regression.
- **`.tape__scroll` at narrow widths** means the chart's right edge can sit
  off-screen at 900–1000px. Deliberate; the alternative is compressing the
  timebase.
- **The field is a flat graticule, not a perspective floor.** See The HUD
  material above. This is a decision, not an omission.
- **The tick lattice is the only index into 24 cases.** With more cases it
  wraps; it is not yet a virtualised list.
