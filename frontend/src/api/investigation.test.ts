import { describe, expect, it } from 'vitest'
import {
  breakEvenIntervention,
  buildStepTree,
  citedEvidenceIds,
  flattenStepTree,
  groupCounterfactuals,
  isInvestigationTerminal,
  normalizeCounterfactual,
  normalizeDecision,
  normalizeIncidentLibrary,
  normalizeInvestigation,
  normalizeInvestigationBundle,
  normalizeInvestigationEvent,
  normalizeMemoryMatch,
  normalizeStep,
  probeTargets,
  reportUrl,
  riskRank,
  riskSteps,
  rootCauseEvidenceIds,
  type CounterfactualExperiment,
  type InvestigationBundlePayload,
  type InvestigationStep,
  type InvestigationTransportInfo,
} from './investigation'
import { HttpInvestigationTransport } from '../httpInvestigationTransport'
import { MockInvestigationTransport } from '../mockInvestigationTransport'
/**
 * The V2 adapter is where a payload the contract leaves open gets narrowed into
 * something the workspace can render without lying about it. These tests pin the
 * four decisions that do that work:
 *
 *   1. an envelope and a flat bundle both normalise, because the contract fixes
 *      the fields but not the wrapper;
 *   2. a missing field degrades to an absence, never to a plausible value —
 *      including an unreadable risk level, which must not become "low";
 *   3. a `delta` the service omitted is read from the two scores it did send;
 *   4. the mock has a *lifecycle*, so the workspace's start-and-follow path is
 *      reachable offline.
 */

const RUN_ID = 'a4f1c8e2-7d35-4b90-8e21-5f6a9c3d0b47'

function step(over: Partial<InvestigationStep> = {}): InvestigationStep {
  return {
    id: 'step-1',
    investigation_id: 'inv-1',
    parent_id: null,
    sequence: 1,
    kind: 'risk',
    title: 'a hypothesis',
    status: 'completed',
    detail: 'because',
    data: {},
    evidence_ids: [],
    created_at: '2026-09-11T09:40:00Z',
    completed_at: '2026-09-11T09:40:05Z',
    ...over,
  }
}

describe('normalizeInvestigationBundle', () => {
  // Deliberately lean payloads. The point is the adapter's behaviour on a
  // response that carries only what the contract requires, so these fixtures
  // are typed as `never`-checked inputs rather than dressed up as complete
  // records the service might not send.
  const flat = {
    investigation: { id: 'inv-1', run_id: RUN_ID, objective: 'ship?', status: 'completed' },
    steps: [{ ...step(), sequence: 2 }, { ...step(), id: 'step-2', sequence: 1 }],
    memory_matches: [{ incident_id: 'ESC-2214', score: 0.87 }],
    counterfactuals: [],
    decision: null,
  } as unknown as InvestigationBundlePayload

  it('reads a flat bundle', () => {
    const bundle = normalizeInvestigationBundle(flat)
    expect(bundle.investigation.id).toBe('inv-1')
    expect(bundle.investigation.run_id).toBe(RUN_ID)
    expect(bundle.steps).toHaveLength(2)
    expect(bundle.memory_matches[0]!.incident_id).toBe('ESC-2214')
    expect(bundle.decision).toBeNull()
  })

  it('reads the same bundle behind an envelope', () => {
    const bundle = normalizeInvestigationBundle({ ...flat })
    // Detection, not layout: a backend that starts wrapping the bundle keeps
    // working unchanged, the way `GET /runs/{id}` already wraps the run.
    expect(bundle.investigation.id).toBe('inv-1')
    expect(bundle.steps).toHaveLength(2)
  })

  it('turns absent arrays into empty ones rather than throwing', () => {
    const bundle = normalizeInvestigationBundle({ investigation: { id: 'inv-1' } } as never)
    expect(bundle.steps).toEqual([])
    expect(bundle.memory_matches).toEqual([])
    expect(bundle.counterfactuals).toEqual([])
    expect(bundle.decision).toBeNull()
  })

  it('reads a decision that the service sent', () => {
    const bundle = normalizeInvestigationBundle({
      ...flat,
      decision: {
        verdict: 'block',
        risk_level: 'critical',
        summary: 'do not ship',
        blocking_findings: ['ev-1', 'ev-2'],
        recommended_actions: ['roll back'],
        confidence: 0.94,
        generated_at: '2026-09-11T09:40:52Z',
      },
    })
    expect(bundle.decision?.verdict).toBe('block')
    expect(bundle.decision?.blocking_findings).toEqual(['ev-1', 'ev-2'])
    expect(bundle.decision?.confidence).toBe(0.94)
  })
})

