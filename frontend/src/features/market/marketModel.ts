/**
 * The market surface's model.
 *
 * One rule governs everything here, and it is the same rule the fixtures live
 * by (`src/fixtures/seed.ts`): nothing in this file may call `Math.random` or
 * `Date.now`, and every displayed number must be *derived* from the data in
 * `marketFixtures.ts` rather than typed into a component. A market panel is
 * the easiest place in a product to make a number up; deriving it is what
 * stops that happening by accident.
 *
 * `PROOF_LADDER` is the spine. It is a ladder of evidence — a shipped product
 * is not a pilot, a pilot is not a customer — and the panel's honest job is to
 * point at the rung we are actually standing on. Everything else on the
 * surface (the headline counts, the disclosure strip) is read off that rung
 * rather than asserted next to it.
 *
 * No React, no DOM, no transport: this module is deliberately pure so the
 * tests can pin the derivations without a renderer.
 */

// ---------------------------------------------------------------- evidence --

/** The rungs, weakest first. Order is load-bearing: `PROOF_LADDER` is indexed by it. */
export type ProofLevelId =
  | 'idea'
  | 'prototype'
  | 'internal_validation'
  | 'design_partner'
  | 'pilot'
  | 'paid_pilot'
  | 'paying_customers'

export interface ProofLevel {
  id: ProofLevelId
  /** As printed on the ladder. */
  label: string
  /** One line a judge can hold us to. */
  definition: string
  /** What has to be true for this rung to be claimed. */
  requires: string
  /** True only for the rung we are standing on. Exactly one entry may set this. */
  current: boolean
}

/**
 * The rungs, in climbing order.
 *
 * `internal_validation` is the rung this build occupies: the comparison engine
 * runs end to end and reports a confirmed regression across the 26-scenario
 * corpus the project ships with — but that corpus is the team's own, built by
 * the team, and every one of the eight regressed scenarios was put there
 * deliberately. That is real validation of the *product* and zero validation
 * of the *market*. Marking it anything higher would be the specific dishonesty
 * this surface exists to prevent.
 */
export const PROOF_LADDER: readonly ProofLevel[] = [
  {
    id: 'idea',
    label: 'Idea',
    definition: 'A written hypothesis about who has this problem.',
    requires: 'A document.',
    current: false,
  },
  {
    id: 'prototype',
    label: 'Prototype',
    definition: 'Something that runs, on synthetic data, for an audience of the team.',
    requires: 'A demo that does not crash.',
    current: false,
  },
  {
    id: 'internal_validation',
    label: 'Internal validation',
    definition:
      'The loop runs end to end and is checked against a corpus the team built and seeded with its own known defects.',
    requires:
      'A reproducible measurement — and the honesty to say the corpus was authored by the same people who wrote the tool.',
    current: true,
  },
  {
    id: 'design_partner',
    label: 'Design partner',
    definition: 'One external team has agreed to run it on their own system and their own data.',
    requires: 'A named counterparty and a signed agreement, even if no money moves.',
    current: false,
  },
  {
    id: 'pilot',
    label: 'Pilot',
    definition: 'That team has run it against a real release and acted on the verdict.',
    requires: 'A gate decision someone actually made, on the tool’s recommendation.',
    current: false,
  },
  {
    id: 'paid_pilot',
    label: 'Paid',
    definition: 'One team has paid for it, or committed budget to a second engagement.',
    requires: 'An invoice that was paid.',
    current: false,
  },
  {
    id: 'paying_customers',
    label: 'Multiple paying customers',
    definition: 'Two or more paying customers, with renewal decisions pending or made.',
    requires: 'Repeat revenue.',
    current: false,
  },
]

export function currentProofLevel(): ProofLevel {
  const found = PROOF_LADDER.find((level) => level.current)
  // A ladder with no current rung would silently render the whole surface as
  // "not started"; fail loudly instead, because that is a code error, not data.
  if (!found) throw new Error('PROOF_LADDER has no current rung')
  return found
}

