/**
 * Mirrors the frozen domain models in docs/INTERFACES.md.
 *
 * Do not rename a field here without changing that document first. Every
 * union member below is quoted verbatim from the contract so a backend that
 * satisfies the contract satisfies this file.
 */

export type UUID = string
/** UTC ISO-8601, e.g. "2026-09-11T08:12:04Z". */
export type ISODateTime = string

export type RunStatus =
  | 'queued'
  | 'planning'
  | 'executing'
  | 'evaluating'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type TestCaseCategory = 'normal' | 'boundary' | 'adversarial' | 'regression'
export type TestCaseStatus = 'pending' | 'running' | 'passed' | 'failed' | 'error'
export type TestCaseVersion = 'baseline' | 'candidate'

export type EvidenceKind = 'text' | 'screenshot' | 'log' | 'citation' | 'trace' | 'metric'

export type Severity = 'info' | 'low' | 'medium' | 'high' | 'critical'

export type EventType =
  | 'run.started'
  | 'task.created'
  | 'task.started'
  | 'evidence.created'
  | 'task.completed'
  | 'finding.created'
  | 'run.completed'
  | 'run.failed'

export interface Project {
  id: UUID
  name: string
  scenario: string
  created_at: ISODateTime
}

export interface Run {
  id: UUID
  project_id: UUID
  baseline_version: string
  candidate_version: string
  status: RunStatus
  /** Number of matched scenarios the run was planned with, when reported. */
  case_count?: number
  created_at: ISODateTime
  completed_at: ISODateTime | null
}

export interface TestCase {
  id: UUID
  run_id: UUID
  title: string
  category: TestCaseCategory
  input: Record<string, unknown>
  expected: Record<string, unknown>
  /** 0..1 */
  difficulty: number
  status: TestCaseStatus
  version: TestCaseVersion
  output: Record<string, unknown> | null
}

export interface Evidence {
  id: UUID
  run_id: UUID
  test_case_id: UUID
  kind: EvidenceKind
  uri: string | null
  payload: Record<string, unknown>
  created_at: ISODateTime
}

export interface Finding {
  id: UUID
  run_id: UUID
  test_case_id: UUID | null
  severity: Severity
  title: string
  description: string
  /** 0..1 */
  confidence: number
  evidence_ids: UUID[]
  recommendation: string | null
}

export interface Report {
  id: UUID
  run_id: UUID
  summary: string
  metrics: Record<string, unknown>
  findings: Finding[]
  generated_at: ISODateTime
}

export interface ProgressEvent {
  run_id: UUID
  sequence: number
  type: EventType
  message: string
  data: Record<string, unknown>
  created_at: ISODateTime
}

/** `GET /api/health` */
export interface Health {
  status: string
  version: string
}

/** `POST /api/runs` request body. */
export interface CreateRunRequest {
  project_id: UUID
  baseline_version: string
  candidate_version: string
  case_count?: number
  seed?: number
}

/**
 * `GET /api/demo/seed` — deterministic demo metadata only, no side effects.
 *
 * The shape below is the one `docs/INTERFACES.md` names but does not expand.
 * It is a *local* interface, not a frozen one: the console tolerates every
 * field being absent and falls back to its bundled fixtures. Flagged as a
 * contract gap in the handoff notes.
 */
export interface DemoSeed {
  project: Project
  runs: Run[]
  /** Recognised suggestions the one-click demo entry offers. */
  scenarios?: DemoScenario[]
  /**
   * The metadata the live `GET /demo/seed` returns above the faked-out
   * `project`/`runs`. `docs/INTERFACES.md` specifies the endpoint but does not
   * fix its body; these are the fields the running service actually sends and
   * the adapter reads. All optional — the console never requires them.
   */
  scenario?: string
  baseline_version?: string
  candidate_version?: string
  seed?: number
  case_count?: number
  deterministic?: boolean
}

export interface DemoScenario {
  id: string
  label: string
  note: string
  /** The `Change` that produced the candidate version. */
  change: VersionChange
}

/**
 * Why the candidate version differs from the baseline. Not part of the frozen
 * contract — the backend does not expose it yet — but the causal-comparison
 * story is unintelligible without it, so the console carries it locally.
 */
export interface VersionChange {
  summary: string
  items: string[]
  /** Configuration knobs that moved, for the "what actually changed" panel. */
  settings: Array<{ key: string; baseline: string; candidate: string }>
}

/**
 * `GET /api/runs/{run_id}/report` returns the frozen `Report`, whose `metrics`
 * field is an untyped object. The console reads it through this shape and
 * treats every field as optional, so an unfamiliar payload degrades to
 * "metric unavailable" rather than crashing the verdict.
 */
export interface MetricValue {
  baseline: number
  candidate: number
  /** Display unit, e.g. "%" or "ms". */
  unit: string
  /**
   * Which way is better. `higher` means a drop is a regression; `lower` means
   * a rise is. Latency is `lower`; citation coverage is `higher`.
   */
  direction: 'higher' | 'lower' | string
  label: string
  /** How many matched cases produced this number. */
  n: number
}

export interface ReportMetrics {
  metrics?: Record<string, MetricValue>
  /** Aggregate verdict the backend computed, when it supplies one. */
  verdict?: string
  /** Matched-case statistics backing the verdict. */
  comparison?: Comparison
}

export interface Comparison {
  matched_cases: number
  repeats: number
  /** Confidence that the candidate is worse than the baseline, 0..1. */
  regression_confidence: number
  /** Cases whose delta survived matched control and repeat sampling. */
  stable_regressions: number
  /** Cases that moved in one sample but not across repeats. */
  noise_only: number
}

/**
 * The live backend's report summary.
 *
 * `docs/INTERFACES.md` types `Report.metrics` as a bare `object`, and the
 * running service fills it with a flat aggregate rather than the frozen
 * `MetricValue` map the console renders. Naming the fields here is a *local*
 * adapter decision, documented in `frontend/TRANSPORT.md`; nothing below is
 * invented, and every field is optional so a payload that lacks one degrades
 * to "not reported" instead of a wrong number.
 */
export interface LiveReportMetrics {
  baseline_pass_rate?: number
  candidate_pass_rate?: number
  baseline_score?: number
  candidate_score?: number
  matched_scenarios?: number
  baseline_cases?: number
  candidate_cases?: number
  regression_detected?: boolean
  regression_confirmed?: boolean
  mean_difference?: number
  ci_lower?: number
  ci_upper?: number
  effect_size?: number
  confidence?: number
  direction?: string
  is_significant?: boolean
  regression_threshold?: number
  regressed_scenarios?: string[]
  control_scenarios?: string[]
  fixed_scenarios?: string[]
  findings_by_severity?: Partial<Record<Severity, number>>
  by_category?: Record<string, { total?: number; regressed?: number }>
}

/**
 * The result of resolving the demo entry against a live backend.
 *
 * `GET /demo/seed` is side-effect free by contract, so it cannot create the
 * project or the run. When live, the adapter calls this instead: the seed
 * metadata supplies the versions and seed, `listProjects`/`listRuns` supply
 * the identities, and a run is created only when none exists. Repeated calls
 * return the same run, which is what makes a second click of "Start demo run"
 * idempotent rather than a second run.
 */
export interface DemoContext {
  project: Project
  /** The run the console should open. */
  run: Run
  /** True when this call created the run rather than reusing one. */
  created: boolean
  /** The versions and seed the run was (or would be) built from. */
  baselineVersion: string
  candidateVersion: string
  seed: number | null
  caseCount: number | null
}