describe('normalisation refuses to invent a value', () => {
  it('ranks an unreadable risk level worst, not best', () => {
    // A level this build cannot read must never be the reason a release is
    // waved through, so the fallback is the top of the scale.
    expect(riskRank('low')).toBe(0)
    expect(riskRank('critical')).toBe(3)
    expect(riskRank('catastrophic' as never)).toBe(4)
  })

  it('treats an unreadable verdict as a block', () => {
    expect(normalizeDecision({ verdict: 'perhaps' })?.verdict).toBe('block')
    expect(normalizeInvestigation({ id: 'i', decision_verdict: '' }).decision_verdict).toBe('block')
  })

  it('normalises a bare incident library without matches', () => {
    const library = normalizeIncidentLibrary({
      incidents: [{ id: 'INC-1', title: 't', symptoms: ['s'], tags: ['tag'], guard_scenario_id: null }],
    })
    expect(library.incidents).toHaveLength(1)
    // `null`, not `[]`: no query was made, so no search happened, and reporting
    // an empty match list would be reporting a search that never ran.
    expect(library.matches).toBeNull()
  })

  it('defaults a step parent to null and an event type to a string', () => {
    expect(normalizeStep({ id: 's' }).parent_id).toBeNull()
    expect(normalizeStep({ id: 's' }).evidence_ids).toEqual([])
    const event = normalizeInvestigationEvent({ sequence: 3, type: 'step.completed' })
    expect(event.sequence).toBe(3)
    expect(event.type).toBe('step.completed')
    expect(event.data).toEqual({})
  })

  it('reads a memory match score as a number and a missing one as zero', () => {
    expect(normalizeMemoryMatch({ incident_id: 'x', score: 0.5 }).score).toBe(0.5)
    expect(normalizeMemoryMatch({ incident_id: 'x' }).score).toBe(0)
  })
})

describe('normalizeCounterfactual', () => {
  it('reads delta from the two scores when the service omitted it', () => {
    const experiment = normalizeCounterfactual({
      id: 'cf-1',
      scenario_id: 'escalation-path',
      intervention: 'compression_disabled',
      original_score: 0.6,
      counterfactual_score: 1,
    })
    expect(experiment.delta).toBeCloseTo(0.4, 6)
  })

  it('prefers a delta the service sent', () => {
    const experiment = normalizeCounterfactual({
      id: 'cf-1',
      original_score: 0.6,
      counterfactual_score: 1,
      delta: 0.35,
    })
    expect(experiment.delta).toBe(0.35)
  })

  it('does not claim a delta when a score is absent', () => {
    const experiment = normalizeCounterfactual({ id: 'cf-1', original_score: 0.6 })
    expect(experiment.delta).toBe(0)
  })

  it('defaults an unreadable verdict to inconclusive, not root cause', () => {
    expect(normalizeCounterfactual({ scenario_id: 's' }).verdict).toBe('inconclusive')
    expect(normalizeCounterfactual({ scenario_id: 's', verdict: 'sort-of' }).verdict).toBe('sort-of')
  })
})

