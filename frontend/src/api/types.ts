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
