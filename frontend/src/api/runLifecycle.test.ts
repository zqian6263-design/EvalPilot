import { describe, expect, it } from 'vitest'
import { ApiError, type Transport } from './transport'
import { ensureRunStarted, isTerminal, readReport, resolveDemoContext, waitForRun } from './runLifecycle'
import { HttpTransport } from './httpTransport'
import type { DemoContext, Report, Run } from './types'

/**
 * The run lifecycle is where the console stops being a reader and starts
 * driving. These tests pin the four ways that goes wrong in practice — a
 * second start, a report that does not exist yet, a poll that outlives its
 * budget, and a backend that cannot seed a demo — so the UI says what happened
 * instead of retrying until something gives.
 */

function run(over: Partial<Run> = {}): Run {
  return {
    id: '11111111-1111-4111-8111-111111111111',
    project_id: '22222222-2222-4222-8222-222222222222',
    baseline_version: 'v1.0-baseline',
    candidate_version: 'v1.1-candidate',
    status: 'queued',
    created_at: '2026-09-11T10:00:00Z',
    completed_at: null,
    ...over,
  }
}

/** A transport stub recording the calls the lifecycle made. */
function stubTransport(over: Partial<Transport> = {}): Transport & { calls: string[] } {
  const calls: string[] = []
  const base = {
    describe: () => ({ kind: 'mock' as const, live: false, label: 'stub', baseUrl: null }),
    health: async () => ({ status: 'ok', version: 'stub' }),
    listProjects: async () => [],
    getProject: async () => {
      throw new Error('unused')
    },
    listRuns: async () => [],
    getRun: async () => ({ ...run(), test_cases: [], evidence: [], evidence_count: 0, finding_count: 0, event_count: 0 }),
    createRun: async () => run(),
    startRun: async () => run({ status: 'planning' }),
    cancelRun: async () => run({ status: 'cancelled' }),
    getReport: async () => {
      throw new Error('unused')
    },
    getDemoSeed: async () => ({ project: null as never, runs: [] }),
    streamEvents: async function* () {},
    ...over,
  } as unknown as Transport
  return Object.assign(base, { calls })
}

describe('ensureRunStarted', () => {
  it('starts a queued run', async () => {
    const transport = stubTransport({
      startRun: async (id) => {
        transport.calls.push(`start:${id}`)
        return run({ status: 'planning' })
      },
    })
    const result = await ensureRunStarted({
      transport,
      run: run({ status: 'queued' }),
      create: async () => run(),
    })
    expect(result.started).toBe(true)
    expect(result.run.status).toBe('planning')
    expect(transport.calls).toEqual([`start:${run().id}`])
    expect(result.note).toBeNull()
  })

  it('creates a run when the caller has none, then starts it', async () => {
    const transport = stubTransport({
      startRun: async () => run({ status: 'executing' }),
    })
    const result = await ensureRunStarted({
      transport,
      run: null,
      create: async () => run({ status: 'queued' }),
    })
    expect(result.started).toBe(true)
  })

  it('refuses to start a run that is already moving', async () => {
    const transport = stubTransport({
      startRun: async () => {
        throw new ApiError('conflict', 409, '/start')
      },
    })
    const result = await ensureRunStarted({
      transport,
      run: run({ status: 'executing' }),
      create: async () => run(),
    })
    // The 409 the backend would have raised is never issued: the console opens
    // the run as it stands and says why.
    expect(result.started).toBe(false)
    expect(result.note).toContain('executing')
  })

  it('opens a completed run without restarting it', async () => {
    const transport = stubTransport({
      startRun: async () => {
        throw new ApiError('conflict', 409, '/start')
      },
    })
    const result = await ensureRunStarted({
      transport,
      run: run({ status: 'completed' }),
      create: async () => run(),
    })
    expect(result.started).toBe(false)
    expect(result.note).toContain('completed')
  })
})

describe('waitForRun', () => {
  it('returns as soon as the run reaches a terminal status', async () => {
    const statuses: Run['status'][] = ['executing', 'evaluating', 'completed']
    let index = 0
    const transport = stubTransport({
      getRun: async () =>
        ({ ...run({ status: statuses[Math.min(index++, statuses.length - 1)]! }), test_cases: [], evidence: [], evidence_count: 0, finding_count: 0, event_count: 0 }),
    })
    const result = await waitForRun({
      transport,
      runId: run().id,
      sleep: async () => {},
    })
    expect(result.settled).toBe(true)
    expect(result.run.status).toBe('completed')
  })

  it('returns the partial run when the budget runs out', async () => {
    let clock = 0
    const transport = stubTransport({
      getRun: async () =>
        ({ ...run({ status: 'executing' }), test_cases: [], evidence: [], evidence_count: 0, finding_count: 0, event_count: 0 }),
    })
    const result = await waitForRun({
      transport,
      runId: run().id,
      timeoutMs: 500,
      now: () => (clock += 250),
      sleep: async () => {},
    })
    // Not an error and not a success: the run is still moving and the caller
    // renders that state with it stated.
    expect(result.settled).toBe(false)
    expect(result.run.status).toBe('executing')
  })
})