describe('buildStepTree', () => {
  it('nests children and orders by sequence', () => {
    const tree = buildStepTree([
      step({ id: 'child', parent_id: 'root', sequence: 3 }),
      step({ id: 'root', sequence: 1 }),
      step({ id: 'sibling', parent_id: 'root', sequence: 2 }),
    ])
    expect(tree).toHaveLength(1)
    expect(tree[0]!.step.id).toBe('root')
    expect(tree[0]!.children.map((node) => node.step.id)).toEqual(['sibling', 'child'])
    expect(tree[0]!.children[0]!.depth).toBe(1)
  })

  it('keeps a step whose parent is missing rather than dropping it', () => {
    // A hole in the payload must not silently delete a step from the record.
    const tree = buildStepTree([step({ id: 'orphan', parent_id: 'gone' })])
    expect(tree).toHaveLength(1)
    expect(tree[0]!.step.id).toBe('orphan')
  })

  it('flattens back into reading order with depths', () => {
    const tree = buildStepTree([
      step({ id: 'root', sequence: 1 }),
      step({ id: 'child', parent_id: 'root', sequence: 2 }),
    ])
    expect(flattenStepTree(tree).map((node) => [node.step.id, node.depth])).toEqual([
      ['root', 0],
      ['child', 1],
    ])
  })

  it('lists the hypothesis steps and the scenarios a probe targets', () => {
    const steps = [
      step({ id: 'r1', kind: 'risk' }),
      step({ id: 'p1', kind: 'probe', data: { target_scenarios: ['a', 'b'] } }),
      step({ id: 'r2', kind: 'risk' }),
    ]
    expect(riskSteps(steps).map((s) => s.id)).toEqual(['r1', 'r2'])
    expect(probeTargets(steps[1]!)).toEqual(['a', 'b'])
    // A non-probe has no targets even if its data happens to carry the key.
    expect(probeTargets(steps[0]!)).toEqual([])
  })

  it('knows which statuses stop moving', () => {
    expect(isInvestigationTerminal('completed')).toBe(true)
    expect(isInvestigationTerminal('failed')).toBe(true)
    expect(isInvestigationTerminal('deciding')).toBe(false)
    expect(isInvestigationTerminal('queued')).toBe(false)
  })
})

// ------------------------------------------------------------- derivations --

function experiment(over: Partial<CounterfactualExperiment> = {}): CounterfactualExperiment {
  return {
    id: 'cf',
    investigation_id: 'inv',
    scenario_id: 'escalation-path',
    intervention: 'compression_disabled',
    original_score: 0.6,
    counterfactual_score: 1,
    delta: 0.4,
    confidence: 0.9,
    verdict: 'root_cause',
    evidence_ids: [],
    rationale: '',
    created_at: '2026-09-11T09:40:00Z',
    ...over,
  }
}

describe('breakEvenIntervention', () => {
  it('picks the largest delta and reports the margin over the runner-up', () => {
    const best = breakEvenIntervention([
      experiment({ id: 'a', delta: 0.4 }),
      experiment({ id: 'b', intervention: 'retrieval_top_k_restored', delta: 0.05 }),
    ])
    expect(best?.intervention).toBe('compression_disabled')
    expect(best?.gain).toBeCloseTo(0.4, 6)
    expect(best?.marginPoints).toBeCloseTo(35, 6)
  })

  it('claims no winner when the top two interventions tie', () => {
    // A tie is not a finding; picking one would manufacture a certainty the
    // replay did not produce.
    const tied = breakEvenIntervention([experiment({ id: 'a' }), experiment({ id: 'b', delta: 0.4 })])
    expect(tied?.intervention).toBe('')
    expect(tied?.marginPoints).toBe(0)
  })

  it('has nothing to say about no experiments', () => {
    expect(breakEvenIntervention([])).toBeNull()
  })
})

