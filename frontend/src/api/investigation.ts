/**
 * The V2 autonomous-investigation contract, and the adapter that normalises the
 * running service into it.
 *
 * `docs/V2_INTERFACES.md` is the source of truth for every entity and endpoint
 * named below. This module is the *only* place the investigation workspace
 * talks to a backend: two implementations satisfy `InvestigationTransport` —
 * `HttpInvestigationTransport` (the real service, through the Vite `/api`
 * proxy) and `MockInvestigationTransport` (a deterministic, self-contained
 * investigation). The workspace is written against this file, so it cannot tell
 * them apart except by asking `describe().live`.
 *
 * Three rules govern the normalisers at the bottom, and they are the same three
 * rules the V1 adapter follows (`frontend/TRANSPORT.md`):
 *
 * 1. **A payload the contract leaves open is narrowed, not guessed.** The
 *    memo notes that `GET /investigations/{id}` is described as a bundle
 *    without a fixed layout, and that the run-event envelope is reused for
 *    events. Both are handled by detection, exactly as `normalizeRunDetail`
 *    handles the run envelope.
 * 2. **A missing field degrades to an absence, never to a plausible value.**
 *    Every reader below returns `null` or a labelled fallback; none invents a
 *    number.
 * 3. **Anything the adapter computes rather than copies is named.** The one
 *    derived quantity here is `breakEvenIntervention`, labelled as such.
 */

import type { UUID } from './types'

/**
 * Re-exported so a caller of the investigation endpoints can catch a
 * transport failure by shape without importing the V1 contract module as well.
 * It *is* `./transport`'s class — one error type for both API surfaces, not a
 * second one that would need its own `instanceof` check.
 */
export { ApiError } from './transport'

// --------------------------------------------------------------- entities --

/** `Investigation.status` — the pipeline stages, in order. */
export type InvestigationStatus =
  | 'queued'
  | 'planning'
  | 'investigating'
  | 'replaying'
  | 'deciding'
  | 'completed'
  | 'failed'

/** 'critical' is worst. Ordered so the workspace can rank without a lookup. */
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'

export type DecisionVerdict = 'allow' | 'review' | 'block'

/**
 * The kinds of step the tree can carry.
 *
 * `risk`, `memory`, `probe` and `counterfactual` are the investigation's own
 * reasoning artefacts. `tool` and `observation` are the structured actions it
 * took — the contract's answer to "tool traces must be displayed as structured
 * actions, not hidden reasoning". `decision` closes the run.
 */
export type InvestigationStepKind =
  | 'risk'
  | 'memory'
  | 'probe'
  | 'tool'
  | 'observation'
  | 'counterfactual'
  | 'decision'

export type InvestigationStepStatus = 'pending' | 'running' | 'completed' | 'failed'

export interface Investigation {
  id: UUID
  run_id: UUID
  objective: string
  status: InvestigationStatus
  summary: string
  risk_level: RiskLevel
  decision_verdict: DecisionVerdict
  created_at: string
  completed_at: string | null
}

export interface InvestigationStep {
  id: UUID
  investigation_id: UUID
  /** `null` for a root step; otherwise the step this one hangs beneath. */
  parent_id: UUID | null
  /** 1-based position in the investigation. Unique within an investigation. */
  sequence: number
  kind: InvestigationStepKind
  title: string
  status: InvestigationStepStatus
  detail: string
  /**
   * Kind-specific structured payload. The workspace reads this for probe
   * targets, observations, and fingerprints, and never renders it raw where a
   * named field would do.
   */
  data: Record<string, unknown>
  /** Persisted evidence this step cites. A step may cite none. */
  evidence_ids: UUID[]
  created_at: string
  completed_at: string | null
}

export interface HistoricalIncident {
  id: string
  title: string
  symptoms: string[]
  tags: string[]
  root_cause: string
  resolution: string
  /** The regression scenario this incident's fix is guarded by, when it has one. */
  guard_scenario_id: string | null
  occurred_at: string
}

