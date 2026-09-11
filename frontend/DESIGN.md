# Design System

<!-- impeccable:design-schema 1 -->

DESIGN.md records what the console *is*, as built. PRODUCT.md records what the
product is for. Where the two disagree about intent, PRODUCT.md wins; where they
disagree about the interface, this file is the description of record.

## World

**Chart paper and a machine.** EvalPilot's console is drawn as a strip-chart
recorder: two versions of an AI assistant are traced onto one moving paper tape
against a pre-printed tolerance band. A regression is not a badge colour, it is
a geometric event — the candidate trace leaving the band — and the whole surface
is organised so a reviewer can watch that happen and then audit it.

The category default (near-black dashboard, signal-green trend line, KPI tiles,
one glowing accent, rounded cards) is refused deliberately. The console is
paper-light because it is a record, not a control room.

Seed: `bd33dbaa`, direction candidate 7 of the grounded list. Raises carried in
from the challengers it beat:

| Kept from | The discipline it donated |
| --- | --- |
| Teletext service | A character-lattice tick margin down the tape's edge that doubles as the directly-keyed case index. |
| Depot destination blind | A mid-run state shows two half-legends meeting across a seam instead of a spinner. |
| Bound analytical notebook | Machine-printed entry slugs and an initialled sign-off strip; the tape is evidence, not decoration. |

## Palette

Three inks, one ground, one graphite for every aid hairline. Nothing else.

| Token | Value | Role |
| --- | --- | --- |
| `--ground` | `#e8e2d4` | Bare chart paper. The page background, always. |
| `--ground-lit` | `#f0ebe0` | Paper under the lamp: panels, readouts, the drawer. |
| `--ground-shade` | `#ddd6c5` | Paper in the machine's shadow: rails, table headers, side column. |
| `--ink` | `#221f1a` | The printed record: body text, rules, primary controls. |
| `--ink-soft` | `#4a453c` | Secondary print: descriptions, supporting prose. |
| `--baseline` | `#2f4a6d` | Baseline trace, baseline values, "better" movement. Deep blue. |
| `--candidate` | `#c8452c` | Candidate trace, regressions, failures, the ink stamp. Vermilion. |
| `--graphite` | `#8d8677` | Graticule, all aid hairlines, de-emphasised data. |
| `--graphite-faint` | `#b8b09e` | Minor graticule and inner row rules only. |
| `--band` | `rgba(47,74,109,0.11)` | The tolerance band. A tint of the baseline ink, not a new colour. |
| `--chassis` | `#2b2721` | The machine's body: the tape chassis and the provenance bar. |

Colour strategy: **Restrained**, with one committed exception. The tape is the
only region where saturation appears at scale, and there it is load-bearing —
the candidate trace is drawn in muted graphite while inside tolerance and in
full vermilion where it departs. The colour *is* the measurement.

**Rule: a value may only be a literal in `tokens.css`.** If a colour or size is
hard-coded inside a component or a page stylesheet, it is a defect.

## Type

| Role | Stack | Used for |
| --- | --- | --- |
| `--face-label` | Arial Narrow → Bahnschrift SemiCondensed → Liberation Sans Narrow | Headings, labels, verdicts, controls. |
| `--face-device` | Consolas → SF Mono → Cascadia Mono | Anything a device would have printed: ids, timestamps, scores, document paths, log lines. |
| `--face-body` | Arial Narrow → Bahnschrift → Arial | Prose. |

Scale: 10 / 11 / 13 / 15 / 21 / 30 px. Label tracking is `0.14em`; micro-labels
`0.20em`. Every label is uppercase.

The two-face split carries meaning and is not decorative: **human-printed
information is set in the grotesque; machine-printed information is set in the
device face.** A reviewer can tell at a glance whether a value came from the
tool or from a person.

## Rules, corners, elevation

1px hairlines, structural only. `--rule` (graphite) separates, `--rule-ink`
(ink) is a hard division, `--rule-faint` is an inner row. **There is no
`border-radius` anywhere in the system and no `box-shadow` except the
single inset rule on a selected table row.** The world has no rounded corners
and nothing floats.

