/**
 * The market surface's public entry point.
 *
 * `App.tsx` is owned by another agent in this worktree, so this feature is
 * built to be mounted without touching it. The default export — and the
 * component with no required props — is `MarketImpactPanel`, which renders the
 * whole surface from `marketFixtures.ts` and nothing else:
 *
 *     import { MarketImpactPanel } from './features/market'
 *     <MarketImpactPanel />
 *
 * With no props it needs no transport, no run, and no backend. Every fact it
 * shows therefore carries its own label rather than inheriting a provenance
 * from a run it cannot see.
 *
 * To attribute the report figures to a run the panel is mounted beside, pass
 * `measured` — the only optional prop — and the section that speaks about the
 * product will name that run. Nothing else changes: a measured run figure and
 * a bundled fixture must never be presented as the same kind of claim, so the
 * demo fixture carries its `Fixture` label in both cases.
 *
 * The stylesheet is imported from `MarketImpactPanel.tsx` rather than added to
 * `styles/index.css`, which is an existing file owned elsewhere. Vite resolves
 * the import once and the rules land in the same production bundle; the only
 * cost is that this feature must be imported for its styles to ship, which is
 * true of any lazily-loaded feature.
 */

export { MarketImpactPanel } from './MarketImpactPanel'
export type { MarketImpactPanelProps, MarketMeasuredContext } from './MarketImpactPanel'

export {
  PROOF_LADDER,
  TRACTION,
  ZERO_TRACTION_DISCLOSURE,
  ROI_INPUT_BY_ID,
  PRICING,
  PRICING_FALSIFIER,
  GTM_PLAN,
  GTM_SUCCESS_DEFINITION,
  MOAT,
  SOURCE_LABELS,
  currentProofLevel,
  rungsToRevenue,
  roiValueBand,
  roiCostBand,
  roiBandSpread,
  roiIsUnresolved,
  formatCount,
  formatCompact,
  formatBand,
  bandPosition,
  clamp01,
} from './marketModel'

export type {
  ProofLevel,
  ProofLevelId,
  Traction,
  TractionKey,
  Counted,
  RoiInput,
  RoiBand,
  PriceRung,
  GtmStage,
  MoatLayer,
  SourceLabel,
} from './marketModel'

export {
  CRITERIA,
  MAX_TOTAL,
  POSITION,
  TRACTION_ROWS,
  sourceLabel,
  totalSelfScore,
  totalTargetScore,
} from './marketFixtures'

export type { Criterion, ImprovementAction, MarketPosition } from './marketFixtures'
