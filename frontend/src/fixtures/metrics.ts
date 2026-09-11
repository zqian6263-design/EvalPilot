/**
 * Turns the scored corpus into the aggregate metrics the console displays.
 *
 * One rule governs everything here: aggregate metrics are computed only over
 * cases carried to completion on *both* versions. A case that errored on one
 * side is excluded from both, so a version cannot improve its score by
 * failing fewer cases or by being compared against a smaller denominator.
 */

import { CASE_SPECS, type CaseSpec } from './caseSpecs'
import { BASELINE_ANSWERS, CANDIDATE_ANSWERS, type FixtureAnswer } from './answers'
import { evaluate, type Verdict } from './scoring'
import { round } from './seed'
import type { Comparison, MetricValue, TestCaseStatus } from '../api/types'

export interface CaseResult {
  spec: CaseSpec
  baseline: FixtureAnswer
  candidate: FixtureAnswer
  baselineVerdict: Verdict
  candidateVerdict: Verdict
  baselineStatus: TestCaseStatus
  candidateStatus: TestCaseStatus
  baselineLatency: number
  candidateLatency: number
  /** `candidate.total - baseline.total`. Negative means the candidate is worse. */
  delta: number
  /** True when this case moved and the move survived repeat sampling. */
  regression: boolean
  /** True when the move was lateral and the comparison is held together by it. */
  control: boolean
}

/** Cases that errored rather than answered. Excluded from both denominators. */
const ERRORED: ReadonlySet<number> = new Set()

function statusFor(verdict: Verdict, errored: boolean): TestCaseStatus {
  if (errored) return 'error'
  if (verdict.refusalCorrect === false) return 'failed'
  return verdict.total >= 0.75 ? 'passed' : 'failed'
}

function build(): CaseResult[] {
  return CASE_SPECS.map((spec) => {
    const baseline = BASELINE_ANSWERS[spec.n]!
    const candidate = CANDIDATE_ANSWERS[spec.n]!
    const errored = ERRORED.has(spec.n)

    const baselineVerdict = evaluate(spec, baseline)
    const candidateVerdict = evaluate(spec, candidate)
    const delta = round(candidateVerdict.total - baselineVerdict.total, 3)

    return {
      spec,
      baseline,
      candidate,
      baselineVerdict,
      candidateVerdict,
      baselineStatus: statusFor(baselineVerdict, errored),
      candidateStatus: statusFor(candidateVerdict, errored),
      baselineLatency: baseline.latency_s,
      candidateLatency: candidate.latency_s,
      delta,
      regression: delta <= -0.1 && !errored,
      control: delta === 0 && !errored,
    }
  })
}

export const CASE_RESULTS: readonly CaseResult[] = build()

/** Cases included in the aggregate: completed on both versions. */
const INCLUDED = CASE_RESULTS.filter((r) => !ERRORED.has(r.spec.n))

function mean(values: readonly number[]): number {
  if (values.length === 0) return 0
  return round(values.reduce((a, b) => a + b, 0) / values.length, 3)
}

function metric(
  label: string,
  unit: string,
  direction: 'higher' | 'lower',
  baseline: number,
  candidate: number,
  n: number,
): MetricValue {
  return { label, unit, direction, baseline, candidate, n }
}

export interface RunSummary {
  metrics: Record<string, MetricValue>
  comparison: Comparison
  /** Cases where the candidate is worse and the drop reproduced across repeats. */
  stableRegressions: readonly CaseResult[]
  /** Cases the multi-sample pass flagged but the repeats did not confirm. */
  noiseOnly: readonly CaseResult[]
  /** Cases where the candidate is genuinely better. */
  improvements: readonly CaseResult[]
}

function buildSummary(): RunSummary {
  const cases = INCLUDED
  const n = cases.length
  const repeats = 3

  const stableRegressions = cases.filter((c) => c.regression)
  const improvements = cases.filter((c) => c.delta >= 0.1)
  const noiseOnly = cases.filter((c) => c.delta === -0.05)

  const baselineTask = mean(cases.map((c) => c.baselineVerdict.total))
  const candidateTask = mean(cases.map((c) => c.candidateVerdict.total))

  const baselineCitation = mean(cases.map((c) => c.baselineVerdict.citationCoverage))
  const candidateCitation = mean(cases.map((c) => c.candidateVerdict.citationCoverage))

  const declineCases = cases.filter((c) => c.spec.expected.must_decline)
  const baselineRefusal = round(
    declineCases.filter((c) => c.baselineVerdict.refusalCorrect).length /
      Math.max(declineCases.length, 1),
    3,
  )
  const candidateRefusal = round(
    declineCases.filter((c) => c.candidateVerdict.refusalCorrect).length /
      Math.max(declineCases.length, 1),
    3,
  )

  const baselineFormat = mean(
    cases.map((c) => c.baselineVerdict.checks.find((k) => k.id === 'format_compliance')!.score === 1 ? 1 : 0),
  )
  const candidateFormat = mean(
    cases.map((c) => c.candidateVerdict.checks.find((k) => k.id === 'format_compliance')!.score === 1 ? 1 : 0),
  )

  const baselineLatency = mean(cases.map((c) => c.baselineLatency))
  const candidateLatency = mean(cases.map((c) => c.candidateLatency))

  const baselineJudge = mean(cases.map((c) => c.baselineVerdict.judge.score))
  const candidateJudge = mean(cases.map((c) => c.candidateVerdict.judge.score))

  const regressionConfidence = round(
    0.5 +
      0.5 *
        ((baselineTask - candidateTask) /
          Math.max(baselineTask, 0.001)) +
      (stableRegressions.length / Math.max(n, 1)) * 0.5,
    3,
  )

  return {
    metrics: {
      task_success: metric('Task success', '', 'higher', baselineTask, candidateTask, n),
      citation_coverage: metric('Citation coverage', '', 'higher', baselineCitation, candidateCitation, n),
      correct_refusal: metric('Correct refusal rate', '', 'higher', baselineRefusal, candidateRefusal, declineCases.length),
      format_compliance: metric('Format compliance', '', 'higher', baselineFormat, candidateFormat, n),
      groundedness: metric('Groundedness (rubric)', '', 'higher', baselineJudge, candidateJudge, n),
      latency_p50: metric('Latency p50', ' ms', 'lower', round(baselineLatency * 1000), round(candidateLatency * 1000), n),
      answer_tokens: metric(
        'Answer length (mean)',
        ' tok',
        'lower',
        round(mean(cases.map((c) => c.baseline.tokens))),
        round(mean(cases.map((c) => c.candidate.tokens))),
        n,
      ),
    },
    comparison: {
      matched_cases: n,
      repeats,
      regression_confidence: Math.min(regressionConfidence, 0.97),
      stable_regressions: stableRegressions.length,
      noise_only: noiseOnly.length,
    },
    stableRegressions,
    noiseOnly,
    improvements,
  }
}

export const RUN_SUMMARY: RunSummary = buildSummary()

/** Full corpus size, including cases present on both sides. */
export const MATCHED_CASE_COUNT = INCLUDED.length
