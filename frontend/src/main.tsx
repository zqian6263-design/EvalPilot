/**
 * THESIS: The console is an instrument range. An operator sits at it in a dark
 * room and adjudicates a release; every element is a field (the coordinate
 * plane), a signal (a luminous trace), or an annotation (a bracket, a stamped
 * word). It refuses the category default of floating glass cards lit by a
 * single neon accent.
 *
 * OWN-WORLD: A committed cyan signal — #34d8ea structure, #67e8f5 hot core —
 * owning edges, rails, index keys and the candidate trace, on deep navy-black
 * plates (#05080f ground, #0a121f plate) that sit on a fixed coordinate field.
 * Status enters as ink: cobalt #5b9cff improves, amber #f2a33c flags without
 * confirming, red #ff5f57 is a confirmed departure, violet #b08cff marks the
 * tool channel. Panels are angular — one diagonal cut at the top-right, never
 * a rounded corner — with a lit top edge and a base shadow, never a halo. Type
 * is a condensed instrument panel face (Bahnschrift SemiCondensed) over a
 * monospace readout face (Consolas), with the system UI face carrying prose.
 *
 * STORY: A reviewer opens the console, sees two traces on one field that are
 * identical for the first third and then diverge, reads the tag number at the
 * departure, walks the tabulated record of all 24 matched cases, pulls the
 * evidence packet for any of them, and signs the report. They believe the
 * verdict because they watched it leave the band — not because a colour told
 * them to.
 *
 * FIRST VIEWPORT: A lit header plate with the run identity and the live
 * provenance lamp, the view keys beneath it, then the console: the field and
 * its trace on the left at full width, the metric strip on the right. The
 * one-click demo entry is the largest control in the first viewport, left
 * edge, bracketed like an armed control.
 *
 * FORM: Mission-control operator console, the room the product's own header
 * already named. Seed key e24d54a1. Raised by the hand it beat: from the
 * strip-chart incumbent, the fixed 0..1 field with its pre-printed tolerance
 * band, so a departure stays a geometric event and never becomes a badge; from
 * the teletext challenger, the character-lattice tick margin that doubles as a
 * directly-keyed case index; and from the printed-notebook challenger, the
 * stamped verdict and the initialled sign-off strip, because the record is
 * evidence and not decoration.
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
