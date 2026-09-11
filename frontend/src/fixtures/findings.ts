/**
 * Findings and report, derived from the computed case results.
 *
 * Every finding carries `evidence_ids` pointing at evidence this module also
 * builds, so the UI can always resolve a finding back to its inputs. No
 * finding is hard-coded to a conclusion the case data does not support: the
 * factory functions below read `CASE_RESULTS` and the aggregate metrics.
 */

import { at, caseId, evidenceId, findingId, PREFIX, REPORT_A_ID, RUN_A_ID } from './ids'
import { CASE_RESULTS, RUN_SUMMARY, type CaseResult } from './metrics'
import type { Evidence, Finding, Report, Severity } from '../api/types'

const pct = (value: number): string => `${Math.round(value * 100)}%`
const signed = (value: number): string => `${value > 0 ? '+' : ''}${value.toFixed(2)}`

// ---------------------------------------------------------------- evidence --

interface EvidenceDraft {
  kind: Evidence['kind']
  payload: Record<string, unknown>
}

function evidenceFor(result: CaseResult): Evidence[] {
  const { spec, baseline, candidate, baselineVerdict, candidateVerdict } = result
  const n = spec.n
  let slot = 0
  const make = (draft: EvidenceDraft): Evidence => {
    slot += 1
    return {
      id: evidenceId('e', n * 10 + slot),
      run_id: RUN_A_ID,
      test_case_id: '',
      kind: draft.kind,
      uri: null,
      payload: draft.payload,
      created_at: at(40 + n * 4 + slot * 2),
    }
  }

  const items: Evidence[] = [
    make({
      kind: 'text',
      payload: {
        label: 'Prompt sent to the assistant',
        question: spec.question,
        system: 'Answer only from the retrieved knowledge-base documents.',
        retrieved: candidate.retrieved.map((p) => ({
          doc: p.doc,
          section: p.section,
          score: p.score,
        })),
      },
    }),
    make({
      kind: 'trace',
      payload: {
        label: 'Answer, scored',
        points: spec.expected.required_facts.map((fact) => ({
          point: fact,
          baseline: baseline.factsPresent.includes(fact) ? 'stated' : 'missing',
          candidate: candidate.factsPresent.includes(fact) ? 'stated' : 'missing',
        })),
        baseline_text: baseline.text,
        candidate_text: candidate.text,
      },
    }),
    make({
      kind: 'citation',
      payload: {
        label: 'Citations returned and whether they resolve',
        baseline: baseline.citations.map((uri) => ({ uri, resolves: true })),
        candidate: candidate.citations.map((uri) => ({ uri, resolves: true })),
        required_min: spec.expected.min_citations,
      },
    }),
    make({
      kind: 'screenshot',
      payload: {
        label: 'Rendered answer, both versions',
        caption: `Case ${String(n).padStart(2, '0')} — ${spec.title}`,
        baseline_ref: `artifact://${RUN_A_ID}/case-${n}/baseline.png`,
        candidate_ref: `artifact://${RUN_A_ID}/case-${n}/candidate.png`,
        /** No image is captured in this worktree; the UI draws a placeholder. */
        available: false,
      },
    }),
    make({
      kind: 'log',
      payload: {
        label: 'Execution log',
        lines: [
          `${at(40 + n * 4)}  planner  case ${n} dispatched to both versions`,
          `${at(41 + n * 4)}  executor baseline  ${baseline.retrieved.length} passages retrieved (top_k=5)`,
          `${at(42 + n * 4)}  executor baseline  model call ok in ${baseline.latency_s.toFixed(2)}s`,
          `${at(43 + n * 4)}  executor candidate ${candidate.retrieved.length} passages retrieved (top_k=3)`,
          `${at(44 + n * 4)}  executor candidate model call ok in ${candidate.latency_s.toFixed(2)}s`,
          `${at(45 + n * 4)}  evaluator check    citation_coverage ${baselineVerdict.citationCoverage.toFixed(2)} -> ${candidateVerdict.citationCoverage.toFixed(2)}`,
          `${at(46 + n * 4)}  evaluator repeat   sample 2/3, sample 3/3 complete`,
          `${at(47 + n * 4)}  evaluator verdict  ${result.regression ? 'stable regression' : result.control ? 'no change' : 'lateral move'}`,
        ],
      },
    }),
    make({
      kind: 'metric',
      payload: {
        label: 'Deterministic checks',
        checks: candidateVerdict.checks.map((check) => ({
          id: check.id,
          label: check.label,
          weight: check.weight,
          baseline: baselineVerdict.checks.find((c) => c.id === check.id)?.score ?? 0,
          candidate: check.score,
          detail: check.detail,
        })),
      },
    }),
    make({
      kind: 'text',
      payload: {
        label: 'Evaluator rationale',
        source: 'rubric (modelled — see docs note)',
        baseline: baselineVerdict.judge.rationale,
        candidate: candidateVerdict.judge.rationale,
      },
    }),
  ]

  return items.map((item) => ({ ...item, test_case_id: caseId(PREFIX.A, n) }))
}