export interface MemoryMatch {
  incident_id: string
  /** 0..1 similarity. */
  score: number
  reason: string
  matched_terms: string[]
}

export interface CounterfactualExperiment {
  id: UUID
  investigation_id: UUID
  scenario_id: string
  /** What was changed for the replay, e.g. `compression_disabled`. */
  intervention: string
  original_score: number
  counterfactual_score: number
  /** `counterfactual_score - original_score`. */
  delta: number
  confidence: number
  verdict: CounterfactualVerdict
  evidence_ids: UUID[]
  rationale: string
  created_at: string
}

export type CounterfactualVerdict = 'root_cause' | 'partial' | 'no_effect' | 'inconclusive'

export interface ReleaseDecision {
  verdict: DecisionVerdict
  risk_level: RiskLevel
  summary: string
  /** Evidence ids of the findings that block the release. */
  blocking_findings: UUID[]
  recommended_actions: string[]
  confidence: number
  generated_at: string
}

/**
 * `GET /investigations/{id}` — the whole investigation in one response.
 *
 * `docs/V2_INTERFACES.md` names the fields the bundle carries but does not fix
 * the envelope around them; the service sends them flattened. `normalizeInvestigationBundle`
 * accepts either layout, so a backend that later wraps the bundle keeps working.
 */
export interface InvestigationBundle {
  investigation: Investigation
  steps: InvestigationStep[]
  memory_matches: MemoryMatch[]
  counterfactuals: CounterfactualExperiment[]
  /** `null` until the investigation reaches `deciding`. */
  decision: ReleaseDecision | null
}

/**
 * The same bundle behind an envelope, for a service that wraps it.
 *
 * A local adapter shape, not a frozen one: it exists only so the normaliser can
 * detect the case rather than assume it away.
 */
export interface InvestigationBundleEnvelope {
  investigation: Investigation
  steps?: InvestigationStep[]
  memory_matches?: MemoryMatch[]
  counterfactuals?: CounterfactualExperiment[]
  decision?: ReleaseDecision | null
}

export type InvestigationBundlePayload = InvestigationBundleEnvelope | InvestigationBundle

/** `POST /investigations` request body. */
export interface CreateInvestigationRequest {
  run_id: UUID
  objective: string
}

/**
 * A progress event on `GET /investigations/{id}/events`.
 *
 * The contract says to reuse the run-event envelope, whose `type` is a closed
 * union of run-event names. An investigation advances through its own step
 * lifecycle, so this widens `type` to `string` while keeping the envelope's
 * other four fields exactly as `docs/INTERFACES.md` fixes them. Widening
 * accepts both vocabularies; narrowing to the run-event union would have thrown
 * away the step events the timeline is built from.
 */
export interface InvestigationEvent {
  run_id: UUID
  sequence: number
  type: string
  message: string
  data: Record<string, unknown>
  created_at: string
}

/** `GET /memory/incidents` — seeded history, plus matches when a query is given. */
export interface IncidentLibrary {
  incidents: HistoricalIncident[]
  /** Present only when the request carried a `query`. */
  matches: MemoryMatch[] | null
}

// --------------------------------------------------------------- endpoint --

export interface InvestigationRequestOptions {
  /** Aborts the request. */
  signal?: AbortSignal | undefined
}

export interface InvestigationTransport {
  /** Identifies the transport for the workspace's provenance line. */
  describe(): InvestigationTransportInfo

  /** Create a queued investigation for an existing evaluation run. */
  createInvestigation(
    request: CreateInvestigationRequest,
    options?: InvestigationRequestOptions,
  ): Promise<Investigation>

  /** Start an investigation. The service answers `202`; the record is re-read. */
  startInvestigation(id: UUID, options?: InvestigationRequestOptions): Promise<void>