/** How many rungs remain between us and a paying-customer claim. */
export function rungsToRevenue(): number {
  const currentIndex = PROOF_LADDER.findIndex((level) => level.current)
  const revenueIndex = PROOF_LADDER.findIndex((level) => level.id === 'paid_pilot')
  return revenueIndex - currentIndex
}

// ----------------------------------------------------------------- traction --

/**
 * The commercial numbers, all zero.
 *
 * These are typed as literals rather than computed, because the only correct
 * change to this object is a real signed counterparty — at which point the
 * value changes *and* `current` moves up a rung above. The panel renders these
 * as dashes, not as `0`: "we have none" and "we measured zero" are different
 * claims, and only the first is true.
 */
export interface Counted {
  /** Null means "not measured", which is distinct from a measured zero. */
  value: number | null
  /** What the count would mean if it were not zero. */
  note: string
}

export interface Traction {
  paying_customers: Counted
  active_pilots: Counted
  external_users: Counted
  design_partners: Counted
  external_conversations: Counted
  revenue_ytd_cny: Counted
}

export type TractionKey = keyof Traction

export const TRACTION: Traction = {
  paying_customers: { value: null, note: 'No person has ever paid for this product.' },
  active_pilots: { value: null, note: 'No external team has run it on their own system.' },
  external_users: { value: null, note: 'Nobody outside this repository has used the console.' },
  design_partners: { value: null, note: 'No agreement, letter of intent, or handshake exists.' },
  external_conversations: {
    value: null,
    note: 'Not zero by policy — simply not yet conducted.',
  },
  revenue_ytd_cny: { value: null, note: 'No revenue, in any currency, at any time.' },
}

/** The single sentence the surface must never stop printing. */
export const ZERO_TRACTION_DISCLOSURE =
  'Zero customers, zero pilots, zero external users. Nothing on this surface has been validated by anyone outside this repository; every commercial figure inside it is labelled as an assumption, a target, or a range.'

// --------------------------------------------------------------------- ROI --

/**
 * An ROI reading is always a *band*, never a point.
 *
 * Every input is an assumption with a low and a high, so the output has to be
 * a range. Collapsing it to a single seductive number is the classic way a
 * pre-validation market slide lies; the type deliberately makes that awkward.
 */
export interface RoiInput {
  id: string
  label: string
  /** Rendered small, under the label. */
  detail: string
  low: number
  high: number
  unit: string
  /**
   * Why this input is trustworthy or not. `assumption` is the default and the
   * honest state for every input in this build.
   */
  basis: 'assumption' | 'target' | 'measured'
  /** What would replace this assumption with a measurement. */
  would_measure_by: string
}

export interface RoiBand {
  low: number
  high: number
}

/** A model input that scales the whole result, kept separate from the counts. */
const ROI_INPUTS: readonly RoiInput[] = [
  {
    id: 'releases_per_year',
    label: 'Releases per year',
    detail: 'Version changes that could regress: model, prompt, retrieval, tools.',
    low: 24,
    high: 104,
    unit: '/yr',
    basis: 'assumption',
    would_measure_by: 'One design partner’s release log, counted.',
  },
  {
    id: 'p_bad_release',
    label: 'Share that regress',
    detail: 'Fraction of those releases that actually made quality worse.',
    low: 0.05,
    high: 0.2,
    unit: '',
    basis: 'assumption',
    would_measure_by: 'A retrospective on a real team’s last 20 releases.',
  },
  {
    id: 'p_detected',
    label: 'Share caught in time',
    detail:
      'Fraction of real regressions this tool would catch before production. Bounded above by the engine’s statistical power on the customer’s corpus — not by wishful thinking.',
    low: 0.3,
    high: 0.7,
    unit: '',
    basis: 'assumption',
    would_measure_by: 'Replaying the tool over known-bad releases and counting the hits.',
  },
  {
    id: 'cost_of_bad_release',
    label: 'Cost of one bad release',
    detail:
      'Diagnosis and hotfix hours, support escalations, the delayed release itself, and any compliance cost. Only the first two are usually quantifiable at all.',
    low: 50_000,
    high: 500_000,
    unit: ' CNY',
    basis: 'assumption',
    would_measure_by: 'One post-incident review with the numbers attached.',
  },
  {
    id: 'seats',
    label: 'Seats',
    detail: 'Champion plus reviewer, with a floor so a one-seat deal cannot stall.',
    low: 3,
    high: 10,
    unit: '',
    basis: 'target',
    would_measure_by: 'The first contract’s seat count.',
  },
  {
    id: 'seat_price',
    label: 'Seat price',
    detail: 'Annual, per seat.',
    low: 8_000,
    high: 25_000,
    unit: ' CNY/yr',
    basis: 'target',
    would_measure_by: 'A quoted price, and then a paid one.',
  },
  {
    id: 'cost_per_comparison',
    label: 'Cost per comparison',
    detail: 'Dominated by the model inference the run itself consumes.',
    low: 20,
    high: 200,
    unit: ' CNY',
    basis: 'assumption',
    would_measure_by: 'One live run with token accounting switched on.',
  },
]

