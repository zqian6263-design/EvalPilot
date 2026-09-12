/**
 * The bridge between a live run and the console.
 *
 * `GET /runs/{run_id}` gives the console cases, evidence and counts;
 * `GET /runs/{run_id}/report` gives it the aggregate. Neither matches the
 * console's view model, and one part of that view model — the frozen
 * `MetricValue` a metric row renders — the backend does not produce at all.
 *
 * Two rules govern everything below.
 *
 * First, nothing here invents a number. Every value traces to a field the
 * backend sent; where a field is absent the view model records the *absence*
 * (`null` score, a missing metric id) so the UI can say "not reported" rather
 * than print a plausible-looking figure.
 *
 * Second, the derivations are stated. Pairing a baseline case with its
 * candidate by `input.scenario_id` and calling the pair regressed when the
 * baseline passed and the candidate failed are both readings of two backend
 * facts, not estimates — and both are named `derived`, never `measured`.
 * `frontend/TRANSPORT.md` lists every one of them.
 */

import type { RunDetail } from './transport'
import type {
  Evidence,
  Finding,
  LiveReportMetrics,
  MetricValue,
  Report,
  Run,
  Severity,
  TestCase,
  TestCaseCategory,
  TestCaseStatus,
} from './types'

/** A metric row the console can render: a real pair, or an explicit absence. */
export interface LiveMetricRow {
  id: string
  label: string
  /** `null` when the backend reported no baseline/candidate pair for it. */
  value: MetricValue | null
}

/**
 * The metric rows the console knows how to render, in display order.
 *
 * This list is the console's, not the backend's: the backend reports one
 * aggregate pair (a pass rate) and no per-metric breakdown at all, so most of
 * these render as unavailable. The list stays full-width rather than shrinking
 * to what one backend happens to send, because a metric silently vanishing
 * from the table is worse than a metric visibly marked "not reported".
 */
export const LIVE_METRIC_ROWS: ReadonlyArray<{ id: string; label: string }> = [
  { id: 'task_success', label: '任务成功率（通过率）' },
  { id: 'citation_coverage', label: '引用覆盖率' },
  { id: 'correct_refusal', label: '正确拒答率' },
  { id: 'format_compliance', label: '格式合规率' },
  { id: 'groundedness', label: '有据性（评分表）' },
  { id: 'latency_p50', label: '延迟 P50' },
  { id: 'answer_tokens', label: '回答长度（均值）' },
]

/**
 * Read the aggregate pass rate out of the live report as a `MetricValue`.
 *
 * This is the one metric the running service reports as a baseline/candidate
 * pair over matched cases — precisely what `MetricValue` means, so converting
 * it fabricates nothing. `n` is `matched_scenarios`, the denominator the
 * backend itself divided by, not a count this module chose.
 */
function passRateMetric(metrics: LiveReportMetrics): MetricValue | null {
  const { baseline_pass_rate: baseline, candidate_pass_rate: candidate } = metrics
  if (typeof baseline !== 'number' || typeof candidate !== 'number') return null
  return {
    label: '任务成功率（通过率）',
    unit: '',
    direction: 'higher',
    baseline,
    candidate,
    n: typeof metrics.matched_scenarios === 'number' ? metrics.matched_scenarios : 0,
  }
}

export function buildLiveMetricRows(report: Report | null): LiveMetricRow[] {
  const metrics = (report?.metrics ?? {}) as LiveReportMetrics
  const pairs: Record<string, MetricValue | null> = {
    task_success: passRateMetric(metrics),
  }
  return LIVE_METRIC_ROWS.map(({ id, label }) => ({ id, label, value: pairs[id] ?? null }))
}

/** Sources the console consulted, so the UI can name them rather than imply. */
export interface LiveSources {
  runDetail: boolean
  report: boolean
}

/**
 * One matched case, as the live run reported it.
 *
 * `baseline` and `candidate` are the backend's own rows. `regressed` is the
 * only derived field: the baseline passed the case and the candidate did not,
 * which is exactly what the backend's own finding text says happened.
 */
export interface LiveCase {
  /** 1-based position in the run's case order, for the table's No column. */
  n: number
  scenarioId: string
  category: TestCaseCategory
  difficulty: number
  baseline: TestCase
  candidate: TestCase
  baselineStatus: TestCaseStatus
  candidateStatus: TestCaseStatus
  regressed: boolean
  /**
   * Candidate minus baseline latency in ms, when both versions reported one.
   *
   * A difference of two numbers the backend sent, not a score.
   */
  latencyDeltaMs: number | null
}

const asNumber = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null

const asRecord = (value: unknown): Record<string, unknown> =>
  typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : {}

export function scenarioIdOf(testCase: TestCase): string {
  const fromInput = asRecord(testCase.input).scenario_id
  if (typeof fromInput === 'string' && fromInput) return fromInput
  // The planner falls back to the title when it has no scenario id; strip the
  // `[baseline]` / `[candidate]` suffix so the pair still meets.
  return testCase.title.replace(/\s*\[(baseline|candidate)\]$/, '')
}

/**
 * Pair the run's cases into matched baseline/candidate rows.
 *
 * A scenario present on only one side is dropped rather than paired with a
 * hole: the console's whole claim is that it compares two versions of the same
 * input, and a one-sided row would quietly weaken that. Dropped ids are
 * returned so the view can say how many were unmatched instead of silently
 * showing a shorter table.
 */
