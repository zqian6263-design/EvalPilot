import { describe, expect, it } from 'vitest'
import { normalizeRunDetail } from './httpTransport'
import { buildLiveEvaluation, pairCases, scenarioIdOf } from './evaluation'
import type { RunDetail } from './transport'
import type { Evidence, Finding, Report, Run, TestCase } from './types'

/**
 * These tests are about one claim: the console shows what the backend sent
 * and nothing else. Every case below feeds the adapter a payload shaped the
 * way the running service shapes it and asserts that a field the adapter was
 * not given stays absent rather than becoming a plausible number.
 */

const RUN: Run = {
  id: '11111111-1111-4111-8111-111111111111',
  project_id: '22222222-2222-4222-8222-222222222222',
  baseline_version: 'v1.0-baseline',
  candidate_version: 'v1.1-candidate',
  status: 'completed',
  created_at: '2026-09-11T10:00:00Z',
  completed_at: '2026-09-11T10:00:04Z',
}

function testCase(over: Partial<TestCase> & Pick<TestCase, 'id' | 'version'>): TestCase {
  return {
    run_id: RUN.id,
    title: `${over.input?.['scenario_id'] ?? 'case'} [${over.version}]`,
    category: 'normal',
    input: { scenario_id: 'refund-window', question: 'How long can I return a product?' },
    expected: { must_include: ['30 days'] },
    difficulty: 0.15,
    status: 'passed',
    output: { answer: 'Within 30 days.', latency_ms: 200, citations: ['kb-refund-policy'] },
    ...over,
  }
}

const BASELINE_CASE = testCase({ id: 'b1', version: 'baseline' })
const CANDIDATE_CASE = testCase({
  id: 'c1',
  version: 'candidate',
  status: 'failed',
  difficulty: 0.45,
  output: { answer: 'Contact support.', latency_ms: 260, citations: [] },
})

function evidence(over: Partial<Evidence> & Pick<Evidence, 'id' | 'test_case_id'>): Evidence {
  return {
    run_id: RUN.id,
    kind: 'citation',
    uri: 'kb://kb-refund-policy',
    payload: { doc_id: 'kb-refund-policy' },
    created_at: '2026-09-11T10:00:02Z',
    ...over,
  }
}

describe('normalizeRunDetail flattens the live envelope', () => {
  it('unwraps {run, test_cases, evidence, counts}', () => {
    const flat = normalizeRunDetail({
      run: RUN,
      test_cases: [BASELINE_CASE, CANDIDATE_CASE],
      evidence: [evidence({ id: 'e1', test_case_id: 'b1' })],
      evidence_count: 78,
      finding_count: 3,
      event_count: 66,
    })

    expect(flat.id).toBe(RUN.id)
    expect(flat.status).toBe('completed')
    expect(flat.test_cases).toHaveLength(2)
    expect(flat.evidence).toHaveLength(1)
    // Counts are the backend's tally, not the array lengths.
    expect(flat.evidence_count).toBe(78)
    expect(flat.finding_count).toBe(3)
    expect(flat.event_count).toBe(66)
  })

  it('leaves an already-flat detail alone', () => {
    const detail: RunDetail = {
      ...RUN,
      test_cases: [BASELINE_CASE],
      evidence: [],
      evidence_count: 1,
      finding_count: 0,
      event_count: 2,
    }
    expect(normalizeRunDetail(detail)).toEqual(detail)
  })

  it('reports an omitted count as 0 rather than deriving it', () => {
    const flat = normalizeRunDetail({ run: RUN, test_cases: [BASELINE_CASE] })
    // One case is present but the backend claimed no count, so the count is 0.
    expect(flat.test_cases).toHaveLength(1)
    expect(flat.evidence_count).toBe(0)
    expect(flat.finding_count).toBe(0)
    expect(flat.event_count).toBe(0)
  })
})