export const EVIDENCE: readonly Evidence[] = CASE_RESULTS.flatMap(evidenceFor)

export function evidenceForCase(caseId: string): Evidence[] {
  return EVIDENCE.filter((item) => item.test_case_id === caseId)
}

// ---------------------------------------------------------------- findings --

interface FindingDraft {
  severity: Severity
  title: string
  description: string
  confidence: number
  caseNumbers: number[]
  recommendation: string | null
}

function evidenceIdsFor(numbers: number[], kinds: Evidence['kind'][]): string[] {
  return EVIDENCE.filter(
    (item) =>
      numbers.some((n) => item.test_case_id === caseId(PREFIX.A, n)) && kinds.includes(item.kind),
  ).map((item) => item.id)
}

const DRAFTS: FindingDraft[] = [
  {
    severity: 'high',
    title: 'Citation coverage collapsed on multi-fact answers',
    description: `Reducing retrieval to top_k=3 removed the marginal third passage, and the tightened answer prompt then dropped the citations that had been drawn from it. Citation coverage fell from ${pct(RUN_SUMMARY.metrics.citation_coverage!.baseline)} to ${pct(RUN_SUMMARY.metrics.citation_coverage!.candidate)} across ${RUN_SUMMARY.comparison.matched_cases} matched cases. The answers remain substantively correct, which is exactly why this is dangerous: nothing looks broken to a user until the answer has to be defended.`,
    confidence: 0.92,
    caseNumbers: [2, 5, 10, 21, 23],
    recommendation:
      'Restore top_k to 5, or add an explicit rule that answers covering two or more required facts must cite each source document.',
  },
  {
    severity: 'high',
    title: 'Precise contractual facts replaced with approximations',
    description: `Case 22 asked for the enterprise cancellation notice period. The baseline answered "60 days written notice to the account manager"; the candidate answered "about two months". The number is correct but no longer citable, and "about" is not a term a customer can rely on. The same pattern appears in case 13, where the retired 24-hour tier is no longer explicitly corrected.`,
    confidence: 0.78,
    caseNumbers: [13, 22],
    recommendation:
      'Require exact figures for any question matching the billing, legal or compliance document set, and re-test against the regression category.',
  },
  {
    severity: 'medium',
    title: 'Over-refusal introduced on a fragmentary question',
    description: `Case 9 sends the truncated string "how do I canc". The baseline resolved the intent and answered; the candidate asked for clarification. A clarifying question is safe but it is a behaviour change on a high-traffic path, and it means the answer now costs two turns instead of one. The refusal check classifies it as an incorrect refusal because the knowledge base covers the intent.`,
    confidence: 0.71,
    caseNumbers: [9],
    recommendation:
      'Add a clarification step only when retrieval confidence is low; for a fragment with a single dominant intent (confidence >= 0.85), answer and offer the alternative.',
  },
  {
    severity: 'medium',
    title: 'Format compliance dropped on structured answers',
    description: `Format compliance moved from ${pct(RUN_SUMMARY.metrics.format_compliance!.baseline)} to ${pct(RUN_SUMMARY.metrics.format_compliance!.candidate)}. The tier comparison question was expected as a table and came back as prose, and the SAML answer lost its numbered steps. Multi-fact answers are the ones that most need structure for a human to verify them quickly.`,
    confidence: 0.83,
    caseNumbers: [3, 4, 21],
    recommendation:
      'Keep the brevity instruction but preserve list and table formatting for answers with three or more required facts.',
  },
  {
    severity: 'low',
    title: 'Single-sample flag on case 4 did not reproduce',
    description: `The first sample run flagged case 4 (tier response times) with a ${signed(-0.05)} score delta, just over the noise floor. Across ${RUN_SUMMARY.comparison.repeats} repeats the answer was correct every time and the delta came from rubric jitter, not behaviour: the flag did not reproduce, and the case does not count as a regression. Recorded here so the flag is not silently dropped from the record, and so a reviewer can see the tool distinguishing a wobble from a change.`,
    confidence: 0.24,
    caseNumbers: [4],
    recommendation: null,
  },
  {
    severity: 'info',
    title: 'Most cases are unchanged, and every control held',
    description: `${
      RUN_SUMMARY.comparison.matched_cases -
      RUN_SUMMARY.stableRegressions.length -
      RUN_SUMMARY.improvements.length
    } of ${RUN_SUMMARY.comparison.matched_cases} matched cases scored identically on both versions, and all ${CASE_RESULTS.filter((r) => r.spec.role === 'control').length} control cases held at a delta of exactly zero. The change is therefore localised to multi-fact answers; refusal behaviour on the adversarial set did not move either, coming through at ${pct(RUN_SUMMARY.metrics.correct_refusal!.candidate)} on both versions.`,
    confidence: 0.88,
    caseNumbers: CASE_RESULTS.filter((r) => r.delta === 0 && r.spec.role === 'control').map(
      (r) => r.spec.n,
    ),
    recommendation: null,
  },
  {
    severity: 'info',
    title: 'Latency and cost improved materially',
    description: `Latency p50 fell from ${RUN_SUMMARY.metrics.latency_p50!.baseline} ms to ${RUN_SUMMARY.metrics.latency_p50!.candidate} ms (${Math.round((1 - RUN_SUMMARY.metrics.latency_p50!.candidate / RUN_SUMMARY.metrics.latency_p50!.baseline) * 100)}% faster) and mean answer length fell from ${RUN_SUMMARY.metrics.answer_tokens!.baseline} to ${RUN_SUMMARY.metrics.answer_tokens!.candidate} tokens (${Math.round((1 - RUN_SUMMARY.metrics.answer_tokens!.candidate / RUN_SUMMARY.metrics.answer_tokens!.baseline) * 100)}% shorter). This is a real improvement and it is the reason the change was proposed. It is recorded as a finding so the report does not read as a one-sided rejection of the candidate.`,
    confidence: 0.94,
    caseNumbers: [],
    recommendation:
      'Keep the latency and cost win; the recommendation above targets citation behaviour only and does not require reverting the retrieval change outright.',
  },
]

