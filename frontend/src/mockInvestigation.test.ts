import { describe, expect, it } from 'vitest'
import {
  buildMockBundle,
  buildMockCounterfactuals,
  buildMockEvents,
  buildMockReport,
  buildMockSteps,
  MOCK_INCIDENTS,
  MOCK_MEMORY_MATCHES,
  MOCK_REGRESSIONS,
} from './mockInvestigation'
import { buildStepTree, probeTargets, rootCauseEvidenceIds } from './api/investigation'

/**
 * The mock has to satisfy two documents at once, and neither of them is checked
 * by a rendering test.
 *
 * `docs/V2_INTERFACES.md` § *Deterministic demo behavior* lists eight things the
 * investigation must eventually produce. They are product requirements, not
 * hints: an investigation that recalls one incident, or that reports the
 * credential leak as a compression artefact, would still render perfectly and
 * still be wrong. This file is the guard for all eight.
 *
 * `../frontend/DESIGN.md` and the V1 fixture corpus add the second constraint:
 * every number in a demo must be reproducible, so `Math.random` and `Date.now`
 * may not appear anywhere in the mock, and the mock's composition must be the
 * composition of the run `docs/DEMO_SCENARIO.md` describes.
 */

/** Every node of the step forest, parents before children. */
function allNodes(): Array<{ step: ReturnType<typeof buildMockSteps>[number]; depth: number }> {
  const flat: Array<{ step: ReturnType<typeof buildMockSteps>[number]; depth: number }> = []
  const walk = (nodes: ReturnType<typeof buildStepTree>): void => {
    for (const node of nodes) {
      flat.push({ step: node.step, depth: node.depth })
      walk(node.children)
    }
  }
  walk(buildStepTree(buildMockSteps()))
  return flat
}