  /** The whole investigation: record, steps, memory matches, replays, decision. */
  getInvestigation(id: UUID, options?: InvestigationRequestOptions): Promise<InvestigationBundle>

  /** Sequenced progress events, normalised out of SSE or NDJSON. */
  streamInvestigation(
    id: UUID,
    options?: InvestigationRequestOptions,
  ): AsyncIterable<InvestigationEvent>

  /** Historical incidents, optionally matched against a query. */
  listIncidents(
    query?: string,
    tag?: string,
    options?: InvestigationRequestOptions,
  ): Promise<IncidentLibrary>

  /**
   * The final Markdown report as text.
   *
   * Returns text rather than a blob so the offline transport can serve the same
   * call as the online one, and so the workspace can assert on the report's
   * claims without a browser download path.
   */
  getReport(id: UUID, options?: InvestigationRequestOptions): Promise<string>
}

export interface InvestigationTransportInfo {
  /** `http` when talking to a real backend, `mock` when serving the mock run. */
  kind: 'http' | 'mock'
  live: boolean
  /** Shown in the workspace, e.g. "offline — deterministic mock investigation". */
  label: string
  baseUrl: string | null
}

/**
 * An extra the deterministic mock offers, and the live service does not.
 *
 * `startInvestigation` on the real service is a `202` and nothing else: the
 * investigation then advances on its own, and the client finds out how far it
 * has got by reading the bundle. A mock has no scheduler behind it, so the
 * *read* is what advances it — and a test that wants to inspect a partially
 * built timeline has no way to say so through the shared interface.
 *
 * The workspace detects this optional method and calls it in the follow loop,
 * which is why the type lives here rather than in the mock's own module: the
 * same detection-not-assumption rule the two envelope normalisers follow. The
 * live transport simply does not implement it.
 */
export interface SteppableInvestigationTransport {
  advanceMockStage(): boolean
}

// -------------------------------------------------------------- view model --

/** One step plus its children, in the order the investigation recorded them. */
export interface StepTreeNode {
  step: InvestigationStep
  depth: number
  children: StepTreeNode[]
}

/**
 * The step forest, in sequence order.
 *
 * The contract gives every step a `parent_id`, so the timeline is a tree rather
 * than a list. The service sends it flat and in order; this nests it. A step
 * whose `parent_id` names a step that is not in the payload is treated as a
 * root rather than dropped — a hole in the tree must not delete a step.
 */
export function buildStepTree(steps: readonly InvestigationStep[]): StepTreeNode[] {
  const ordered = [...steps].sort((a, b) => a.sequence - b.sequence)
  const nodes = new Map<string, StepTreeNode>()
  for (const step of ordered) {
    nodes.set(step.id, { step, depth: 0, children: [] })
  }

  const roots: StepTreeNode[] = []
  for (const step of ordered) {
    const node = nodes.get(step.id)!
    const parent = step.parent_id === null ? undefined : nodes.get(step.parent_id)
    if (!parent || parent === node) {
      roots.push(node)
      continue
    }
    node.depth = parent.depth + 1
    parent.children.push(node)
  }

  return roots
}

/** Flatten a step forest back into reading order, carrying each node's depth. */
export function flattenStepTree(nodes: readonly StepTreeNode[]): StepTreeNode[] {
  const flat: StepTreeNode[] = []
  const walk = (list: readonly StepTreeNode[], depth: number): void => {
    for (const node of list) {
      node.depth = depth
      flat.push(node)
      walk(node.children, depth + 1)
    }
  }
  walk(nodes, 0)
  return flat
}

/** The regressed scenarios a probe step is aimed at, when it names any. */
export function probeTargets(step: InvestigationStep): string[] {
  if (step.kind !== 'probe') return []
  const raw = step.data.target_scenarios ?? step.data.scenario_ids ?? step.data.scenarios
  if (!Array.isArray(raw)) return []
  return raw.filter((value): value is string => typeof value === 'string')
}