export const ROI_INPUT_BY_ID: ReadonlyMap<string, RoiInput> = new Map(
  ROI_INPUTS.map((input) => [input.id, input]),
)

/** The narrative band: what one avoided bad release is worth per year. */
export function roiValueBand(): RoiBand {
  const input = (id: string): RoiInput => {
    const found = ROI_INPUT_BY_ID.get(id)
    if (!found) throw new Error(`unknown ROI input: ${id}`)
    return found
  }
  const value = (multiplier: number): number =>
    input('releases_per_year')[multiplier === 0 ? 'low' : 'high'] *
    input('p_bad_release')[multiplier === 0 ? 'low' : 'high'] *
    input('p_detected')[multiplier === 0 ? 'low' : 'high'] *
    input('cost_of_bad_release')[multiplier === 0 ? 'low' : 'high']
  return { low: value(0), high: value(1) }
}

/**
 * The cost of the tool itself, as a band.
 *
 * `comparisonsPerYear` defaults to the *low* release estimate: buying a
 * release gate does not mean every release is gated on day one, and pricing
 * the tool against the most optimistic usage would flatter the comparison.
 */
export function roiCostBand(comparisonsPerYear?: number): RoiBand {
  const seats = ROI_INPUT_BY_ID.get('seats')!
  const seatPrice = ROI_INPUT_BY_ID.get('seat_price')!
  const perComparison = ROI_INPUT_BY_ID.get('cost_per_comparison')!
  const releases = ROI_INPUT_BY_ID.get('releases_per_year')!
  const comparisons = comparisonsPerYear ?? releases.low
  return {
    low: seats.low * seatPrice.low + comparisons * perComparison.low,
    high: seats.high * seatPrice.high + comparisons * perComparison.high,
  }
}

/**
 * How many orders of magnitude the value band spans.
 *
 * This is the honesty metric of the whole model and it is rendered on the
 * surface: a band that spans two orders of magnitude cannot support a
 * confident ROI claim, and a reader who is told the span will not be fooled by
 * the midpoint. A `null` low (a zero anywhere in the multiplicands) has no
 * meaningful ratio.
 */
export function roiBandSpread(): number | null {
  const band = roiValueBand()
  if (band.low <= 0) return null
  return Math.log10(band.high / band.low)
}

/** True when the band is too wide for a point estimate to mean anything. */
export function roiIsUnresolved(spread = roiBandSpread()): boolean {
  return spread !== null && spread > 1
}

// ----------------------------------------------------------------- pricing --

export interface PriceRung {
  id: string
  name: string
  /** The number as it would appear on a quote — a range, or a single figure. */
  shape: string
  low: number | null
  high: number | null
  unit: string
  /** What the customer gets. */
  includes: readonly string[]
  /** Why the shape is what it is. */
  rationale: string
  /**
   * How this price has been arrived at: `hypothesis` for every rung in this
   * build, since none has been quoted to anyone.
   */
  basis: 'hypothesis' | 'quoted' | 'paid'
}