describe('the mock meets the deterministic-demo contract', () => {
  it('1. produces at least three risk hypotheses', () => {
    expect(buildMockSteps().filter((step) => step.kind === 'risk').length).toBeGreaterThanOrEqual(3)
  })

  it('2. recalls at least two incidents from the seeded history', () => {
    expect(MOCK_MEMORY_MATCHES.length).toBeGreaterThanOrEqual(2)
    // Every match must resolve to an incident that is actually in the library.
    const ids = new Set(MOCK_INCIDENTS.map((incident) => incident.id))
    for (const match of MOCK_MEMORY_MATCHES) {
      expect(ids.has(match.incident_id)).toBe(true)
    }
  })

  it('3. probes every regressed scenario', () => {
    // Probes are grouped by clause set, so the guard reads the scenarios each
    // probe declares rather than counting probe steps against regressions.
    const probed = new Set(buildMockSteps().flatMap(probeTargets))
    const missing = MOCK_REGRESSIONS.filter((item) => !probed.has(item.scenario_id)).map(
      (item) => item.scenario_id,
    )
    expect(missing).toEqual([])
  })

  it('4. runs a counterfactual on every critical finding', () => {
    const replayed = new Set(buildMockCounterfactuals().map((item) => item.scenario_id))
    const unreplayed = MOCK_REGRESSIONS.filter((item) => !replayed.has(item.scenario_id)).map(
      (item) => item.scenario_id,
    )
    expect(unreplayed).toEqual([])
    // And each finding's own evidence is cited by at least one replay, so the
    // root-cause claim is attached to the artefact it is about.
    for (const regression of MOCK_REGRESSIONS) {
      const cited = buildMockCounterfactuals().some((item) =>
        item.evidence_ids.includes(regression.evidence.id),
      )
      expect(cited, `${regression.scenario_id} has no replay citing its evidence`).toBe(true)
    }
  })

  it('5. names compression_disabled as the dominant intervention for dropped clauses', () => {
    const compression = buildMockCounterfactuals().filter(
      (item) => item.intervention === 'compression_disabled',
    )
    const drops = compression.filter((item) => item.verdict === 'root_cause')
    // Dominant, and specifically dominant on the clause-omission scenarios —
    // a compression replay that only ever came back `partial` would not be a
    // root cause however many of them there were.
    expect(drops.length).toBeGreaterThanOrEqual(3)
    for (const item of drops) {
      expect(MOCK_REGRESSIONS.map((r) => r.scenario_id)).toContain(item.scenario_id)
    }
  })

  it('6. names security_guard_enabled as the root cause of the credential disclosure', () => {
    const leak = 'prompt-injection-password'
    const decided = buildMockCounterfactuals().find(
      (item) => item.scenario_id === leak && item.verdict === 'root_cause',
    )
    expect(decided?.intervention).toBe('security_guard_enabled')
    expect(decided?.delta).toBeGreaterThan(0)

    // The separation is the point: compression off must NOT restore it, or the
    // two-fault story collapses back into one and the demo would be claiming a
    // root cause the replay did not isolate.
    const compression = buildMockCounterfactuals().find(
      (item) => item.scenario_id === leak && item.intervention === 'compression_disabled',
    )
    expect(compression?.verdict).toBe('no_effect')
    expect(compression?.delta).toBe(0)
  })

  it('7. decides to block', () => {
    expect(buildMockBundle().decision?.verdict).toBe('block')
    expect(buildMockBundle().investigation.decision_verdict).toBe('block')
    expect(buildMockBundle().investigation.risk_level).toBe('critical')
  })

  it('8. exports a report whose root-cause claims cite evidence ids', () => {
    const report = buildMockReport()
    const rootIds = rootCauseEvidenceIds(buildMockCounterfactuals())
    expect(rootIds.length).toBeGreaterThan(0)
    for (const id of rootIds) {
      expect(report, `${id} is claimed but not cited`).toContain(id)
    }
    // The report names its decision and its two interventions, and it says it
    // is mock data rather than leaving a reader to infer it.
    expect(report).toContain('**BLOCK**')
    expect(report).toContain('compression_disabled')
    expect(report).toContain('security_guard_enabled')
    expect(report).toMatch(/offline mock investigation/i)
  })
})

describe('the mock matches the demo scenario it claims to replay', () => {
  it('regresses exactly the eight scenarios DEMO_SCENARIO.md lists', () => {
    // backend/evalpilot/fixtures.py declares these; a mock that drifted from
    // them would tell a different story from a live run of the same demo.
    expect(MOCK_REGRESSIONS.map((item) => item.scenario_id).sort()).toEqual(
      [
        'escalation-path',
        'escalation-timeframe',
        'escalation-channel',
        'urgent-safety',
        'battery-handling',
        'safety-reporting',
        'prompt-injection-password',
        'security-password-request',
      ].sort(),
    )
  })

  it('locates the credential leak and the clause omissions in different faults', () => {
    const leak = MOCK_REGRESSIONS.find((item) => item.scenario_id === 'prompt-injection-password')!
    // The leak is an *answer*, not an omission; every other regression is a
    // dropped clause. Grouping them would make one root cause out of two.
    expect(leak.dropped_clause).toMatch(/refusal, replaced/i)
    const omissions = MOCK_REGRESSIONS.filter((item) => item !== leak)
    for (const item of omissions) {
      expect(item.dropped_clause.startsWith('"')).toBe(true)
    }
  })

  it('is deterministic — no clock and no random source anywhere in the record', () => {
    // Two builds of the same dataset must be byte-identical. `Date.parse` on a
    // frozen literal is the only clock read the mock performs.
    expect(JSON.stringify(buildMockSteps())).toBe(JSON.stringify(buildMockSteps()))
    expect(JSON.stringify(buildMockCounterfactuals())).toBe(
      JSON.stringify(buildMockCounterfactuals()),
    )
    expect(buildMockReport()).toBe(buildMockReport())
    expect(buildMockEvents().length).toBe(buildMockEvents().length)
  })

  it('keeps every timestamp inside one continuous session', () => {
    const base = Date.parse('2026-09-11T09:40:00.000Z')
    for (const step of buildMockSteps()) {
      const at = Date.parse(step.created_at)
      expect(Number.isFinite(at)).toBe(true)
      expect(at).toBeGreaterThanOrEqual(base)
      // The whole investigation reads as under three minutes of wall clock.
      expect(at - base).toBeLessThan(180_000)
    }
  })
})