export function pairCases(cases: readonly TestCase[]): {
  rows: LiveCase[]
  unmatched: string[]
} {
  const byScenario = new Map<string, { baseline?: TestCase; candidate?: TestCase }>()
  for (const testCase of cases) {
    const id = scenarioIdOf(testCase)
    const bucket = byScenario.get(id) ?? {}
    if (testCase.version === 'baseline') bucket.baseline ??= testCase
    else bucket.candidate ??= testCase
    byScenario.set(id, bucket)
  }

  const rows: LiveCase[] = []
  const unmatched: string[] = []
  for (const [scenarioId, bucket] of byScenario) {
    if (!bucket.baseline || !bucket.candidate) {
      unmatched.push(scenarioId)
      continue
    }
    const baselineLatency = asNumber(asRecord(bucket.baseline.output).latency_ms)
    const candidateLatency = asNumber(asRecord(bucket.candidate.output).latency_ms)
    rows.push({
      n: rows.length + 1,
      scenarioId,
      category: bucket.candidate.category,
      difficulty: bucket.candidate.difficulty,
      baseline: bucket.baseline,
      candidate: bucket.candidate,
      baselineStatus: bucket.baseline.status,
      candidateStatus: bucket.candidate.status,
      regressed: bucket.baseline.status === 'passed' && bucket.candidate.status !== 'passed',
      latencyDeltaMs:
        baselineLatency === null || candidateLatency === null
          ? null
          : candidateLatency - baselineLatency,
    })
  }

  // Report order is the backend's; sorting by scenario id would impose one the
  // run never had.
  const order = cases.map(scenarioIdOf)
  rows.sort((a, b) => order.indexOf(a.scenarioId) - order.indexOf(b.scenarioId))
  rows.forEach((row, index) => {
    row.n = index + 1
  })

  return { rows, unmatched }
}

/** Evidence rows the run attached to one case, in backend order. */
export function evidenceForLiveCase(detail: RunDetail, caseId: string): Evidence[] {
  return detail.evidence.filter((item) => item.test_case_id === caseId)
}

/**
 * Every evidence row a finding cites, resolved against the run.
 *
 * A finding names `evidence_ids`; this returns the rows behind them, and
 * reports the ids that resolved to nothing so "4 evidence links" can never
 * quietly describe three rows and a hole.
 */
export function evidenceForFinding(detail: RunDetail, finding: Finding): {
  rows: Evidence[]
  dangling: string[]
} {
  const index = new Map(detail.evidence.map((item) => [item.id, item]))
  const rows: Evidence[] = []
  const dangling: string[] = []
  for (const id of finding.evidence_ids) {
    const row = index.get(id)
    if (row) rows.push(row)
    else dangling.push(id)
  }
  return { rows, dangling }
}

export function severityCounts(findings: readonly Finding[]): Record<Severity, number> {
  const counts: Record<Severity, number> = { critical: 0, high: 0, medium: 0, low: 0, info: 0 }
  for (const finding of findings) counts[finding.severity] += 1
  return counts
}

/** Verdicts the live backend can state. */
export type LiveVerdict = 'regression' | 'localized-regression' | 'no-regression'

export interface LiveEvaluation {
  run: Run
  /** The run detail the view was built from, for evidence lookups. */
  detail: RunDetail
  cases: LiveCase[]
  /** Scenario ids that appeared on only one version and are excluded. */
  unmatchedScenarios: string[]
  findings: Finding[]
  evidence: Evidence[]
  counts: { evidence: number; findings: number; events: number; cases: number }
  metrics: LiveMetricRow[]
  /** Metric rows the backend supplied no pair for. */
  missingMetricIds: string[]
  /** The report's raw metrics object, for views that read it directly. */
  reportMetrics: Record<string, unknown>
  verdict: LiveVerdict
  summary: string
  sources: LiveSources
}

export interface BuildArgs {
  detail: RunDetail
  /** `null` when the report could not be read (a run that has not completed). */
  report: Report | null
  findings: readonly Finding[]
}

/**
 * Assemble the console's live view from one run.
 *
 * `detail` is kept whole rather than reduced to its parts, because the
 * evidence lookups below need the run's full evidence list and a view that
 * only had the row array could not answer "which rows does this finding cite".
 * `findings` is passed separately because a report holds the findings but a
 * run that has not completed has no report yet, and the console still wants to
 * show whatever the run has produced so far.
 */
export function buildLiveEvaluation({ detail, report, findings }: BuildArgs): LiveEvaluation {
  const { rows, unmatched } = pairCases(detail.test_cases)
  const metrics = buildLiveMetricRows(report)
  const liveMetrics = (report?.metrics ?? {}) as LiveReportMetrics

  // Distinguish a statistically confirmed aggregate regression from real
  // regressions that were localized to specific cases. Both are release
  // blockers, but only the first is supported by the paired confidence interval.
  // When there is no report there is no verdict, so the console reports the
  // run's own state rather than guessing one from the case rows.
  const verdict: LiveVerdict =
    liveMetrics.regression_confirmed === true
      ? 'regression'
      : liveMetrics.regression_detected === true
        ? 'localized-regression'
        : 'no-regression'

  return {
    run: detail,
    detail,
    cases: rows,
    unmatchedScenarios: unmatched,
    findings: [...findings],
    evidence: detail.evidence,
    counts: {
      evidence: detail.evidence_count,
      findings: detail.finding_count,
      events: detail.event_count,
      // The UI calls a matched scenario a case. `test_cases` contains one
      // row per version, so using its raw length would double the denominator
      // while the table and the report both count paired scenarios.
      cases: rows.length,
    },
    metrics,
    missingMetricIds: metrics.filter((row) => row.value === null).map((row) => row.id),
    reportMetrics: report?.metrics ?? {},
    verdict,
    summary: report?.summary ?? '',
    sources: { runDetail: true, report: report !== null },
  }
}