/** Statuses after which an investigation will not change again. */
const TERMINAL_INVESTIGATION: ReadonlySet<InvestigationStatus> = new Set<InvestigationStatus>([
  'completed',
  'failed',
])

export function isInvestigationTerminal(status: InvestigationStatus): boolean {
  return TERMINAL_INVESTIGATION.has(status)
}

/** The hypothesis steps, in order. */
export function riskSteps(steps: readonly InvestigationStep[]): InvestigationStep[] {
  return steps.filter((step) => step.kind === 'risk')
}

// ----------------------------------------------------------- normalisation --

const asRecord = (value: unknown): Record<string, unknown> =>
  typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {}

const asArray = (value: unknown): unknown[] => (Array.isArray(value) ? value : [])

const asString = (value: unknown, fallback = ''): string =>
  typeof value === 'string' ? value : fallback

const asNumber = (value: unknown, fallback = 0): number =>
  typeof value === 'number' && Number.isFinite(value) ? value : fallback

const asStringList = (value: unknown): string[] =>
  asArray(value).filter((item): item is string => typeof item === 'string')

const RISK_LEVELS: readonly RiskLevel[] = ['low', 'medium', 'high', 'critical']
const DECISION_VERDICTS: readonly DecisionVerdict[] = ['allow', 'review', 'block']

/**
 * Rank a risk level. Higher is worse. An unrecognised level ranks *worst*
 * rather than best, because a level this build cannot read must not be the
 * reason a release is waved through.
 */
export function riskRank(level: RiskLevel): number {
  const index = RISK_LEVELS.indexOf(level)
  return index < 0 ? RISK_LEVELS.length : index
}

export function asRiskLevel(value: unknown): RiskLevel {
  const raw = asString(value)
  return (RISK_LEVELS as readonly string[]).includes(raw) ? (raw as RiskLevel) : 'critical'
}

export function asDecisionVerdict(value: unknown): DecisionVerdict {
  const raw = asString(value)
  return (DECISION_VERDICTS as readonly string[]).includes(raw)
    ? (raw as DecisionVerdict)
    : // An unreadable verdict is not permission to ship.
      'block'
}

export function normalizeInvestigation(raw: unknown): Investigation {
  const record = asRecord(raw)
  return {
    id: asString(record.id),
    run_id: asString(record.run_id),
    objective: asString(record.objective),
    status: asString(record.status, 'queued') as InvestigationStatus,
    summary: asString(record.summary),
    risk_level: asRiskLevel(record.risk_level),
    decision_verdict: asDecisionVerdict(record.decision_verdict),
    created_at: asString(record.created_at),
    completed_at: typeof record.completed_at === 'string' ? record.completed_at : null,
  }
}

export function normalizeStep(raw: unknown): InvestigationStep {
  const record = asRecord(raw)
  return {
    id: asString(record.id),
    investigation_id: asString(record.investigation_id),
    parent_id: typeof record.parent_id === 'string' ? record.parent_id : null,
    sequence: asNumber(record.sequence),
    kind: asString(record.kind, 'observation') as InvestigationStepKind,
    title: asString(record.title),
    status: asString(record.status, 'pending') as InvestigationStepStatus,
    detail: asString(record.detail),
    data: asRecord(record.data),
    evidence_ids: asStringList(record.evidence_ids),
    created_at: asString(record.created_at),
    completed_at: typeof record.completed_at === 'string' ? record.completed_at : null,
  }
}

export function normalizeMemoryMatch(raw: unknown): MemoryMatch {
  const record = asRecord(raw)
  return {
    incident_id: asString(record.incident_id),
    score: asNumber(record.score),
    reason: asString(record.reason),
    matched_terms: asStringList(record.matched_terms),
  }
}