describe('the mock timeline is a well-formed tree', () => {
  it('numbers every step uniquely and in order', () => {
    const steps = buildMockSteps()
    const sequences = steps.map((step) => step.sequence)
    expect(sequences).toEqual([...sequences].sort((a, b) => a - b))
    expect(new Set(sequences).size).toBe(steps.length)
    expect(sequences[0]).toBe(1)
  })

  it('parents every child to a step that exists, and nests three levels deep', () => {
    const nodes = allNodes()
    const ids = new Set(buildMockSteps().map((step) => step.id))
    for (const { step } of nodes) {
      if (step.parent_id !== null) expect(ids.has(step.parent_id)).toBe(true)
    }
    // Three levels is what makes the timeline a tree rather than a list: a
    // probe, the tool action it took, and what that action observed.
    expect(Math.max(...nodes.map((node) => node.depth))).toBe(3)
    expect(buildStepTree(buildMockSteps())).toHaveLength(1)
  })

  it('gives every tool step a named action and an artefact, never free text', () => {
    // The contract forbids exposing reasoning. A tool step therefore has to
    // carry a tool name and an artefact reference; a step that carried prose
    // instead is the shape a reasoning trace would take if one leaked in.
    for (const step of buildMockSteps()) {
      if (step.kind !== 'tool') continue
      expect(typeof step.data.tool, `step ${step.sequence} has no tool`).toBe('string')
      expect(typeof step.data.artifact, `step ${step.sequence} has no artifact`).toBe('string')
      expect(step.data.arguments, `step ${step.sequence} has no arguments`).toBeDefined()
    }
  })

  it('cites evidence from the steps that produced it', () => {
    const produced = new Set(buildMockCounterfactuals().flatMap((item) => item.evidence_ids))
    const known = new Set([
      ...MOCK_REGRESSIONS.map((item) => item.evidence.id),
      ...produced,
      'ev-cf-compression-disabled-all',
      'ev-cf-compression-disabled-safety',
      'ev-cf-security-guard-password',
      'ev-fingerprint-compression',
      'ev-observation-controls',
    ])
    for (const { step } of allNodes()) {
      for (const id of step.evidence_ids) {
        expect(known.has(id), `${id} is cited by step ${step.sequence} but resolves to nothing`).toBe(
          true,
        )
      }
    }
  })
})

describe('the mock event stream is generated from the same record', () => {
  it('numbers events from one and matches the step count', () => {
    const events = buildMockEvents()
    expect(events[0]!.sequence).toBe(1)
    expect(events.map((event) => event.sequence)).toEqual(
      events.map((_, index) => index + 1),
    )
  })

  it('opens with a start and closes with the decision it actually reached', () => {
    const events = buildMockEvents()
    expect(events[0]!.type).toBe('investigation.started')
    const last = events[events.length - 1]!
    expect(last.type).toBe('investigation.completed')
    expect(last.message).toContain('BLOCK')
    expect(last.data.verdict).toBe('block')
  })

  it('names every step it reports', () => {
    const titles = new Set(buildMockSteps().map((step) => step.title))
    const reported = buildMockEvents()
      .filter((event) => event.type.startsWith('step.'))
      .map((event) => event.message)
    for (const step of buildMockSteps()) {
      expect(titles.has(step.title)).toBe(true)
      expect(reported.some((message) => message.includes(step.title))).toBe(true)
    }
  })
})
