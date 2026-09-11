/**
 * THESIS: Two versions of the assistant are recorded on one moving tape
 * against a pre-printed tolerance band. A regression is the trace leaving the
 * band — a geometric event on paper — not a red badge. The category-default
 * arrangement (dark console, signal-green trend, KPI tiles, glowing accent)
 * is refused.
 *
 * OWN-WORLD: Chart paper and a machine, not a dashboard. Three inks only:
 * ink #221f1a, baseline blue #2f4a6d, candidate vermilion #c8452c, with every
 * aid hairline in graphite #8d8677 on the bare ground #e8e2d4. Rules are 1px
 * and structural, never decorative; there is no border-radius anywhere and no
 * shadow. Type is condensed industrial grotesque — Arial Narrow, with
 * Bahnschrift SemiCondensed when available — and the machine's own typewriter
 * face (Consolas) for anything a device would have printed: identifiers,
 * timestamps, values, document paths. Controls are physical and labelled.
 *
 * STORY: A reviewer opens the console, sees two traces on one tape that are
 * identical for the first third and then diverge, reads the tag number at the
 * departure, walks the tabulated record of all 24 matched cases, pulls the
 * evidence packet for any of them, and signs the report. They believe the
 * verdict because they watched it leave the band — not because a colour told
 * them to.
 *
 * FIRST VIEWPORT: The tape fills the viewport below a compact run header
 * (project, versions, timestamps, the ink-stamped verdict). On the tape: the
 * pre-printed graticule, the shaded tolerance band, the baseline trace, the
 * candidate trace, and a tag callout at the first stable departure. At the
 * right edge the run's verdict is stamped onto the paper. Below the tape, the
 * machine: transport controls on the left, the record readout beside them.
 * The one-click demo entry is the largest control in the first viewport,
 * bottom-left, under its perspex guard.
 *
 * FORM: Strip-chart recorder, candidate 7 of the grounded list. Seed key
 * bd33dbaa. Raised by the hand it beat: from the teletext challenger, a
 * character-lattice tick margin down the tape's edge that doubles as the
 * directly-keyed event index; from the depot-blind challenger, a mid-run
 * state that shows two half-legends meeting across a seam instead of a
 * spinner; from the notebook challenger, machine-printed entry slugs and one
 * initialled sign-off strip, because the tape is evidence and not decoration.
 *
 * FINISH: unreviewed and undocumented is unfinished; this build ends with the
 * finish review, the verdict, DESIGN.md, and every shipping raster carrying
 * its provenance.
 */

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import './styles/index.css'

const root = document.getElementById('root')
if (!root) throw new Error('#root is missing from index.html')

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