export function normalizeCounterfactual(raw: unknown): CounterfactualExperiment {
  const record = asRecord(raw)
  const original = asNumber(record.original_score)
  const counterfactual = asNumber(record.counterfactual_score)
  return {
    id: asString(record.id),
    investigation_id: asString(record.investigation_id),
    scenario_id: asString(record.scenario_id),
    intervention: asString(record.intervention),
    original_score: original,
    counterfactual_score: counterfactual,
    // The contract defines `delta` as the difference. When the service omits it
    // the two scores it did send determine it, so this is a reading of two
    // reported facts rather than an estimate; when either score is absent the
    // difference is not claimed.
    delta:
      typeof record.delta === 'number'
        ? record.delta
        : typeof record.original_score === 'number' &&
            typeof record.counterfactual_score === 'number'
          ? counterfactual - original
          : 0,
    confidence: asNumber(record.confidence),
    verdict: asString(record.verdict, 'inconclusive') as CounterfactualVerdict,
    evidence_ids: asStringList(record.evidence_ids),
    rationale: asString(record.rationale),
    created_at: asString(record.created_at),
  }
}

export function normalizeDecision(raw: unknown): ReleaseDecision | null {
  if (raw === null || raw === undefined) return null
  const record = asRecord(raw)
  if (Object.keys(record).length === 0) return null
  return {
    verdict: asDecisionVerdict(record.verdict),
    risk_level: asRiskLevel(record.risk_level),
    summary: asString(record.summary),
    blocking_findings: asStringList(record.blocking_findings),
    recommended_actions: asStringList(record.recommended_actions),
    confidence: asNumber(record.confidence),
    generated_at: asString(record.generated_at),
  }
}

/**
 * Flatten `GET /investigations/{id}` into the bundle the workspace renders.
 *
 * The service sends the bundle flattened; the envelope branch exists so a
 * backend that wraps it — the way `GET /runs/{id}` does — keeps working
 * unchanged. Detection, not assumption, is what lets both feed one workspace.
 *
 * Absent arrays become `[]` rather than throwing: an investigation that has
 * produced no probes yet is a normal state, not a malformed response.
 */
export function normalizeInvestigationBundle(raw: InvestigationBundlePayload): InvestigationBundle {
  const record = asRecord(raw)
  const investigation = normalizeInvestigation(record.investigation)
  return {
    investigation,
    steps: asArray(record.steps).map(normalizeStep),
    memory_matches: asArray(record.memory_matches).map(normalizeMemoryMatch),
    counterfactuals: asArray(record.counterfactuals).map(normalizeCounterfactual),
    decision: normalizeDecision(record.decision ?? null),
  }
}

export function normalizeIncident(raw: unknown): HistoricalIncident {
  const record = asRecord(raw)
  return {
    id: asString(record.id),
    title: asString(record.title),
    symptoms: asStringList(record.symptoms),
    tags: asStringList(record.tags),
    root_cause: asString(record.root_cause),
    resolution: asString(record.resolution),
    guard_scenario_id:
      typeof record.guard_scenario_id === 'string' ? record.guard_scenario_id : null,
    occurred_at: asString(record.occurred_at),
  }
}

export function normalizeIncidentLibrary(raw: unknown): IncidentLibrary {
  const record = asRecord(raw)
  return {
    incidents: asArray(record.incidents).map(normalizeIncident),
    matches: Array.isArray(record.matches) ? record.matches.map(normalizeMemoryMatch) : null,
  }
}

export function normalizeInvestigationEvent(raw: unknown): InvestigationEvent {
  const record = asRecord(raw)
  return {
    run_id: asString(record.run_id),
    sequence: asNumber(record.sequence),
    type: asString(record.type),
    message: asString(record.message),
    data: asRecord(record.data),
    created_at: asString(record.created_at),
  }
}

// --------------------------------------------------- adapter derivations ----

export interface CounterfactualOutcome {
  /** The intervention that, applied to the original, would restore the score. */
  intervention: string
  /** The counterfactual score it restores. */
  restores: number
  /** `restores - original`. */
  gain: number
  /** The largest `delta` any other experiment on this scenario achieved. */
  runnerUpDelta: number
  /** Percentage points by which it beats the runner-up. */
  marginPoints: number
}