describe('evidence accounting', () => {
  it('counts only the evidence behind a root cause or partial verdict', () => {
    const ids = rootCauseEvidenceIds([
      experiment({ id: 'a', evidence_ids: ['ev-1', 'ev-2'] }),
      experiment({ id: 'b', verdict: 'partial', evidence_ids: ['ev-2', 'ev-3'] }),
      experiment({ id: 'c', verdict: 'inconclusive', evidence_ids: ['ev-9'] }),
      experiment({ id: 'd', verdict: 'no_effect', evidence_ids: ['ev-8'] }),
    ])
    // `ev-9` cites why the replay is inconclusive; counting it as support for a
    // root cause is the error this accounting exists to catch.
    expect(ids.sort()).toEqual(['ev-1', 'ev-2', 'ev-3'])
  })

  it('gathers every cited id across steps, replays and the decision', () => {
    const ids = citedEvidenceIds({
      investigation: normalizeInvestigation({ id: 'i' }),
      steps: [step({ evidence_ids: ['ev-1'] }), step({ evidence_ids: ['ev-2', 'ev-1'] })],
      memory_matches: [],
      counterfactuals: [experiment({ evidence_ids: ['ev-3'] })],
      decision: normalizeDecision({ blocking_findings: ['ev-4', 'ev-1'] }),
    })
    expect(ids.sort()).toEqual(['ev-1', 'ev-2', 'ev-3', 'ev-4'])
  })

  it('groups replays by scenario in first-seen order', () => {
    const groups = groupCounterfactuals([
      experiment({ id: 'a', scenario_id: 's1' }),
      experiment({ id: 'b', scenario_id: 's2' }),
      experiment({ id: 'c', scenario_id: 's1' }),
    ])
    expect(groups.map((group) => group.scenario_id)).toEqual(['s1', 's2'])
    expect(groups[0]!.experiments.map((item) => item.id)).toEqual(['a', 'c'])
  })
})

// ----------------------------------------------------------- report URL -----

describe('reportUrl', () => {
  const live: InvestigationTransportInfo = {
    kind: 'http',
    live: true,
    label: 'live backend',
    baseUrl: '/api',
  }
  const mock: InvestigationTransportInfo = {
    kind: 'mock',
    live: false,
    label: 'offline',
    baseUrl: null,
  }

  it('builds the live endpoint path', () => {
    expect(reportUrl(live, 'inv-1')).toBe('/api/investigations/inv-1/report.md')
  })

  it('escapes an id that would otherwise break the path', () => {
    expect(reportUrl(live, 'a/b')).toBe('/api/investigations/a%2Fb/report.md')
  })

  it('returns empty for a transport with no endpoint', () => {
    // Printing a URL that would 404 is worse than printing nothing; the
    // workspace downloads the mock's own text instead.
    expect(reportUrl(mock, 'inv-1')).toBe('')
  })

  it('returns empty when a live transport has no base URL', () => {
    expect(reportUrl({ ...live, baseUrl: null }, 'inv-1')).toBe('')
  })
})

// --------------------------------------------------------------- lifecycle --

