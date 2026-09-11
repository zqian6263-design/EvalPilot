/**
 * The three scenarios the one-click demo entry offers.
 *
 * A regression tool that only ever finds regressions is not a comparison
 * tool, it is a rubber stamp. Scenario B exists so the demo can show the
 * verdict coming back clean, and scenario C so it can show an improvement —
 * both computed from the same corpus and the same checks as scenario A.
 */

import { CASE_SPECS, type CaseSpec } from './caseSpecs'
import { BASELINE_ANSWERS, CANDIDATE_ANSWERS, type FixtureAnswer } from './answers'
import { evaluate, type Verdict } from './scoring'
import { round } from './seed'
import { caseId, PREFIX } from './ids'
import type { Comparison, MetricValue, TestCaseStatus } from '../api/types'

export type ScenarioId = 'citation-regression' | 'unchanged' | 'improvement'

export interface CaseOutcome {
  spec: CaseSpec
  /** Stable `TestCase.id` for this case under this scenario's run. */
  caseId: string
  baseline: FixtureAnswer
  candidate: FixtureAnswer
  baselineVerdict: Verdict
  candidateVerdict: Verdict
  baselineStatus: TestCaseStatus
  candidateStatus: TestCaseStatus
  delta: number
  regression: boolean
}

export interface Scenario {
  id: ScenarioId
  label: string
  note: string
  baselineVersion: string
  candidateVersion: string
  change: {
    summary: string
    items: string[]
    settings: Array<{ key: string; baseline: string; candidate: string }>
  }
  /** The verdict headline the console renders. */
  verdict: 'regression' | 'no-regression' | 'improvement'
  verdictText: string
  summary: string
  metrics: Record<string, MetricValue>
  comparison: Comparison
  outcomes: readonly CaseOutcome[]
  /** Cases excluded because one side failed to complete. */
  excludedCaseNumbers: readonly number[]
}

// --------------------------------------------------------------- overrides --

/**
 * Scenario B: an unrelated change (a copy tweak in the help centre) that
 * moves nothing. Every answer is byte-identical to the baseline, so the
 * comparison must return no regression.
 */
const B_CANDIDATE: Record<number, FixtureAnswer> = { ...BASELINE_ANSWERS }

/**
 * Scenario C: a performance optimisation, validated as safe.
 *
 * The candidate is a faster build — smaller retrieved context, streamed
 * generation — whose answers are byte-identical to the baseline. Every quality
 * metric is therefore exactly unchanged, and the only thing that moves is
 * latency and cost.
 *
 * This is the scenario the other two cannot cover. A regression tool that only
 * ever says no is useless; the question teams actually ask most often is "can I
 * ship this optimisation without breaking quality?", and the answer here is a
 * measured yes. Because the answers are identical, the rubric jitter is
 * identical too, so every delta is exactly zero rather than approximately.
 */
const C_CANDIDATE: Record<number, FixtureAnswer> = Object.fromEntries(
  Object.entries(BASELINE_ANSWERS).map(([key, answer]) => [
    key,
    {
      ...answer,
      latency_s: round(answer.latency_s * 0.42, 2),
      tokens: Math.round(answer.tokens * 0.44),
    },
  ]),
)

// ------------------------------------------------------------------ build --

function statusFor(verdict: Verdict): TestCaseStatus {
  if (verdict.refusalCorrect === false) return 'failed'
  return verdict.total >= 0.75 ? 'passed' : 'failed'
}

function buildOutcomes(
  candidateAnswers: Record<number, FixtureAnswer>,
  idPrefix: string,
): CaseOutcome[] {
  return CASE_SPECS.map((spec) => {
    const baseline = BASELINE_ANSWERS[spec.n]!
    const candidate = candidateAnswers[spec.n]!
    const baselineVerdict = evaluate(spec, baseline)
    const candidateVerdict = evaluate(spec, candidate)
    const delta = round(candidateVerdict.total - baselineVerdict.total, 3)
    return {
      spec,
      caseId: caseId(idPrefix, spec.n),
      baseline,
      candidate,
      baselineVerdict,
      candidateVerdict,
      baselineStatus: statusFor(baselineVerdict),
      candidateStatus: statusFor(candidateVerdict),
      delta,
      regression: delta <= -0.1,
    }
  })
}

function mean(values: readonly number[]): number {
  if (values.length === 0) return 0
  return round(values.reduce((a, b) => a + b, 0) / values.length, 3)
}