/**
 * The experiment that would most nearly undo the original result.
 *
 * **Derived.** This is the largest `delta` among the experiments run on one
 * scenario, with the runner-up's delta reported beside it so the margin is
 * visible rather than asserted. It is a ranking of measurements the service
 * made, not a new measurement, and the workspace labels it as a derived
 * reading. When the top two tie, `intervention` is `null`: a tie is not a
 * finding, and picking one would manufacture certainty the replay did not
 * produce.
 */
export function breakEvenIntervention(
  experiments: readonly CounterfactualExperiment[],
): CounterfactualOutcome | null {
  if (experiments.length === 0) return null
  const ranked = [...experiments].sort((a, b) => b.delta - a.delta)
  const best = ranked[0]!
  const runnerUp = ranked[1]
  if (runnerUp && Math.abs(runnerUp.delta - best.delta) < 1e-9) {
    return {
      intervention: '',
      restores: best.counterfactual_score,
      gain: best.delta,
      runnerUpDelta: runnerUp.delta,
      marginPoints: 0,
    }
  }
  return {
    intervention: best.intervention,
    restores: best.counterfactual_score,
    gain: best.delta,
    runnerUpDelta: runnerUp ? runnerUp.delta : 0,
    marginPoints: Math.round((best.delta - (runnerUp?.delta ?? 0)) * 1000) / 10,
  }
}

/** Group experiments by the scenario they replay, preserving first-seen order. */
export function groupCounterfactuals(
  experiments: readonly CounterfactualExperiment[],
): Array<{ scenario_id: string; experiments: CounterfactualExperiment[] }> {
  const groups = new Map<string, CounterfactualExperiment[]>()
  for (const experiment of experiments) {
    const bucket = groups.get(experiment.scenario_id)
    if (bucket) bucket.push(experiment)
    else groups.set(experiment.scenario_id, [experiment])
  }
  return [...groups].map(([scenario_id, list]) => ({ scenario_id, experiments: list }))
}

/**
 * The evidence ids every root-cause claim rests on, deduplicated.
 *
 * Only experiments whose verdict is `root_cause` or `partial` contribute: an
 * `inconclusive` replay cites evidence for why it is inconclusive, and counting
 * that as support for a root cause is exactly the error this product exists to
 * catch. The workspace prints this list so "3 of 3 claims cite evidence" is a
 * countable statement rather than a claim about the whole.
 */
export function rootCauseEvidenceIds(
  experiments: readonly CounterfactualExperiment[],
): string[] {
  const ids = new Set<string>()
  for (const experiment of experiments) {
    if (experiment.verdict !== 'root_cause' && experiment.verdict !== 'partial') continue
    for (const id of experiment.evidence_ids) ids.add(id)
  }
  return [...ids]
}

/** Every evidence id cited anywhere in the investigation, deduplicated. */
export function citedEvidenceIds(bundle: InvestigationBundle): string[] {
  const ids = new Set<string>()
  for (const step of bundle.steps) for (const id of step.evidence_ids) ids.add(id)
  for (const experiment of bundle.counterfactuals) for (const id of experiment.evidence_ids) ids.add(id)
  for (const id of bundle.decision?.blocking_findings ?? []) ids.add(id)
  return [...ids]
}

/**
 * The report URL the workspace offers for download.
 *
 * Empty for a mock transport: an offline investigation has no endpoint to
 * point at, and printing a URL that would 404 is worse than printing nothing.
 * The workspace falls back to downloading the mock's own Markdown text.
 */
export function reportUrl(
  transport: InvestigationTransportInfo,
  investigationId: string,
): string {
  if (!transport.live || !transport.baseUrl) return ''
  return `${transport.baseUrl}/investigations/${encodeURIComponent(investigationId)}/report.md`
}