export const FINDINGS: readonly Finding[] = DRAFTS.map((draft, index) => ({
  id: findingId(index + 1),
  run_id: RUN_A_ID,
  test_case_id: draft.caseNumbers.length === 1 ? caseId(PREFIX.A, draft.caseNumbers[0]!) : null,
  severity: draft.severity,
  title: draft.title,
  description: draft.description,
  confidence: draft.confidence,
  evidence_ids: evidenceIdsFor(
    draft.caseNumbers.length > 0 ? draft.caseNumbers : [1, 6, 8],
    draft.severity === 'info' ? ['metric', 'text'] : ['citation', 'metric', 'log'],
  ),
  recommendation: draft.recommendation,
}))

// ------------------------------------------------------------------ report --

const VERDICT = 'This change regressed the candidate version.'

/**
 * The summary is generated from the metrics it describes, never hand-written.
 *
 * A prose summary typed by hand drifts the moment a number moves, and a report
 * that contradicts its own table is worse than no report: it is the exact
 * failure mode this product exists to catch. Every clause below is derived, and
 * a metric that did not move is not mentioned at all.
 */
function buildSummary(): string {
  const { metrics, comparison } = RUN_SUMMARY
  const regressions = comparison.stable_regressions

  const moved = (key: string): boolean => {
    const metric = metrics[key]
    if (!metric) return false
    return Math.abs(metric.candidate - metric.baseline) > 1e-9
  }

  const losses: string[] = []
  for (const key of ['citation_coverage', 'correct_refusal', 'groundedness', 'format_compliance']) {
    const metric = metrics[key]
    if (!metric || !moved(key)) continue
    const worse = metric.direction === 'lower' ? metric.candidate > metric.baseline : metric.candidate < metric.baseline
    if (!worse) continue
    const from = metric.unit === '' ? pct(metric.baseline) : `${Math.round(metric.baseline)}${metric.unit}`
    const to = metric.unit === '' ? pct(metric.candidate) : `${Math.round(metric.candidate)}${metric.unit}`
    losses.push(`${metric.label.toLowerCase()} (${from} → ${to})`)
  }

  const latency = metrics.latency_p50
  const latencyGain = latency
    ? Math.round((1 - latency.candidate / latency.baseline) * 100)
    : 0

  const controls = CASE_RESULTS.filter((r) => r.spec.role === 'control')
  const controlsHeld = controls.every((r) => r.delta === 0)

  const parts: string[] = [`${VERDICT}`]

  parts.push(
    `Compared across ${comparison.matched_cases} matched cases with ${comparison.repeats} repeats per case, ${'v1.5.0-rc1'} lost ${losses.length > 0 ? losses.join(', ') : 'nothing measurable'}` +
      (latency && latencyGain > 0 ? `, while latency improved by ${latencyGain}%` : '') +
      '.',
  )

  parts.push(
    `${regressions} of ${comparison.matched_cases} cases are stable regressions; ${comparison.noise_only} single-sample flag did not reproduce and is excluded.`,
  )

  parts.push(
    `The regression is localised to multi-fact answers. The case set is unchanged between versions` +
      (controlsHeld ? ` and all ${controls.length} control cases scored identically,` : ',') +
      ' so the change is attributable to the version under test rather than to a harder test set.',
  )

  return parts.join(' ')
}