describe('readReport', () => {
  it('treats a 409 as "no report yet", not as a failure', async () => {
    const transport = stubTransport({
      getReport: async () => {
        throw new ApiError('run is executing', 409, '/report')
      },
    })
    const { report, error } = await readReport(transport, run().id)
    expect(report).toBeNull()
    expect(error).toBeNull()
  })

  it('surfaces a real failure with its reason', async () => {
    const transport = stubTransport({
      getReport: async () => {
        throw new ApiError('request failed', 500, '/report')
      },
    })
    const { report, error } = await readReport(transport, run().id)
    expect(report).toBeNull()
    expect(error).toContain('request failed')
  })

  it('returns the report when the run has one', async () => {
    const report = { id: 'r1', run_id: run().id } as unknown as Report
    const transport = stubTransport({ getReport: async () => report })
    const result = await readReport(transport, run().id)
    expect(result.report).toBe(report)
    expect(result.error).toBeNull()
  })
})

describe('resolveDemoContext', () => {
  it('returns null for a transport that cannot seed', async () => {
    const transport = stubTransport()
    expect(await resolveDemoContext(transport)).toBeNull()
  })

  it('returns the context when the transport can', async () => {
    const context = { run: run(), project: {} } as unknown as DemoContext
    const transport = stubTransport({ getDemoContext: async () => context })
    expect(await resolveDemoContext(transport)).toBe(context)
  })

  it('returns null rather than throwing when seeding fails', async () => {
    const transport = stubTransport({
      getDemoContext: async () => {
        throw new ApiError('boom', 500, '/projects')
      },
    })
    expect(await resolveDemoContext(transport)).toBeNull()
  })
})

describe('isTerminal', () => {
  it('knows which statuses stop moving', () => {
    expect(isTerminal('completed')).toBe(true)
    expect(isTerminal('failed')).toBe(true)
    expect(isTerminal('cancelled')).toBe(true)
    expect(isTerminal('executing')).toBe(false)
    expect(isTerminal('queued')).toBe(false)
  })
})

describe('HttpTransport.getDemoContext is idempotent', () => {
  /** A fetch stub that serves the demo endpoints and records writes. */
  function demoFetch(existingRuns: Run[]) {
    const writes: string[] = []
    const fetchImpl = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      if (method === 'POST') writes.push(`${method} ${url}`)
      const body = (() => {
        if (url.endsWith('/demo/seed')) {
          return {
            scenario: 'kb-qa',
            project: { name: 'Enterprise Knowledge Base QA', scenario: 'kb-qa' },
            baseline_version: 'v1.0-baseline',
            candidate_version: 'v1.1-candidate',
            seed: 20260919,
            case_count: 26,
          }
        }
        if (url.endsWith('/projects')) {
          return [
            {
              id: '22222222-2222-4222-8222-222222222222',
              name: 'Enterprise Knowledge Base QA',
              scenario: 'kb-qa',
              created_at: '2026-09-11T09:00:00Z',
            },
          ]
        }
        if (url.endsWith('/runs') && method === 'GET') return existingRuns
        if (url.endsWith('/runs') && method === 'POST') {
          return run({ status: 'queued' })
        }
        throw new Error(`unexpected request: ${method} ${url}`)
      })()
      return new Response(JSON.stringify(body), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      })
    }) as unknown as typeof fetch
    return { fetchImpl, writes }
  }

  it('adopts the existing project and run without writing anything', async () => {
    const existing = run({ id: '99999999-9999-4999-8999-999999999999', case_count: 26 })
    const { fetchImpl, writes } = demoFetch([existing])
    const transport = new HttpTransport('/api', fetchImpl)

    const context = await transport.getDemoContext()
    expect(context.created).toBe(false)
    expect(context.run.id).toBe(existing.id)
    // A second demo click must not create a second project or run.
    expect(writes).toEqual([])
  })

  it('creates exactly one run when the existing run has an outdated case count', async () => {
    const { fetchImpl, writes } = demoFetch([run({ case_count: 10 })])
    const transport = new HttpTransport('/api', fetchImpl)

    const context = await transport.getDemoContext()
    expect(context.created).toBe(true)
    expect(context.baselineVersion).toBe('v1.0-baseline')
    expect(context.candidateVersion).toBe('v1.1-candidate')
    expect(context.seed).toBe(20260919)
    expect(context.caseCount).toBe(26)
    expect(writes).toEqual(['POST /api/runs'])
  })
})