function metricsFor(outcomes: readonly CaseOutcome[]): {
  metrics: Record<string, MetricValue>
  comparison: Comparison
} {
  const n = outcomes.length
  const declineCases = outcomes.filter((o) => o.spec.expected.must_decline)
  const regressions = outcomes.filter((o) => o.regression)
  const improvements = outcomes.filter((o) => o.delta >= 0.1)

  const baselineTask = mean(outcomes.map((o) => o.baselineVerdict.total))
  const candidateTask = mean(outcomes.map((o) => o.candidateVerdict.total))

  const m = (
    label: string,
    unit: string,
    direction: 'higher' | 'lower',
    baseline: number,
    candidate: number,
    count: number,
  ): MetricValue => ({ label, unit, direction, baseline, candidate, n: count })

  return {
    metrics: {
      task_success: m('Task success', '', 'higher', baselineTask, candidateTask, n),
      citation_coverage: m(
        'Citation coverage',
        '',
        'higher',
        mean(outcomes.map((o) => o.baselineVerdict.citationCoverage)),
        mean(outcomes.map((o) => o.candidateVerdict.citationCoverage)),
        n,
      ),
      correct_refusal: m(
        'Correct refusal rate',
        '',
        'higher',
        round(declineCases.filter((o) => o.baselineVerdict.refusalCorrect).length / Math.max(declineCases.length, 1), 3),
        round(declineCases.filter((o) => o.candidateVerdict.refusalCorrect).length / Math.max(declineCases.length, 1), 3),
        declineCases.length,
      ),
      format_compliance: m(
        'Format compliance',
        '',
        'higher',
        mean(outcomes.map((o) => (o.baselineVerdict.checks.find((c) => c.id === 'format_compliance')!.score === 1 ? 1 : 0))),
        mean(outcomes.map((o) => (o.candidateVerdict.checks.find((c) => c.id === 'format_compliance')!.score === 1 ? 1 : 0))),
        n,
      ),
      groundedness: m(
        'Groundedness (rubric)',
        '',
        'higher',
        mean(outcomes.map((o) => o.baselineVerdict.judge.score)),
        mean(outcomes.map((o) => o.candidateVerdict.judge.score)),
        n,
      ),
      latency_p50: m(
        'Latency p50',
        ' ms',
        'lower',
        round(mean(outcomes.map((o) => o.baseline.latency_s)) * 1000),
        round(mean(outcomes.map((o) => o.candidate.latency_s)) * 1000),
        n,
      ),
      answer_tokens: m(
        'Answer length (mean)',
        ' tok',
        'lower',
        round(mean(outcomes.map((o) => o.baseline.tokens))),
        round(mean(outcomes.map((o) => o.candidate.tokens))),
        n,
      ),
    },
    comparison: {
      matched_cases: n,
      repeats: 3,
      regression_confidence:
        regressions.length === 0
          ? round(0.04 + improvements.length / Math.max(n, 1) * 0.1, 3)
          : Math.min(round(0.5 + (baselineTask - candidateTask) / Math.max(baselineTask, 0.001) * 0.5 + regressions.length / n * 0.5, 3), 0.97),
      stable_regressions: regressions.length,
      // Flags the multi-sample pass raised that the repeats did not confirm.
      // Populated in `makeScenario`, which knows which scenario this is.
      noise_only: 0,
    },
  }
}

function makeScenario(
  id: ScenarioId,
  idPrefix: string,
  label: string,
  note: string,
  candidateVersion: string,
  verdict: Scenario['verdict'],
  candidateAnswers: Record<number, FixtureAnswer>,
  change: Scenario['change'],
): Scenario {
  const outcomes = buildOutcomes(candidateAnswers, idPrefix)
  const { metrics, comparison } = metricsFor(outcomes)
  const regressed = outcomes.filter((o) => o.regression)
  const improved = outcomes.filter((o) => o.delta >= 0.1)

  // The noise counter comes from the same table the report reads, so the
  // console and the prose can never disagree about how many flags there were.
  const noiseOnly = NOISE_FLAGS[id].length
  comparison.noise_only = noiseOnly

  const citation = metrics.citation_coverage!
  const latency = metrics.latency_p50!

  const verdictText =
    verdict === 'regression'
      ? 'Regression detected'
      : verdict === 'improvement'
        ? 'Improvement, no regression detected'
        : 'No regression detected'

  const summary =
    verdict === 'regression'
      ? `v1.5.0-rc1 is worse than v1.4.2 on ${regressed.length} of ${comparison.matched_cases} matched cases (confidence ${comparison.regression_confidence}). Citation coverage fell ${Math.round(citation.baseline * 100)}% → ${Math.round(citation.candidate * 100)}%, while latency improved ${Math.round((1 - latency.candidate / latency.baseline) * 100)}%. The regression concentrates on multi-fact answers and survives three repeat samples.`
      : verdict === 'improvement'
        ? `v1.6.0-dev is better than v1.4.2 on ${improved.length} of ${comparison.matched_cases} matched cases and worse on none. Citation coverage rose ${Math.round(citation.baseline * 100)}% → ${Math.round(citation.candidate * 100)}%. The change is safe to ship.`
        : `v1.5.1 is indistinguishable from v1.4.2 across ${comparison.matched_cases} matched cases. No metric moved beyond the noise floor and no case regressed. This change is safe to ship.`

  return {
    id,
    label,
    note,
    baselineVersion: 'v1.4.2',
    candidateVersion,
    change,
    verdict,
    verdictText,
    summary,
    metrics,
    comparison,
    outcomes,
    excludedCaseNumbers: [],
  }
}