export const PRICING: readonly PriceRung[] = [
  {
    id: 'pilot',
    name: 'Pilot engagement',
    shape: '¥30k–80k, fixed fee',
    low: 30_000,
    high: 80_000,
    unit: ' one engagement',
    includes: [
      'One application, one corpus, configured against the customer’s endpoint.',
      'A baseline/candidate comparison over that corpus.',
      'A release-gate report the customer can take to their own review.',
    ],
    rationale:
      'Converts the trigger into a purchase order without asking for a platform decision. It is also what pays for the integration work, which is the real cost of the first engagement.',
    basis: 'hypothesis',
  },
  {
    id: 'subscription',
    name: 'Team subscription',
    shape: '¥8k–25k per seat per year',
    low: 8_000,
    high: 25_000,
    unit: ' / seat / yr',
    includes: [
      'Both the champion and the reviewer need access, hence a 3–5 seat floor.',
      'Run history and the accumulated regression memory.',
      'The counterfactual replay engine.',
    ],
    rationale:
      'The subscription is the anchor. A usage-only price would scale with the customer’s change frequency, penalising exactly the behaviour the product wants.',
    basis: 'hypothesis',
  },
  {
    id: 'usage',
    name: 'Comparison usage',
    shape: '¥20–200 per executed comparison',
    low: 20,
    high: 200,
    unit: ' / comparison',
    includes: [
      'Metered on matched scenarios × repeats × versions.',
      'Priced to sit below the inference cost the run itself consumes.',
    ],
    rationale:
      'A guardrail against pathological runs rather than a profit centre. Priced above inference cost, the tool reads as a tax on using it.',
    basis: 'hypothesis',
  },
]

/**
 * What would falsify the pricing shape — stated on the surface, because a
 * price with no falsification criterion is a wish.
 */
export const PRICING_FALSIFIER =
  'If, after ten qualified conversations, no champion can name the budget line that would pay for this, the pricing shape is wrong — not the price. Re-derive the shape before touching the numbers.'

// ---------------------------------------------------------------------- GTM --

export interface GtmStage {
  n: number
  name: string
  window: string
  goal: string
  artifact: string
  /** The condition under which we stop and rethink rather than push on. */
  kill: string
}

export const GTM_PLAN: readonly GtmStage[] = [
  {
    n: 1,
    name: 'Falsify the profile',
    window: 'Days 0–30',
    goal: 'Ten conversations with teams that ship a knowledge-base or support assistant.',
    artifact: 'Ten written notes, plus a count of how many hit the trigger recently.',
    kill: 'Fewer than four of ten report a blocked, delayed, or rolled-back release in the last six months. The trigger hypothesis is wrong; rewrite it before building anything else.',
  },
  {
    n: 2,
    name: 'One real corpus',
    window: 'Days 31–60',
    goal: 'Configure the tool against one design partner’s assistant and their own documents.',
    artifact: 'A retro-diagnosis on a release they have already shipped — agreement or disagreement.',
    kill: 'No signed partner by Day 45, or integration past five engineer-days. Either means the product is not yet sellable as it stands.',
  },
  {
    n: 3,
    name: 'Gate a real release',
    window: 'Days 61–90',
    goal: 'Run it as the release gate on one upcoming change and let the team act on the verdict.',
    artifact: 'A gate decision someone actually made, plus the hours it replaced.',
    kill: 'The recommendation was produced and then ignored. The product is not yet load-bearing, whatever the report said.',
  },
]

/** The one thing this plan is trying to buy. */
export const GTM_SUCCESS_DEFINITION =
  'Success is not “the tool worked”. It is: one named team ran it on real data, acted on its verdict for a real release, and can say in one sentence what it replaced.'

// --------------------------------------------------------------------- moat --

export interface MoatLayer {
  id: string
  name: string
  /** What the layer actually is. */
  claim: string
  /** How strong it is today: `none` is a real answer and is used here. */
  strength: 'none' | 'weak' | 'building' | 'strong'
  /** Why — specifically, why a competitor could or could not copy it. */
  why: string
}

/**
 * The moat, stated as three layers with three different strengths.
 *
 * Reporting a single "our moat is X" claim would be the easy version. The
 * layers are genuinely different: the mechanism is not defensible at all, the
 * memory is defensible but empty, and only the discipline is defensible today
 * — and discipline is a team property, not a product feature.
 */