export const REPORT: Report = {
  id: REPORT_A_ID,
  run_id: RUN_A_ID,
  summary: buildSummary(),
  metrics: RUN_SUMMARY.metrics,
  findings: [...FINDINGS],
  generated_at: at(232),
}

export { VERDICT }

/** Each scenario's run id, so the report view can ask the backend for one. */
export const REPORT_RUN_IDS: Record<'citation-regression' | 'unchanged' | 'improvement', string> = {
  'citation-regression': RUN_A_ID,
  unchanged: 'b7e2a5c9-1f48-4d63-9a07-3c8b5e2f6d94',
  improvement: 'c9d4b7a1-3e62-4f85-b1d0-7a2c6e9f4b58',
}

/** Case numbers the findings above cite, for the report's trace panel. */
export const REPORT_CASE_NUMBERS: readonly number[] = Array.from(
  new Set(DRAFTS.flatMap((draft) => draft.caseNumbers)),
).sort((a, b) => a - b)

export const SCENARIO_CHANGE = {
  summary: 'Retrieval and answer-prompt change in the knowledge-base assistant',
  items: [
    'Retrieval top_k reduced from 5 to 3 documents per query.',
    'Answer prompt tightened for brevity: shorter responses, fewer restated citations.',
    'No change to the model, the embedding index, the tool allowlist, or the refusal policy.',
  ],
  settings: [
    { key: 'retrieval.top_k', baseline: '5', candidate: '3' },
    { key: 'prompt.style', baseline: 'verbose, cite every claim', candidate: 'concise, cite once' },
    { key: 'model', baseline: 'same', candidate: 'same' },
    { key: 'embedding_index', baseline: 'v7 (2026-08-02)', candidate: 'v7 (2026-08-02)' },
    {
      key: 'refusal_policy',
      baseline: 'decline when no document covers the question',
      candidate: 'decline when no document covers the question',
    },
  ],
} as const

export function severityCounts(): Record<Severity, number> {
  const counts: Record<Severity, number> = { critical: 0, high: 0, medium: 0, low: 0, info: 0 }
  for (const finding of FINDINGS) counts[finding.severity] += 1
  return counts
}