Two documented exceptions to the "no thick side border" rule, both carrying
meaning rather than decorating a container, and both invisible unless there is a
finding to report:

- `.prompt` (evidence drawer) — a rule in the margin marking a quoted passage,
  the way a printed edition marks a block quote.
- `.rationale` (evidence drawer) — the same convention for the evaluator's
  quoted reasoning.

## Motion

One transition, `--snap`: `160ms cubic-bezier(0.2, 0, 0.2, 1)`, on control
colour changes. Damped, single axis, no overshoot, no entrance animation.

The only deliberate loop is the mid-run seam (`.seam__clipped`), where a clipped
line steps between two half-legends. It is disabled under
`prefers-reduced-motion`, as is `--snap`.

## Components

- **Tape** — the hero. Chassis bar, graticule, tolerance band, two traces,
  departure tag, tick margin, legend. The y-axis is fixed to `0..1` so the
  band's position is comparable across runs.
- **Ink stamp** — `.stamp`, the verdict, rotated 1.5°. Vermilion for a
  regression, blue for clear or improved.
- **Meter** — a two-ended bar with a fixed zero at centre. Left of centre is
  loss, right is gain. A proportional bar cannot show direction honestly, and
  direction is the entire question.
- **Record** — the case table. One status column (the candidate's), never two:
  a version that errors on both sides is not two facts.
- **Evidence drawer** — a right-hand sheet that never navigates away, so a
  reviewer checking a claim keeps their place in the table.
- **Rocker** — a two-position switch pair used for every filter and for the
  data-source toggle. The pressed position inverts to ink-on-paper.
- **Ledger** — a ruled `<dl>`, used for run metadata and the report header. The
  label/value form, printed.
- **Sheet** — the report and findings layout: a masthead, a generated summary,
  a ledger, tables, findings, and a sign-off strip.

## Accessibility

- Contrast: `--ink` on `--ground` is 13.4:1; `--ink-soft` 7.9:1; `--candidate`
  4.9:1; `--baseline` 7.6:1; `--graphite` on `--ground` is 2.6:1 and is
  therefore **restricted to rules, graticule, and non-essential decoration** —
  never to text carrying meaning on its own.
- Status is never conveyed by colour alone: every status is a labelled chip with
  a border style (`passed` solid ink, `failed` heavy vermilion, `error` dashed).
  Score deltas carry a sign as well as a colour.
- Focus is a 2px vermilion outline on every interactive element. Nothing relies
  on `:hover` alone.
- The tape is an `<svg role="img">` with a `<title>` and `<desc>` carrying the
  verdict and summary as text, and the same information is stated in the verdict
  block beneath it. No information exists only inside the chart.
- Every interactive control is a real `<button>`; nothing is a clickable `div`.
- `prefers-reduced-motion` disables the one looping animation and the one
  transition.

## Responsive

Desktop-first, because the demo is presented on a large screen.

- `> 1180px` — two columns: tape and record left, metrics and event index right.
- `≤ 1180px` — single column, tape first, then verdict, record, metrics, events.
- `≤ 900px` — the tape scrolls horizontally at a 720px minimum rather than
  being redrawn. **A squeezed chart is a lying chart**; the timebase keeps its
  aspect. Filters wrap; the drawer takes `min(660px, 92vw)`.
- `@media print` — chrome, controls, and the drawer are removed; the sheet
  prints clean at full width.

## Known gaps

- **Screenshot evidence is a placeholder.** `Evidence.kind = 'screenshot'`
  renders a ruled frame with the artifact URI and an explicit "not captured in
  this build" label. No browser capture runs in this worktree. The frame must
  never be mistaken for a real capture, so it says so in words.
- **The rubric judge is modelled, not real.** Deterministic checks are computed
  for real from the fixture answers; the LLM half of the rubric
  (`docs/SPEC.md`) is modelled as a small text-seeded jitter, labelled
  `rubric (modelled)` wherever it is shown. It is bounded to ±0.015 so it can
  shade a result but never create a regression.
- **`.tape__scroll` at narrow widths** means the chart's right edge can sit
  off-screen at 900–1000px. Deliberate; the alternative is compressing the
  timebase.