describe('pairCases matches the two versions of one scenario', () => {
  it('pairs by scenario id and reads regression off the statuses', () => {
    const { rows, unmatched } = pairCases([BASELINE_CASE, CANDIDATE_CASE])
    expect(unmatched).toEqual([])
    expect(rows).toHaveLength(1)
    expect(rows[0]!.baselineStatus).toBe('passed')
    expect(rows[0]!.candidateStatus).toBe('failed')
    // Derived from two backend statuses, not from any score.
    expect(rows[0]!.regressed).toBe(true)
    expect(rows[0]!.latencyDeltaMs).toBe(60)
  })

  it('excludes a scenario present on only one version', () => {
    const orphan = testCase({ id: 'c2', version: 'candidate', input: { scenario_id: 'orphan' } })
    const { rows, unmatched } = pairCases([BASELINE_CASE, CANDIDATE_CASE, orphan])
    expect(rows).toHaveLength(1)
    expect(unmatched).toEqual(['orphan'])
  })

  it('reads the scenario id from the title when the input omits it', () => {
    const bare = testCase({
      id: 'b9',
      version: 'baseline',
      input: {},
      title: 'refund-window [baseline]',
    })
    expect(scenarioIdOf(bare)).toBe('refund-window')
  })

  it('reports no latency delta when a version recorded no latency', () => {
    const withoutLatency = testCase({
      id: 'c3',
      version: 'candidate',
      input: { scenario_id: 'refund-window' },
      output: { answer: 'x' },
    })
    const { rows } = pairCases([BASELINE_CASE, withoutLatency])
    expect(rows[0]!.latencyDeltaMs).toBeNull()
  })
})

describe('buildLiveEvaluation never invents a metric', () => {
  const detail: RunDetail = {
    ...RUN,
    test_cases: [BASELINE_CASE, CANDIDATE_CASE],
    evidence: [evidence({ id: 'e1', test_case_id: 'b1' })],
    evidence_count: 78,
    finding_count: 3,
    event_count: 66,
  }

  const report: Report = {
    id: '33333333-3333-4333-8333-333333333333',
    run_id: RUN.id,
    summary: '1 of 1 matched scenarios regressed.',
    metrics: {
      baseline_pass_rate: 1,
      candidate_pass_rate: 0,
      matched_scenarios: 1,
      regression_detected: true,
      regression_confirmed: true,
      regressed_scenarios: ['refund-window'],
      by_category: { normal: { total: 1, regressed: 1 } },
    },
    findings: [],
    generated_at: '2026-09-11T10:00:05Z',
  }

  it('converts only the pass-rate pair the backend actually reported', () => {
    const evaluation = buildLiveEvaluation({ detail, report, findings: [] })
    const byId = new Map(evaluation.metrics.map((row) => [row.id, row.value]))

    const taskSuccess = byId.get('task_success')
    expect(taskSuccess).not.toBeNull()
    expect(taskSuccess!.baseline).toBe(1)
    expect(taskSuccess!.candidate).toBe(0)
    // n is the backend's own denominator.
    expect(taskSuccess!.n).toBe(1)

    // Everything else is explicitly absent, never a fixture substitute.
    for (const id of ['citation_coverage', 'latency_p50', 'answer_tokens', 'groundedness']) {
      expect(byId.get(id)).toBeNull()
    }
    expect(evaluation.missingMetricIds).toContain('citation_coverage')
  })

  it('reports no metric at all when the report is unavailable', () => {
    const evaluation = buildLiveEvaluation({ detail, report: null, findings: [] })
    expect(evaluation.metrics.every((row) => row.value === null)).toBe(true)
    expect(evaluation.verdict).toBe('no-regression')
    expect(evaluation.summary).toBe('')
    expect(evaluation.sources.report).toBe(false)
  })

  it('carries the backend verdict and counts through unchanged', () => {
    const evaluation = buildLiveEvaluation({ detail, report, findings: [] })
    expect(evaluation.verdict).toBe('regression')
    expect(evaluation.counts).toEqual({ evidence: 78, findings: 3, events: 66, cases: 2 })
    expect(evaluation.cases[0]!.regressed).toBe(true)
  })

  it('resolves a finding to its evidence rows and names dangling ids', () => {
    const finding: Finding = {
      id: 'f1',
      run_id: RUN.id,
      test_case_id: CANDIDATE_CASE.id,
      severity: 'high',
      title: 'Regression in refund-window',
      description: 'dropped required content',
      confidence: 0.85,
      evidence_ids: ['e1', 'missing-id'],
      recommendation: null,
    }
    const evaluation = buildLiveEvaluation({ detail, report, findings: [finding] })
    expect(evaluation.findings).toHaveLength(1)

    // The view resolves links through the detail; a dangling id must surface.
    const index = new Map(evaluation.detail.evidence.map((item) => [item.id, item]))
    const resolved = finding.evidence_ids.filter((id) => index.has(id))
    const dangling = finding.evidence_ids.filter((id) => !index.has(id))
    expect(resolved).toEqual(['e1'])
    expect(dangling).toEqual(['missing-id'])
  })
})
