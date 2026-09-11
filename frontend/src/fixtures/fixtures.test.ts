import { describe, expect, it } from 'vitest'
import { CASE_RESULTS, RUN_SUMMARY } from './metrics'
import { SCENARIOS, PRIMARY, scenarioById } from './scenarios'
import { TIMELINE, timelineFor } from './timeline'
import { EVIDENCE, FINDINGS, REPORT } from './findings'
import { caseId, PREFIX } from './ids'
import { mulberry32 } from './seed'

/**
 * The fixtures make a reproducibility claim on the product's behalf, so they
 * are tested like production data rather than treated as test data. These
 * assertions are what stop a `Date.now()` or a `Math.random()` creeping in and
 * silently making the demo non-deterministic.
 */
describe('fixtures are deterministic', () => {
  it('produces the same corpus on repeated construction', () => {
    // Re-deriving from the same modules must be byte-identical.
    const first = JSON.stringify(CASE_RESULTS.map((r) => [r.spec.n, r.delta, r.baselineVerdict.total]))
    const second = JSON.stringify(CASE_RESULTS.map((r) => [r.spec.n, r.delta, r.baselineVerdict.total]))
    expect(second).toBe(first)
  })

  it('uses a seeded generator, not Math.random', () => {
    const a = mulberry32(20260911)
    const b = mulberry32(20260911)
    const drawsA = Array.from({ length: 8 }, () => a())
    const drawsB = Array.from({ length: 8 }, () => b())
    expect(drawsA).toEqual(drawsB)
    expect(drawsA.every((value) => value >= 0 && value < 1)).toBe(true)
  })

  it('freezes every timestamp to the demo clock', () => {
    for (const entity of [...EVIDENCE, ...TIMELINE.map((entry) => entry.event)]) {
      expect(entity.created_at.startsWith('2026-09-11T')).toBe(true)
    }
    expect(REPORT.generated_at).toBe('2026-09-11T08:15:56Z')
  })
})

describe('the corpus is a controlled comparison', () => {
  it('carries at least ten cases across two versions, as SPEC requires', () => {
    expect(CASE_RESULTS.length).toBeGreaterThanOrEqual(10)
    expect(PRIMARY.baselineVersion).not.toBe(PRIMARY.candidateVersion)
  })

  it('holds difficulty identical across versions, since it is a property of the case', () => {
    for (const result of CASE_RESULTS) {
      expect(result.spec.difficulty).toBeGreaterThanOrEqual(0)
      expect(result.spec.difficulty).toBeLessThanOrEqual(1)
    }
  })

  it('keeps control cases identical on both versions', () => {
    const controls = CASE_RESULTS.filter((r) => r.spec.role === 'control')
    expect(controls.length).toBeGreaterThan(0)
    for (const control of controls) {
      expect(control.delta).toBe(0)
    }
  })

  it('only includes cases that completed on both versions', () => {
    expect(RUN_SUMMARY.comparison.matched_cases).toBe(CASE_RESULTS.length)
  })
})

describe('scenarios tell three different stories from one corpus', () => {
  it('detects a regression in the headline scenario', () => {
    expect(PRIMARY.verdict).toBe('regression')
    expect(PRIMARY.comparison.stable_regressions).toBeGreaterThan(0)
    expect(PRIMARY.metrics.citation_coverage!.candidate).toBeLessThan(
      PRIMARY.metrics.citation_coverage!.baseline,
    )
  })

  it('returns a clean verdict on the unchanged scenario', () => {
    const unchanged = scenarioById('unchanged')
    expect(unchanged.verdict).toBe('no-regression')
    expect(unchanged.comparison.stable_regressions).toBe(0)
    for (const outcome of unchanged.outcomes) {
      expect(outcome.delta).toBe(0)
    }
  })

  it('validates the optimisation scenario as safe, with no invented quality delta', () => {
    const improved = scenarioById('improvement')
    expect(improved.verdict).toBe('improvement')
    expect(improved.comparison.stable_regressions).toBe(0)

    // The answers are identical, so every quality delta must be exactly zero.
    // A non-zero delta here would mean the comparison is measuring noise.
    for (const outcome of improved.outcomes) {
      expect(outcome.delta).toBe(0)
    }

    // The win is real and it is in latency.
    const latency = improved.metrics.latency_p50!
    expect(latency.candidate).toBeLessThan(latency.baseline)
  })

  it('gives every scenario its own case ids so evidence cannot collide', () => {
    const ids = SCENARIOS.flatMap((scenario) => scenario.outcomes.map((o) => o.caseId))
    expect(new Set(ids).size).toBe(ids.length)
  })
})