export const MOAT: readonly MoatLayer[] = [
  {
    id: 'mechanism',
    name: 'The comparison mechanism',
    claim:
      'Matched cases, repeated samples, bootstrap uncertainty — so a real regression is separable from a harder test set.',
    strength: 'weak',
    why: 'This is textbook statistics. Open-source eval harnesses already ship the primitives and any competent team could assemble the design in a sprint. It is the product’s substance, but it is not a defence.',
  },
  {
    id: 'memory',
    name: 'The regression memory',
    claim:
      'Every run adds incident fingerprints and counterfactual replays, so the next engineer is told which knob caused which failure before they investigate.',
    strength: 'building',
    why: 'The only layer that compounds and the only one that gets harder to copy over time. Today it is demonstrated on seeded incidents, so its value on a real history is a hypothesis rather than a fact.',
  },
  {
    id: 'discipline',
    name: 'Evidence discipline',
    claim:
      'Every finding carries evidence ids and a rationale; the aggregate verdict is permitted to come back inconclusive; the model may not override the measurement.',
    strength: 'building',
    why: 'Hard for a score-dashboard competitor to copy, because copying it means reporting that they cannot tell. But it is a team property before it is a product feature, and a competitor with the same discipline has the same moat.',
  },
]

// ------------------------------------------------------------------ sources --

/**
 * Honesty labels. Every number on the surface carries one of these, and
 * `measured` is defined narrowly on purpose — a fixture the team authored is
 * not a measurement of the market, however precisely it is computed.
 */
export interface SourceLabel {
  id: 'measured' | 'fixture' | 'target' | 'assumption' | 'none'
  text: string
  /** Rendered with the label so the word is never decorative. */
  meaning: string
}

export const SOURCE_LABELS: readonly SourceLabel[] = [
  {
    id: 'measured',
    text: 'Measured',
    meaning:
      'Computed from this repository and reproducible by running its tests. About the product — never about the market.',
  },
  {
    id: 'fixture',
    text: 'Fixture',
    meaning: 'Seeded data authored by the team, including the defects it detects.',
  },
  {
    id: 'target',
    text: 'Target',
    meaning: 'A number the team intends to reach. Not an observation.',
  },
  {
    id: 'assumption',
    text: 'Assumption',
    meaning: 'A belief with no evidence either way. Every commercial figure here is one.',
  },
  {
    id: 'none',
    text: 'No data',
    meaning: 'Not measured. Distinct from a measured zero, and rendered as a dash.',
  },
]

// ---------------------------------------------------------------- formatting --

/** A count, or a dash. Null is never rendered as `0`. */
export function formatCount(counted: Counted): string {
  return counted.value === null ? '—' : String(counted.value)
}

/** Compact money for a chart axis: 18 000 → `18k`, 7 300 000 → `7.3M`. */
export function formatCompact(value: number): string {
  const abs = Math.abs(value)
  if (abs >= 1_000_000) return `${round1(value / 1_000_000)}M`
  if (abs >= 1_000) return `${round1(value / 1_000)}k`
  return String(Math.round(value))
}

function round1(value: number): string {
  const rounded = Math.round(value * 10) / 10
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)
}

/** A band as it appears in prose: `¥18k – ¥7.3M`. */
export function formatBand(band: RoiBand, prefix = '¥'): string {
  return `${prefix}${formatCompact(band.low)} – ${prefix}${formatCompact(band.high)}`
}

/**
 * The log10 position of a value inside a band, 0 at the low end and 1 at the
 * high end. Log scale because the bands here span orders of magnitude; a
 * linear axis would draw every interesting reading as a dot at the left edge.
 */
export function bandPosition(value: number, band: RoiBand): number {
  const spread = roiSpreadOf(band)
  if (spread === 0) return 0
  return clamp01((Math.log10(value) - Math.log10(band.low)) / spread)
}

function roiSpreadOf(band: RoiBand): number {
  if (band.low <= 0 || band.high <= 0) return 0
  return Math.log10(band.high) - Math.log10(band.low)
}

export function clamp01(value: number): number {
  return Math.min(1, Math.max(0, value))
}