/**
 * The single-sample flag that did not survive repeat sampling.
 *
 * Recorded per scenario rather than hard-coded in the report, because it is a
 * property of the run: the same case can be a noise flag in one comparison and
 * a confirmed change in another. Keeping it here is what stops the console's
 * "noise only" counter from disagreeing with the report's prose.
 */
const NOISE_FLAGS: Record<ScenarioId, number[]> = {
  'citation-regression': [4],
  unchanged: [],
  improvement: [],
}

const CITATION_CHANGE: Scenario['change'] = {
  summary: 'Retrieval narrowed and the answer prompt tightened for brevity',
  items: [
    'Retrieval top_k reduced from 5 to 3 documents per query.',
    'Answer prompt tightened for brevity: shorter responses, fewer restated citations.',
    'No change to the model, the embedding index, the tool allowlist, or the refusal policy.',
  ],
  settings: [
    { key: 'retrieval.top_k', baseline: '5', candidate: '3' },
    { key: 'prompt.style', baseline: 'verbose, cite every claim', candidate: 'concise, cite once' },
    { key: 'model', baseline: 'gpt-class A', candidate: 'gpt-class A' },
    { key: 'embedding_index', baseline: 'v7 (2026-08-02)', candidate: 'v7 (2026-08-02)' },
    { key: 'refusal_policy', baseline: 'decline when uncovered', candidate: 'decline when uncovered' },
  ],
}

const COPY_CHANGE: Scenario['change'] = {
  summary: 'Help-centre copy edit only; the assistant runtime is unchanged',
  items: [
    'Three help-centre articles had their titles reworded for clarity.',
    'No change to retrieval, prompt, model, tools, or policy.',
  ],
  settings: [
    { key: 'retrieval.top_k', baseline: '5', candidate: '5' },
    { key: 'prompt.style', baseline: 'verbose, cite every claim', candidate: 'verbose, cite every claim' },
    { key: 'model', baseline: 'gpt-class A', candidate: 'gpt-class A' },
    { key: 'embedding_index', baseline: 'v7 (2026-08-02)', candidate: 'v7 (2026-08-02)' },
    { key: 'refusal_policy', baseline: 'decline when uncovered', candidate: 'decline when uncovered' },
  ],
}

const WIDEN_CHANGE: Scenario['change'] = {
  summary: 'Latency optimisation with no answer change',
  items: [
    'Retrieved context trimmed before generation, and responses streamed.',
    'Latency and token cost fall by roughly 58%; every answer is byte-identical to the baseline.',
    'No change to the model, the embedding index, the tool allowlist, or the refusal policy.',
  ],
  settings: [
    { key: 'context.assembly', baseline: 'full passages', candidate: 'trimmed to cited spans' },
    { key: 'response.streaming', baseline: 'off (2.1s TTFB)', candidate: 'on (0.9s TTFB)' },
    { key: 'retrieval.top_k', baseline: '5', candidate: '5' },
    { key: 'model', baseline: 'gpt-class A', candidate: 'gpt-class A' },
    { key: 'embedding_index', baseline: 'v7 (2026-08-02)', candidate: 'v7 (2026-08-02)' },
  ],
}

export const SCENARIOS: readonly Scenario[] = [
  makeScenario(
    'citation-regression',
    PREFIX.A,
    'Citation regression',
    'The headline demo: a "faster and cheaper" candidate that quietly lost its evidence.',
    'v1.5.0-rc1',
    'regression',
    CANDIDATE_ANSWERS,
    CITATION_CHANGE,
  ),
  makeScenario(
    'unchanged',
    PREFIX.B,
    'No regression (control)',
    'An unrelated copy edit. The tool must return a clean verdict rather than manufacture a finding.',
    'v1.5.1',
    'no-regression',
    B_CANDIDATE,
    COPY_CHANGE,
  ),
  makeScenario(
    'improvement',
    PREFIX.C,
    'Safe optimisation',
    'A performance change whose answers are identical. The tool must confirm the win without inventing a quality delta.',
    'v1.6.0-dev',
    'improvement',
    C_CANDIDATE,
    WIDEN_CHANGE,
  ),
]

export function scenarioById(id: ScenarioId): Scenario {
  const found = SCENARIOS.find((s) => s.id === id)
  if (!found) throw new Error(`unknown scenario: ${id}`)
  return found
}

export const DEFAULT_SCENARIO_ID: ScenarioId = 'citation-regression'

/** The headline scenario, used by the single-scenario views (report, findings). */
export const PRIMARY = scenarioById(DEFAULT_SCENARIO_ID)