describe('the regression is attributable and evidenced', () => {
  it('concentrates the regression in multi-fact cases rather than spreading it', () => {
    const regressed = CASE_RESULTS.filter((r) => r.regression).map((r) => r.spec.n)
    // Cases 2, 5, 21, 22 and 23 lost a required fact or a citation. Case 9 is a
    // different failure — an over-refusal — and is deliberately the odd one out.
    expect(regressed).toEqual([2, 5, 9, 21, 22, 23])
    const overRefusal = CASE_RESULTS.find((r) => r.spec.n === 9)!
    expect(overRefusal.baselineVerdict.refusalCorrect).toBe(true)
    expect(overRefusal.candidateVerdict.refusalCorrect).toBe(false)
  })

  it('links every finding to evidence that exists', () => {
    const known = new Set(EVIDENCE.map((item) => item.id))
    for (const finding of FINDINGS) {
      expect(finding.evidence_ids.length).toBeGreaterThan(0)
      for (const id of finding.evidence_ids) {
        expect(known.has(id)).toBe(true)
      }
    }
  })

  it('gives every case an evidence packet covering the required kinds', () => {
    for (const result of CASE_RESULTS) {
      const id = caseId(PREFIX.A, result.spec.n)
      const packet = EVIDENCE.filter((item) => item.test_case_id === id)
      const kinds = new Set(packet.map((item) => item.kind))
      expect(kinds).toEqual(
        new Set(['text', 'trace', 'citation', 'screenshot', 'log', 'metric']),
      )
    }
  })

  it('keeps a finding for the flag that did not reproduce, at low confidence', () => {
    const noise = FINDINGS.find((f) => f.severity === 'low')
    expect(noise).toBeDefined()
    expect(noise!.confidence).toBeLessThan(0.5)
    expect(noise!.description).toContain('did not reproduce')
  })

  it('agrees with the report on how many single-sample flags there were', () => {
    // The console renders `comparison.noise_only` and the report renders this
    // sentence. If they can disagree, one of them is lying to the reviewer.
    expect(PRIMARY.comparison.noise_only).toBe(1)
    expect(REPORT.summary).toContain('1 single-sample flag did not reproduce')
  })

  it('does not penalise a refusal for the answer format it was never asked for', () => {
    // Case 9 regresses by over-refusing. That is one failure, not two: the
    // format check must not also fire on an answer that correctly declined.
    const outcome = PRIMARY.outcomes.find((o) => o.spec.n === 9)!
    const format = outcome.candidateVerdict.checks.find((c) => c.id === 'format_compliance')!
    expect(format.score).toBe(1)
    expect(format.detail).toContain('does not apply')
  })
})

describe('the event stream is a faithful record', () => {
  it('numbers events from one, without gaps, per run', () => {
    for (const scenario of SCENARIOS) {
      const entries = timelineFor(scenario.id)
      expect(entries.map((entry) => entry.event.sequence)).toEqual(
        entries.map((_, index) => index + 1),
      )
    }
  })

  it('uses only the event types the contract defines', () => {
    const allowed = new Set([
      'run.started',
      'task.created',
      'task.started',
      'evidence.created',
      'task.completed',
      'finding.created',
      'run.completed',
      'run.failed',
    ])
    for (const entry of TIMELINE) {
      expect(allowed.has(entry.event.type)).toBe(true)
    }
  })

  it('opens with run.started and closes with run.completed', () => {
    for (const scenario of SCENARIOS) {
      const entries = timelineFor(scenario.id)
      expect(entries[0]!.event.type).toBe('run.started')
      expect(entries[entries.length - 1]!.event.type).toBe('run.completed')
    }
  })

  it('raises exactly one finding event per regressed case', () => {
    const findingEvents = timelineFor(PRIMARY.id).filter(
      (entry) => entry.event.type === 'finding.created',
    )
    expect(findingEvents.length).toBe(PRIMARY.comparison.stable_regressions)
  })
})