describe('MockInvestigationTransport lifecycle', () => {
  const mock = (): MockInvestigationTransport => new MockInvestigationTransport()

  it('creates a queued record carrying the objective and run it was given', async () => {
    const transport = mock()
    const created = await transport.createInvestigation({
      run_id: RUN_ID,
      objective: 'ship the candidate?',
    })
    expect(created.status).toBe('queued')
    expect(created.objective).toBe('ship the candidate?')
    expect(created.run_id).toBe(RUN_ID)
    expect(created.completed_at).toBeNull()
  })

  it('advances one stage per start and 409s once it is finished', async () => {
    const transport = mock()
    const created = await transport.createInvestigation({ run_id: RUN_ID, objective: 'o' })

    const seen: string[] = []
    for (let i = 0; i < 10; i += 1) {
      try {
        await transport.startInvestigation(created.id)
        seen.push((await transport.getInvestigation(created.id)).investigation.status)
      } catch (cause) {
        expect((cause as { status?: number }).status).toBe(409)
        // The conflict must land *after* the investigation has finished, not
        // before: a mock that 409s early would hide the whole lifecycle behind
        // a working start button.
        expect(seen[seen.length - 1]).toBe('completed')
        break
      }
    }

    expect(seen).toEqual(['planning', 'investigating', 'replaying', 'deciding', 'completed'])
  })

  it('reveals the timeline progressively rather than all at once', async () => {
    const transport = mock()
    const created = await transport.createInvestigation({ run_id: RUN_ID, objective: 'o' })

    const beforeStart = await transport.getInvestigation(created.id)
    expect(beforeStart.steps).toEqual([])
    expect(beforeStart.decision).toBeNull()

    await transport.startInvestigation(created.id)
    const planning = await transport.getInvestigation(created.id)
    expect(planning.steps.every((step) => step.kind === 'risk')).toBe(true)
    expect(planning.counterfactuals).toEqual([])

    await transport.startInvestigation(created.id)
    const investigating = await transport.getInvestigation(created.id)
    expect(investigating.steps.some((step) => step.kind === 'probe')).toBe(true)
    expect(investigating.memory_matches.length).toBeGreaterThan(0)
    expect(investigating.counterfactuals).toEqual([])

    await transport.startInvestigation(created.id)
    const replaying = await transport.getInvestigation(created.id)
    expect(replaying.counterfactuals.length).toBeGreaterThan(0)
    // The replays are in; the call is not. A decision printed before the
    // replays finish would be a decision without its evidence.
    expect(replaying.decision).toBeNull()

    await transport.startInvestigation(created.id)
    const deciding = await transport.getInvestigation(created.id)
    expect(deciding.decision?.verdict).toBe('block')
  })

  it('offers the report only once the investigation has decided', async () => {
    const transport = mock()
    const created = await transport.createInvestigation({ run_id: RUN_ID, objective: 'o' })

    await expect(transport.getReport(created.id)).rejects.toMatchObject({ status: 409 })
    for (let i = 0; i < 5; i += 1) await transport.startInvestigation(created.id)

    const report = await transport.getReport(created.id)
    // Chinese heading; the intervention name inside the body is an identifier.
    expect(report).toContain('# 调查报告')
    expect(report).toContain('**阻断发布**')
    expect(report).toContain('compression_disabled')
  })

  it('404s an investigation it did not issue', async () => {
    const transport = mock()
    await expect(transport.getInvestigation('not-mine')).rejects.toMatchObject({ status: 404 })
    await expect(transport.startInvestigation('not-mine')).rejects.toMatchObject({ status: 404 })
  })

  it('answers the incident library with matches only when asked to search', async () => {
    const transport = mock()
    const library = await transport.listIncidents()
    expect(library.matches).toBeNull()
    expect(library.incidents.length).toBeGreaterThan(0)

    const searched = await transport.listIncidents('escalation')
    expect(searched.matches).not.toBeNull()
    expect(searched.matches!.length).toBeGreaterThan(0)
  })

  it('describes itself as offline so the workspace can say so', () => {
    expect(mock().describe()).toMatchObject({ kind: 'mock', live: false, baseUrl: null })
  })
})

// ------------------------------------------------------------ http adapter --

describe('HttpInvestigationTransport', () => {
  function stubFetch(handlers: Record<string, () => Response | Promise<Response>>) {
    const calls: string[] = []
    const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      calls.push(`${method} ${url}`)
      for (const [key, handler] of Object.entries(handlers)) {
        if (url.includes(key)) return handler()
      }
      return new Response('', { status: 404, statusText: 'not found' })
    }) as unknown as typeof fetch
    return { fetchImpl, calls }
  }

  const json = (body: unknown, status = 200): Response =>
    new Response(JSON.stringify(body), {
      status,
      headers: { 'content-type': 'application/json' },
    })

  it('posts the objective and normalises the created record', async () => {
    const { fetchImpl, calls } = stubFetch({
      '/investigations': () => json({ id: 'inv-1', run_id: RUN_ID, status: 'queued' }),
    })
    const transport = new HttpInvestigationTransport('/api', fetchImpl)
    const created = await transport.createInvestigation({ run_id: RUN_ID, objective: 'ship?' })
    expect(created.id).toBe('inv-1')
    expect(calls).toEqual(['POST /api/investigations'])
  })

  it('accepts a 202 from start without parsing a body', async () => {
    const { fetchImpl } = stubFetch({ '/start': () => new Response('', { status: 202 }) })
    const transport = new HttpInvestigationTransport('/api', fetchImpl)
    await expect(transport.startInvestigation('inv-1')).resolves.toBeUndefined()
  })

  it('reads a Markdown report as text', async () => {
    const { fetchImpl } = stubFetch({
      'report.md': () =>
        new Response('# report\n\nblock', { headers: { 'content-type': 'text/markdown' } }),
    })
    const transport = new HttpInvestigationTransport('/api', fetchImpl)
    const report = await transport.getReport('inv-1')
    expect(report).toContain('# report')
  })

  it('raises with the status when the report is not available yet', async () => {
    const { fetchImpl } = stubFetch({
      'report.md': () => new Response('', { status: 409, statusText: 'conflict' }),
    })
    const transport = new HttpInvestigationTransport('/api', fetchImpl)
    await expect(transport.getReport('inv-1')).rejects.toMatchObject({ status: 409 })
  })

  it('passes the incident query through as parameters', async () => {
    const { fetchImpl, calls } = stubFetch({
      '/memory/incidents': () => json({ incidents: [] }),
    })
    const transport = new HttpInvestigationTransport('/api', fetchImpl)
    await transport.listIncidents('escalation', 'boundary')
    expect(calls[0]).toBe('GET /api/memory/incidents?query=escalation&tag=boundary')
  })

  it('normalises the bundle it reads back', async () => {
    const { fetchImpl } = stubFetch({
      '/investigations/inv-1': () =>
        json({
          investigation: { id: 'inv-1', run_id: RUN_ID, status: 'completed' },
          steps: [{ id: 's1', sequence: 1, kind: 'risk' }],
          memory_matches: [{ incident_id: 'ESC-2214', score: 0.87 }],
          counterfactuals: [
            { id: 'cf1', scenario_id: 'escalation-path', original_score: 0.6, counterfactual_score: 1 },
          ],
          decision: { verdict: 'block' },
        }),
    })
    const transport = new HttpInvestigationTransport('/api', fetchImpl)
    const bundle = await transport.getInvestigation('inv-1')
    expect(bundle.steps).toHaveLength(1)
    expect(bundle.memory_matches[0]!.score).toBe(0.87)
    expect(bundle.counterfactuals[0]!.delta).toBeCloseTo(0.4, 6)
    expect(bundle.decision?.verdict).toBe('block')
  })

  it('reads NDJSON and SSE event frames through one stream', async () => {
    const ndjson = new ReadableStream<Uint8Array>({
      start(controller) {
        const encoder = new TextEncoder()
        controller.enqueue(encoder.encode('{"sequence":1,"type":"step.completed"}\n'))
        controller.enqueue(encoder.encode('{"sequence":2,"type":"investigation.completed"}\n'))
        controller.close()
      },
    })
    const sse = new ReadableStream<Uint8Array>({
      start(controller) {
        const encoder = new TextEncoder()
        controller.enqueue(encoder.encode('data: {"sequence":1,"type":"step.completed"}\n\n'))
        controller.close()
      },
    })

    const ndjsonTransport = new HttpInvestigationTransport(
      '/api',
      (async () =>
        new Response(ndjson, { headers: { 'content-type': 'application/x-ndjson' } })) as never,
    )
    const sseTransport = new HttpInvestigationTransport(
      '/api',
      (async () =>
        new Response(sse, { headers: { 'content-type': 'text/event-stream' } })) as never,
    )

    const seen: string[] = []
    for await (const event of ndjsonTransport.streamInvestigation('inv-1')) seen.push(event.type)
    expect(seen).toEqual(['step.completed', 'investigation.completed'])

    const sseSeen: string[] = []
    for await (const event of sseTransport.streamInvestigation('inv-1')) sseSeen.push(event.type)
    expect(sseSeen).toEqual(['step.completed'])
  })
})
